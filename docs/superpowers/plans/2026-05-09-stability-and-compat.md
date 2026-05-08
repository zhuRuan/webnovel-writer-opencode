# Stability & Compatibility Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 CJK 编码 bug 类别，修复复合题材路由，加固 agent 输出稳定性，优化流程体验。

**Architecture:** 新增 `skill_runner.py` 作为 CJK 安全中间层（stdin 传参替代 CLI args），修改 5 个现有文件。按依赖顺序：skill_runner → story_system_engine → review_pipeline → chapter-writer-agent → SKILL.md × 2。

**Tech Stack:** Python 3.10+ (stdlib + subprocess), argparse, Claude Code Agent/Skill markdown

---

## 文件清单

| 文件 | 操作 | 任务 |
|------|------|------|
| `scripts/skill_runner.py` | 新增 | Task 1 |
| `data_modules/story_system_engine.py` | 修改 | Task 2 |
| `scripts/review_pipeline.py` | 修改 | Task 3 |
| `agents/chapter-writer-agent.md` | 修改 | Task 4 |
| `skills/webnovel-write/SKILL.md` | 修改 | Task 5 |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | Task 6 |

---

### Task 1: 创建 skill_runner.py

**Files:**
- Create: `.opencode/scripts/skill_runner.py`
- Create: `.opencode/scripts/data_modules/tests/test_skill_runner.py`

- [ ] **Step 1: 写测试**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for skill_runner.py"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from scripts.skill_runner import (
    cmd_check_file,
    cmd_check_commit,
    cmd_check_index,
    cmd_check_batch_integrity,
    filter_structural_checks,
)


def test_check_file_exists():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "test.md"
        f.write_text("hello", encoding="utf-8")
        assert cmd_check_file(str(f)) == 0


def test_check_file_missing():
    with tempfile.TemporaryDirectory() as td:
        assert cmd_check_file(str(Path(td) / "nope.md")) == 1


def test_check_file_empty():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "empty.md"
        f.write_text("", encoding="utf-8")
        assert cmd_check_file(str(f)) == 1


def test_check_commit_exists():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        commits = root / ".story-system" / "commits"
        commits.mkdir(parents=True)
        (commits / "chapter_0020.commit.json").write_text('{"status":"ok"}', encoding="utf-8")
        assert cmd_check_commit(str(root), 20) == 0


def test_check_commit_missing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".story-system" / "commits").mkdir(parents=True)
        assert cmd_check_commit(str(root), 20) == 1


def test_check_index_ok():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        webnovel = root / ".webnovel"
        webnovel.mkdir()
        db_path = webnovel / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO chapters VALUES (20, 'test')")
        conn.commit()
        conn.close()
        assert cmd_check_index(str(root), 20) == 0


def test_check_index_missing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        webnovel = root / ".webnovel"
        webnovel.mkdir()
        db_path = webnovel / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.commit()
        conn.close()
        assert cmd_check_index(str(root), 20) == 1


def test_filter_structural_infra():
    result = {
        "chapter": 22,
        "passed": False,
        "checks": [
            {"name": "strand_balance", "passed": False, "severity": "blocking", "detail": "quest 连续 6 章", "fix": "切换"},
            {"name": "contract_coverage", "passed": False, "severity": "blocking", "detail": "缺少 chapter_0022.json", "fix": "运行 story-system"},
            {"name": "memory_bloat", "passed": True, "severity": "warning", "detail": "", "fix": ""},
        ],
    }
    filtered = filter_structural_checks(result)
    assert filtered["passed"] is False  # strand_balance still blocking
    contract_check = [c for c in filtered["checks"] if c["name"] == "contract_coverage"][0]
    assert contract_check["severity"] == "warning"
    assert contract_check["passed"] is True  # 降级后不阻断


