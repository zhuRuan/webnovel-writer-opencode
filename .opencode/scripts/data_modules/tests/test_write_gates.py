#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_gates 测试。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_modules.write_gates import (
    format_gate_report,
    gate_report,
    issue,
    run_write_gate,
)


class TestIssue:
    def test_basic_fields(self):
        i = issue("test_code", "error", "test message")
        assert i["code"] == "test_code"
        assert i["severity"] == "error"
        assert i["message"] == "test message"

    def test_optional_fields(self):
        i = issue("test", "warning", "msg", impact="high", repair="fix it")
        assert i["impact"] == "high"
        assert i["repair"] == "fix it"


class TestGateReport:
    def test_ok_when_no_errors(self):
        report = gate_report("prewrite", [], [])
        assert report["ok"] is True
        assert report["stage"] == "prewrite"

    def test_not_ok_when_errors(self):
        errors = [issue("test", "error", "fail")]
        report = gate_report("precommit", errors, [])
        assert report["ok"] is False
        assert report["error_count"] == 1

    def test_warnings_only(self):
        warnings = [issue("test", "warning", "warn")]
        report = gate_report("postcommit", [], warnings)
        assert report["ok"] is True
        assert report["warning_count"] == 1


class TestFormatGateReport:
    def test_json_format(self):
        report = gate_report("prewrite", [], [])
        output = format_gate_report(report, "json")
        parsed = json.loads(output)
        assert parsed["stage"] == "prewrite"

    def test_text_format(self):
        report = gate_report("prewrite", [], [])
        output = format_gate_report(report, "text")
        assert "prewrite" in output
        assert "通过" in output

    def test_text_with_errors(self):
        errors = [issue("test_code", "error", "test message", repair="fix it")]
        report = gate_report("precommit", errors, [])
        output = format_gate_report(report, "text")
        assert "test_code" in output
        assert "fix it" in output


class TestRunWriteGate:
    def test_unknown_stage(self):
        result = run_write_gate("unknown", Path("/tmp"), 1)
        assert result["ok"] is False
        assert any(e["code"] == "unknown_stage" for e in result["errors"])

    def test_prewrite_missing_contracts(self, tmp_path):
        result = run_write_gate("prewrite", tmp_path, 1)
        assert result["ok"] is False
        assert any(e["code"] == "missing_master_setting" for e in result["errors"])

    def test_prewrite_with_contracts(self, tmp_path):
        # 创建最小合同结构
        story_dir = tmp_path / ".story-system"
        story_dir.mkdir()
        (story_dir / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
        chapters_dir = story_dir / "chapters"
        chapters_dir.mkdir()
        (chapters_dir / "chapter_001.json").write_text("{}", encoding="utf-8")

        result = run_write_gate("prewrite", tmp_path, 1)
        assert result["ok"] is True
