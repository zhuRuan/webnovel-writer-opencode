# Engineering Foundation Reinforcement — Design Spec

Date: 2026-04-28  
Status: approved  
Scope: Code quality, test stability, exception system, documentation  

## Overview

Strengthen the engineering foundation of the webnovel-writer codebase by fixing test failures, migrating to the unified exception hierarchy, and syncing stale documentation. Three independent phases, each with a measurable success criterion.

**Current baseline:** 479 passed / 26 failed (run_all_tests.py)  

---

## Phase 1: Test Fixation

**Goal:** 26 failure → 0 failure, all tests green with `run_all_tests.py`

### Category A — Import Path Standardization (~12 failures)

**Root cause:** Test files use `from data_modules import ...` without consistent sys.path setup. `run_all_tests.py` adds the scripts directory but not all test files benefit from it equally. Some test files manually insert sys.path (`test_dict_auto_rebuild.py`); most don't.

**Fix:** Add a `conftest.py` at `data_modules/tests/conftest.py` that uniformly adds `scripts/` to sys.path before any test module loads.

```
.opencode/scripts/data_modules/tests/conftest.py
```

```python
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
```

**Affected test files:** `test_projection_writers.py`, `test_data_modules.py`, `test_entity_linker_cli.py`, `test_relationship_graph.py`, `test_sql_state_manager.py`, `test_state_manager_extra.py`, `test_migrate_state_to_sqlite.py`, plus any that fail with `ModuleNotFoundError: No module named 'data_modules'`.

**Note:** Remove ad-hoc `sys.path.insert` from individual test files (e.g., `test_dict_auto_rebuild.py` line 14) — conftest handles it globally.

### Category B — Missing Config Fields (~5 failures)

**Root cause:** `ScratchpadManager` in `data_modules/memory/store.py:37` accesses `self.config.scratchpad_file`, but `DataModulesConfig` has no such field.

**Failures:** All 5 memory contract adapter tests + 2 projection writer tests that touch scratchpad.

**Fix:** Add `scratchpad_file: str` to `DataModulesConfig` with default `".webnovel/scratchpad.json"`. Verify default path is created by `ensure_dirs()` if needed.

### Category C — Logic Bugs (~3 failures)

**Known failures (after ruling out import issues in categories A/B):**
- `test_api_client.py::test_rerank_headers_payload_and_stats` — headers/payload assertion mismatch
- `test_api_client.py::test_modal_client_helpers` — helper function behavior change
- `test_rag_adapter.py::test_search_respects_chapter_filter_across_strategies` — strategy behavior change
- `test_runtime_contract_builder.py::test_runtime_contract_builder_creates_volume_and_review_contracts` — contract builder assertion
- `test_dict_auto_rebuild.py::test_init_auto_rebuild_when_dict_not_exists` — dictionary auto-rebuild trigger
- `test_webnovel_unified_cli.py::test_quality_trend_report_writes_to_book_root_when_input_is_workspace_root` — CLI output path

**Fix:** Read each failing test, compare against the code-under-test, determine if the bug is in the test (outdated expectation) or in the code. Fix the side that's wrong. Exact root cause for each will be determined during execution.

### Verification

After each category, run: `python .opencode/scripts/run_all_tests.py`

---

## Phase 2: Exception System Adoption

**Goal:** All production modules use `WebnovelError` subclasses instead of generic Python exceptions.

**Entry condition:** All 26 test failures resolved, 505 passed.

### Migration Rules

| Generic Exception | WebnovelError Subclass | Rationale |
|---|---|---|
| `ValueError` (config/payload) | `ConfigError` | Invalid config, bad JSON, wrong args |
| `RuntimeError` (state) | `StateManagerError` | Lock acquisition, state corruption |
| `RuntimeError` (index) | `IndexManagerError` | Index corruption, db failure |
| `RuntimeError` (api) | `APIClientError` | API call failure |
| `FileNotFoundError` (config) | `ConfigError` | Missing registry/schema file |
| `FileNotFoundError` (data) | `StateManagerError` | Missing state data file |

### Module Migration Plan

| # | Module | File | Count | After |
|---|---|---|---|---|
| 1 | CLI args | `cli_args.py` | 2× ValueError → ConfigError | Run test_cli_args if exists, else test_webnovel_unified_cli |
| 2 | Checkers manager | `checkers_manager.py` | 2× FileNotFoundError → ConfigError, 1× ValueError → ConfigError | Run test_checkers_manager |
| 3 | Story contracts | `story_contracts.py` | 2× ValueError → ConfigError | Run test_story_contracts |
| 4 | Webnovel CLI | `webnovel.py` | 1× RuntimeError → ConfigError, 1× FileNotFoundError → ConfigError | Run test_webnovel_unified_cli |
| 5 | RAG adapter | `rag_adapter.py` | 1× FileNotFoundError → StateManagerError | Run test_rag_adapter |
| 6 | State manager | `state_manager.py` | 1× RuntimeError → StateManagerError | Run test_state_manager_extra |
| 7 | Index debt mixin | `index_debt_mixin.py` | 1× RuntimeError → IndexManagerError | Run test_data_modules (IndexManager tests) |

### Verification

After each module: run its related tests. After all 7: run full suite.

---

## Phase 3: Documentation Sync

**Goal:** All architecture/docs files reflect actual project state.

| File | Current Issue | Fix |
|---|---|---|
| `docs/architecture.md` | "10 skills", "8 agents", references `config_defaults.py` (doesn't exist) | Update to 12 skills, 9 agents (add unified-reviewer), remove stale file references |
| `docs/operations.md` | Script paths and command examples partially outdated | Align with current CLI entry point and actual file paths |
| `AGENTS.md` | Already updated | Verify no new stale info introduced by Phase 1/2 |

### Verification

Manual review: spot-check each doc against actual directory listings and CLI output.

---

## Non-Goals

- No new features
- No refactoring of working code beyond exception class swaps
- No test coverage improvements (focus is on existing failures)
- No lint/typecheck tooling addition (may be a separate project)

## Risks

- **Test import fix could mask real import issues** — mitigated by verifying that tests still test what they claim to test
- **Exception migration may break callers that catch specific types** — mitigated by keeping all new exceptions as subclasses of `WebnovelError`, which existing `except Exception` handlers still catch
- **config field addition could have side effects** — mitigated by using a sensible default and verifying that related tests pass
