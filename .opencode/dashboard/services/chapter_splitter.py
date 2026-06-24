"""
智能分章引擎 — 用正则匹配 + 可选本地模型确认的双重策略，
从整本小说文本中自动识别章节边界并切分。

支持格式：中文数字章、阿拉伯数字章、英文格式、数字编号。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 中文数字 → 阿拉伯数字
# ---------------------------------------------------------------------------

_CN_DIGIT: dict[str, int] = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "两": 2,
}
_CN_UNIT: dict[str, int] = {
    "十": 10, "百": 100, "千": 1_000, "万": 10_000,
    "亿": 100_000_000,
}


def _parse_chinese_number(cn: str) -> int | None:
    """将中文数字字符串转换为阿拉伯数字，失败返回 None。

    算法：从左到右扫描，数字乘以下一个单位后累加到段值，
    遇到「万/亿」时将当前段值升级并重置。

    >>> _parse_chinese_number("一百二十")
    120
    >>> _parse_chinese_number("十一")
    11
    >>> _parse_chinese_number("一千零一")
    1001
    >>> _parse_chinese_number("十二万")
    120000
    """
    if not cn:
        return None

    # 纯阿拉伯数字混入（如 "第12章" 中的 "12"）
    if cn.isdigit():
        return int(cn)

    section = 0
    digit = 0
    total = 0

    for ch in cn:
        if ch in _CN_DIGIT:
            digit = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            unit = _CN_UNIT[ch]
            if unit >= 10_000:
                if digit == 0 and section == 0:
                    section = 1
                elif digit > 0:
                    section += digit
                section *= unit
                if unit == 100_000_000:
                    total += section
                    section = 0
                digit = 0
            else:
                if digit == 0:
                    digit = 1
                section += digit * unit
                digit = 0
        elif ch == "零":
            continue
        else:
            return None

    total += section + digit
    return total


# ---------------------------------------------------------------------------
# 章节标题正则模式集（优先级排序）
# ---------------------------------------------------------------------------

# 1. 中文数字 + 阿拉伯数字混合 — 行首 "第X章"
_RE_CN_CHAPTER = re.compile(
    r"^第\s*([零一二三四五六七八九十百千万两\d]+)\s*章(?:\s|$)\s*(.*)",
    re.MULTILINE,
)

# 2. 纯阿拉伯数字 — 行首 "第 123 章"
_RE_ARABIC_CHAPTER = re.compile(
    r"^第\s*(\d+)\s*章(?:\s|$)\s*(.*)",
    re.MULTILINE,
)

# 3. 英文格式 — 行首 "Chapter 123"
_RE_EN_CHAPTER = re.compile(
    r"^Chapter\s+(\d+)\s*[：:\s]?\s*(.*)",
    re.MULTILINE | re.IGNORECASE,
)

# 4. 数字编号行首 — "123. " 或 "123、"
_RE_NUMERIC_HEADING = re.compile(
    r"^(\d+)\s*[\.\、]\s+(.*)",
    re.MULTILINE,
)

# 5. 纯数字前缀 — "001 序章"（2-3 位数字 + 空格，低优先级防误伤）
_RE_NUMERIC_PREFIX = re.compile(
    r"^(\d{2,3})\s+(.*)",
    re.MULTILINE,
)

# 复合模式：将所有模式合并用于扫描章节边界位置
_CHAPTER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cn_chapter", _RE_CN_CHAPTER),
    ("arabic_chapter", _RE_ARABIC_CHAPTER),
    ("en_chapter", _RE_EN_CHAPTER),
    ("numeric_heading", _RE_NUMERIC_HEADING),
    ("numeric_prefix", _RE_NUMERIC_PREFIX),
]

# ---------------------------------------------------------------------------
# 卷 / 篇 / 部 标记正则模式（不改变章节编号，仅标注所属卷）
# ---------------------------------------------------------------------------

# 中文卷标记 — 行首 "第一卷 标题"
_RE_CN_VOLUME = re.compile(
    r"^第\s*([零一二三四五六七八九十百千万两\d]+)\s*卷(?:\s|$)\s*(.*)",
    re.MULTILINE,
)

# 中文篇标记 — 行首 "第一篇 标题"
_RE_CN_PART = re.compile(
    r"^第\s*([零一二三四五六七八九十百千万两\d]+)\s*篇(?:\s|$)\s*(.*)",
    re.MULTILINE,
)

# 中文部标记 — 行首 "第一部 标题"
_RE_CN_BOOK = re.compile(
    r"^第\s*([零一二三四五六七八九十百千万两\d]+)\s*部(?:\s|$)\s*(.*)",
    re.MULTILINE,
)

# 英文卷标记 — 行首 "Part 1: Title" 或 "Part 1 Title"
_RE_EN_PART = re.compile(
    r"^Part\s+(\d+)\s*[：:\s]?\s*(.*)",
    re.MULTILINE | re.IGNORECASE,
)

# 卷模式合并列表（按维护的 label 区分）
_VOLUME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cn_volume", _RE_CN_VOLUME),
    ("cn_part", _RE_CN_PART),
    ("cn_book", _RE_CN_BOOK),
    ("en_part", _RE_EN_PART),
]

# 卷标记类型 → 中文前缀的映射（用于拼装卷标题）
_CN_TYPE_LABEL: dict[str, str] = {
    "cn_volume": "卷",
    "cn_part": "篇",
    "cn_book": "部",
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ChapterSegment:
    """章节片段。"""
    chapter_num: int
    """章节序号（从 1 开始）。"""
    title: str
    """章节标题（不含"第X章"前缀）。"""
    start_pos: int
    """在原文本中的起始字符位置。"""
    end_pos: int
    """在原文本中的结束字符位置（不含）。"""
    content: str
    """该章节的完整文本内容。"""
    is_suspicious: bool = False
    """该章节边界是否可疑（由验证规则标记）。"""
    match_type: str = "unknown"
    """匹配所用的模式类型：cn_chapter / arabic_chapter / en_chapter / numeric_heading。"""
    volume_title: str = ""
    """所属卷/篇/部的标题（如"第一卷 初始"）。从最近的卷标记继承。"""
    meta: dict[str, Any] = field(default_factory=dict)
    """额外的元数据（如原文匹配到的完整行等）。"""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def split_chapters(
    text: str,
    metadata: dict[str, Any] | None = None,
    *,
    use_model_verification: bool = False,
    min_chapter_chars: int = 100,
    min_chapter_count: int = 2,
) -> list[ChapterSegment]:
    """将整本小说文本切分为章节列表。

    Parameters
    ----------
    text:
        小说全文文本。
    metadata:
        上游文件解析器传入的元数据（如 author, work_title），当前版本预留。
    use_model_verification:
        是否启用 Ollama 模型对可疑边界进行确认。默认关闭。
    min_chapter_chars:
        相邻章节边界之间的最小字符数。间距小于此值的视为可疑。
    min_chapter_count:
        最少章节数阈值。匹配到的章节数少于此值时，整个文本作为单章返回。

    Returns
    -------
    list[ChapterSegment]
        按 chapter_num 排序的章节列表。
    """
    _ = metadata  # 预留，当前不使用

    if not text or not text.strip():
        return []

    # Step 1: 收集所有潜在章节边界点
    boundaries = _find_boundaries(text)

    # Step 2: 如果匹配过少，视为单章返回（仍然尝试检测卷标记）
    if len(boundaries) < min_chapter_count:
        return _assign_volumes_to_chapters(_single_chapter(text), _find_volumes(text))

    # Step 3: 排序并去重（同一位置可能有多个模式匹配）
    boundaries = _deduplicate_boundaries(boundaries)

    # Step 4: 按章节号排序
    boundaries.sort(key=lambda b: b["chapter_num"])

    # Step 5: 切分文本
    segments = _split_by_boundaries(text, boundaries)

    # Step 5.5: 检测卷/篇/部标记，标注到各章节的 volume_title
    segments = _assign_volumes_to_chapters(segments, _find_volumes(text))

    # Step 6: 验证边界 — 标记可疑片段
    segments = _validate_segments(segments, min_chapter_chars)

    # Step 7: 可选模型确认（当前为占位）
    if use_model_verification and any(s.is_suspicious for s in segments):
        segments = _model_verify(segments, text)

    return segments


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------

def _find_boundaries(text: str) -> list[dict[str, Any]]:
    """扫描文本，收集所有匹配到的章节边界信息。"""
    boundaries: list[dict[str, Any]] = []

    for match_type, pattern in _CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            raw_num = m.group(1)
            title = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""

            chapter_num = _resolve_chapter_num(raw_num, match_type)
            if chapter_num is None:
                continue

            boundaries.append({
                "pos": m.start(),
                "end_pos": m.end(),
                "chapter_num": chapter_num,
                "title": title,
                "match_type": match_type,
                "raw_match": m.group(0),
            })

    return boundaries


def _find_volumes(text: str) -> list[dict[str, Any]]:
    """扫描文本，收集所有卷/篇/部标记的位置和标题。"""
    volumes: list[dict[str, Any]] = []

    for match_type, pattern in _VOLUME_PATTERNS:
        for m in pattern.finditer(text):
            raw_num = m.group(1)
            title = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""

            vol_num = _parse_volume_num(raw_num, match_type)
            if vol_num is None:
                continue

            volume_label = _build_volume_label(raw_num, match_type, vol_num, title)

            volumes.append({
                "pos": m.start(),
                "end_pos": m.end(),
                "volume_num": vol_num,
                "volume_title": volume_label,
                "match_type": match_type,
            })

    volumes.sort(key=lambda v: v["pos"])
    return volumes


def _parse_volume_num(raw: str, match_type: str) -> int | None:
    """解析卷编号：中文数字或阿拉伯数字→整数。"""
    if match_type == "en_part":
        try:
            return int(raw)
        except ValueError:
            return None
    if raw.isdigit():
        return int(raw)
    return _parse_chinese_number(raw)


def _build_volume_label(
    raw_num: str,
    match_type: str,
    volume_num: int,
    title: str,
) -> str:
    """根据匹配类型组装人类可读的卷标题。"""
    if match_type in ("cn_volume", "cn_part", "cn_book"):
        label = _CN_TYPE_LABEL[match_type]
        if title:
            return f"第{raw_num}{label} {title}".strip()
        return f"第{raw_num}{label}"
    if title:
        return f"Part {volume_num}: {title}".strip()
    return f"Part {volume_num}"


def _assign_volumes_to_chapters(
    segments: list[ChapterSegment],
    volumes: list[dict[str, Any]],
) -> list[ChapterSegment]:
    """将每个章节的 volume_title 设为最近的前一个卷标记标题。"""
    if not volumes:
        return segments

    vol_idx = 0
    current_volume = ""
    segments_sorted = sorted(segments, key=lambda s: s.start_pos)

    for seg in segments_sorted:
        while vol_idx < len(volumes) and volumes[vol_idx]["pos"] < seg.start_pos:
            current_volume = volumes[vol_idx]["volume_title"]
            vol_idx += 1
        seg.volume_title = current_volume

    return segments


def _resolve_chapter_num(raw: str, match_type: str) -> int | None:
    """将匹配到的原始数字字符串解析为整数。"""
    if match_type in ("arabic_chapter", "en_chapter", "numeric_heading", "numeric_prefix"):
        try:
            return int(raw)
        except ValueError:
            return None
    elif match_type == "cn_chapter":
        if raw.isdigit():
            return int(raw)
        return _parse_chinese_number(raw)
    return None


def _deduplicate_boundaries(
    boundaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """去重：同一位置附近只保留优先级最高的匹配。

    优先级：cn_chapter > arabic_chapter > en_chapter > numeric_heading > numeric_prefix。
    """
    priority = {
        "cn_chapter": 0,
        "arabic_chapter": 1,
        "en_chapter": 2,
        "numeric_heading": 3,
        "numeric_prefix": 4,
    }

    # 按位置排序
    boundaries.sort(key=lambda b: (b["pos"], priority.get(b["match_type"], 99)))

    merged: list[dict[str, Any]] = []
    for b in boundaries:
        if merged and abs(b["pos"] - merged[-1]["pos"]) < 5:
            # 同一位置，保留优先级更高的（已排序，先到的高优先级）
            continue
        merged.append(b)
    return merged


def _split_by_boundaries(
    text: str,
    boundaries: list[dict[str, Any]],
) -> list[ChapterSegment]:
    """根据边界点将文本切分为 ChapterSegment 列表。"""
    segments: list[ChapterSegment] = []
    text_len = len(text)

    for i, b in enumerate(boundaries):
        start = b["pos"]
        # 下一章的起始位置，或文本末尾
        if i + 1 < len(boundaries):
            end = boundaries[i + 1]["pos"]
        else:
            end = text_len

        content = text[start:end]

        segments.append(ChapterSegment(
            chapter_num=b["chapter_num"],
            title=b["title"],
            start_pos=start,
            end_pos=end,
            content=content,
            match_type=b["match_type"],
        ))

    return segments


def _validate_segments(
    segments: list[ChapterSegment],
    min_chars: int,
) -> list[ChapterSegment]:
    """验证章节边界，标记可疑片段。

    规则：
    - 章节内容长度 < min_chars → 可疑（可能是误匹配）
    - 连续两个以上章节都 < min_chars → 全部标记为可疑
    """
    for seg in segments:
        if len(seg.content) < min_chars:
            seg.is_suspicious = True

    # 批量标记：如果连续多个短章，整体可疑
    i = 0
    while i < len(segments):
        if segments[i].is_suspicious:
            j = i
            while j < len(segments) and segments[j].is_suspicious:
                j += 1
            # i..j-1 都是可疑的（已经是了，不需要重复标记）
            i = j
        else:
            i += 1

    return segments


def _model_verify(
    segments: list[ChapterSegment],
    text: str,
) -> list[ChapterSegment]:
    """使用 Ollama 模型对可疑边界进行确认（占位实现）。

    当前版本为占位 —— 后续可通过调用 Ollama HTTP API 实现。
    """
    # TODO: 调用 Ollama 确认可疑边界
    _ = text
    return segments


def _single_chapter(text: str) -> list[ChapterSegment]:
    """匹配数不足时，将整个文本作为一个章节返回。"""
    return [
        ChapterSegment(
            chapter_num=1,
            title="",
            start_pos=0,
            end_pos=len(text),
            content=text,
            match_type="fallback",
            is_suspicious=False,
        ),
    ]
