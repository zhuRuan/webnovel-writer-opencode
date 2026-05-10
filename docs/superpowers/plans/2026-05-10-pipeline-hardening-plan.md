# Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 23 bugs across 5 subsystems: pipeline integrity (A), Windows compatibility (B), agent reliability (C), noise reduction (D), experience polish (E).

**Architecture:** Surgical changes across 13 files — no new modules, no abstractions. Each task touches 1-2 files with TDD: write failing test → implement → verify pass → commit.

**Tech Stack:** Python 3.14, pytest, sqlite3 (index.db), argparse

**Pre-existing fixes confirmed during code review:**
- B1: `webnovel.py:34`, `skill_runner.py:150`, `chapter_commit.py:48-49` already call `enable_windows_utf8_stdio()`
- A4 data-agent: `data-agent.md:59` already requires protagonist location delta even when unchanged
- BUG-016: `skill_runner.py:104` already uses correct `chapter` column name

---

### Task A1: PROJECT_ROOT child directory scanning

**Files:**
- Modify: `.opencode/scripts/project_locator.py:239-249`
- Test: `.opencode/scripts/data_modules/tests/test_project_locator.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_project_root_finds_nested_child_project(tmp_path):
    _ensure_scripts_on_path()
    from project_locator import resolve_project_root

    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)

    nested_project = repo_root / "my-novel"
    (nested_project / ".webnovel").mkdir(parents=True, exist_ok=True)
    (nested_project / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    # CWD is repo root (no .webnovel), child has project
    resolved = resolve_project_root(cwd=repo_root)
    assert resolved == nested_project.resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_project_locator.py::test_resolve_project_root_finds_nested_child_project -q --no-cov`
Expected: FAIL with FileNotFoundError

- [ ] **Step 3: Implement child directory scanning in _candidate_roots**

In `.opencode/scripts/project_locator.py`, modify `_candidate_roots()` — insert child scanning after DEFAULT_PROJECT_DIR_NAMES loop and before ancestor loop:

```python
def _candidate_roots(cwd: Path, *, stop_at: Optional[Path] = None) -> Iterable[Path]:
    yield cwd
    for name in DEFAULT_PROJECT_DIR_NAMES:
        yield cwd / name

    # Scan immediate children for nested project directories
    try:
        for child in sorted(cwd.iterdir()):
            if child.is_dir() and _is_project_root(child):
                yield child
    except OSError:
        pass

    for parent in cwd.parents:
        yield parent
        for name in DEFAULT_PROJECT_DIR_NAMES:
            yield parent / name
        if stop_at is not None and parent == stop_at:
            break
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_project_locator.py -q --no-cov`
Expected: all tests PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/project_locator.py .opencode/scripts/data_modules/tests/test_project_locator.py
git commit -m "fix: scan CWD children for nested project directories

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task A2: preflight fs_state_sync check

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py:173-238`

- [ ] **Step 1: Add fs_state_sync to _build_preflight_report**

In `_build_preflight_report()`, after the `story_runtime` block (line 194), insert:

```python
        # fs_state_sync: compare filesystem chapters vs state.json
        fs_state_check = _build_fs_state_sync(resolved_root)
        checks.append(fs_state_check)
```

Add new helper function before `_build_preflight_report`:

```python
def _build_fs_state_sync(project_root: Path) -> dict:
    import re
    fs_nums = set()
    text_dir = project_root / "正文"
    if text_dir.is_dir():
        for f in text_dir.rglob("第*章*.md"):
            m = re.match(r"第0*(\d+)章", f.name)
            if m:
                fs_nums.add(int(m.group(1)))

    state_path = project_root / ".webnovel" / "state.json"
    state_nums = set()
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            chapter_status = (state.get("progress") or {}).get("chapter_status") or {}
            state_nums = set(int(k) for k in chapter_status.keys())
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    orphans = sorted(fs_nums - state_nums)
    ghosts = sorted(state_nums - fs_nums)
    if orphans or ghosts:
        detail_parts = []
        if orphans:
            detail_parts.append(f"孤文件(有正文无状态): {orphans}")
        if ghosts:
            detail_parts.append(f"幽灵章(有状态无正文): {ghosts}")
        return {
            "name": "fs_state_sync",
            "ok": True,
            "severity": "warning",
            "detail": "; ".join(detail_parts),
        }
    return {
        "name": "fs_state_sync",
        "ok": True,
        "severity": "info",
        "detail": f"fs={len(fs_nums)} chapters, state={len(state_nums)} records, in sync",
    }
