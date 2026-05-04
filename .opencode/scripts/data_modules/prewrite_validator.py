#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class PrewriteValidator:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def _get_active_rules(self, project_root: Path) -> list:
        scratchpad_path = project_root / ".webnovel" / "scratchpad.json"
        if not scratchpad_path.exists():
            return []
        try:
            data = json.loads(scratchpad_path.read_text(encoding="utf-8"))
            rules = data.get("world_rules", [])
            return [
                r.get("value", r.get("field", ""))
                for r in rules
                if r.get("status") == "active"
            ][:10]
        except Exception:
            return []

    def _review_cpn_consistency(
        self,
        chapter: int,
        nodes: list,
        index_manager: Any,
    ) -> dict:
        reviewed = []
        entity_context = {}
        active_rules = self._get_active_rules(self.project_root)

        try:
            recent_appearances = index_manager.get_recent_appearances(limit=10)
            for entry in recent_appearances:
                name = entry.get("canonical_name") or entry.get("entity_id", "")
                if name:
                    entity_context[name] = {
                        "last_chapter": entry.get("last_chapter", 0),
                        "total_appearances": entry.get("total", 0),
                    }
        except Exception:
            pass

        open_loops = []
        try:
            prev_chapters = range(max(1, chapter - 3), chapter)
            for ch in prev_chapters:
                prev_nodes = index_manager.get_chapter_nodes(ch)
                for node in prev_nodes:
                    if node.get("node_type") == "cen" and node.get("status") == "pending":
                        open_loops.append(node.get("goal", ""))
        except Exception:
            pass

        for node in nodes:
            if node.get("node_type") != "cpn":
                reviewed.append({
                    "node_type": node.get("node_type", ""),
                    "goal": node.get("goal", ""),
                    "status": "ok",
                    "seq": node.get("seq", 0),
                })
                continue

            goal = node.get("goal", "")
            status = "ok"
            warnings = []

            entity_mentioned = False
            for name, ctx in entity_context.items():
                if name and name in goal:
                    entity_mentioned = True
                    if ctx["total_appearances"] == 0:
                        warnings.append(f"角色「{name}」尚未出场")
                    break

            for loop in open_loops:
                if loop and len(loop) > 2 and loop[:3] in goal:
                    warnings.append(f"前章未闭合循环: {loop[:30]}...")

            if warnings:
                status = "warning"

            reviewed.append({
                "node_type": node.get("node_type", ""),
                "goal": goal,
                "status": status,
                "warning": "; ".join(warnings) if warnings else "",
                "seq": node.get("seq", 0),
            })

        total = len(reviewed)
        ok_count = sum(1 for r in reviewed if r["status"] == "ok")
        warning_count = sum(1 for r in reviewed if r["status"] == "warning")

        relationship_context = {}
        try:
            for name in entity_context:
                rels = index_manager.get_entity_relationships_at_chapter(name, chapter)
                if rels:
                    relationship_context[name] = rels[:5]
        except Exception:
            pass

        return {
            "reviewed_nodes": reviewed,
            "entity_context": entity_context,
            "relationship_context": relationship_context,
            "active_rules": active_rules,
            "open_loops_from_last_cen": open_loops,
            "total": total,
            "ok": ok_count,
            "warning": warning_count,
        }

    def build(
        self,
        chapter: int,
        review_contract: Dict[str, Any],
        plot_structure: Dict[str, Any],
        story_contract: Dict[str, Any] | None = None,
        index_manager: Any | None = None,
    ) -> Dict[str, Any]:
        state = json.loads(
            (self.project_root / ".webnovel" / "state.json").read_text(encoding="utf-8")
        )
        pending = state.get("disambiguation_pending") or []
        warnings = state.get("disambiguation_warnings") or []
        contract_provided = story_contract is not None
        story_contract = story_contract or {}
        missing_contracts = []
        if contract_provided:
            missing_contracts = [
                name
                for name in ("master_setting", "chapter_brief", "volume_brief", "review_contract")
                if not story_contract.get(name)
            ]
        blocking_reasons = []
        if pending:
            blocking_reasons.append("存在高优先级 disambiguation_pending")
        if missing_contracts:
            blocking_reasons.append(
                "缺少 Story System 合同: " + ", ".join(missing_contracts)
            )
        result = {
            "chapter": chapter,
            "blocking": bool(pending) or bool(missing_contracts),
            "blocking_reasons": blocking_reasons,
            "missing_contracts": missing_contracts,
            "forbidden_zones": list(review_contract.get("blocking_rules") or []),
            "disambiguation_domain": {
                "pending_count": len(pending),
                "warning_count": len(warnings),
                "allowed_mentions": [
                    item.get("mention", "")
                    for item in warnings
                    if isinstance(item, dict) and item.get("mention")
                ],
            },
            "fulfillment_seed": {
                "planned_nodes": list(plot_structure.get("mandatory_nodes") or []),
                "prohibitions": list(plot_structure.get("prohibitions") or []),
            },
        }

        if index_manager is not None:
            try:
                nodes = index_manager.get_chapter_nodes(chapter)
                if nodes:
                    result["cpn_review"] = self._review_cpn_consistency(
                        chapter, nodes, index_manager
                    )
            except Exception:
                pass

        return result
