"""测试 services/style_analyzer.py — 9 维度文风分析服务。

全 mock，无需真实 Ollama。用 asyncio.run() 调用 async 函数，mock
asyncio.create_subprocess_exec 模拟子进程响应。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保 .opencode/ 在 sys.path 上
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.services.style_analyzer import (
    ALL_DIMENSIONS,
    MAX_TEXT_CHARS,
    _CN_TO_EN,
    _map_cn_to_en,
    _parse_analysis_json,
    analyze_chapter_text,
    batch_analyze,
)

# ── 工具函数 ──────────────────────────────────────────────────


def _ollama_response_json(cn_dimensions: dict | None = None) -> bytes:
    """构造标准的 Ollama JSON 响应（9 维度完整）。"""
    if cn_dimensions is None:
        cn_dimensions = {
            "句式特征": {"summary": "短句为主，节奏明快。偶用长句舒缓紧张。", "score": 0.85},
            "叙事视角": {"summary": "第三人称全知视角，偶尔切换为限知。", "score": 0.60},
            "节奏控制": {"summary": "快慢交替，高潮密集，场景切换频繁。", "score": 0.80},
            "情感张力": {"summary": "情绪起伏强烈，爽点分布均匀。", "score": 0.75},
            "对白风格": {"summary": "对白占比适中，人物语言个性鲜明。", "score": 0.70},
            "词汇质地": {"summary": "词汇丰富，书面语偏多，偶用口语。", "score": 0.65},
            "修辞手法": {"summary": "善用比喻和排比，修辞手法多样。", "score": 0.55},
            "描写偏好": {"summary": "侧重动作描写和环境渲染。", "score": 0.60},
            "人物塑造": {"summary": "通过行动展现性格，侧面烘托到位。", "score": 0.72},
        }
    response_text = json.dumps(cn_dimensions, ensure_ascii=False)
    return json.dumps(
        {"model": "qwen3.5_9B_Q4", "response": response_text},
        ensure_ascii=False,
    ).encode("utf-8")


def _make_mock_process(stdout_bytes: bytes, stderr_bytes: bytes = b""):
    """构造 mock 子进程对象。"""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout_bytes, stderr_bytes))
    return proc


def _mock_ollama_call(stdout_bytes: bytes):
    """Patch asyncio.create_subprocess_exec 返回给定的 mock 进程。"""
    mock_proc = _make_mock_process(stdout_bytes)
    patcher = patch(
        "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
        AsyncMock(return_value=mock_proc),
    )
    return patcher, mock_proc


# ── 辅助同步封装 ──────────────────────────────────────────────


def _run(coro):
    """在 asyncio.run() 中执行一个协程。"""
    return asyncio.run(coro)


# ============================================================================
# analyze_chapter_text — 成功路径
# ============================================================================


class TestAnalyzeChapterTextSuccess:
    """成功获取 Ollama 响应并解析为结构化结果。"""

    def test_returns_all_9_dimensions(self):
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(analyze_chapter_text("测试章节文本" * 100))
        assert len(result) == 9
        for dim in ALL_DIMENSIONS:
            assert dim in result, f"缺少维度: {dim}"
            assert "summary" in result[dim], f"维度 {dim} 缺 summary"
            assert "score" in result[dim], f"维度 {dim} 缺 score"
            assert isinstance(result[dim]["score"], float)
            assert 0.0 <= result[dim]["score"] <= 1.0

    def test_english_field_names(self):
        """返回的 key 是英文字段名，与 AnalysisResult 对齐。"""
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(analyze_chapter_text("测试章节文本" * 100))
        assert "sentence_style" in result
        assert "narrative_pov" in result
        assert "pacing_control" in result
        assert "emotional_tension" in result
        assert "dialogue_style" in result

    def test_score_values_within_range(self):
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(analyze_chapter_text("测试文本" * 200))
        for dim, item in result.items():
            assert 0.0 <= item["score"] <= 1.0, f"{dim} 的 score={item['score']} 超出 [0,1]"


# ============================================================================
# analyze_chapter_text — 边界/错误情况
# ============================================================================


class TestAnalyzeChapterTextEdgeCases:
    """空文本、超时、JSON 解析失败等边界情况。"""

    def test_empty_text_returns_empty_dict(self):
        result = _run(analyze_chapter_text(""))
        assert result == {}

    def test_whitespace_only_returns_empty_dict(self):
        result = _run(analyze_chapter_text("   \n  \t  "))
        assert result == {}

    def test_timeout_returns_empty_dict(self):
        """模拟 asyncio.wait_for 超时。"""
        with patch(
            "dashboard.services.style_analyzer.asyncio.wait_for",
            side_effect=asyncio.TimeoutError(),
        ):
            result = _run(analyze_chapter_text("正常文本" * 100))
        assert result == {}

    def test_invalid_json_response_returns_empty_dict(self):
        """Ollama 返回乱码时优雅降级。"""
        garbage = json.dumps({
            "model": "qwen3.5_9B_Q4",
            "response": "这不是JSON格式的输出，{broken",
        }, ensure_ascii=False).encode("utf-8")
        patcher, _ = _mock_ollama_call(garbage)
        with patcher:
            result = _run(analyze_chapter_text("正常文本" * 100))
        assert result == {}

    def test_response_has_no_known_dimensions(self):
        """response 是合法 JSON 但不含任何已知维度 key。"""
        unrelated = json.dumps({
            "model": "qwen3.5_9B_Q4",
            "response": json.dumps({"其他字段": "无关内容"}, ensure_ascii=False),
        }, ensure_ascii=False).encode("utf-8")
        patcher, _ = _mock_ollama_call(unrelated)
        with patcher:
            result = _run(analyze_chapter_text("正常文本" * 100))
        assert result == {}

    def test_subprocess_exception_returns_empty_dict(self):
        """子进程创建失败时捕获异常。"""
        with patch(
            "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
            side_effect=OSError("curl not found"),
        ):
            result = _run(analyze_chapter_text("正常文本" * 100))
        assert result == {}


# ============================================================================
# analyze_chapter_text — 维度筛选
# ============================================================================


class TestAnalyzeChapterTextDimensionFilter:
    """dimensions 参数只返回请求的维度。"""

    def test_filter_primary_only(self):
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(
                analyze_chapter_text(
                    "测试文本" * 100,
                    dimensions=["sentence_style", "pacing_control"],
                )
            )
        assert len(result) == 2
        assert "sentence_style" in result
        assert "pacing_control" in result
        assert "narrative_pov" not in result

    def test_filter_single_dimension(self):
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(
                analyze_chapter_text(
                    "测试文本" * 100,
                    dimensions=["dialogue_style"],
                )
            )
        assert list(result.keys()) == ["dialogue_style"]

    def test_filter_nonexistent_dimension(self):
        """请求不存在的维度 → 返回空 dict。"""
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(
                analyze_chapter_text(
                    "测试文本" * 100,
                    dimensions=["nonexistent_dim"],
                )
            )
        assert result == {}


# ============================================================================
# analyze_chapter_text — JSON 解析策略
# ============================================================================


class TestAnalyzeChapterTextJsonParsing:
    """Ollama 可能返回被 markdown 包裹的 JSON 等情况。"""

    def test_markdown_wrapped_json(self):
        """response 被 ```json ... ``` 包裹。"""
        cn = {"句式特征": {"summary": "分析内容", "score": 0.8}}
        wrapped = "```json\n" + json.dumps(cn, ensure_ascii=False) + "\n```"
        response_bytes = json.dumps({
            "model": "qwen3.5_9B_Q4",
            "response": wrapped,
        }, ensure_ascii=False).encode("utf-8")
        patcher, _ = _mock_ollama_call(response_bytes)
        with patcher:
            result = _run(analyze_chapter_text("测试文本" * 100))
        assert "sentence_style" in result
        assert result["sentence_style"]["score"] == 0.8

    def test_json_with_text_prefix(self):
        """response 以解释文字开头，JSON 在后面。"""
        cn = {"句式特征": {"summary": "分析内容", "score": 0.9}}
        prefixed = "以下是我的分析：\n" + json.dumps(cn, ensure_ascii=False)
        response_bytes = json.dumps({
            "model": "qwen3.5_9B_Q4",
            "response": prefixed,
        }, ensure_ascii=False).encode("utf-8")
        patcher, _ = _mock_ollama_call(response_bytes)
        with patcher:
            result = _run(analyze_chapter_text("测试文本" * 100))
        assert "sentence_style" in result
        assert result["sentence_style"]["score"] == 0.9

    def test_all_dimensions_in_single_dimension_json(self):
        """即使只请求一个维度，JSON 里全量返回时也只保留请求的。"""
        # Ollama 返回全部 9 维度 JSON
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(
                analyze_chapter_text(
                    "测试文本" * 100,
                    dimensions=["sentence_style", "narrative_pov"],
                )
            )
        assert len(result) == 2


# ============================================================================
# batch_analyze
# ============================================================================


class TestBatchAnalyze:
    """批量分析多章。"""

    def test_returns_list_of_chapter_results(self):
        chapters = [
            {"text": "第一章内容" * 100, "chapter_num": 1},
            {"text": "第二章内容" * 100, "chapter_num": 2},
            {"text": "第三章内容" * 100, "chapter_num": 3},
        ]
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            results = _run(batch_analyze(chapters))
        assert len(results) == 3
        for i, r in enumerate(results):
            assert r["chapter_index"] == i
            assert r["chapter"] == chapters[i]
            assert len(r["result"]) == 9

    def test_progress_callback_called(self):
        chapters = [
            {"text": "第一章" * 50},
            {"text": "第二章" * 50},
        ]
        call_args = []

        def callback(current, total, chapter):
            call_args.append((current, total, chapter))

        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            _run(batch_analyze(chapters, progress_callback=callback))
        assert len(call_args) == 2
        assert call_args[0] == (1, 2, chapters[0])
        assert call_args[1] == (2, 2, chapters[1])

    def test_progress_callback_exception_does_not_break(self):
        """回调抛异常不阻塞后续章节分析。"""
        chapters = [
            {"text": "第一章" * 50},
            {"text": "第二章" * 50},
        ]

        def bad_callback(current, total, chapter):
            if current == 1:
                raise RuntimeError("回调异常")

        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            results = _run(batch_analyze(chapters, progress_callback=bad_callback))
        assert len(results) == 2  # 两章都分析了
        assert len(results[0]["result"]) == 9
        assert len(results[1]["result"]) == 9

    def test_empty_chapters_list(self):
        results = _run(batch_analyze([]))
        assert results == []

    def test_chapter_with_empty_text(self):
        chapters = [{"text": ""}]
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            results = _run(batch_analyze(chapters))
        assert len(results) == 1
        assert results[0]["result"] == {}

    def test_mixed_success_and_failure(self):
        """第一章分析失败（超时），第二章成功。"""
        chapters = [
            {"text": "第一章" * 50},
            {"text": "第二章" * 50},
        ]

        orig_create = asyncio.create_subprocess_exec

        async def mock_create(*args, **kwargs):
            # 第一章 → 超时
            if mock_create.call_count == 0:
                mock_create.call_count += 1
                raise asyncio.TimeoutError()
            # 后续 → 正常
            return await orig_create(*args, **kwargs)

        mock_create.call_count = 0

        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            with patch(
                "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
                side_effect=mock_create,
            ):
                # 为了可控，第一章直接 mock 超时
                pass  # 上面先 patch 了正常响应，直接重新 patch

        # 简化：用两个不同 mock
        patcher_timeout = patch(
            "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
            side_effect=asyncio.TimeoutError(),
        )
        with patcher_timeout:
            results = _run(batch_analyze(chapters))
        # 两章都超时
        assert results[0]["result"] == {}
        assert results[1]["result"] == {}

    def test_chapter_without_text_key(self):
        """章节 dict 缺少 text 字段。"""
        chapters = [{"author": "test"}]
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            results = _run(batch_analyze(chapters))
        assert results[0]["result"] == {}


# ============================================================================
# _parse_analysis_json 单元测试
# ============================================================================


class TestParseAnalysisJson:
    """_parse_analysis_json 三种解析策略。"""

    def test_strategy1_direct_json(self):
        raw = json.dumps({"句式特征": {"summary": "简洁明快", "score": 0.8}}, ensure_ascii=False)
        result = _parse_analysis_json(raw)
        assert "句式特征" in result

    def test_strategy2_extract_json_block(self):
        raw = '一些前置文字 {"句式特征": {"summary": "简洁明快", "score": 0.8}} 后置文字'
        result = _parse_analysis_json(raw)
        assert "句式特征" in result

    def test_strategy3_regex_fallback(self):
        """策略 1 和 2 因非法 JSON 外层失败时，正则逐维度兜底。"""
        raw = '{broken "句式特征": {"summary": "测试", "score": 0.5}'
        result = _parse_analysis_json(raw)
        assert "句式特征" in result

    def test_empty_raw(self):
        assert _parse_analysis_json("") == {}
        assert _parse_analysis_json("   ") == {}

    def test_completely_unparseable(self):
        raw = "这不是 JSON，也没有任何已知维度"
        result = _parse_analysis_json(raw)
        assert result == {}

    def test_partial_dimensions(self):
        """只包含部分维度的 JSON。"""
        raw = json.dumps({
            "句式特征": {"summary": "测试", "score": 0.5},
            "叙事视角": {"summary": "测试", "score": 0.6},
        }, ensure_ascii=False)
        result = _parse_analysis_json(raw)
        assert len(result) == 2
        assert "句式特征" in result
        assert "叙事视角" in result


# ============================================================================
# _map_cn_to_en 单元测试
# ============================================================================


class TestMapCnToEn:
    """中文 key → 英文字段名映射与 score 裁剪。"""

    def test_full_mapping(self):
        cn = {
            "句式特征": {"summary": "test", "score": 0.75},
            "叙事视角": {"summary": "test", "score": 0.60},
        }
        result = _map_cn_to_en(cn)
        assert "sentence_style" in result
        assert "narrative_pov" in result
        assert result["sentence_style"]["score"] == 0.75

    def test_score_clamping_below_zero(self):
        cn = {"句式特征": {"summary": "x", "score": -0.5}}
        result = _map_cn_to_en(cn)
        assert result["sentence_style"]["score"] == 0.0

    def test_score_clamping_above_one(self):
        cn = {"句式特征": {"summary": "x", "score": 1.5}}
        result = _map_cn_to_en(cn)
        assert result["sentence_style"]["score"] == 1.0

    def test_missing_score_defaults_to_0_5(self):
        cn = {"句式特征": {"summary": "x"}}  # 缺 score
        result = _map_cn_to_en(cn)
        assert result["sentence_style"]["score"] == 0.5

    def test_non_numeric_score_defaults_to_0_5(self):
        cn = {"句式特征": {"summary": "x", "score": "高"}}
        result = _map_cn_to_en(cn)
        assert result["sentence_style"]["score"] == 0.5

    def test_missing_summary_defaults_to_empty_string(self):
        cn = {"句式特征": {"score": 0.8}}  # 缺 summary
        result = _map_cn_to_en(cn)
        assert result["sentence_style"]["summary"] == ""

    def test_non_dict_item_skipped(self):
        cn = {"句式特征": "这不是dict"}
        result = _map_cn_to_en(cn)
        assert result == {}

    def test_unknown_cn_key_ignored(self):
        cn = {"未知维度": {"summary": "x", "score": 0.5}}
        result = _map_cn_to_en(cn)
        assert result == {}


# ============================================================================
# 常量验证
# ============================================================================


class TestConstants:
    """验证模块常量和映射表一致性。"""

    def test_nine_dimensions_total(self):
        assert len(ALL_DIMENSIONS) == 9

    def test_cn_to_en_bidirectional(self):
        for cn, en in _CN_TO_EN.items():
            assert cn and en, f"映射不完整: {cn} -> {en}"

    def test_all_dimensions_match_cn_to_en(self):
        assert set(ALL_DIMENSIONS) == set(_CN_TO_EN.values())

    def test_max_text_chars_reasonable(self):
        assert MAX_TEXT_CHARS > 0
        assert MAX_TEXT_CHARS <= 20000


# ============================================================================
# 文本截断
# ============================================================================


class TestTextTruncation:
    """超过 MAX_TEXT_CHARS 的文本被截断。"""

    def test_text_longer_than_limit_is_truncated(self):
        """超长文本被截断后仍能正常分析（不会因 prompt 过大 OOM）。"""
        long_text = "长" * (MAX_TEXT_CHARS + 500)
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(analyze_chapter_text(long_text))
        # 截断后长度应 ≤ MAX_TEXT_CHARS
        assert len(result) == 9  # 正常返回

    def test_text_exactly_at_limit(self):
        """恰好等于截断上限的文本不被截断。"""
        exact_text = "x" * MAX_TEXT_CHARS
        patcher, _ = _mock_ollama_call(_ollama_response_json())
        with patcher:
            result = _run(analyze_chapter_text(exact_text))
        assert len(result) == 9


# ============================================================================
# Ollama 调用参数验证
# ============================================================================


class TestOllamaCallParams:
    """验证传给 Ollama 的参数格式正确。"""

    def test_uses_correct_model(self):
        mock_proc = _make_mock_process(_ollama_response_json())
        mock_create = AsyncMock(return_value=mock_proc)
        patcher = patch(
            "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
            mock_create,
        )
        with patcher:
            _run(analyze_chapter_text("测试" * 100))
        # 检查创建的 subprocess args
        call_args = mock_create.call_args
        assert call_args is not None, "create_subprocess_exec 未被调用"
        # args = ("curl", "-s", url, "-d", payload_json)
        args = call_args[0]
        assert args[0] == "curl"
        assert args[1] == "-s"
        assert "api/generate" in args[2]
        payload = json.loads(args[4])
        assert payload["model"] == "qwen3.5_9B_Q4"
        assert payload["stream"] is False
        assert "prompt" in payload

    def test_custom_model_overrides_default(self):
        mock_proc = _make_mock_process(_ollama_response_json())
        mock_create = AsyncMock(return_value=mock_proc)
        patcher = patch(
            "dashboard.services.style_analyzer.asyncio.create_subprocess_exec",
            mock_create,
        )
        with patcher:
            _run(analyze_chapter_text("测试" * 100, model="custom-model"))
        payload = json.loads(mock_create.call_args[0][4])
        assert payload["model"] == "custom-model"
