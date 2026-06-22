"""
文件解析服务 —— .txt / .docx 文件内容提取与元数据解析。

Public API:
- parse_text_file(file_path: Path) -> str: 读取 .txt 文件（自动检测编码）
- parse_docx_file(file_path: Path) -> str: 读取 .docx 文件
- extract_metadata(filename: str) -> dict: 从文件名提取作者/作品名
- parse_uploaded_file(file: UploadFile) -> dict: 上传文件一站式解析
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import IO

# python-docx 可选；未安装时 parse_docx_file 会抛出 ImportError
try:
    from docx import Document as DocxDocument

    HAS_DOCX = True
except ImportError:  # pragma: no cover
    HAS_DOCX = False

_DOCX_MAGIC = b"\x50\x4b\x03\x04"  # ZIP 文件头（.docx 本质是 ZIP）


# ── 编码检测 ──────────────────────────────────────────────────────────


def _detect_encoding(data: bytes) -> str:
    """依次尝试 UTF-8 → GBK → GB2312，返回首个可解码的编码名。

    Raises:
        UnicodeDecodeError: 三种编码均无法解码时抛出。
    """
    for enc in ("utf-8", "gbk", "gb2312"):
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    # 全部失败，用 utf-8 抛出原始异常
    data.decode("utf-8")


# ── 公开函数 ──────────────────────────────────────────────────────────


def parse_text_file(file_path: Path) -> str:
    """读取 .txt 文件内容，自动检测 UTF-8 / GBK / GB2312 编码。

    Args:
        file_path: 文本文件路径。

    Returns:
        解码后的文件内容字符串。

    Raises:
        FileNotFoundError: 文件不存在。
        UnicodeDecodeError: 所有常见编码均无法解码。
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件未找到: {file_path}")
    raw = file_path.read_bytes()
    encoding = _detect_encoding(raw)
    return raw.decode(encoding)


def parse_docx_file(file_path: Path) -> str:
    """读取 .docx 文件，提取全部段落文本，每段间用换行拼接。

    Args:
        file_path: .docx 文件路径。

    Returns:
        拼接后的文档文本。

    Raises:
        FileNotFoundError: 文件不存在。
        ImportError: python-docx 未安装。
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件未找到: {file_path}")
    if not HAS_DOCX:
        raise ImportError(
            "python-docx 未安装，无法解析 .docx 文件。"
            "请执行 pip install python-docx"
        )
    document = DocxDocument(str(file_path))
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs)


def extract_metadata(filename: str) -> dict:
    """从文件名中提取作者和作品名称。

    支持的文件名格式（按优先级匹配）：
      1. "作品名（作者名）.txt" 或 "作品名（XXX）作者XXX.txt"
      2. "作品名 - 作者名.txt"
      3. "作品名 作者名.txt"

    Args:
        filename: 文件名（可含扩展名）。

    Returns:
        含 ``author`` 和 ``work_title`` 的字典；无法提取时字段为空字符串。
    """
    result: dict[str, str] = {"author": "", "work_title": ""}

    # 去除路径前缀，只保留文件名
    basename = Path(filename).name

    # 尝试各格式匹配（按优先级降序）
    # 格式 1a: "作品名（作者名）.ext"
    m = re.search(r"^(.+?)（(.+?)）\.\w+$", basename)
    if m:
        result["work_title"] = m.group(1).strip()
        result["author"] = m.group(2).strip()
        return result

    # 格式 1b: "作品名作者名.ext" (keyword "作者")
    m = re.search(r"^(.+?)作者(.+?)\.\w+$", basename)
    if m:
        result["work_title"] = m.group(1).strip()
        result["author"] = m.group(2).strip().lstrip("：:")
        return result

    # 格式 2: "作品名 - 作者名.ext"
    m = re.search(r"^(.+?)\s*-\s*(.+?)\.\w+$", basename)
    if m:
        result["work_title"] = m.group(1).strip()
        result["author"] = m.group(2).strip()
        return result

    # 格式 3: "作品名 作者名.ext"（以空格分隔，最后一段为作者）
    m = re.search(r"^(.+?)\s+(.+?)\.\w+$", basename)
    if m:
        result["work_title"] = m.group(1).strip()
        result["author"] = m.group(2).strip()
        return result

    return result


def extract_metadata_from_content(text: str) -> dict:
    """从正文前几行解析作者名和作品名。

    扫描正文前 10 行，匹配以下格式：
      - ``作者：爱潜水的乌贼`` 或 ``Author: xxx``
      - ``《诡秘之主》``（书名号括起）
      - ``〓作者〓 爱潜水的乌贼 〓``

    Args:
        text: 章节正文内容。

    Returns:
        含 ``author`` 和 ``work_title`` 的字典；无法提取时字段为空字符串。
    """
    result: dict[str, str] = {"author": "", "work_title": ""}
    lines = text.splitlines()[:10]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = re.match(r"〓作者〓\s*(.+?)\s*〓", line)
        if m:
            result["author"] = m.group(1).strip()
            continue

        m = re.match(r"^作者[：:]\s*(.+)$", line)
        if m:
            result["author"] = m.group(1).strip()
            continue

        m = re.match(r"^(?:Author|author)[：:]\s*(.+)$", line)
        if m:
            result["author"] = m.group(1).strip()
            continue

        m = re.search(r"《(.+?)》", line)
        if m:
            result["work_title"] = m.group(1).strip()

    return result


def parse_uploaded_file(file: "UploadFile") -> dict:  # noqa: F821
    """一站式解析上传文件。

    根据文件扩展名分发到 ``parse_text_file`` 或 ``parse_docx_file``，
    同时从文件名提取元数据。

    Args:
        file: FastAPI UploadFile 实例。

    Returns:
        ``{"text": str, "metadata": dict, "file_type": str}``。

    Raises:
        ValueError: 不支持的扩展名。
        FileNotFoundError / UnicodeDecodeError / ImportError: 底层解析异常。
    """
    # 延迟导入以避免对 fastapi 的强制依赖
    from fastapi import UploadFile as _UploadFile

    _UploadFile  # 仅用于类型检查，实际参数已是 UploadFile

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    metadata = extract_metadata(filename)

    # 读取原始字节
    raw_bytes = file.file.read()

    if ext == ".txt":
        encoding = _detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding)
        return {"text": text, "metadata": metadata, "file_type": "txt"}
    elif ext == ".docx":
        # 写入临时文件，再由 parse_docx_file 读取
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        try:
            tmp.write(raw_bytes)
            tmp.flush()
            tmp.close()
            text = parse_docx_file(Path(tmp.name))
        finally:
            os.unlink(tmp.name)
        return {"text": text, "metadata": metadata, "file_type": "docx"}
    else:
        raise ValueError(f"不支持的文件类型: '{ext}'（仅支持 .txt / .docx）")