def test_filter_structural_only_infra():
    """只有基础设施问题时，整体 pass"""
    result = {
        "chapter": 22,
        "passed": False,
        "checks": [
            {"name": "contract_coverage", "passed": False, "severity": "blocking", "detail": "缺少", "fix": "运行 story-system"},
        ],
    }
    filtered = filter_structural_checks(result)
    assert filtered["passed"] is True  # 仅有 infra 问题，不阻断
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py -q --no-cov
```

预期: ModuleNotFoundError

- [ ] **Step 3: 实现 skill_runner.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill 运行器 — CJK 安全中间层。

所有 CJK 文本通过 stdin 或文件传递，不经过 CLI args。
启动时强制 UTF-8 输入输出。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

# 确保 scripts 目录在 path 中
_scripts_root = Path(__file__).resolve().parent
if str(_scripts_root) not in sys.path:
    sys.path.insert(0, str(_scripts_root))

from runtime_compat import enable_windows_utf8_stdio


# ── 基础设施检查 ──────────────────────────────

INFRA_CHECKS = {"contract_coverage"}


def filter_structural_checks(result: dict) -> dict:
    """降级已知基础设施问题为 warning，不阻断写作。"""
    for c in result["checks"]:
        if c["name"] in INFRA_CHECKS:
            c["severity"] = "warning"
            c["passed"] = True
            if not c["fix"]:
                c["fix"] = "基础设施问题，不影响本章写作，可忽略"
    result["passed"] = not any(
        c["severity"] == "blocking" and not c["passed"]
        for c in result["checks"]
    )
    return result


# ── Actions ───────────────────────────────────

def cmd_story_system(args: argparse.Namespace) -> int:
    """刷新合同树。genre 从 state.json 读取，chapter goal 从 stdin 读取。"""
    root = Path(args.project_root)
    goal = sys.stdin.read().strip()
    if not goal:
        print("❌ stdin 未收到 CHAPTER_GOAL", file=sys.stderr)
        return 1

    s = json.loads((root / ".webnovel" / "state.json").read_text("utf-8"))
    genre = s.get("project_info", {}).get("genre", "")

    scripts_dir = str(_scripts_root)
    return subprocess.run([
        sys.executable, "-X", "utf8",
        f"{scripts_dir}/webnovel.py", "--project-root", str(root),
        "story-system", goal, "--genre", genre,
        "--chapter", str(args.chapter),
        "--persist", "--emit-runtime-contracts", "--format", "both",
    ], check=False).returncode


def cmd_check_structural(args: argparse.Namespace) -> int:
    """运行结构自检，应用分级过滤后输出。"""
    from data_modules.structural_checker import run_checks

    root = Path(args.project_root)
    result = run_checks(root, args.chapter)
    result = filter_structural_checks(result)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "✅ 全部通过" if result["passed"] else "❌ 存在阻断问题"
        print(f"第{result['chapter']}章 结构自检: {status}")
        for c in result["checks"]:
            icon = "✅" if c["passed"] else "❌"
            print(f"  {icon} [{c['severity']}] {c['name']}")
            if not c["passed"]:
                print(f"         {c['detail']}")
                print(f"      →  {c['fix']}")

    return 0 if result["passed"] else 1


def cmd_check_file(path: str) -> int:
    """检查文件存在且非空。替代 test -s。"""
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        print("OK")
        return 0
    print("MISSING")
    return 1


def cmd_check_commit(project_root: str, chapter: int) -> int:
    """检查章节 commit 文件存在且非空。"""
    p = Path(project_root) / ".story-system" / "commits" / f"chapter_{chapter:04d}.commit.json"
    return cmd_check_file(str(p))


def cmd_check_index(project_root: str, chapter: int) -> int:
    """检查章节在 index.db 的 chapters 表中。"""
    db_path = Path(project_root) / ".webnovel" / "index.db"
    if not db_path.is_file():
        print("MISSING")
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM chapters WHERE chapter=?", (chapter,)
        ).fetchone()
        if row and row[0] > 0:
            print("OK")
            return 0
        print("MISSING")
        return 1
    finally:
        conn.close()


def cmd_check_batch_integrity(project_root: str, start: int, end: int) -> int:
    """跨章 batch_state 完整性校验。"""
    state_path = Path(project_root) / ".webnovel" / "batch_state.json"
    if not state_path.is_file():
        print("MISSING: batch_state.json 不存在")
        return 1
    s = json.loads(state_path.read_text("utf-8"))
    completed = set(s.get("completed_chapters", []))
    expected = set(range(start, end + 1))
    missing = sorted(expected - completed)
    if missing:
        print(f"MISSING: {missing}")
        return 1
    print("OK")
    return 0


# ── CLI ───────────────────────────────────────

def main() -> None:
    enable_windows_utf8_stdio(skip_in_pytest=True)

    parser = argparse.ArgumentParser(description="skill_runner — CJK 安全中间层")
    sub = parser.add_subparsers(dest="action", required=True)

    # story-system
    p_ss = sub.add_parser("story-system", help="刷新合同树 (genre 自动读取, goal 从 stdin)")
    p_ss.add_argument("--project-root", required=True)
    p_ss.add_argument("--chapter", type=int, required=True)

    # check-structural
    p_cs = sub.add_parser("check-structural", help="结构自检 (含分级过滤)")
    p_cs.add_argument("--project-root", required=True)
    p_cs.add_argument("--chapter", type=int, required=True)
    p_cs.add_argument("--format", choices=["json", "text"], default="json")

    # check-commit
    p_cc = sub.add_parser("check-commit", help="验证 commit 文件")
    p_cc.add_argument("--project-root", required=True)
    p_cc.add_argument("--chapter", type=int, required=True)

    # check-index
    p_ci = sub.add_parser("check-index", help="验证 index.db 覆盖")
    p_ci.add_argument("--project-root", required=True)
    p_ci.add_argument("--chapter", type=int, required=True)

    # check-file
    p_cf = sub.add_parser("check-file", help="检查文件存在且非空")
    p_cf.add_argument("--path", required=True)

    # check-batch-integrity
    p_cbi = sub.add_parser("check-batch-integrity", help="跨章 batch_state 完整性校验")
    p_cbi.add_argument("--project-root", required=True)
    p_cbi.add_argument("--start", type=int, required=True)
    p_cbi.add_argument("--end", type=int, required=True)

    args = parser.parse_args()

    action_map = {
        "story-system": lambda: cmd_story_system(args),
        "check-structural": lambda: cmd_check_structural(args),
        "check-commit": lambda: cmd_check_commit(args.project_root, args.chapter),
        "check-index": lambda: cmd_check_index(args.project_root, args.chapter),
        "check-file": lambda: cmd_check_file(args.path),
        "check-batch-integrity": lambda: cmd_check_batch_integrity(args.project_root, args.start, args.end),
    }

    code = action_map[args.action]()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_skill_runner.py -q --no-cov
```

