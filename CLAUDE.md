# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Webnovel Writer for OpenCode — a long-form Chinese web novel AI writing system built on the OpenCode framework. Combats AI "forgetting" and "hallucination" in serialized fiction through layered RAG, story contracts, and structured quality review.

## Commands

### Testing

```bash
# Full test suite (from repo root)
python -m pytest .opencode/scripts/data_modules/tests -q --no-cov

# Smoke tests (rapid pre-commit check, 2 critical test files)
pwsh .opencode/scripts/run_tests.ps1 -Mode smoke

# Full tests via PowerShell (creates isolated temp dir)
pwsh .opencode/scripts/run_tests.ps1 -Mode full

# Single test file
python -m pytest .opencode/scripts/data_modules/tests/test_config.py -q --no-cov

# Single test function
python -m pytest .opencode/scripts/data_modules/tests/test_config.py::test_load_env -q --no-cov
```

Tests live in `.opencode/scripts/data_modules/tests/` (60 test files). The PowerShell runner creates isolated temp dirs under `.tmp/pytest/` to avoid Windows permission issues. `conftest.py` patches `tempfile.mkdtemp` and sets `sqlite3` journal mode for test safety.

### CLI

```bash
# Unified entry point for all commands
python .opencode/scripts/webnovel.py <command> [args]

# Common subcommands
python .opencode/scripts/webnovel.py preflight       # validate runtime environment
python .opencode/scripts/webnovel.py status          # project health report
python .opencode/scripts/webnovel.py story-system    # story contract management
python .opencode/scripts/webnovel.py review-pipeline # review pipeline management
python .opencode/scripts/webnovel.py export          # export novel
python .opencode/scripts/webnovel.py publish         # publish to platform
python .opencode/scripts/webnovel.py memory          # memory system management
```

Full command list (28 commands): `where`, `preflight`, `use`, `index`, `state`, `rag`, `style`, `entity`, `context`, `memory`, `migrate`, `status`, `update-state`, `backup`, `archive`, `init`, `extract-context`, `story-system`, `story-events`, `chapter-commit`, `memory-contract`, `project-memory`, `review-pipeline`, `placeholder-scan`, `master-outline-sync`, `export`, `publish`, `knowledge`.

Most subcommands forward to `data_modules/<module>.py` via argparse dispatch. Writing tools (`--project-root` aware) use the `PASSTHROUGH_TOOLS` set; the entry point auto-resolves the book project root (directory containing `.webnovel/state.json`).

### Dashboard

```bash
# Backend (FastAPI on port 8080)
python -m .opencode.dashboard

# Frontend dev server (React + Vite, separate terminal)
cd .opencode/dashboard/frontend && npm run dev
```

## Architecture

### Six-Layer Data Flow

Code is organized as a pipeline — each layer feeds the next:

| Layer | What | Where |
|-------|------|-------|
| Knowledge | CSV tables + MD references + BM25 retrieval | `.opencode/references/` |
| Reasoning | Genre routing + anti-pattern ranking | `.opencode/genres/` |
| Contract | MASTER_SETTING + volume/chapter briefs + review contracts | `.story-system/` (per-project) |
| Context | JSON assembly of what the writer needs | `data_modules/context_manager.py` |
| Commit | Fact extraction + event sourcing + projection routing | `data_modules/chapter_commit_service.py`, `data_modules/event_log_store.py` |
| Projection | 5 writers: state, index, summary, memory, vector | `data_modules/` various `*_writer.py` |

### Key Subsystems

**Story Contract Engine** — MASTER_SETTING.json is the source of truth. Runtime contracts derive from it per chapter. Event sourcing records all mutations; projections materialize state/index/summary/memory/vector views. Core files: `story_system_engine.py`, `story_contracts.py`, `event_log_store.py`, `event_projection_router.py`, `chapter_commit_service.py`.

**Memory System** — Three tiers: working (short-term), plot (mid-term), semantic (long-term). Modules in `data_modules/memory/`: orchestrator, compactor, store, writer, schema, bootstrap, budget.

**DebtTracker** — Foreshadowing tracking with hard constraint blocking. Active debts > 2 triggers debt-aware context budget (auto-allocate 15% tokens to foreshadowing list). Implemented in `data_modules/index_debt_mixin.py` (mixed into `index_manager.py`).

**Review Pipeline** — Two layers: Code Checkers (deterministic, run before LLM, block critical issues) → 6 parallel LLM reviewers (consistency, continuity, OOC, high-point, pacing, reader-pull). Reviewer output processed via `.opencode/scripts/review_pipeline.py` (CLI: `review-pipeline`), schema defined in `data_modules/review_schema.py`.

**Graph-RAG** — Entity relationship graph with SQLite persistence. Located in `data_modules/` entity linking and index modules.

**Dashboard** — FastAPI backend (read-only GET endpoints serving project state) + React 19 frontend with ECharts visualization. Backend: `.opencode/dashboard/app.py`. Frontend: `.opencode/dashboard/frontend/`.

### OpenCode Integration

11 skills (slash commands like `/webnovel-write`) and 4 agents (context-agent, data-agent, reviewer, deconstruction-agent) defined in `.opencode/skills/` and `.opencode/agents/`. The reviewer agent is instantiated 6 times in parallel for different review dimensions. The OpenCode runtime invokes these; this repo defines their behavior.

### Key Convention: Unified CLI

All Python functionality routes through a single entry point: `.opencode/scripts/webnovel.py` → `data_modules/webnovel.py`. Subcommands are dispatched via argparse — most forward to `data_modules/<module>.py` via `_run_data_module()`. New subcommands should be added to the argparse subparser chain in `webnovel.py`.

## Guidelines

These behavioral guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For multi-step tasks, state a brief plan with verification per step. Strong success criteria enable independent iteration.

## 外置

**实际写小说的目录。**

D:\workspace\凡尘之舞