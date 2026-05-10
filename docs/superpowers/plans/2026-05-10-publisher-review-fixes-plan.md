# Publisher + Review + Structural Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 16 bugs across publisher (A), review scoring (B), structural checker design (C), and data integrity (D).

**Architecture:** Surgical edits to 8 existing files. Publisher fixes are browser-based (no pytest — manual verification). Review and structural fixes have existing test suites. Tasks ordered by dependency: A (publisher) → B (review) → C (structural) → D (data integrity).

**Tech Stack:** Python 3.14, pytest, Playwright (browser), asyncio

**Pre-existing context from spec code baseline:**
- `fanqie.py:231-233`: create_book() already has `aid` + `app_name` in form body
- `fanqie.py:183-187`: _ensure_writer_context() only checks `about:blank`
- `fanqie.py:80-81`: _page_fetch empty response error missing status code
- `review_pipeline.py`: clean_reviewer_output() exists, `other` dimension taints overall_score
- `structural_checker.py`: run_checks() has no intended_strand parameter
- `skill_runner.py`: cmd_check_structural() has no --intended-strand arg

---

### Task A1-A3: Publisher quick fixes (aid/app_name, domain check, status code)

**Files:**
- Modify: `.opencode/scripts/publisher/adapters/fanqie.py`

Three independent one-line fixes in the same file:

**A1**: Add `_COMMON_FORM` constant after `_COMMON_PARAMS` (line 21):
```python
_COMMON_FORM = {"aid": "2503", "app_name": "muye_novel"}
```

In `upload_chapter()` (line 314-321 new_article form), add `**_COMMON_FORM` to the dict:
```python
        create_data = await _page_fetch(page, "POST",
            "/api/author/article/new_article/v0/", form={
                **_COMMON_FORM,
                "book_id": book_id,
                "title": full_title,
                "content": html_content,
                "volume_id": volume_id,
                "volume_name": volume_name,
            })
```

Same for cover_article form (line 331-339). And in `create_book()` (line 231), replace literal `"aid": "2503", "app_name": "muye_novel"` with `**_COMMON_FORM`.

**A2**: In `_ensure_writer_context()` (line 183-187), change:
```python
    if page.url == "about:blank":
        await page.goto(self.login_url, wait_until="commit", timeout=30_000)
```
To:
```python
    if page.url == "about:blank" or "fanqienovel.com" not in page.url:
        await page.goto(self.login_url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(3)
```
Note: `import asyncio` must exist at file top (check if already imported).

**A3**: In `_page_fetch()` (line 80-81), change:
```python
    if not raw:
        raise RuntimeError(f"API {path} returned empty response")
```
To:
```python
    if not raw:
        status = result.get("status", "?")
        raise RuntimeError(f"API {path} returned empty response (status={status})")
```

- [ ] **Step 1: Read fanqie.py to verify exact line positions**
- [ ] **Step 2: Apply A1 — add _COMMON_FORM and use in 3 places**
- [ ] **Step 3: Apply A2 — domain check + networkidle + sleep**
- [ ] **Step 4: Apply A3 — status code in error message**
- [ ] **Step 5: Verify: `python -c "from publisher.adapters.fanqie import FanqieAdapter; print('import OK')"`**
- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/publisher/adapters/fanqie.py
git commit -m "fix: add aid/app_name to upload POST, domain check, status code in errors

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task A4: upload_log book_id cross-contamination prevention

**Files:**
- Modify: `.opencode/scripts/publisher/config.py:42-48`
- Modify: `.opencode/scripts/publisher/__init__.py:90-115`

- [ ] **Step 1: Add book_id/book_name to save_upload_log**

In `config.py`, change `save_upload_log()` signature and payload:

```python
def save_upload_log(platform: str, book_id: str, uploaded: set[int], book_name: str = ""):
    p = _log_path(platform, book_id)
    payload = {
        "book_id": book_id,
        "book_name": book_name,
        "uploaded": sorted(uploaded),
        "last_upload": datetime.now(timezone.utc).isoformat(),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

Note: `load_upload_log()` unchanged — it reads `uploaded` field only, backward compatible.

- [ ] **Step 2: Add cross-contamination check in _cmd_upload**

In `__init__.py` _cmd_upload(), after `uploaded = load_upload_log(...)` and after `_log_path` is available (add import: `from publisher.config import _log_path`), insert:

```python
    # 交叉校验：防止 book_id 误用
    log_path = _log_path(args.platform, args.book_id)
    if log_path.is_file():
        try:
            log_data = json.loads(log_path.read_text(encoding="utf-8"))
            logged_book_id = log_data.get("book_id", "")
            if logged_book_id and logged_book_id != args.book_id:
                logged_name = log_data.get("book_name", "未知")
                print(f"⚠️ 警告: 上传日志中的 book_id ({logged_book_id}, {logged_name}) 与当前 book_id ({args.book_id}) 不一致！")
                print("可能原因: 误用了另一本书的 book_id。")
                resp = input("确认继续上传？(y/N): ")
                if resp.lower() != "y":
                    print("已取消。")
                    return
        except (json.JSONDecodeError, KeyError):
            pass  # old format without book_id field, skip check