预期: 9 passed

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/skill_runner.py .opencode/scripts/data_modules/tests/test_skill_runner.py
git commit -m "feat: add skill_runner.py — CJK-safe intermediate layer for skill commands"
```

---

### Task 2: S2 复合题材路由

**Files:**
- Modify: `.opencode/scripts/data_modules/story_system_engine.py`
- Modify: `.opencode/scripts/data_modules/tests/test_story_system_engine.py` (追加测试)

- [ ] **Step 1: 追加测试**

在现有测试文件中添加：

```python
def test_compound_genre_split():
    """复合题材应按 + 分割后逐个匹配"""
    engine = StorySystemEngine(CSV_DIR)
    # 模拟: 直接匹配失败后走拆解
    rows = engine._load_csv_rows("题材与调性推理")
    # "末世+异能" → 末世命中 GR-012
    result = engine._fallback_row_for_genre(rows, "末世+异能")
    assert result is not None
    assert "末世" in result.get("题材/流派", "")

def test_compound_genre_first_component_wins():
    """第一个组件命中即返回，不继续尝试"""
    engine = StorySystemEngine(CSV_DIR)
    rows = engine._load_csv_rows("题材与调性推理")
    result = engine._fallback_row_for_genre(rows, "修仙+异能")
    assert result is not None
    # "修仙" 先于 "异能"，应命中 GR-011
    assert "修真" in result.get("题材/流派", "") or "修仙" in result.get("题材/流派", "")

def test_pure_genre_unchanged():
    """纯题材不受拆解影响"""
    engine = StorySystemEngine(CSV_DIR)
    rows = engine._load_csv_rows("题材与调性推理")
    result = engine._fallback_row_for_genre(rows, "末世")
    assert result is not None
```

- [ ] **Step 2: 运行测试确认新增的失败**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_story_system_engine.py::test_compound_genre_split -q --no-cov
```

预期: FAIL (AttributeError or AssertionError)

- [ ] **Step 3: 实现拆解逻辑**

