#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

import pytest

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager


@pytest.fixture
def project_root(tmp_path):
    """Create minimal project root with required state.json."""
    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir()
    (webnovel / "state.json").write_text(json.dumps({"schema_version": "5.1", "progress": {}}))
    return tmp_path


def test_commit_service_rejects_when_missed_nodes_exist(project_root):
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "missed_nodes": ["发现陷阱"]},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    assert payload["meta"]["status"] == "rejected"


def test_commit_service_accepts_when_all_checks_pass(project_root):
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    assert payload["meta"]["status"] == "accepted"
    assert "MASTER_SETTING.json" in payload["contract_refs"]["master"]
    assert "volume_001.json" in payload["contract_refs"]["volume"]
    assert "chapter_003.json" in payload["contract_refs"]["chapter"]
    assert payload["outline_snapshot"]["covered_nodes"] == ["发现陷阱"]


def test_commit_service_includes_volume_ref_and_write_fact_provenance(project_root):
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )

    assert "volume_001.json" in payload["contract_refs"]["volume"]
    assert payload["provenance"]["write_fact_role"] == "chapter_commit"
    assert payload["provenance"]["projection_role"] == "derived_read_models"


def test_chapter_commit_cli_builds_and_persists_commit(project_root, monkeypatch):
    review_path = project_root / "review.json"
    fulfillment_path = project_root / "fulfillment.json"
    disambiguation_path = project_root / "disambiguation.json"
    extraction_path = project_root / "extraction.json"
    review_path.write_text('{"blocking_count": 0}', encoding="utf-8")
    fulfillment_path.write_text(
        '{"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []}',
        encoding="utf-8",
    )
    disambiguation_path.write_text('{"pending": []}', encoding="utf-8")
    extraction_path.write_text('{"state_deltas": [], "entity_deltas": [], "accepted_events": []}', encoding="utf-8")

    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from chapter_commit import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chapter_commit",
            "--project-root",
            str(project_root),
            "--chapter",
            "3",
            "--review-result",
            str(review_path),
            "--fulfillment-result",
            str(fulfillment_path),
            "--disambiguation-result",
            str(disambiguation_path),
            "--extraction-result",
            str(extraction_path),
        ],
    )
    main()

    assert (project_root / ".story-system" / "commits" / "chapter_003.commit.json").is_file()


def test_apply_projections_writes_events_and_amend_proposals(project_root):
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": ["发现陷阱"],
            "covered_nodes": ["发现陷阱"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "",
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "world_rule_broken",
                    "subject": "金手指",
                    "payload": {
                        "field": "world_rule",
                        "base_value": "每日一次",
                        "proposed_value": "短时失控突破",
                    },
                }
            ],
        },
    )

    service.apply_projections(payload)

    assert (project_root / ".story-system" / "events" / "chapter_003.events.json").is_file()
    manager = IndexManager(DataModulesConfig.from_project_root(project_root))
    with manager._get_conn() as conn:
        row = conn.execute(
            """
            SELECT record_type, field, override_value, status
            FROM override_contracts
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row["record_type"] == "amend_proposal"
    assert row["field"] == "world_rule"
    assert row["override_value"] == "短时失控突破"
    assert row["status"] == "pending"