```

- [ ] **Step 3: Update callers of save_upload_log**

Search for existing `save_upload_log(` calls (likely in `__init__.py` and `fanqie.py`). If any exist, add `book_name` parameter. If no calls pass book_name, the default `""` works.

- [ ] **Step 4: Verify import chain: `python -c "from publisher.config import save_upload_log, _log_path; print('OK')"`**
- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/publisher/config.py .opencode/scripts/publisher/__init__.py
git commit -m "fix: embed book_id in upload_log + cross-contamination check

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task A5-A8: POST retry + mode hint + warmup

**Files:**
- Modify: `.opencode/scripts/publisher/adapters/fanqie.py`

Combine retry (A5), backoff (A7), warmup (A8), and mode hint (A6) into one change.

- [ ] **Step 1: Add _post_with_retry helper method to FanqieAdapter**

Insert before `upload_chapter()`:

```python
    async def _post_with_retry(self, page, path, form, max_retries=2):
        """POST with retry on empty response. Refreshes writer context between attempts."""
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                result = await _page_fetch(page, "POST", path, form=form)
                return result
            except RuntimeError as e:
                last_exc = e
                if attempt < max_retries:
                    delay = 2 ** attempt  # 1s, 2s exponential backoff
                    await asyncio.sleep(delay)
                    await self._ensure_writer_context(page)
        raise last_exc
```

- [ ] **Step 2: Add warmup in upload_chapter**

At the start of `upload_chapter()`, after `_ensure_writer_context()`, insert:

```python
        # 预热：验证登录态
        await page.goto(f"https://writer.fanqienovel.com?aid=2503&app_name=muye_novel",
                        wait_until="networkidle", timeout=30_000)
        if "fanqienovel.com" not in page.url:
            raise RuntimeError("登录态失效: 未跳转到 writer 域名，请重新 setup-auth")
```

- [ ] **Step 3: Replace _page_fetch with _post_with_retry in upload_chapter**

In `upload_chapter()`, change both `_page_fetch(page, "POST", ...)` calls to `await self._post_with_retry(page, ...)`.

- [ ] **Step 4: Add publish mode warning**

At the end of `upload_chapter()`, before return:

```python
        if self._mode == "publish":
            print("  ⚠️ 注意: 当前仅支持草稿保存，章节未正式发布。发布请前往番茄作者后台手动操作。")
```

Note: `self._mode` needs to be set in `FanqieAdapter.__init__()`. Check existing __init__ and add `self._mode = "draft"` if not present. Update `_cmd_upload()` in `__init__.py` to call `adapter.set_mode(cfg.mode)` or pass mode at init.

- [ ] **Step 5: Verify import: `python -c "from publisher.adapters.fanqie import FanqieAdapter; print('OK')"`**
- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/publisher/adapters/fanqie.py .opencode/scripts/publisher/__init__.py
git commit -m "feat: add POST retry with backoff, warmup check, publish mode hint

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task B1: Chinese quotes breaking JSON

**Files:**
- Modify: `.opencode/scripts/review_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `.opencode/scripts/data_modules/tests/test_review_pipeline.py` (create if not exists, or use existing test file):

```python
def test_clean_reviewer_output_handles_chinese_quotes():
    from review_pipeline import clean_reviewer_output
    raw = '{"description": "陈升回答能量剩余"二十二"次"}'
    result = clean_reviewer_output(raw)
    assert isinstance(result, dict)
    assert "二十二" in result.get("description", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_review_pipeline.py::test_clean_reviewer_output_handles_chinese_quotes -q --no-cov`
Expected: FAIL with JSONDecodeError

- [ ] **Step 3: Implement sanitization in clean_reviewer_output**

In `review_pipeline.py`, enhance `clean_reviewer_output()` — after existing markdown extraction and before final `json.loads()`, add a fallback pass:

```python
def _sanitize_json_text(raw: str) -> str:
    """Replace bare ASCII double quotes inside CJK text with Chinese quotes."""
    # Match internal quotes that appear between CJK characters
    sanitized = re.sub(
        r'(?<=["一-鿿　-〿＀-￯])"'
        r'(?=[一-鿿　-〿＀-￯])',
        r'「',  # 「
        raw
    )
    return sanitized
```

In `clean_reviewer_output()`, wrap the final `json.loads()`:

```python
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            sanitized = _sanitize_json_text(raw)
            return json.loads(sanitized)
        except json.JSONDecodeError as e:
            preview = raw[:500] + "..." if len(raw) > 500 else raw
            raise ValueError(f"JSON解析失败，raw前500字符: {preview}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_review_pipeline.py::test_clean_reviewer_output_handles_chinese_quotes -q --no-cov`
Expected: PASS

- [ ] **Step 5: Run ALL existing review_pipeline tests**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_review_pipeline.py -q --no-cov`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/review_pipeline.py .opencode/scripts/data_modules/tests/test_review_pipeline.py
git commit -m "fix: handle Chinese quotes in reviewer JSON output

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task B2-B4: overall_score exclude system dimensions + top-level score + debug output

**Files:**
- Modify: `.opencode/scripts/review_pipeline.py`

Three related changes in the same file.

- [ ] **Step 1: Add dimension classification and scoring logic**

Add module-level constants (after imports):

```python
CONTENT_DIMENSIONS = {"continuity", "setting", "character", "timeline", "ai_flavor", "logic", "pacing"}
SYSTEM_DIMENSIONS = {"other"}
```

Find the overall_score calculation (search for `overall_score` in the review pipeline). Change from equal-weight average to content-only average:

```python
content_scores = {d: s for d, s in dimension_scores.items() if d in CONTENT_DIMENSIONS}
overall_score = round(sum(content_scores.values()) / len(content_scores)) if content_scores else 0

system_health = {d: dimension_scores.get(d, 0) for d in SYSTEM_DIMENSIONS}
```

- [ ] **Step 2: Add top-level score to output**

In the result JSON assembly, add `score` as alias for `overall_score`:

```python
result = {
    "score": overall_score,
    "overall_score": overall_score,
    "system_health": system_health,
    ...
}
```

- [ ] **Step 3: Verify on existing review data**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/ -q --no-cov -k "review"`
Check that no existing tests break.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/review_pipeline.py
git commit -m "fix: exclude system dimensions from overall_score, add top-level score field

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task C1: strand_balance intent awareness

**Files:**
- Modify: `.opencode/scripts/data_modules/structural_checker.py`
- Modify: `.opencode/scripts/skill_runner.py`
- Modify: `.opencode/skills/webnovel-write/SKILL.md`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Add intended_strand to run_checks and _check_strand_balance**

In `structural_checker.py`, change `run_checks()` signature:

```python
def run_checks(project_root: Path, chapter: int, intended_strand: str = "") -> dict:
```

Pass `intended_strand` to `_check_strand_balance`:

```python
checks.append(_check_strand_balance(state, chapter, intended_strand))
```

In `_check_strand_balance()`, add intended_strand parameter and logic before the constellation check:

```python
def _check_strand_balance(state: dict, chapter: int, intended_strand: str = "") -> dict:
    ...
    # If intended_strand matches the missing strand, this chapter is fixing it
    last_const = _safe_int(tracker.get("last_constellation_chapter"))
    if intended_strand == "constellation" and (last_const == 0 or chapter - last_const > 8):
        result["passed"] = True
        result["detail"] = f"本章已设定为 constellation 线，正在修复中（上次: {'从未激活' if last_const == 0 else f'第{last_const}章'}）"
        result["fix"] = ""
        return result
```

Same pattern for fire strand. The quest consecutive check has lower priority (quest consecutive > 5 but intended_strand fixes it).

- [ ] **Step 2: Add --intended-strand to skill_runner**

In `skill_runner.py`, `cmd_check_structural()`:

```python
    result = run_checks(root, args.chapter, intended_strand=args.intended_strand or "")
```

Add argument to subparser:

```python
    p_cs.add_argument("--intended-strand", choices=["quest", "fire", "constellation"], default=None)
```

- [ ] **Step 3: Update SKILL.md files to extract and pass intended_strand**

In both SKILL.md files, Step 1b, add before the check-structural call:

```bash
# 从章纲提取 intended_strand
INTENDED_STRAND=$(python -c "
import json
contract = '${PROJECT_ROOT}/.story-system/chapters/chapter_$(printf '%03d' $N).json'
try:
    d = json.load(open(contract))
    print(d.get('chapter_directive', {}).get('strand', ''))
except: pass
")
```

Then update the check-structural call to include `--intended-strand "${INTENDED_STRAND}"`.

- [ ] **Step 4: Run structural checker tests**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_structural_checker.py -q --no-cov`
Expected: all pass (new parameter defaults to `""`, backward compatible)

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/structural_checker.py .opencode/scripts/skill_runner.py .opencode/skills/webnovel-write/SKILL.md .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat: add intended_strand parameter to structural checker

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task C2: entity_freshness value-based check

**Files:**
- Modify: `.opencode/scripts/data_modules/structural_checker.py`

- [ ] **Step 1: Modify _check_entity_freshness**

Change gap threshold from 5 back to effectively add a value-change detection. The simplest approach that works:

```python
def _check_entity_freshness(state: dict, chapter: int) -> dict:
    ...
    gap = chapter - last_chapter
    if gap >= 5:
        current_value = (location.get("current") or "").strip()
        if current_value:
            # location.current has a value — data-agent IS writing location.
            # The last_chapter field may be stale but the value is maintained.
            # Downgrade to warning.
            result["severity"] = "warning"
            result["passed"] = True
            result["detail"] = f"主角位置 last_chapter 字段 {gap} 章未更新（最后: 第{last_chapter}章），但 location.current 值存在"
            result["fix"] = "data-agent 需确保写入 location.current 时同步更新 last_chapter"
            return result
        result["passed"] = False
        result["detail"] = f"主角位置 {gap} 章未更新（最后: 第{last_chapter}章）"
        result["fix"] = "data-agent 需输出 location.current state_delta（即使位置未变）"
    return result
```

- [ ] **Step 2: Run existing tests**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_structural_checker.py -q --no-cov`
Expected: all pass (the existing test with gap=6 and no current_value should still fail; gap=2 test should still pass)

- [ ] **Step 3: Update test_entity_freshness_stale to test the downgrade path**

Add a test for the case where location.current exists but last_chapter is stale:

```python
def test_entity_freshness_stale_but_value_present():
    """位置值存在但 last_chapter 陈旧应降级为 warning"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "protagonist_state": {
                "location": {"current": "城西废墟", "last_chapter": 16},
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "entity_freshness")
        assert check["passed"] is True
        assert check["severity"] == "warning"
```

- [ ] **Step 4: Run all tests**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_structural_checker.py -q --no-cov`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/structural_checker.py .opencode/scripts/data_modules/tests/test_structural_checker.py
git commit -m "fix: entity_freshness downgrades to warning when location value exists

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task D1: batch_state.json UTF-8 BOM resilience

**Files:**
- Modify: `.opencode/scripts/skill_runner.py`
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: Change skill_runner.py read_text to utf-8-sig**

In `cmd_pause_batch()` and `cmd_check_batch_integrity()` (lines 134-147), change all `state_path.read_text("utf-8")` to `state_path.read_text("utf-8-sig")`.

- [ ] **Step 2: Update SKILL.md python -c writes to include encoding**

In Step 0.6 and Step 9 of batch SKILL.md, find all `open('$BATCH_STATE', 'w')` calls and change to `open('$BATCH_STATE', 'w', encoding='utf-8')`.

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/skill_runner.py .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "fix: handle UTF-8 BOM in batch_state.json reads, enforce encoding on writes

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task D2: chapter-path CLI subcommand

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: Write the test**

Add to `test_webnovel_unified_cli.py` or a new test:

```python
def test_chapter_path(tmp_path):
    import subprocess, sys
    root = tmp_path
    text_dir = root / "正文"
    text_dir.mkdir(parents=True)
    (text_dir / "第0028章-测试.md").write_text("test", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-X", "utf8",
         str(Path(__file__).resolve().parents[2] / "webnovel.py"),
         "--project-root", str(root),
         "chapter-path", "--chapter", "28"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "第0028章" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_webnovel_unified_cli.py::test_chapter_path -q --no-cov`
Expected: FAIL (invalid choice: 'chapter-path')

- [ ] **Step 3: Implement cmd_chapter_path and register**

Add function in webnovel.py:

```python
def cmd_chapter_path(args: argparse.Namespace) -> int:
    import re
    root = Path(args.project_root).expanduser().resolve()
    text_dir = root / "正文"
    if not text_dir.is_dir():
        print("ERROR: 正文目录不存在", file=sys.stderr)
        return 1

    pattern = re.compile(rf"第0*{args.chapter}章")
    for f in text_dir.rglob("*.md"):
        if pattern.search(f.name):
            print(str(f.relative_to(root)))
            return 0

    print(f"ERROR: 未找到第{args.chapter}章的章节文件", file=sys.stderr)
    return 1
```

Add subparser in `main()`:

```python
    p_chapter_path = sub.add_parser("chapter-path", help="查找章节文件相对路径")
    p_chapter_path.add_argument("--project-root", required=True)
    p_chapter_path.add_argument("--chapter", type=int, required=True)
    p_chapter_path.set_defaults(func=cmd_chapter_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .opencode/scripts && python -m pytest data_modules/tests/test_webnovel_unified_cli.py::test_chapter_path -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py .opencode/scripts/data_modules/tests/test_webnovel_unified_cli.py
git commit -m "feat: add chapter-path CLI subcommand

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task Execution Order

```
A1-A3 (quick fixes, 1 file) → A4 (cross-contam, 2 files) → A5-A8 (retry+warmup, 1-2 files)
    ↓ (publisher independent from rest)
B1 → B2-B4 (both touch review_pipeline.py)
    ↓
C1 → C2 (both touch structural_checker.py)
    ↓
D1 → D2 (independent of each other)
```

---

## Verification Checklist

After all tasks:

```bash
# Python import check
python -c "from publisher.adapters.fanqie import FanqieAdapter; print('Publisher OK')"

# Structural checker tests
cd .opencode/scripts && python -m pytest data_modules/tests/test_structural_checker.py -q --no-cov

# Review pipeline tests
cd .opencode/scripts && python -m pytest data_modules/tests/test_review_pipeline.py -q --no-cov

# CLI chapter-path
python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" chapter-path --chapter 28
```