在 `story_system_engine.py` 的 `_fallback_row_for_genre` 方法中（约 line 325），在现有直接匹配失败后（line 334 `return None` 之前）插入：

```python
    # 复合题材拆解: "末世+异能" → ["末世", "异能"] → 逐个匹配
    if "+" in genre:
        components = [g.strip() for g in genre.split("+")]
        for component in components:
            if not component:
                continue
            component_text = self._normalize_text(resolve_genre(component) or component)
            for row in rows:
                candidates = (
                    self._split_multi_value(row.get("适用题材"))
                    + self._split_multi_value(row.get("题材/流派"))
                    + self._split_multi_value(row.get("canonical_genre"))
                )
                if any(self._normalize_text(candidate) == component_text for candidate in candidates):
                    return row
```

- [ ] **Step 4: 运行所有相关测试**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_story_system_engine.py -q --no-cov
```

预期: 全部通过（含新增的 3 个测试）

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/story_system_engine.py .opencode/scripts/data_modules/tests/test_story_system_engine.py
git commit -m "feat: split compound genres by + in story routing fallback"
```

---

### Task 3: S3a reviewer JSON 清洗

**Files:**
- Modify: `.opencode/scripts/review_pipeline.py`

- [ ] **Step 1: 添加清洗函数并集成**

在 `review_pipeline.py` 中，找到 `parse_review_output` 调用处。在其上方添加：

```python
import re

def clean_reviewer_output(raw: str) -> str:
    """从 reviewer agent 输出中提取纯 JSON。
    
    处理四种情况:
    1. markdown 代码块包裹: ```json ... ```
    2. JSON 前有对话文本: "好的，以下是审查结果: {...}"
    3. JSON 后有对话文本: "{...} 以上就是审查结果"
    4. 纯 JSON
    """
    if not raw or not raw.strip():
        raise ValueError("reviewer 输出为空")
    
    # 尝试 markdown 代码块
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', raw)
    if m:
        return m.group(1).strip()
    
    # 找到第一个 { 和最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end+1]
    
    raise ValueError("reviewer 输出中未找到有效 JSON")
```

在 `parse_review_output` 调用前，将原始文本先通过 `clean_reviewer_output`。

- [ ] **Step 2: 验证**

```bash
python -c "
from scripts.review_pipeline import clean_reviewer_output

# case 1: pure JSON
assert '{\"issues\":[]}' in clean_reviewer_output('{\"issues\":[]}')

# case 2: markdown code block
assert '{\"issues\":[]}' in clean_reviewer_output('\`\`\`json\n{\"issues\":[]}\n\`\`\`')

# case 3: prefix text
assert '{\"issues\":[]}' in clean_reviewer_output('好的，以下是审查结果: {\"issues\":[]}')

# case 4: suffix text
assert '{\"issues\":[]}' in clean_reviewer_output('{\"issues\":[]}\n以上就是审查结果')

# case 5: both prefix and suffix
result = clean_reviewer_output('审查结果如下:\n{\"issues\":[]}\n请审核。')
assert result == '{\"issues\":[]}'

print('✅ 全部通过')
"
```

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/review_pipeline.py
git commit -m "fix: add review output cleaner to strip non-JSON wrapper text"
```

---

### Task 4: S3b chapter-writer-agent 约束加固

**Files:**
- Modify: `.opencode/agents/chapter-writer-agent.md`

- [ ] **Step 1: 修改 Step A 和 Step C**

将 `### Step A: 理解任务` 替换为：

```markdown
### Step A: 确认硬性约束

**起草前逐条确认，全部通过才进 Step B：**

□ 过渡承接: 本章开篇必须衔接上章结尾的 open_question
□ 必须覆盖: 任务书第 2 段中标注的 must_cover_nodes 全部覆盖
□ 禁区: 任务书第 3 段中标注的 forbidden_zones 绝不违反
□ 字数: 2000-2500 字

**修复轮额外约束:**
□ 逐条对照【审查反馈】中的每条 issue，只修改指出的位置，不改无关段落
```

将 `### Step C: 自检` 替换为：

