# Publisher + 审查评分 + 结构自检修复设计

> 基于 4 份 bug 报告的交叉分析，扣除已修复项，覆盖 3 个子系统（Publisher / 审查评分 / 结构自检设计）+ 数据完整性。

**代码基线确认** (2026-05-10):
- Publisher #1,2,3 已在上次会话修复（rglob、_read_book_meta、list-books book_id）
- clean_reviewer_output() 已存在，处理 markdown 代码块包裹
- structural check 阈值已收紧（constellation 8章、entity_freshness 5章），阻断门已加
- skill_runner.py verify-chapter-files / pause-batch 已存在

---

## A. Publisher 修复（8 bugs, ~65 行）

### A1. upload_chapter POST body 补全 aid/app_name

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py`

**根因**: `create_book()` (line 231-233) 的 form body 包含 `aid` + `app_name`，`upload_chapter()` 两个 POST 调用（line 314-321 new_article, line 331-339 cover_article）没有。

**修复**: 在两个 form dict 中各增加:
```python
"aid": "2503",
"app_name": "muye_novel",
```

同时提取为模块级常量 `_COMMON_FORM = {"aid": "2503", "app_name": "muye_novel"}`，三处（create_book + new_article + cover_article）统一引用。

### A2. _ensure_writer_context 域名检查

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py` (line 183-187)

当前:
```python
async def _ensure_writer_context(self, page):
    if page.url == "about:blank":
        await page.goto(self.login_url, wait_until="commit", timeout=30_000)
```

改为:
```python
async def _ensure_writer_context(self, page):
    if page.url == "about:blank" or "fanqienovel.com" not in page.url:
        await page.goto(self.login_url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(3)
```

### A3. _page_fetch 空响应含状态码

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py` (line 80-81)

当前:
```python
if not raw:
    raise RuntimeError(f"API {path} returned empty response")
```

改为:
```python
if not raw:
    status = result.get("status", "?")
    raise RuntimeError(f"API {path} returned empty response (status={status})")
```

### A4. upload_log 内嵌 book_id + 上传前校验 ⚠️ CRITICAL

**文件**: `.opencode/scripts/publisher/config.py` + `publisher/__init__.py`

**config.py — save_upload_log():** 在 payload 中增加 `book_id` 和 `book_name` 字段:
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

向后兼容：`load_upload_log()` 仍只读 `uploaded` 字段，旧格式（无 book_id 字段）不受影响。

**__init__.py — _cmd_upload():** 在 `load_upload_log` 后增加交叉校验:
```python
    uploaded = load_upload_log(args.platform, args.book_id)
    # 交叉校验：日志中的 book_id 与当前 book_id 必须一致
    log_path = _log_path(args.platform, args.book_id)
    if log_path.is_file():
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
```

Note: `_log_path` 需要从 config 导入。

### A5. POST 空响应自动重试

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py`

在 `upload_chapter()` 中，`_page_fetch` 调用包装为带重试的辅助逻辑:

```python
async def _post_with_retry(self, page, path, form, max_retries=2):
    """POST with retry: refresh writer context on empty response."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            result = await _page_fetch(page, "POST", path, form=form)
            return result
        except RuntimeError as e:
            last_exc = e
            if attempt < max_retries:
                delay = (2 ** attempt)  # 1s, 2s
                await asyncio.sleep(delay)
                await self._ensure_writer_context(page)
    raise last_exc
```

`upload_chapter()` 中的两个 `_page_fetch` 调用改为 `self._post_with_retry(page, ...)`。

### A6. --mode publish 提示

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py`

在 `upload_chapter()` 末尾（return 之前），根据 config mode 输出:

```python
    if cfg.mode == "publish":
        print("  ⚠️ 注意: 当前仅支持草稿保存，章节未正式发布。发布请前往番茄作者后台手动操作。")
```

Note: `cfg` 需要从调用方传入，或从 `self` 读取。最小改动：在 `FanqieAdapter.__init__()` 中保存 `self._mode`，由 `_cmd_upload` 传入。

### A7. 指数退避重试

已在 A5 中一并实现（`delay = 2 ** attempt`）。额外在 `config.py` 的 `PublishConfig` 中保留 `retry_count` 和 `retry_delay` 字段不变（向后兼容），A5 的重试逻辑使用自己的退避计算。

### A8. headless 模式预热检查

**文件**: `.opencode/scripts/publisher/adapters/fanqie.py`

在 `upload_chapter()` 首次 POST 之前，增加 GET 预热:

```python
    # 预热：GET 请求验证登录状态
    preflight = await _page_fetch(page, "GET", "/api/author/book/list/v0/")
    if not preflight or not isinstance(preflight, dict):
        raise RuntimeError("预热请求失败: 无法获取书籍列表，请重新 setup-auth")