```

- [ ] **Step 2: Run preflight to verify**

Run: `python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" preflight`
Expected: fs_state_sync line appears in output

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: add fs_state_sync check to preflight

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task A3: Contract tree prerequisite gate

**Files:**
- Modify: `.opencode/agents/chapter-writer-agent.md:45-50`
- Modify: `.opencode/skills/webnovel-write/SKILL.md`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Add contract tree check to chapter-writer-agent Step A**

In `.opencode/agents/chapter-writer-agent.md`, after line 50 (`□ 必须覆盖`), insert:

```markdown
□ 合同树: .story-system/chapters/chapter_{NNN}.json 必须存在。若不存在，输出 "❌ 合同树缺失: 请先运行 story-system 刷新合同" 并退出，不进行起草。
```

Also add a bash verification in Step A:

```bash
# 验证合同树存在
CHAPTER_CONTRACT="${PROJECT_ROOT}/.story-system/chapters/chapter_$(printf '%03d' $N).json"
if [ ! -f "$CHAPTER_CONTRACT" ]; then
  echo "❌ 合同树缺失: $CHAPTER_CONTRACT"
  echo "请先运行: echo \"\${CHAPTER_GOAL}\" | python -X utf8 \"\${SCRIPTS_DIR}/skill_runner.py\" story-system --project-root \"\${PROJECT_ROOT}\" --chapter $N"
  exit 1
fi
```

- [ ] **Step 2: Add story-system return code check to single-chapter SKILL.md**

In `.opencode/skills/webnovel-write/SKILL.md`, after the story-system call (line ~93), add:

```bash
|| { echo "❌ story-system 合同刷新失败，阻断流程"; exit 1; }
```

- [ ] **Step 3: Add same check to batch SKILL.md**

In `.opencode/skills/webnovel-write-batch/SKILL.md`, after the story-system call (line ~200), add the same `||` guard.

- [ ] **Step 4: Commit**

```bash
git add .opencode/agents/chapter-writer-agent.md .opencode/skills/webnovel-write/SKILL.md .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat: add contract tree prerequisite gate to writing flow

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task A4: Structural checker threshold tuning + skill-level gating

**Files:**
- Modify: `.opencode/scripts/data_modules/structural_checker.py:33-96`
- Test: `.opencode/scripts/data_modules/tests/test_structural_checker.py`
- Modify: `.opencode/skills/webnovel-write/SKILL.md`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Update test expectations for new thresholds**

In `test_structural_checker.py`, update `test_strand_constellation_absent` to test at chapter=10 (was chapter=22 with threshold 15+):

```python
def test_strand_constellation_absent():
    """constellation 从未激活且超过 8 章应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "strand_tracker": {
                "last_constellation_chapter": 0,
                "chapters_since_switch": 2,
            }
        })
        _write_state(root, state)
        _write_contract(root, 10)
        result = run_checks(root, 10)
        check = _find_check(result, "strand_balance")
        assert check["passed"] is False
        assert "从未激活" in check["detail"]
```

Update `test_entity_freshness_stale` to test at gap=6 (threshold changed from 3 to 5):

```python
def test_entity_freshness_stale():
    """主角位置落后 >= 5 章应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "protagonist_state": {
                "location": {"current": "废弃工厂", "last_chapter": 16},
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "entity_freshness")
        assert check["passed"] is False
        assert check["severity"] == "blocking"