```markdown
### Step C: 硬性约束验证

起草完成后，逐条回填确认：

□ 过渡承接 ← 正文第__段已实现（写具体段号）
□ must_cover_nodes ← 已全部覆盖
□ 禁区 ← 未违反
□ 修复轮 issue ← 全部已修改（如有）

**任一条无法回填具体段号 → 回到 Step B 补充该条，不得跳过。**
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/agents/chapter-writer-agent.md
git commit -m "fix(agent): harden chapter-writer constraints with verify checklist"
```

---

### Task 5: S1/S3c/S4c — 单章 SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: 替换合同树刷新为 skill_runner 调用**

找到 "准备：刷新合同树" 中的 bash 代码块，替换为：

```bash
# 用 skill_runner 传递 CJK，避免 shell 编码损坏
echo "${CHAPTER_GOAL}" | python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" story-system \
  --project-root "${PROJECT_ROOT}" --chapter {chapter_num}
```

- [ ] **Step 2: 替换结构自检为 skill_runner 调用**

找到 "准备：结构自检" 中的 bash 代码块，替换为：

```bash
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-structural \
  --project-root "${PROJECT_ROOT}" --chapter {chapter_num} --format json
# skill_runner 已内置 S4a 分级过滤，contract_coverage 自动降级
```

- [ ] **Step 3: 修复轮加 rm**

在 Step 3 审查的修复轮流程中，重审前加：

```bash
rm -f "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"
```

- [ ] **Step 4: placeholder 去重**

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" placeholder-scan --format text | sort -u
```

- [ ] **Step 5: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "fix(write): use skill_runner for CJK ops, add review cleanup, dedupe placeholders"
```

---

### Task 6: S1/S3c/S4b — 批量 SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: 批量中同样替换为 skill_runner 调用**

与 Task 5 相同的三处替换：
- 合同树刷新 → `echo "${CHAPTER_GOAL}" | skill_runner.py story-system`
- 结构自检 → `skill_runner.py check-structural`
- placeholder → `sort -u`

- [ ] **Step 2: 修复轮加 rm（同 Task 5 Step 3）**

- [ ] **Step 3: 写后校验改为 skill_runner 调用**

找到 Step 8 的 "写后校验" 代码块，替换为：

```bash
#### 写后校验

# 1. commit 验证
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-commit \
  --project-root "${PROJECT_ROOT}" --chapter {N}

# 2. projection 验证
python -c "
import json
state = json.load(open('${PROJECT_ROOT}/.webnovel/state.json'))
status = state.get('progress', {}).get('chapter_status', {}).get(str($N))
if status != 'chapter_committed':
    raise SystemExit(f'chapter_status={status}, 期望 committed')
print('✅ projection 已提交')
"

# 3. index.db 验证
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-index \
  --project-root "${PROJECT_ROOT}" --chapter {N}

# 4. batch_state 跨章完整性
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" check-batch-integrity \
  --project-root "${PROJECT_ROOT}" --start {S} --end {N}
```

- [ ] **Step 4: 默认 paused 状态**

修改 Step 0.6 初始化代码中的 `status`：

```python
s = {
    ...
    'status': 'paused',  # 默认暂停，用户确认后改 running
    ...
}
```

并在 Step 0（每章环境验证）后增加状态门：

```markdown
**状态门**: 若 batch_state.status 不是 "running"，输出进度摘要并等待用户输入 "继续"。24h 无输入→保持 paused。
```

- [ ] **Step 5: Commit**

```bash
git add .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "fix(batch): use skill_runner, default paused state, auto post-write checks"
```

---

## Self-Review

**Spec coverage:**
- S1 (skill_runner.py) → Task 1 ✅
- S1 (skill 集成) → Tasks 5, 6 ✅
- S2 (compound genre) → Task 2 ✅
- S3a (JSON cleaner) → Task 3 ✅
- S3b (agent constraints) → Task 4 ✅
- S3c (review cleanup) → Tasks 5, 6 ✅
- S4a (infra filter) → Task 1 (built into skill_runner) + Tasks 5, 6 ✅
- S4b (paused state) → Task 6 ✅
- S4c (placeholder dedup) → Tasks 5, 6 ✅

**Placeholder scan:** No TBD/TODO found. All code shown.

**Type consistency:** `filter_structural_checks` signature in Task 1 tests matches implementation. `clean_reviewer_output` tested inline. CLI args consistent across all action definitions.