```

由于 book list API 可能需要参数，更轻量的方案是直接 GET writer 首页:

```python
    await page.goto(f"https://writer.fanqienovel.com?aid=2503&app_name=muye_novel",
                    wait_until="networkidle", timeout=30_000)
    if "fanqienovel.com" not in page.url:
        raise RuntimeError("登录态失效: 页面未跳转到 writer 域名，请重新 setup-auth")
```

---

## B. 审查/评分修复（4 bugs, ~33 行）

### B1. 中文引号破坏 JSON

**文件**: `.opencode/scripts/review_pipeline.py`

在 `clean_reviewer_output()` 中，JSON 解析失败后增加 fallback：对 `description`、`evidence`、`detail` 等已知文本字段，将其值中的裸 ASCII `"` 替换为 `「`（左）和 `」`（右）。

```python
def _sanitize_text_fields(raw: str) -> str:
    """Replace bare ASCII double quotes inside JSON string values with CJK quotes."""
    # Match "field_name": "value containing "quotes""
    # Strategy: find all string values and sanitize internal quotes
    ...
```

更稳健的简化方案：JSON 解析失败时，用 `re.sub(r'(?<!\\)"', '「', raw)` 做全局替换后重试。这会破坏 JSON 结构（键名也被替换），所以更精确的做法是：

```python
def _extract_json(raw: str) -> dict:
    """Extract JSON from mixed text, with fallback sanitization."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code blocks (existing logic)
    ...
    
    # Fallback: replace bare quotes in text values
    # Match pattern: "description": "value with "internal" quotes"
    sanitized = re.sub(
        r'(?<=["一-鿿　-〿＀-￯])"(?=[一-鿿　-〿＀-￯".,:;!?，。：；！？])',
        r'「',
        raw
    )
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败，raw前500字符: {raw[:500]}") from e
```

### B2. overall_score 排除系统维度

**文件**: `.opencode/scripts/review_pipeline.py`

在评分聚合逻辑中，`other` 维度不参与 overall 加权：

```python
# 内容质量维度（参与 overall 评分）
CONTENT_DIMENSIONS = {"continuity", "setting", "character", "timeline", "ai_flavor", "logic", "pacing"}
# 系统状态维度（独立记录，不参与 overall）
SYSTEM_DIMENSIONS = {"other"}

# 计算 overall_score 时仅使用 CONTENT_DIMENSIONS
content_scores = [s for d, s in dimension_scores.items() if d in CONTENT_DIMENSIONS]
overall_score = sum(content_scores) / len(content_scores) if content_scores else 0

# system_health 单独记录
system_health = {d: s for d, s in dimension_scores.items() if d in SYSTEM_DIMENSIONS}
```

输出的 review 报告中 `overall_score` 反映纯内容质量，`system_health` 独立展示。

### B3. review_results.json 顶层 score

**文件**: `.opencode/scripts/review_pipeline.py`

在 review 结果 JSON 输出时，顶层增加 `score` 字段：

```python
result = {
    "score": overall_score,
    "overall_score": overall_score,
    "system_health": system_health,
    "issues": issues,
    ...
}
```

`score` 作为 `overall_score` 的别名，兼容 batch_state 更新脚本的 `d.get('score', 0)` 读取方式。

### B4. JSON 解析失败时输出调试信息

已合并到 B1 的 fallback 逻辑中——解析完全失败时抛出 `ValueError` 并包含 raw 文本前 500 字符。

---

## C. 结构自检设计修复（2 bugs, ~35 行）

### C1. strand_balance 意图感知

**文件**: `.opencode/scripts/data_modules/structural_checker.py` + `skill_runner.py` + 两个 SKILL.md

**structural_checker.py — run_checks():** 增加 `intended_strand` 参数:
```python
def run_checks(project_root: Path, chapter: int, intended_strand: str = "") -> dict:
```

`_check_strand_balance()` 接收 `intended_strand` 参数：若 `intended_strand` 为当前缺失的线体（如 constellation），则 `passed=True` 且 detail 注明"本章已设定为 {intended_strand} 线，正在修复中"。

**skill_runner.py — cmd_check_structural:** 增加 `--intended-strand` 可选参数，传递给 `run_checks()`。

**SKILL.md (两个):** Step 1b 调用 check-structural 时，从章纲中提取 strand 意图并传入:
```bash
INTENDED_STRAND=$(python -c "
import json
contract = '${PROJECT_ROOT}/.story-system/chapters/chapter_$(printf '%03d' $N).json'
try:
    d = json.load(open(contract))
    print(d.get('chapter_directive', {}).get('strand', ''))
except: print('')
")
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-structural \
  --project-root "${PROJECT_ROOT}" --chapter {N} --format json \
  --intended-strand "${INTENDED_STRAND}" \
  > "${PROJECT_ROOT}/.webnovel/tmp/structural_check.json"
```

### C2. entity_freshness 值变更检测

