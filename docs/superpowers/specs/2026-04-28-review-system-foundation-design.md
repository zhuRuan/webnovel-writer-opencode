# Review System Foundation Reinforcement — Design Spec

Date: 2026-04-28  
Status: approved  
Scope: Fix review system bugs, clean up config, split oversized file  

## Overview

Fix foundational issues in the review/checker subsystem: a path bug that writes new agents to the wrong directory, duplicate `dimension_mapping` in two config files, and an 838-line `checkers_manager.py` that mixes three concerns.

## Change 1: Fix agents_dir path bug

**File:** `.opencode/scripts/data_modules/checkers_manager.py`

**Current bug:**
```python
self.agents_dir = checkers_dir / "agents"  # → .opencode/checkers/agents/ (does not exist)
```

**Fix:**
```python
self.agents_dir = checkers_dir.parent / "agents"  # → .opencode/agents/ (exists)
```

**Also fix** `create_checker()` at line ~675:
```python
# OLD: "file": f"agents/{checker_id}.md"       # relative to checkers/, wrong dir
# NEW: "file": f"../agents/{checker_id}.md"     # matches existing registry convention
```

---

## Change 2: Consolidate dimension_mapping

**Files:** `.opencode/checkers/registry.yaml`, `.opencode/checkers/schema.yaml`, `.opencode/scripts/data_modules/checkers_manager.py`

**Problem:** Both `registry.yaml` and `schema.yaml` define `dimension_mapping`. The schema version omits `unified-reviewer` from its mappings.

**Fix:**
1. Keep `registry.yaml` dimension_mapping as the single source of truth (includes unified-reviewer).
2. Remove `dimension_mapping` key from `schema.yaml`.
3. Remove `aggregation_schema.dimension_mapping` block from `schema.yaml`.
4. Update `checkers_manager.py` references to dimension_mapping to read from `load_registry()` instead of `load_schema()`.

---

## Change 3: Split checkers_manager.py

**Files:** Create `checkers_cli.py`, modify `checkers_manager.py`, modify `webnovel.py`

**Current:** `checkers_manager.py` (838 lines) mixes three concerns.

**After:**

`checkers_manager.py` (~500 lines) — Core class only:
- `CheckersManager` class
- `CodeCheckerProtocol`, `CodeCheckerResult`
- Code checker registration/execution (`register_code_checker`, `run_code_checkers`, `run_layered_checkers`)
- Registry loading/listing/validation (`load_registry`, `load_schema`, `list_checkers`, `get_checkers_for_mode`, `should_trigger_checker`, `get_schema_for_checker`, `create_checker`, `validate_registry`)
- Imports: `ConfigError`, `ConditionEvaluator`, logger

`checkers_cli.py` (~150 lines) — CLI commands:
- `cmd_list()` — list checkers
- `cmd_validate()` — validate registry  
- `cmd_create()` — create new checker
- Each function instantiates `CheckersManager()` locally

`webnovel.py` update:
- `COMMAND_REGISTRY["checkers"]["target"]` changes from `"checkers_manager"` to `"checkers_cli"`
- No other changes needed (dispatch remains the same)

`condition_evaluator.py` — unchanged, already independent.

### Non-Goals

- No changes to review agent content (unified-reviewer.md, consistency-checker.md, etc.)
- No changes to registry.yaml structure (only dimension_mapping consolidation)
- No changes to condition_evaluator.py
- No new features

### Verification

After each change, run:
```bash
python .opencode/scripts/webnovel.py checkers list
python .opencode/scripts/webnovel.py checkers validate
python -m pytest .opencode/scripts/data_modules/tests/test_checkers_manager.py -v
```
