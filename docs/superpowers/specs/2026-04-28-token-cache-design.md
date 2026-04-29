# Token Tracking + Cache Optimization — Design Spec

Date: 2026-04-28  
Status: approved  
Scope: Add token tracking and cache hit rate monitoring to ContextManager, expose via observability  

## Overview

Two focused changes to ContextManager: (1) add cache hit/miss counters with `get_cache_stats()`, (2) add estimated token tracking with `get_token_usage()`. Both are exposed through the existing observability system.

## Change 1: Cache hit rate tracking

**File:** `.opencode/scripts/data_modules/context_manager.py`

Add instance variables in `__init__`:
```python
self._cache_hits = 0
self._cache_misses = 0
```

In `_get_from_memory_cache`: increment `_cache_hits` on hit.
In `build_context` after cache miss: increment `_cache_misses`.

Add method:
```python
def get_cache_stats(self) -> dict[str, Any]:
    total = self._cache_hits + self._cache_misses
    return {
        "hits": self._cache_hits,
        "misses": self._cache_misses,
        "hit_rate": round(self._cache_hits / total, 3) if total > 0 else 0.0,
    }
```

In `safe_append_perf_timing` calls within `build_context`, add `cache_stats` to `meta`:
```python
meta={"..., "cache_stats": self.get_cache_stats()}
```

## Change 2: Token estimation tracking

**File:** `.opencode/scripts/data_modules/context_manager.py`

Add instance variable:
```python
self._token_usage: dict[int, int] = {}  # chapter -> estimated_tokens
```

After `build_context` assembles context, estimate tokens:
```python
# Chinese: ~1.5 tokens per character, ~4 tokens per English word
char_count = len(json.dumps(assembled, ensure_ascii=False))
estimated_tokens = int(char_count * 0.75)  # conservative estimate
self._token_usage[chapter] = estimated_tokens
```

Add method:
```python
def get_token_usage(self, last_n: int = 20) -> dict[str, Any]:
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

In `safe_append_perf_timing`, add `estimated_tokens` to `meta`.

## Change 3: Observability CLI token-report command

**File:** `.opencode/scripts/data_modules/observability_cli.py`

Add `cmd_token_report` function that reads JSONL entries with `context_manager.build_context` tool_name, extracts `estimated_tokens` from meta, and displays per-chapter token consumption.

Add `token-report` sub-command to argparse.

## Change 4: webnovel.py token-report routing

No changes needed — `observability_cli.main()` already handles sub-commands.

## Non-Goals

- No real token counting (no tiktoken/claude-tokenizer dependency)
- No token budget enforcement
- No cache invalidation strategy changes (just monitoring)

## Verification

```bash
python .opencode/scripts/webnovel.py observability report --tool context_manager.build_context
python .opencode/scripts/webnovel.py observability token-report
```
