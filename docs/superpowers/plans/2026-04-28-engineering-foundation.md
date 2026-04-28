# Engineering Foundation Reinforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 26 test failures, migrate 7 modules to unified exception hierarchy, sync 3 stale docs.

**Architecture:** Three independent phases. Phase 1 adds `conftest.py` for import consistency, patches config field, and fixes logic bugs. Phase 2 swaps 12 standard exception raises to `WebnovelError` subclasses across 7 modules. Phase 3 updates architecture/operations docs.

**Tech Stack:** Python 3.10+, pytest, dataclasses

---

## Phase 1: Test Fixation (26 fail → 0 fail)

### Task 1.1: Add conftest.py for consistent test imports

**Files:**
- Create: `.opencode/scripts/data_modules/tests/conftest.py`
- Modify: `.opencode/scripts/data_modules/tests/test_dict_auto_rebuild.py:14` (remove ad-hoc path insert)

- [ ] **Step 1: Create conftest.py**

```python
# .opencode/scripts/data_modules/tests/conftest.py
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
```

- [ ] **Step 2: Remove ad-hoc sys.path.insert from test_dict_auto_rebuild.py**

Remove line 14:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

- [ ] **Step 3: Run full test suite to measure impact**

```bash
python .opencode/scripts/run_all_tests.py
```

Expected: Import-related failures drop. Count new pass/fail numbers.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/tests/conftest.py .opencode/scripts/data_modules/tests/test_dict_auto_rebuild.py
git commit -m "fix: add conftest.py for consistent test import paths"
```

---

### Task 1.2: Add scratchpad_file field to DataModulesConfig

**Files:**
- Modify: `.opencode/scripts/data_modules/config.py` (the `DataModulesConfig` dataclass)

- [ ] **Step 1: Find the exact location in config.py**

Search for `class DataModulesConfig` in config.py, then find the field definitions section. Add the `scratchpad_file` field near other path-related fields.

- [ ] **Step 2: Add the field**

```python
# In class DataModulesConfig, add alongside other path fields:
scratchpad_file: str = ".webnovel/scratchpad.json"
```

Ensure it's placed after existing string-field definitions but before any method definitions.

- [ ] **Step 3: Run affected tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_memory_contract_adapter.py .opencode/scripts/data_modules/tests/test_projection_writers.py -v
```

Expected: All 5 memory-contract tests + 2 projection writer scratchpad tests now pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/config.py
git commit -m "fix: add scratchpad_file field to DataModulesConfig"
```

---

### Task 1.3: Fix test_api_client rerank and modal failures

**Files:**
- Read: `.opencode/scripts/data_modules/api_client.py` (rerank and modal methods)
- Modify: `.opencode/scripts/data_modules/tests/test_api_client.py` (or api_client.py, depending on root cause)

- [ ] **Step 1: Read the failing test to understand expected behavior**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_api_client.py::test_rerank_headers_payload_and_stats -v
```

Read the full test body (around line 200-300). Note the assertions.

- [ ] **Step 2: Read the code-under-test**

Read `api_client.py` `RerankAPIClient` class, specifically the method that the test calls. Compare headers/payload construction against test expectations.

- [ ] **Step 3: Fix the mismatch**

If the code changed behavior and the test is stale → update the test assertions.
If the code has a bug → fix the code.

- [ ] **Step 4: Repeat for test_modal_client_helpers**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_api_client.py::test_modal_client_helpers -v
```

Read and fix.

- [ ] **Step 5: Run both tests to verify**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_api_client.py::test_rerank_headers_payload_and_stats .opencode/scripts/data_modules/tests/test_api_client.py::test_modal_client_helpers -v
```

