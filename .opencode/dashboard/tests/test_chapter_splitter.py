"""测试 services/chapter_splitter.py — 智能分章引擎。

覆盖 ≥8 种格式测试向量 + 边界情况。
"""

import sys
from pathlib import Path

import pytest

# 确保 .opencode/ 在 sys.path 上
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.services.chapter_splitter import (
    ChapterSegment,
    _parse_chinese_number,
    split_chapters,
)


# ========================================================================
# 测试向量文本片段
# ========================================================================

STANDARD_CN = (
    "第一章 统一分配\n"
    "这是第一章的内容，讲述了主角被统一分配到一个神秘世界。\n"
    "第二章 分配\n"
    "这是第二章的内容，讲述了分配制度背后的秘密。\n"
    "第三章 崛起\n"
    "这是第三章的内容，主角开始了自己的崛起之路。"
)

MIXED_FORMAT = (
    "第1章 开始\n"
    "这是第一章的内容，使用阿拉伯数字编号。\n"
    "第二章 继续\n"
    "这是第二章的内容，混合了阿拉伯数字和中文数字。\n"
    "第3章 转折\n"
    "这是第三章的内容，又切回阿拉伯数字。"
)

NO_MARKERS = (
    "这是一段没有任何章节标记的纯叙述文本，讲了很长很长的故事。"
    "故事发生在一个遥远的国度，主角历经千辛万苦终于找到了宝藏。"
    "然而这只是开始，更大的阴谋正在酝酿之中。"
)

SHORT_CHAPTERS = (
    "第1章\n"
    "短内容\n"
    "第2章\n"
    "短内容\n"
    "第3章\n"
    "短内容"
)

NUMERIC_HEADING = (
    "1. 初入江湖\n"
    "第一章的内容在这里展现，主角初入江湖。\n"
    "2. 拜师学艺\n"
    "第二章的内容，主角拜师学艺的过程。\n"
    "3. 出师下山\n"
    "第三章的内容，主角出师下山。"
)

ENGLISH_CHAPTER = (
    "Chapter 1 The Beginning\n"
    "This is the first chapter content. It describes the beginning.\n"
    "Chapter 2 The Journey\n"
    "This is the second chapter content. The journey begins.\n"
    "Chapter 3 The End\n"
    "This is the third chapter content. The end approaches."
)

CN_LARGE_NUMBERS = (
    "第十一章 新世界\n"
    "第十一章的内容，主角进入新世界。\n"
    "第二十章 突破\n"
    "第二十章的内容，主角突破境界。\n"
    "第一百二十章 巅峰\n"
    "第一百二十章的内容，主角达到巅峰。"
)

JAPANESE_NUMERIC = (
    "001 序章\n"
    "这是序章的内容。\n"
    "002 觉醒\n"
    "这是第二章的内容。\n"
    "003 启程\n"
    "这是第三章的内容。"
)

EMPTY_TEXT = ""

SPARSE_CHAPTERS = (
    "第一章 遥远的开始\n"
    + "长" * 500
    + "\n第二百章 漫长旅程\n"
    + "长" * 300
    + "\n第四百章 终点\n"
    + "长" * 200
)


# ========================================================================
# 中文数字解析测试
# ========================================================================

class TestParseChineseNumber:
    """_parse_chinese_number() 单元测试。"""

    def test_single_digit(self):
        assert _parse_chinese_number("一") == 1
        assert _parse_chinese_number("九") == 9
        assert _parse_chinese_number("零") == 0

    def test_ten_series(self):
        assert _parse_chinese_number("十") == 10
        assert _parse_chinese_number("十一") == 11
        assert _parse_chinese_number("十五") == 15
        assert _parse_chinese_number("十九") == 19
        assert _parse_chinese_number("二十") == 20
        assert _parse_chinese_number("二十五") == 25

    def test_hundreds(self):
        assert _parse_chinese_number("一百") == 100
        assert _parse_chinese_number("一百零一") == 101
        assert _parse_chinese_number("一百二十") == 120
        assert _parse_chinese_number("九百九十九") == 999

    def test_thousands(self):
        assert _parse_chinese_number("一千") == 1000
        assert _parse_chinese_number("一千零一") == 1001
        assert _parse_chinese_number("三千五百") == 3500

    def test_ten_thousands(self):
        assert _parse_chinese_number("一万") == 10000
        assert _parse_chinese_number("一万零一") == 10001
        assert _parse_chinese_number("十二万") == 120000

    def test_arabic_fallback(self):
        assert _parse_chinese_number("123") == 123

    def test_invalid_input(self):
        assert _parse_chinese_number("abc") is None
        assert _parse_chinese_number("") is None


# ========================================================================
# split_chapters 主函数测试
# ========================================================================

class TestSplitChaptersStandardCN:
    """标准中文格式："第X章 标题"。"""

    def test_three_chapters(self):
        result = split_chapters(STANDARD_CN)
        assert len(result) == 3

    def test_chapter_numbers(self):
        result = split_chapters(STANDARD_CN)
        assert [s.chapter_num for s in result] == [1, 2, 3]

    def test_chapter_titles(self):
        result = split_chapters(STANDARD_CN)
        assert result[0].title == "统一分配"
        assert result[1].title == "分配"
        assert result[2].title == "崛起"

    def test_match_type(self):
        result = split_chapters(STANDARD_CN)
        for s in result:
            assert s.match_type == "cn_chapter"

    def test_positions_are_monotonic(self):
        result = split_chapters(STANDARD_CN)
        for i in range(1, len(result)):
            assert result[i].start_pos == result[i - 1].end_pos

    def test_content_non_empty(self):
        result = split_chapters(STANDARD_CN)
        for s in result:
            assert len(s.content) > 0


