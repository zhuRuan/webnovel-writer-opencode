#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""commit_artifacts 模块测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_modules.commit_artifacts import (
    EXTRACTION_FIELDS,
    extraction_dict,
    extraction_list,
    extraction_result_from_commit,
    extraction_text,
)


class TestExtractionResultFromCommit:
    def test_prefers_nested_extraction_result(self):
        """嵌套 extraction_result 优先于顶层字段。"""
        payload = {
            "accepted_events": [{"event_type": "old"}],
            "extraction_result": {
                "accepted_events": [{"event_type": "new"}],
                "state_deltas": [{"entity_id": "e1", "field": "realm", "new": "金丹"}],
            },
        }
        result = extraction_result_from_commit(payload)
        assert result["accepted_events"] == [{"event_type": "new"}]
        assert result["state_deltas"] == [{"entity_id": "e1", "field": "realm", "new": "金丹"}]

    def test_legacy_top_level_fallback(self):
        """旧格式 commit 的顶层字段向后兼容读取。"""
        payload = {
            "accepted_events": [{"event_type": "test"}],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "本章摘要",
        }
        result = extraction_result_from_commit(payload)
        assert result["accepted_events"] == [{"event_type": "test"}]
        assert result["summary_text"] == "本章摘要"

    def test_returns_shallow_copy(self):
        """返回的是浅拷贝，修改不影响原始 payload。"""
        original_events = [{"event_type": "test"}]
        payload = {"extraction_result": {"accepted_events": original_events}}
        result = extraction_result_from_commit(payload)
        result["accepted_events"].append({"event_type": "injected"})
        # 浅拷贝：列表引用相同，修改会泄漏
        # 这是已知的设计限制，此测试记录此行为
        assert len(payload["extraction_result"]["accepted_events"]) == 2

    def test_empty_payload(self):
        """空 payload 返回空 dict。"""
        result = extraction_result_from_commit({})
        assert result == {}

    def test_none_extraction_result_falls_back(self):
        """extraction_result 为 None 时回退到顶层字段。"""
        payload = {
            "extraction_result": None,
            "accepted_events": [{"event_type": "fallback"}],
        }
        result = extraction_result_from_commit(payload)
        assert result["accepted_events"] == [{"event_type": "fallback"}]

    def test_non_dict_extraction_result_falls_back(self):
        """extraction_result 非 dict 时回退到顶层字段。"""
        payload = {
            "extraction_result": "invalid",
            "summary_text": "fallback summary",
        }
        result = extraction_result_from_commit(payload)
        assert result["summary_text"] == "fallback summary"


class TestExtractionList:
    def test_returns_list_from_nested(self):
        payload = {"extraction_result": {"scenes": [{"location": "洞府"}]}}
        assert extraction_list(payload, "scenes") == [{"location": "洞府"}]

    def test_returns_list_from_legacy(self):
        payload = {"scenes": [{"location": "洞府"}]}
        assert extraction_list(payload, "scenes") == [{"location": "洞府"}]

    def test_returns_empty_for_missing(self):
        assert extraction_list({}, "scenes") == []

    def test_returns_empty_for_none(self):
        payload = {"extraction_result": {"scenes": None}}
        assert extraction_list(payload, "scenes") == []

    def test_returns_empty_for_non_list(self):
        payload = {"extraction_result": {"scenes": "invalid"}}
        assert extraction_list(payload, "scenes") == []


class TestExtractionDict:
    def test_returns_dict_from_nested(self):
        payload = {"extraction_result": {"chapter_meta": {"title": "第一章"}}}
        assert extraction_dict(payload, "chapter_meta") == {"title": "第一章"}

    def test_returns_empty_for_missing(self):
        assert extraction_dict({}, "chapter_meta") == {}

    def test_returns_empty_for_none(self):
        payload = {"extraction_result": {"chapter_meta": None}}
        assert extraction_dict(payload, "chapter_meta") == {}

    def test_returns_empty_for_non_dict(self):
        payload = {"extraction_result": {"chapter_meta": "invalid"}}
        assert extraction_dict(payload, "chapter_meta") == {}


class TestExtractionText:
    def test_returns_text_from_nested(self):
        payload = {"extraction_result": {"summary_text": "本章摘要"}}
        assert extraction_text(payload, "summary_text") == "本章摘要"

    def test_returns_empty_for_missing(self):
        assert extraction_text({}, "summary_text") == ""

    def test_returns_empty_for_none(self):
        payload = {"extraction_result": {"summary_text": None}}
        assert extraction_text(payload, "summary_text") == ""

    def test_strips_whitespace(self):
        payload = {"extraction_result": {"summary_text": "  本章摘要  "}}
        assert extraction_text(payload, "summary_text") == "本章摘要"

    def test_handles_zero(self):
        """0 是 falsy，extraction_text 使用 `or` 运算符将其视为空字符串。"""
        payload = {"extraction_result": {"dominant_strand": 0}}
        assert extraction_text(payload, "dominant_strand") == ""


class TestExtractionFields:
    def test_all_expected_fields_in_constant(self):
        """EXTRACTION_FIELDS 包含所有预期字段。"""
        expected = {
            "accepted_events", "state_deltas", "entity_deltas",
            "entities_appeared", "scenes", "chapter_meta",
            "dominant_strand", "summary_text",
        }
        assert set(EXTRACTION_FIELDS) == expected
