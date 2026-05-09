#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for skill_runner.py"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from skill_runner import (
    cmd_check_file,
    cmd_check_commit,
    cmd_check_index,
    cmd_check_batch_integrity,
    filter_structural_checks,
)


def test_check_file_exists():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "test.md"
        f.write_text("hello", encoding="utf-8")
        assert cmd_check_file(str(f)) == 0


def test_check_file_missing():
    with tempfile.TemporaryDirectory() as td:
        assert cmd_check_file(str(Path(td) / "nope.md")) == 1


def test_check_file_empty():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "empty.md"
        f.write_text("", encoding="utf-8")
        assert cmd_check_file(str(f)) == 1


def test_check_commit_exists():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        commits = root / ".story-system" / "commits"
        commits.mkdir(parents=True)
        (commits / "chapter_020.commit.json").write_text('{"status":"ok"}', encoding="utf-8")
        assert cmd_check_commit(str(root), 20) == 0


def test_check_commit_missing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".story-system" / "commits").mkdir(parents=True)
        assert cmd_check_commit(str(root), 20) == 1


def test_check_index_ok():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        webnovel = root / ".webnovel"
        webnovel.mkdir()
        db_path = webnovel / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO chapters VALUES (20, 'test')")
        conn.commit()
        conn.close()
        assert cmd_check_index(str(root), 20) == 0


def test_check_index_missing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        webnovel = root / ".webnovel"
        webnovel.mkdir()
        db_path = webnovel / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.commit()
        conn.close()
        assert cmd_check_index(str(root), 20) == 1


def test_filter_structural_infra():
    result = {
        "chapter": 22,
        "passed": False,
        "checks": [
            {"name": "strand_balance", "passed": False, "severity": "blocking", "detail": "quest continuous 6 chapters", "fix": "switch"},
            {"name": "contract_coverage", "passed": False, "severity": "blocking", "detail": "missing chapter_0022.json", "fix": "run story-system"},
            {"name": "memory_bloat", "passed": True, "severity": "warning", "detail": "", "fix": ""},
        ],
    }
    filtered = filter_structural_checks(result)
    assert filtered["passed"] is False  # strand_balance still blocking
    contract_check = [c for c in filtered["checks"] if c["name"] == "contract_coverage"][0]
    assert contract_check["severity"] == "warning"
    assert contract_check["passed"] is True


def test_filter_structural_only_infra():
    """only infra issues: overall pass"""
    result = {
        "chapter": 22,
        "passed": False,
        "checks": [
            {"name": "contract_coverage", "passed": False, "severity": "blocking", "detail": "missing", "fix": "run story-system"},
        ],
    }
    filtered = filter_structural_checks(result)
    assert filtered["passed"] is True