class TestSplitChaptersMixedFormat:
    """混合格式：中文数字 + 阿拉伯数字混用。"""

    def test_three_chapters(self):
        result = split_chapters(MIXED_FORMAT)
        assert len(result) == 3

    def test_chapter_numbers_sequential(self):
        result = split_chapters(MIXED_FORMAT)
        assert [s.chapter_num for s in result] == [1, 2, 3]

    def test_titles(self):
        result = split_chapters(MIXED_FORMAT)
        assert result[0].title == "开始"
        assert result[1].title == "继续"
        assert result[2].title == "转折"


class TestSplitChaptersNoMarkers:
    """无章节标记文本 → 作为单章返回。"""

    def test_single_chapter_fallback(self):
        result = split_chapters(NO_MARKERS)
        assert len(result) == 1

    def test_fallback_has_chapter_one(self):
        result = split_chapters(NO_MARKERS)
        assert result[0].chapter_num == 1

    def test_fallback_contains_full_text(self):
        result = split_chapters(NO_MARKERS)
        assert result[0].content == NO_MARKERS

    def test_fallback_match_type(self):
        result = split_chapters(NO_MARKERS)
        assert result[0].match_type == "fallback"


class TestSplitChaptersShortChapters:
    """连续短章 — 标记为可疑。"""

    def test_three_chapters_detected(self):
        result = split_chapters(SHORT_CHAPTERS)
        assert len(result) == 3

    def test_all_suspicious(self):
        result = split_chapters(SHORT_CHAPTERS)
        for s in result:
            assert s.is_suspicious is True


class TestSplitChaptersNumericHeading:
    """数字编号格式："1. 标题"。"""

    def test_chapters_detected(self):
        result = split_chapters(NUMERIC_HEADING, min_chapter_count=1)
        assert len(result) >= 2

    def test_chapter_numbers(self):
        result = split_chapters(NUMERIC_HEADING, min_chapter_count=1)
        nums = [s.chapter_num for s in result]
        assert 1 in nums
        assert 2 in nums
        assert 3 in nums


class TestSplitChaptersEnglish:
    """英文格式："Chapter N Title"。"""

    def test_chapters_detected(self):
        result = split_chapters(ENGLISH_CHAPTER, min_chapter_count=1)
        assert len(result) == 3

    def test_match_type(self):
        result = split_chapters(ENGLISH_CHAPTER, min_chapter_count=1)
        for s in result:
            assert s.match_type == "en_chapter"

    def test_chapter_numbers(self):
        result = split_chapters(ENGLISH_CHAPTER, min_chapter_count=1)
        assert [s.chapter_num for s in result] == [1, 2, 3]


class TestSplitChaptersLargeCNNumbers:
    """大中文章节号：第十一章、第一百二十章等。"""

    def test_chapters_detected(self):
        result = split_chapters(CN_LARGE_NUMBERS)
        assert len(result) == 3

    def test_chapter_numbers(self):
        result = split_chapters(CN_LARGE_NUMBERS)
        assert [s.chapter_num for s in result] == [11, 20, 120]

    def test_match_type(self):
        result = split_chapters(CN_LARGE_NUMBERS)
        for s in result:
            assert s.match_type == "cn_chapter"


class TestSplitChaptersJapaneseNumeric:
    """日式编号格式："001 标题"。"""

    def test_chapters_detected(self):
        result = split_chapters(JAPANESE_NUMERIC, min_chapter_count=1)
        assert len(result) >= 2


class TestSplitChaptersEdgeCases:
    """边界情况测试。"""

    def test_empty_text(self):
        result = split_chapters(EMPTY_TEXT)
        assert result == []

    def test_whitespace_only(self):
        result = split_chapters("   \n  \n  ")
        assert result == []

    def test_metadata_passthrough(self):
        """metadata 参数被接受但不影响结果。"""
        meta = {"author": "测试作者", "work_title": "测试作品"}
        result = split_chapters(STANDARD_CN, metadata=meta)
        assert len(result) == 3

    def test_sorted_by_chapter_num(self):
        """结果按 chapter_num 排序。"""
        # 章节在文本中乱序出现
        text = "第三章 结尾\n内容C\n第一章 开头\n内容A\n第二章 中间\n内容B"
        result = split_chapters(text, min_chapter_count=3)
        assert [s.chapter_num for s in result] == [1, 2, 3]

    def test_sparse_chapters(self):
        """间距较大的章节不会被误标记为可疑。"""
        result = split_chapters(SPARSE_CHAPTERS)
        assert len(result) == 3
        for s in result:
            assert s.is_suspicious is False

    def test_use_model_verification_noop(self):
        """use_model_verification=True 不会崩溃（占位实现）。"""
        result = split_chapters(STANDARD_CN, use_model_verification=True)
        assert len(result) == 3


# ========================================================================
# ChapterSegment dataclass 测试
# ========================================================================

class TestChapterSegmentDataclass:
    """ChapterSegment 数据类基本行为。"""

    def test_default_values(self):
        seg = ChapterSegment(
            chapter_num=1,
            title="测试",
            start_pos=0,
            end_pos=100,
            content="测试内容",
        )
        assert seg.is_suspicious is False
        assert seg.match_type == "unknown"
        assert seg.meta == {}

    def test_custom_values(self):
        seg = ChapterSegment(
            chapter_num=5,
            title="第五章",
            start_pos=100,
            end_pos=200,
            content="内容",
            is_suspicious=True,
            match_type="cn_chapter",
            meta={"raw_line": "第五章 标题"},
        )
        assert seg.chapter_num == 5
        assert seg.is_suspicious is True
        assert seg.match_type == "cn_chapter"
        assert seg.meta == {"raw_line": "第五章 标题"}
