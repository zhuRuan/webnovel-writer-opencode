#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""artifact_validator 测试。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_modules.artifact_validator import (
    ERROR_BLOCKING_REVIEW,
    ERROR_MISSED_OUTLINE_NODE,
    ERROR_PENDING_DISAMBIGUATION,
    ERROR_SCHEMA,
    validate_artifact_payload,
    validate_commit_artifact_files,
    validate_chapter_commit,
)


class TestValidateArtifactPayload:
    def test_valid_review_result(self):
        payload = {"blocking_count": 0, "issues": []}
        result = validate_artifact_payload("review_result", payload)
        assert result["ok"] is True
        assert result["errors"] == []

    def test_review_with_blocking_issues(self):
        payload = {
            "blocking_count": 0,
            "issues": [{"blocking": True, "severity": "critical", "description": "test"}],
        }
        result = validate_artifact_payload("review_result", payload)
        # blocking_count in schema is 0, but policy checks issues list
        assert any(e["code"] == ERROR_BLOCKING_REVIEW for e in result["errors"])

    def test_valid_fulfillment_result(self):
        payload = {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        }
        result = validate_artifact_payload("fulfillment_result", payload)
        assert result["ok"] is True

    def test_fulfillment_with_missed_cbn(self):
        payload = {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [{"type": "CBN", "name": "test"}],
            "extra_nodes": [],
        }
        result = validate_artifact_payload("fulfillment_result", payload)
        assert any(e["code"] == ERROR_MISSED_OUTLINE_NODE for e in result["errors"])

    def test_valid_disambiguation_result(self):
        payload = {"pending": []}
        result = validate_artifact_payload("disambiguation_result", payload)
        assert result["ok"] is True

    def test_disambiguation_with_pending(self):
        payload = {"pending": [{"entity": "test"}]}
        result = validate_artifact_payload("disambiguation_result", payload)
        assert any(e["code"] == ERROR_PENDING_DISAMBIGUATION for e in result["errors"])

    def test_valid_extraction_result(self):
        payload = {
            "accepted_events": [{"event_type": "test"}],
            "state_deltas": [],
            "entity_deltas": [],
        }
        result = validate_artifact_payload("extraction_result", payload)
        assert result["ok"] is True

    def test_extraction_no_events(self):
        payload = {
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
        }
        result = validate_artifact_payload("extraction_result", payload)
        assert any(w["code"] == "no_events" for w in result["warnings"])

    def test_schema_validation_failure(self):
        payload = {"invalid": "data"}
        result = validate_artifact_payload("review_result", payload)
        assert result["ok"] is False
        assert any(e["code"] == ERROR_SCHEMA for e in result["errors"])

    def test_unknown_artifact(self):
        result = validate_artifact_payload("unknown_type", {})
        assert any(w["code"] == "unknown_artifact" for w in result["warnings"])


class TestValidateCommitArtifactFiles:
    def test_missing_files(self, tmp_path):
        result = validate_commit_artifact_files(tmp_path, 1)
        assert result["ok"] is False
        assert result["error_count"] == 4  # all 4 files missing


class TestValidateChapterCommit:
    def test_missing_commit(self, tmp_path):
        result = validate_chapter_commit(tmp_path, 1)
        assert result["ok"] is False
        assert any(e["code"] == "commit_missing" for e in result["errors"])

    def test_valid_commit(self, tmp_path):
        commits_dir = tmp_path / ".story-system" / "commits"
        commits_dir.mkdir(parents=True)
        commit = {
            "meta": {"chapter": 1, "status": "accepted"},
            "review_result": {"blocking_count": 0, "issues": []},
            "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            "disambiguation_result": {"pending": []},
            "extraction_result": {"accepted_events": [{"event_type": "test"}], "state_deltas": [], "entity_deltas": []},
            "projection_status": {
                "state": "done", "index": "done", "summary": "done",
                "memory": "done", "vector": "done",
            },
        }
        (commits_dir / "chapter_001.commit.json").write_text(
            json.dumps(commit), encoding="utf-8"
        )
        result = validate_chapter_commit(tmp_path, 1)
        assert result["ok"] is True