Expected: Both PASS.

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/data_modules/tests/test_api_client.py .opencode/scripts/data_modules/api_client.py
git commit -m "fix: api_client rerank and modal test assertions"
```

---

### Task 1.4: Fix remaining logic bug tests

**Files:**
- `test_rag_adapter.py::test_search_respects_chapter_filter_across_strategies` → Read `rag_adapter.py` search method
- `test_runtime_contract_builder.py::test_runtime_contract_builder_creates_volume_and_review_contracts` → Read `runtime_contract_builder.py`
- `test_dict_auto_rebuild.py::test_init_auto_rebuild_when_dict_not_exists` → Read `rag_adapter.py` auto-rebuild logic
- `test_webnovel_unified_cli.py::test_quality_trend_report_writes_to_book_root_when_input_is_workspace_root` → Read `webnovel.py` quality trend report logic

- [ ] **Step 1: Fix each test one by one**

For each test:
1. Run it in isolation with `-v` to see the full failure traceback
2. Read both the test body and the code-under-test
3. Determine: test stale or code bug? Fix the broken side
4. Re-run to verify PASS

- [ ] **Step 2: Run full suite to confirm all 26 fixed**

```bash
python .opencode/scripts/run_all_tests.py
```

Expected: 0 failures, all passes.

- [ ] **Step 3: Commit each fix separately**

```bash
git add <fixed files>
git commit -m "fix: resolve test <test name>"
```

---

## Phase 2: Exception System Adoption

### Task 2.1: Migrate cli_args.py (2 raises)

**Files:**
- Modify: `.opencode/scripts/data_modules/cli_args.py:85,90`

- [ ] **Step 1: Add import**

At top of `cli_args.py`, add:
```python
from .exceptions import ConfigError
```

- [ ] **Step 2: Replace raises**

Line 85 (approximate): `raise ValueError("missing json arg")` → `raise ConfigError("missing json arg")`

Line 90 (approximate): `raise ValueError("invalid json arg: '@' without path")` → `raise ConfigError("invalid json arg: '@' without path")`

- [ ] **Step 3: Verify no callers catch ValueError for these**

Search for `except ValueError` in files that call `cli_args` functions.
```bash
python -m pytest .opencode/scripts/data_modules/tests/test_webnovel_unified_cli.py -v
```

Expected: All tests pass (ConfigError is an Exception subclass, so existing broad except handlers still catch it).

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/cli_args.py
git commit -m "refactor: migrate cli_args.py to ConfigError"
```

---

### Task 2.2: Migrate checkers_manager.py (3 raises)

**Files:**
- Modify: `.opencode/scripts/data_modules/checkers_manager.py:353,360,447`

- [ ] **Step 1: Add import**

```python
from .exceptions import ConfigError
```

- [ ] **Step 2: Replace raises**

Line 353: `raise FileNotFoundError(f"注册表不存在: {self.registry_path}")` → `raise ConfigError(f"注册表不存在: {self.registry_path}")`

Line 360: `raise FileNotFoundError(f"Schema 不存在: {self.schema_path}")` → `raise ConfigError(f"Schema 不存在: {self.schema_path}")`

Line 447: `raise ValueError(f"未知模式: {mode}，可用模式: {list(modes.keys())}")` → `raise ConfigError(f"未知模式: {mode}，可用模式: {list(modes.keys())}")`

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_checkers_manager.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/checkers_manager.py
git commit -m "refactor: migrate checkers_manager.py to ConfigError"
```

---

### Task 2.3: Migrate story_contracts.py (2 raises)

**Files:**
- Modify: `.opencode/scripts/data_modules/story_contracts.py:124,137`

- [ ] **Step 1: Add import**

```python
from .exceptions import ConfigError
```

- [ ] **Step 2: Replace raises**

Line 124: `raise ValueError(f"Bad JSON in {path}") from exc` → `raise ConfigError(f"Bad JSON in {path}") from exc`

Line 137: `raise ValueError(f"{path} contains multiple STORY-SYSTEM markers")` → `raise ConfigError(f"{path} contains multiple STORY-SYSTEM markers")`

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_story_contracts.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/story_contracts.py
git commit -m "refactor: migrate story_contracts.py to ConfigError"
```

---

### Task 2.4: Migrate webnovel.py (2 raises)

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py:102,124`

- [ ] **Step 1: Add import**

```python
from .exceptions import ConfigError
```

- [ ] **Step 2: Replace raises**

Line 102: `raise RuntimeError(f"data_modules.{module} 缺少可调用的 main()")` → `raise ConfigError(f"data_modules.{module} 缺少可调用的 main()")`

Line 124: `raise FileNotFoundError(f"未找到脚本: {script_path}")` → `raise ConfigError(f"未找到脚本: {script_path}")`

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_webnovel_unified_cli.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "refactor: migrate webnovel.py to ConfigError"
```