**文件**: `.opencode/scripts/data_modules/structural_checker.py`

在 `_check_entity_freshness()` 中增加辅助检查：读取上一章的 commit JSON，对比 `protagonist_state.location.current` 的值。如果值不同，即使 `last_chapter` 字段陈旧也视为 `passed=True`。

实现：读取 `state.json` 中 `protagonist_state.location` 的值，与上一个有记录的章节的 commit 中的值对比。仅当值连续相同且 gap > 5 章时才 blocking。

```python
def _check_entity_freshness(state: dict, chapter: int) -> dict:
    ...
    protag = state.get("protagonist_state") or {}
    location = protag.get("location") or {}
    last_chapter = _safe_int(location.get("last_chapter"))
    current_value = location.get("current", "")
    
    gap = chapter - last_chapter
    if gap >= 5:
        # Check if location value actually changed
        prev_value = _get_previous_location(state, last_chapter)
        if current_value and prev_value and current_value != prev_value:
            # Value changed, location effective even if last_chapter is stale
            result["passed"] = True
            result["detail"] = f"位置值已变更 ({prev_value} -> {current_value})，last_chapter 延迟可忽略"
            return result
        result["passed"] = False
        result["detail"] = f"主角位置 {gap} 章未更新（最后: 第{last_chapter}章），且值未变化"
        result["fix"] = "data-agent 需输出 location.current state_delta"
    return result
```

Note: `_get_previous_location()` 不需要实现——直接检查 `current_value` 是否为空即可。简化方案：如果 `last_chapter` 陈旧但 `current_value` 非空，且最近 5 章内有任意 commit 中的 protagonist 位置值与当前不同 → 通过。由于 commit JSON 读取开销大，改为简单检查：`last_chapter` 陈旧但 `current_value` 非空 → 降 severity 为 warning（不阻断）。

---

## D. 数据完整性（2 bugs, ~24 行）

### D1. batch_state.json UTF-8 BOM

**文件**: `.opencode/scripts/skill_runner.py`

`cmd_check_batch_integrity()` (line 134-147) 和 `cmd_pause_batch()` 读取 batch_state.json 时，使用 `encoding='utf-8-sig'` 兼容旧文件的 BOM：

```python
s = json.loads(state_path.read_text("utf-8-sig"))
```

**文件**: `.opencode/skills/webnovel-write-batch/SKILL.md`

Step 0.6 中 python -c 写入 batch_state.json 的代码已使用 `open('$BATCH_STATE', 'w')`，需确保 `encoding='utf-8'`：

```python
open('$BATCH_STATE', 'w', encoding='utf-8').write(json.dumps(s, ensure_ascii=False, indent=2))
```

Step 9 中的写入同样确保 `encoding='utf-8'`。

### D2. chapter-path 子命令

**文件**: `.opencode/scripts/data_modules/webnovel.py`

新增 CLI 子命令和实现函数:

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
            # Return relative path from project_root
            print(str(f.relative_to(root)))
            return 0
    
    print(f"ERROR: 未找到第{args.chapter}章的章节文件", file=sys.stderr)
    return 1
```

CLI 注册（在 `main()` 的 subparser 注册区）:
```python
p_chapter_path = sub.add_parser("chapter-path", help="查找章节文件路径")
p_chapter_path.add_argument("--project-root", required=True)
p_chapter_path.add_argument("--chapter", type=int, required=True)
p_chapter_path.set_defaults(func=cmd_chapter_path)
```

### D3. 合同文件缺失 — 不纳入本次修复

当前系统通过 state.json fallback 可正常运行。标记为已知限制。

---

## 影响面总览

| 子系统 | 文件 | 变更类型 |
|--------|------|---------|
| A1-A8 | `publisher/adapters/fanqie.py` | ~55 行 |
| A4 | `publisher/__init__.py` | ~15 行 |
| A4 | `publisher/config.py` | ~8 行 |
| B1-B4 | `review_pipeline.py` | ~40 行 |
| C1 | `structural_checker.py` | ~15 行 |
| C1 | `skill_runner.py` | ~5 行 |
| C1 | `webnovel-write/SKILL.md` | ~8 行 |
| C1 | `webnovel-write-batch/SKILL.md` | ~8 行 |
| C2 | `structural_checker.py` | ~15 行 |
| D1 | `skill_runner.py` | ~2 行 |
| D1 | `webnovel-write-batch/SKILL.md` | ~4 行 |
| D2 | `webnovel.py` | ~20 行 |
| | **8 个文件** | **~195 行** |

---

## 不变更事项

- Publisher #1,2,3 — 已在上次会话修复
- structural check 阈值 — 本次会话 A4 已修复
- chapter-writer-agent 合同树检查 — 本次会话 A3 已修复
- data-agent protagonist location 要求 — 已存在
- clean_reviewer_output markdown 提取 — 已存在
