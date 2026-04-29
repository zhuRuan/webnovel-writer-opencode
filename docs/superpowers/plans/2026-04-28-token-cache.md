# Token Tracking + Cache Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cache hit rate monitoring and estimated token tracking to ContextManager, expose via observability.

**Architecture:** Two tasks. Task 1 modifies `context_manager.py` to add counters and methods. Task 2 extends `observability_cli.py` with `token-report` command.

**Tech Stack:** Python 3.10+

---

### Task 1: Add cache stats and token tracking to ContextManager

**Files:**
- Modify: `.opencode/scripts/data_modules/context_manager.py`

- [ ] **Step 1: Add instance variables in __init__**

Find `self._memory_cache_enabled = getattr(...)` (around line 90). After it, add:
```python
        self._cache_hits = 0
        self._cache_misses = 0
        self._token_usage: Dict[int, int] = {}
```

- [ ] **Step 2: Add hit tracking in _get_from_memory_cache**

Find `_get_from_memory_cache` method. After the `return self._memory_cache.get(key)` line, the method returns `None` or the cached value. The hit/miss logic needs to be in `build_context` where the method is called. In `build_context`, find the line `mem_cached = self._get_from_memory_cache(chapter, template)` (around line 146). After the `if mem_cached:` block that returns early, add increment:

```python
        mem_cached = self._get_from_memory_cache(chapter, template)
        if mem_cached:
            self._cache_hits += 1  # ADD THIS LINE
            # ... existing early return code ...
        self._cache_misses += 1  # ADD THIS LINE (after the if block, before snapshot check)
```

- [ ] **Step 3: Add get_cache_stats method**

After `_set_to_memory_cache`, add:
```python
    def get_cache_stats(self) -> Dict[str, Any]:
        """Return cache hit/miss stats."""
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": round(self._cache_hits / total, 3) if total > 0 else 0.0,
        }
```

- [ ] **Step 4: Add token estimation and get_token_usage**

After `get_cache_stats`, add:
```python
    def get_token_usage(self, last_n: int = 20) -> Dict[str, Any]:
        """Return recent token usage stats."""
        items = sorted(self._token_usage.items(), reverse=True)[:last_n]
        if not items:
            return {"chapters": {}, "total_tokens": 0, "avg_tokens": 0}
        tokens = [t for _, t in items]
        return {
            "chapters": {ch: t for ch, t in items},
            "total_tokens": sum(tokens),
            "avg_tokens": int(sum(tokens) / len(tokens)),
        }
```

- [ ] **Step 5: Update build_context to record token usage and cache stats**

Find the `safe_append_perf_timing` call at the end of `build_context` (around line 204). Update its `meta` dict to include cache stats and token estimate:

```python
                    meta={
                        "snapshot_hit": snapshot_hit,
                        "snapshot_load_ms": int(snapshot_load_time * 1000),
                        "pack_ms": int(pack_time * 1000),
                        "rank_ms": int(rank_time * 1000),
                        "assemble_ms": int(assemble_time * 1000),
                        "context_size": context_size,
                        "chapter": chapter,
                        "template": template,
                        "cache_stats": self.get_cache_stats(),
                        "estimated_tokens": int(context_size * 0.75),
                    },
```

Also, after saving snapshot (around line 199), add token tracking:
```python
            self._token_usage[chapter] = int(context_size * 0.75)
```

- [ ] **Step 6: Verify**

```bash
python -c "import sys; sys.path.insert(0, '.opencode/scripts'); from data_modules.context_manager import ContextManager; print('OK')"
python -m pytest .opencode/scripts/data_modules/tests/test_context_manager.py -v 2>&1 | Select-Object -Last 10
```

Expected: OK, all context_manager tests pass.

- [ ] **Step 7: Commit**

```bash
git add .opencode/scripts/data_modules/context_manager.py
git commit -m "feat: add cache hit rate stats and token estimation to ContextManager"
```

---

### Task 2: Add token-report to observability_cli.py

**Files:**
- Modify: `.opencode/scripts/data_modules/observability_cli.py`

- [ ] **Step 1: Add cmd_token_report function**

After `cmd_report`, add:
```python
def cmd_token_report(args: argparse.Namespace) -> int:
    """Show per-chapter token consumption."""
    from pathlib import Path
    try:
        config = get_config(Path(args.project_root) if args.project_root else None)
        project_root = str(config.project_root)
    except Exception:
        print("无项目目录，无法读取观测数据。")
        return 1

    timings = read_perf_timings(
        project_root,
        tool_name="context_manager.build_context",
        limit=args.last,
    )

    if not timings:
        print("无上下文构建记录。")
        return 0

    chapters: dict[int, int] = {}
    for t in timings:
        meta = t.get("meta", {})
        ch = meta.get("chapter")
        tokens = meta.get("estimated_tokens")
        if ch is not None and tokens is not None:
            if ch not in chapters:
                chapters[ch] = tokens

    if not chapters:
        print("无 Token 估算数据（需要更新后的 ContextManager 生成的数据）。")
        return 0

    if args.format == "json":
        import json as _json
        print(_json.dumps(chapters, ensure_ascii=False, indent=2))
    else:
        print(f"Token 消耗（最近 {len(chapters)} 章）:\n")
        total = 0
        for ch in sorted(chapters.keys()):
            t = chapters[ch]
            total += t
            print(f"  第{ch:>4d}章  {t:>6d} tokens")
        print(f"\n  总计: {total} tokens  平均: {total // len(chapters)} tokens/章")

    return 0
```

- [ ] **Step 2: Add token-report sub-command to main()**

In the `main()` function, after the `p_report` block, add:
```python
    p_token = sub.add_parser("token-report", help="查看 Token 消耗报告")
    p_token.add_argument("--last", "-n", type=int, default=1000, help="最近 N 条记录")
    p_token.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_token.set_defaults(func=cmd_token_report)
```

- [ ] **Step 3: Verify**

```bash
python .opencode/scripts/webnovel.py observability token-report
```

Expected: prints "无上下文构建记录。" or shows token data.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/observability_cli.py
git commit -m "feat: add token-report command to observability CLI"
```

---

### Final Verification

- [ ] **Run full suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 493 passed, 12 failed (unchanged).
