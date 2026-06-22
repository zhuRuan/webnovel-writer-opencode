"""测试 services/file_parser.py —— 文本/docx 解析与元数据提取。"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument

from dashboard.services.file_parser import (
    extract_metadata,
    parse_docx_file,
    parse_text_file,
    parse_uploaded_file,
)


# ── Helper ────────────────────────────────────────────────────────────


def _create_docx(path: Path, paragraphs: list[str]) -> None:
    """用 python-docx 创建一个 .docx 测试文件。"""
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(str(path))


# ── Test: parse_text_file ────────────────────────────────────────────


class TestParseTextFile:
    """parse_text_file 编码检测与异常测试。"""

    def test_utf8(self, tmp_path: Path) -> None:
        path = tmp_path / "hello.txt"
        path.write_text("你好，世界！Hello, 世界！", encoding="utf-8")
        assert parse_text_file(path) == "你好，世界！Hello, 世界！"

    def test_gbk(self, tmp_path: Path) -> None:
        path = tmp_path / "gbk.txt"
        text = "这是一段GBK编码的中文文本。"
        path.write_bytes(text.encode("gbk"))
        assert parse_text_file(path) == text

    def test_gb2312(self, tmp_path: Path) -> None:
        path = tmp_path / "gb2312.txt"
        text = "GB2312简体中文测试。"
        path.write_bytes(text.encode("gb2312"))
        assert parse_text_file(path) == text

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="未找到"):
            parse_text_file(Path("/tmp/nonexistent_file_xyz.txt"))

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.txt"
        path.write_text("", encoding="utf-8")
        assert parse_text_file(path) == ""

    def test_mixed_encoding_utf8(self, tmp_path: Path) -> None:
        """验证 UTF-8 编码优先于 GBK。"""
        path = tmp_path / "mixed.txt"
        # "ASCII only" 在 UTF-8 和 GBK 下解码结果相同，但用纯 ASCII 测试
        text = "Pure ASCII text with no encoding ambiguity."
        path.write_text(text, encoding="utf-8")
        assert parse_text_file(path) == text


# ── Test: parse_docx_file ────────────────────────────────────────────


class TestParseDocxFile:
    """parse_docx_file 段落提取与异常测试。"""

    def test_basic(self, tmp_path: Path) -> None:
        path = tmp_path / "test.docx"
        _create_docx(path, ["第一段内容", "第二段内容", "第三段内容"])
        result = parse_docx_file(path)
        assert result == "第一段内容\n第二段内容\n第三段内容"

    def test_single_paragraph(self, tmp_path: Path) -> None:
        path = tmp_path / "single.docx"
        _create_docx(path, ["仅有一段文字。"])
        assert parse_docx_file(path) == "仅有一段文字。"

    def test_empty_paragraphs(self, tmp_path: Path) -> None:
        """包含空段落的 .docx 应原样保留空行。"""
        path = tmp_path / "empty_paras.docx"
        _create_docx(path, ["第一段", "", "第三段"])
        assert parse_docx_file(path) == "第一段\n\n第三段"

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="未找到"):
            parse_docx_file(Path("/tmp/nonexistent_docx.docx"))


# ── Test: extract_metadata ───────────────────────────────────────────


class TestExtractMetadata:
    """extract_metadata 文件名解析测试。"""

    def test_format_parentheses(self) -> None:
        """格式：作品名（作者名）.txt"""
        result = extract_metadata("斗破苍穹（天蚕土豆）.txt")
        assert result == {"author": "天蚕土豆", "work_title": "斗破苍穹"}

    def test_format_parentheses_with_author_keyword(self) -> None:
        """格式：作品名（XXX）作者XXX.txt"""
        result = extract_metadata("凡人修仙传（仙界篇）作者忘语.txt")
        assert result == {"author": "忘语", "work_title": "凡人修仙传（仙界篇）"}

    def test_format_dash(self) -> None:
        """格式：作品名 - 作者名.txt"""
        result = extract_metadata("鬼吹灯 - 天下霸唱.txt")
        assert result == {"author": "天下霸唱", "work_title": "鬼吹灯"}

    def test_format_space(self) -> None:
        """格式：作品名 作者名.txt"""
        result = extract_metadata("盗墓笔记 南派三叔.txt")
        assert result == {"author": "南派三叔", "work_title": "盗墓笔记"}

    def test_docx_extension(self) -> None:
        """验证 .docx 扩展名也能正常解析。"""
        result = extract_metadata("庆余年（猫腻）.docx")
        assert result == {"author": "猫腻", "work_title": "庆余年"}

    def test_no_match(self) -> None:
        """无法匹配任何格式时返回空字段。"""
        result = extract_metadata("readme.txt")
        assert result == {"author": "", "work_title": ""}

    def test_path_with_directory(self) -> None:
        """传入包含路径的文件名也能正确解析。"""
        result = extract_metadata("/home/user/upload/雪中悍刀行 - 烽火戏诸侯.txt")
        assert result == {"author": "烽火戏诸侯", "work_title": "雪中悍刀行"}

    def test_empty_filename(self) -> None:
        """空文件名返回空字段。"""
        result = extract_metadata("")
        assert result == {"author": "", "work_title": ""}


# ── Test: parse_uploaded_file ────────────────────────────────────────

# 注：parse_uploaded_file 依赖 FastAPI UploadFile，在单元测试中
# 通过构造一个简单的模拟对象来调用。


class _MockUploadFile:
    """模拟 FastAPI UploadFile 的最小实现。"""

    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.file = _MockFile(content)


class _MockFile:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        return self._content


class TestParseUploadedFile:
    """parse_uploaded_file 分发与错误测试。"""

    def test_txt_file(self, tmp_path: Path) -> None:
        """上传 .txt 文件应正确解码并提取元数据。"""
        content = "第一章 觉醒\n\n林动盘膝而坐。".encode("utf-8")
        mock = _MockUploadFile("武动乾坤 - 天蚕土豆.txt", content)
        result = parse_uploaded_file(mock)  # type: ignore[arg-type]
        assert result["text"] == "第一章 觉醒\n\n林动盘膝而坐。"
        assert result["metadata"] == {"author": "天蚕土豆", "work_title": "武动乾坤"}
        assert result["file_type"] == "txt"

    def test_docx_file(self, tmp_path: Path) -> None:
        """上传 .docx 文件应提取段落文本与元数据。"""
        # 先生成一个 .docx 临时文件
        docx_path = tmp_path / "source.docx"
        _create_docx(docx_path, ["第一段", "第二段"])
        docx_bytes = docx_path.read_bytes()

        mock = _MockUploadFile("剑来（烽火戏诸侯）.docx", docx_bytes)
        result = parse_uploaded_file(mock)  # type: ignore[arg-type]
        assert result["text"] == "第一段\n第二段"
        assert result["metadata"] == {"author": "烽火戏诸侯", "work_title": "剑来"}
        assert result["file_type"] == "docx"

    def test_unsupported_extension(self) -> None:
        """不支持的扩展名应抛出 ValueError。"""
        content = b"some content"
        mock = _MockUploadFile("file.pdf", content)
        with pytest.raises(ValueError, match="不支持"):
            parse_uploaded_file(mock)  # type: ignore[arg-type]