---

### Task 2.5: Migrate rag_adapter.py (1 raise)

**Files:**
- Modify: `.opencode/scripts/data_modules/rag_adapter.py:457`

- [ ] **Step 1: Add import**

```python
from .exceptions import StateManagerError
```

- [ ] **Step 2: Replace raise**

Line 457: `raise FileNotFoundError(f"vectors.db 不存在: {db_path}")` → `raise StateManagerError(f"vectors.db 不存在: {db_path}")`

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_rag_adapter.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/rag_adapter.py
git commit -m "refactor: migrate rag_adapter.py to StateManagerError"
```

---

### Task 2.6: Migrate state_manager.py (1 raise)

**Files:**
- Modify: `.opencode/scripts/data_modules/state_manager.py:481`

- [ ] **Step 1: Add import**

```python
from .exceptions import StateManagerError
```

- [ ] **Step 2: Replace raise**

Line 481: `raise RuntimeError("无法获取 state.json 文件锁，请稍后重试")` → `raise StateManagerError("无法获取 state.json 文件锁，请稍后重试")`

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_state_manager_extra.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/state_manager.py
git commit -m "refactor: migrate state_manager.py to StateManagerError"
```

---

### Task 2.7: Migrate index_debt_mixin.py (1 raise)

**Files:**
- Modify: `.opencode/scripts/data_modules/index_debt_mixin.py:89`

- [ ] **Step 1: Add import**

```python
from .exceptions import IndexManagerError
```

- [ ] **Step 2: Replace raise**

Line 89: `raise RuntimeError(...)` → `raise IndexManagerError(...)` (preserve exact message)

- [ ] **Step 3: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_data_modules.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/index_debt_mixin.py
git commit -m "refactor: migrate index_debt_mixin.py to IndexManagerError"
```

---

### Task 2.8: Final Phase 2 verification

- [ ] **Step 1: Run full test suite**

```bash
python .opencode/scripts/run_all_tests.py
```

Expected: 0 failures.

- [ ] **Step 2: Verify no remaining standard exception raises in production code**

```bash
rg "raise (ValueError|RuntimeError|FileNotFoundError|Exception)\(" .opencode/scripts/data_modules/*.py --include="*.py"
```

Expected: No results (all test files excluded from this search).

---

## Phase 3: Documentation Sync

### Task 3.1: Update docs/architecture.md

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Fix skills count**

Line 33: Change `Skills (10个)` → `Skills (12个)`

Line 138: Change `10个 Skills` → `12个 Skills`

- [ ] **Step 2: Fix agents count**

Line 37: Change `Agents (8个)` → `Agents (9个)`

Line 145: Change `8个 Agents` → `8个 Agents（context-agent, data-agent, 6个 Checker, unified-reviewer）`

- [ ] **Step 3: Remove stale file reference**

Line 82: Remove or fix line referencing `config_defaults.py` (file does not exist)

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: sync architecture.md with current project state"
```

---

### Task 3.2: Update docs/operations.md

**Files:**
- Modify: `docs/operations.md`

- [ ] **Step 1: Fix stale dashboard command (line 109)**

Line 109 currently reads:
```
python -m opencode.dashboard --project-root <项目路径>
```
Replace with:
```
python .opencode/scripts/webnovel.py dashboard --port 8765
```

- [ ] **Step 2: Run the updated command to verify**

```bash
python .opencode/scripts/webnovel.py dashboard --help
```

Expected: Prints help text (no ModuleNotFoundError).

- [ ] **Step 3: Commit**

```bash
git add docs/operations.md
git commit -m "docs: fix stale dashboard command in operations.md"
```

---

### Task 3.3: Final verification

- [ ] **Step 1: Verify AGENTS.md is still current**

```bash
python .opencode/scripts/webnovel.py where
python .opencode/scripts/webnovel.py checkers list
```

- [ ] **Step 2: Run full test suite one last time**

```bash
python .opencode/scripts/run_all_tests.py
```

Expected: 0 failures, all phases complete.

- [ ] **Step 3: Commit any final tweaks**

```bash
git add -A
git commit -m "chore: final verification pass for engineering foundation"
```