```

Add new test for entity_freshness at gap=2 (should pass with new threshold):

```python
def test_entity_freshness_gap2_ok():
    """位置 2 章未更新在新阈值下应通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "protagonist_state": {
                "location": {"current": "废弃工厂", "last_chapter": 20},
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "entity_freshness")
        assert check["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail with old thresholds**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_structural_checker.py -q --no-cov`
Expected: `test_strand_constellation_absent` and `test_entity_freshness_stale` FAIL

- [ ] **Step 3: Update thresholds in structural_checker.py**

In `_check_strand_balance` (line 63): change `chapter > 15` to `chapter > 8`, and change `最高容忍 15 章` to `最高容忍 8 章`.

In `_check_strand_balance` (line 69): change `gap > 10` to `gap > 8`.

In `_check_entity_freshness` (line 92): change `gap >= 3` to `gap >= 5`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_structural_checker.py -q --no-cov`
Expected: all tests PASS

- [ ] **Step 5: Add blocking gate to single-chapter SKILL.md**

In `.opencode/skills/webnovel-write/SKILL.md`, after Step 1b (structure self-check), add:

```bash
# 检查结构自检结果，blocking 时阻断
python -c "
import json, sys
d = json.load(open('${PROJECT_ROOT}/.webnovel/tmp/structural_check.json'))
if not d.get('passed'):
    print('❌ 结构自检未通过，停止流程')
    for c in d['checks']:
        if c['severity'] == 'blocking' and not c['passed']:
            print(f'  BLOCKING: {c[\"name\"]}: {c[\"detail\"]}')
            print(f'  FIX: {c[\"fix\"]}')
    sys.exit(1)
" || exit 1
```

Note: Step 1b must first save the structural check result to a file. Update the check-structural call to:
```bash
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-structural \
  --project-root "${PROJECT_ROOT}" --chapter {N} --format json \
  > "${PROJECT_ROOT}/.webnovel/tmp/structural_check.json"
```

- [ ] **Step 6: Add same gate to batch SKILL.md**

Same two changes (save to file + blocking check) in `.opencode/skills/webnovel-write-batch/SKILL.md` Step 1b.

- [ ] **Step 7: Commit**

```bash
git add .opencode/scripts/data_modules/structural_checker.py .opencode/scripts/data_modules/tests/test_structural_checker.py .opencode/skills/webnovel-write/SKILL.md .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "fix: tune structural check thresholds + add blocking gate

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task B1: PYTHONUTF8 in skill shell environment

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Add $env:PYTHONUTF8 to Step 0 of both skills**

In both SKILL.md files, after the environment variable setup block, add:

```powershell
$env:PYTHONUTF8 = 1
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "fix: set PYTHONUTF8=1 in skill shell environment

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task B2: verify-chapter-files action + skill doc validation rewrite

**Files:**
- Modify: `.opencode/scripts/skill_runner.py:93-168`
- Test: `.opencode/scripts/data_modules/tests/test_skill_runner.py`
- Modify: `.opencode/skills/webnovel-write/SKILL.md`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Write test for verify-chapter-files**

```python
def test_verify_chapter_files_ok(tmp_path):
    """验证全部文件存在且投影完成应返回 OK"""
    _ensure_scripts_on_path()
    from skill_runner import cmd_verify_chapter_files
    import argparse

    # Setup chapter file
    text_dir = tmp_path / "正文"
    text_dir.mkdir()
    (text_dir / "第001章-测试.md").write_text("测试内容", encoding="utf-8")

    # Setup commit with all projections done
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    commit = {
        "meta": {"chapter": 1, "status": "accepted"},
        "projection_status": {
            "state": "done", "index": "done", "summary": "done",
            "memory": "done", "vector": "skipped",
        },
    }
    (commits / "chapter_001.commit.json").write_text(
        json.dumps(commit, ensure_ascii=False), encoding="utf-8"
    )

    ns = argparse.Namespace(project_root=str(tmp_path), chapter=1)
    rc = cmd_verify_chapter_files(ns)
    assert rc == 0


def test_verify_chapter_files_missing_chapter(tmp_path):
    """章节文件缺失应返回 FAIL"""
    _ensure_scripts_on_path()
    from skill_runner import cmd_verify_chapter_files
    import argparse

    ns = argparse.Namespace(project_root=str(tmp_path), chapter=1)
    rc = cmd_verify_chapter_files(ns)
    assert rc == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py::test_verify_chapter_files_ok .opencode/scripts/data_modules/tests/test_skill_runner.py::test_verify_chapter_files_missing_chapter -q --no-cov`
Expected: FAIL (cmd_verify_chapter_files not defined / AttributeError)

- [ ] **Step 3: Implement cmd_verify_chapter_files in skill_runner.py**

Add function before `cmd_compact_memory` (after line 113):

```python
def cmd_verify_chapter_files(args: argparse.Namespace) -> int:
    root = Path(args.project_root)
    ch = int(args.chapter)
    errors = []

    text_dir = root / "正文"
    chapter_files = list(text_dir.rglob(f"第*{ch}*章*.md"))
    if not chapter_files:
        errors.append(f"章节文件缺失: 第{ch}章")
    elif not chapter_files[0].stat().st_size:
        errors.append(f"章节文件为空: 第{ch}章")

    commit_file = root / ".story-system" / "commits" / f"chapter_{ch:03d}.commit.json"
    if not commit_file.is_file():
        errors.append(f"commit缺失: chapter_{ch:03d}.commit.json")
    else:
        commit = json.loads(commit_file.read_text("utf-8"))
        proj = commit.get("projection_status", {})
        for name in ("state", "index", "summary", "memory", "vector"):
            status = proj.get(name, "missing")
            if status not in ("done", "skipped"):
                errors.append(f"projection {name}={status}")

    if errors:
        print("FAIL: " + "; ".join(errors))
        return 1
    print("OK")
    return 0
```

Add subparser in `main()` (before `p_cm`):

```python
    p_vcf = sub.add_parser("verify-chapter-files")
    p_vcf.add_argument("--project-root", required=True)
    p_vcf.add_argument("--chapter", type=int, required=True)
    p_vcf.set_defaults(func=cmd_verify_chapter_files)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py::test_verify_chapter_files_ok .opencode/scripts/data_modules/tests/test_skill_runner.py::test_verify_chapter_files_missing_chapter -q --no-cov`
Expected: both PASS

- [ ] **Step 5: Update skill docs to use verify-chapter-files**

In both SKILL.md files, replace the 4 individual post-write validation checks (Step 8 写后校验) with:

```bash
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" verify-chapter-files \
  --project-root "${PROJECT_ROOT}" --chapter {N} \
  || { echo "❌ 写后校验失败"; exit 1; }
```

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/skill_runner.py .opencode/scripts/data_modules/tests/test_skill_runner.py .opencode/skills/webnovel-write/SKILL.md .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat: add verify-chapter-files action to skill_runner

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task B3: Chinese path verification principle

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: Add principle to hard rules**

In `.opencode/skills/webnovel-write/SKILL.md`, after the "硬规则" section, add:

```markdown
- 所有文件存在性验证必须用 Python（`python -c "..."` 或 skill_runner），不得用 PowerShell 原生命令。中文路径在 PowerShell `Test-Path` 和 Python `os.path.isfile` 之间编码不一致。
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "docs: add Chinese path verification principle to skill

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task C1: Strengthen agent post-call file verification in single-chapter skill

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: Add verification after each Agent call**

In `.opencode/skills/webnovel-write/SKILL.md`, after each `Agent()` call, add the following pattern:

After context-agent (Step 1):
```bash
# 写作任务书已由 Agent 输出，校验非空
```

After chapter writing (Step 2):
```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter {N})
test -s "${PROJECT_ROOT}/${CHAPTER_PATH}" || { echo "❌ 章节文件未生成或为空"; exit 1; }
```

After reviewer (Step 3):
```bash
test -s "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" || { echo "❌ 审查结果未生成"; exit 1; }
```

After data-agent (Step 5.1):
```bash
for f in fulfillment_result.json disambiguation_result.json extraction_result.json; do
  test -s "${PROJECT_ROOT}/.webnovel/tmp/${f}" || { echo "❌ ${f} 缺失"; exit 1; }
done
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "fix: add mandatory file verification after each agent call

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task D1: placeholder-scan known placeholders ignore list

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py` (placeholder-scan registration)
- Create/modify: placeholder-scan logic in `.opencode/scripts/data_modules/`
- Test: `.opencode/scripts/data_modules/tests/test_placeholder_scan.py`

- [ ] **Step 1: Write test for placeholder ignore list**

```python
def test_placeholder_scan_respects_ignore_file(tmp_path):
    """已知占位符在 ignore 列表中时应被过滤"""
    # Setup
    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir()
    known = {
        "ignored": [
            {"file": "设定集/反派.md", "line": 4, "text": "（暂名）", "reason": "命名讨论中"},
        ]
    }
    (webnovel / "known_placeholders.json").write_text(
        json.dumps(known, ensure_ascii=False), encoding="utf-8"
    )

    src_dir = tmp_path / "设定集"
    src_dir.mkdir(parents=True)
    (src_dir / "反派.md").write_text("这是一个（暂名）角色\n", encoding="utf-8")

    # Run placeholder-scan
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-X", "utf8",
         str(Path(__file__).resolve().parents[2] / "webnovel.py"),
         "--project-root", str(tmp_path), "placeholder-scan", "--format", "json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    # Should be empty because the only placeholder is in ignore list
    assert len(data.get("placeholders", data if isinstance(data, list) else [])) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_placeholder_scan.py::test_placeholder_scan_respects_ignore_file -q --no-cov`
Expected: FAIL

- [ ] **Step 3: Implement ignore list logic**

Find the placeholder-scan implementation module. Add `--ignore-file` parameter support:

```python
def load_known_placeholders(project_root: Path) -> set:
    """Load known (ignorable) placeholder entries."""
    ignore_file = project_root / ".webnovel" / "known_placeholders.json"
    if not ignore_file.is_file():
        return set()
    try:
        data = json.loads(ignore_file.read_text(encoding="utf-8"))
        ignored = data.get("ignored", [])
        return {(e["file"], e.get("line", 0), e["text"]) for e in ignored}
    except (json.JSONDecodeError, OSError):
        return set()
```

In the scan output, filter results that match the ignore set by (file, line, text) tuple.

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_placeholder_scan.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/ .opencode/scripts/data_modules/tests/test_placeholder_scan.py
git commit -m "feat: add known_placeholders.json ignore list for placeholder-scan

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task E1: Batch progress visualization

**Files:**
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Add step-name mapping and progress print**

In `.opencode/skills/webnovel-write-batch/SKILL.md`, add before the per-chapter loop:

```markdown
**Step name mapping:**
0=环境变量验证, A=上章完整性, 1=刷新合同, 1b=结构自检, 2=context-agent, 3=写作, 4=审查, 5=review-pipeline, 6=修复轮, 7=data-agent, 8=commit+验证, 9=更新状态
```

At the start of each step in the per-chapter loop, add:

```bash
echo "[Ch{N} Step {M}/9] {step_name}..."
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat: add step-level progress visualization to batch writing

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task E2: pause-batch action for safe interrupt

**Files:**
- Modify: `.opencode/scripts/skill_runner.py:187-189`
- Test: `.opencode/scripts/data_modules/tests/test_skill_runner.py`

- [ ] **Step 1: Write test for pause-batch**

```python
def test_pause_batch_running_to_paused(tmp_path):
    """运行中的 batch 应被暂停"""
    _ensure_scripts_on_path()
    from skill_runner import cmd_pause_batch
    import argparse

    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir()
    state = {"status": "running", "current_chapter": 5, "completed_chapters": [3, 4]}
    (webnovel / "batch_state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )

    ns = argparse.Namespace(project_root=str(tmp_path))
    rc = cmd_pause_batch(ns)
    assert rc == 0

    # Verify state changed
    updated = json.loads((webnovel / "batch_state.json").read_text("utf-8"))
    assert updated["status"] == "paused"


def test_pause_batch_no_file(tmp_path):
    """batch_state 不存在时应返回 NO_BATCH"""
    _ensure_scripts_on_path()
    from skill_runner import cmd_pause_batch
    import argparse

    ns = argparse.Namespace(project_root=str(tmp_path))
    rc = cmd_pause_batch(ns)
    assert rc == 0  # Not an error, just nothing to pause
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py::test_pause_batch_running_to_paused .opencode/scripts/data_modules/tests/test_skill_runner.py::test_pause_batch_no_file -q --no-cov`
Expected: FAIL (cmd_pause_batch not defined)

- [ ] **Step 3: Implement cmd_pause_batch**

Add function before `cmd_compact_memory` (after line 113):

```python
def cmd_pause_batch(args: argparse.Namespace) -> int:
    state_path = Path(args.project_root) / ".webnovel" / "batch_state.json"
    if not state_path.is_file():
        print("NO_BATCH")
        return 0
    s = json.loads(state_path.read_text("utf-8"))
    prev = s.get("status", "")
    if prev == "running":
        s["status"] = "paused"
        state_path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PAUSED at chapter={s.get('current_chapter', '?')}")
    elif prev == "paused":
        print("ALREADY PAUSED")
    else:
        print(f"status={prev}, no action taken")
    return 0
```

Add subparser in `main()` (before `p_cm`):

```python
    p_pb = sub.add_parser("pause-batch")
    p_pb.add_argument("--project-root", required=True)
    p_pb.set_defaults(func=cmd_pause_batch)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py::test_pause_batch_running_to_paused .opencode/scripts/data_modules/tests/test_skill_runner.py::test_pause_batch_no_file -q --no-cov`
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/skill_runner.py .opencode/scripts/data_modules/tests/test_skill_runner.py
git commit -m "feat: add pause-batch action for safe batch interruption

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task E3: preflight story_runtime display_text

**Files:**
- Modify: `.opencode/scripts/data_modules/story_runtime_health.py:66-86`
- Modify: `.opencode/scripts/data_modules/webnovel.py:231-238`

- [ ] **Step 1: Add display_text to build_story_runtime_health**

In `story_runtime_health.py`, add after line 85 (`"primary_write_source": ...`):

```python
    volume_num = max(1, (current_chapter - 1) // 20 + 1)
    status_text = (latest_commit.get("meta") or {}).get("status", "missing")
    result["display_text"] = (
        f"主合同链: 第{current_chapter}章 "
        f"(MASTER_SETTING -> volume_{volume_num:03d} -> chapter_{current_chapter:03d}), "
        f"提交: {status_text}"
    )
```

- [ ] **Step 2: Update cmd_preflight to use display_text**

In `webnovel.py`, change lines 232-238 from:

```python
        story_runtime = report.get("story_runtime") or {}
        if story_runtime:
            print(
                "INFO story_runtime: "
                f"chapter={story_runtime.get('chapter')} "
                f"mainline_ready={story_runtime.get('mainline_ready')} "
                f"latest_commit_status={story_runtime.get('latest_commit_status')}"
            )
```

To:

```python
        story_runtime = report.get("story_runtime") or {}
        if story_runtime:
            display = story_runtime.get("display_text") or (
                f"chapter={story_runtime.get('chapter')} "
                f"mainline_ready={story_runtime.get('mainline_ready')} "
                f"latest_commit_status={story_runtime.get('latest_commit_status')}"
            )
            print(f"INFO story_runtime: {display}")
```

- [ ] **Step 3: Verify preflight output**

Run: `python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" preflight`
Expected: `INFO story_runtime: 主合同链: 第28章 (MASTER_SETTING -> volume_001 -> chapter_028), 提交: accepted`

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/story_runtime_health.py .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: add human-readable display_text to preflight story_runtime

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task E4: Close aiohttp session after chapter commit

**Files:**
- Modify: `.opencode/scripts/chapter_commit.py:43-45`

- [ ] **Step 1: Add aiohttp session close**

In `chapter_commit.py`, after line 44 (`payload = service.apply_projections(payload)`), add:

```python
    # Close aiohttp sessions opened by projection writers (e.g. embedding API)
    try:
        from data_modules.api_client import get_client
        get_client().close()
    except Exception:
        pass  # best-effort cleanup, OS reclaims sockets on process exit
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from data_modules.api_client import get_client; print('import OK')"`
Expected: `import OK`

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/chapter_commit.py
git commit -m "fix: close aiohttp session after chapter commit projections

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task E5: CLI --mode parameter

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: Add --mode argument to skill-related subcommands**

In `webnovel.py`, identify the argument parser for the skill execution path and add:

```python
parser.add_argument("--mode", choices=["default", "fast", "minimal"], default="default",
                    help="写作模式 (暂未调度)")
```

Note: mode does not change behavior yet — it exists for future scheduling logic. The parameter is accepted and stored, with no-op behavior.

- [ ] **Step 2: Verify CLI accepts the parameter**

Run: `python -X utf8 ".opencode/scripts/webnovel.py" --help 2>&1 | head -30`
Expected: help output includes `--mode` somewhere

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: add --mode CLI parameter (fast/minimal no-op stub)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task Execution Order

Dependencies between tasks:

```
A1 ──→ A2 ──→ A3 ──→ A4  (pipeline integrity chain)
                           ↓
B1 ──→ B2 ──→ B3           (Windows compat, depends on A4 for skill doc layout awareness)
                           ↓
C1                          (agent reliability, edits same files as A4/B2)
                           ↓
D1                          (independent)
                           ↓
E1 ──→ E2 ──→ E3 ──→ E4 ──→ E5  (experience polish, mostly independent)
```

Execute tasks in order: A1, A2, A3, A4, B1, B2, B3, C1, D1, E1, E2, E3, E4, E5.

---

## Verification Checklist

After all tasks:

```bash
# Full test suite
python -m pytest .opencode/scripts/data_modules/tests/ -q --no-cov

# Verify on real project
python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" preflight
python -X utf8 ".opencode/scripts/skill_runner.py" check-structural --project-root "D:\workspace\凡尘之舞\凡尘之舞" --chapter 29 --format json
python -X utf8 ".opencode/scripts/skill_runner.py" verify-chapter-files --project-root "D:\workspace\凡尘之舞\凡尘之舞" --chapter 28
```
