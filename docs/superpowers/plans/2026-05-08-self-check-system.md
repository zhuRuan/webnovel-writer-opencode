# Self-Check System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增确定性写前阻断机制（structural_checker.py）+ 写后校验 + reviewer 状态注入，解决跨章统计问题只能靠 LLM 偶然发现的系统性缺陷。

**Architecture:** 1 个新 Python 模块（五项确定性检查）→ 注册为 CLI 子命令 → 集成到 write/batch skill 的写前和审查步骤。写后校验以 bash 嵌入 batch skill。

**Tech Stack:** Python 3.10+ (stdlib only — json, pathlib, argparse), bash, Claude Code Agent/Skill system

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `data_modules/structural_checker.py` | 新增 | 五项检查 + CLI main() |
| `data_modules/tests/test_structural_checker.py` | 新增 | 7 个测试用例 |
| `data_modules/webnovel.py` | 修改 | 注册 `checkers structural` 子命令 |
| `skills/webnovel-write/SKILL.md` | 修改 | 合同树后加检查；审查 prompt 注入 |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | 合同树后加检查；审查 prompt 注入；Step 8 写后校验 |

---

### Task 1: 创建 structural_checker.py + 测试

**Files:**
- Create: `.opencode/scripts/data_modules/structural_checker.py`
- Create: `.opencode/scripts/data_modules/tests/test_structural_checker.py`

- [ ] **Step 1: 写测试文件（7 个测试）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for structural_checker.py"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from data_modules.structural_checker import run_checks


def _make_state(overrides=None):
    base = {
        "project_info": {"title": "测试", "genre": "修仙"},
        "progress": {"current_chapter": 21, "chapter_status": {}},
        "protagonist_state": {
            "name": "陈升",
            "location": {"current": "废弃工厂", "last_chapter": 20},
        },
        "strand_tracker": {
            "last_quest_chapter": 20,
            "last_fire_chapter": 15,
            "last_constellation_chapter": 12,
            "current_dominant": "quest",
            "chapters_since_switch": 3,
            "history": [
                {"chapter": 18, "dominant": "quest"},
                {"chapter": 19, "dominant": "quest"},
                {"chapter": 20, "dominant": "quest"},
            ],
        },
        "plot_threads": {
            "foreshadowing": [
                {"id": "f1", "status": "未回收", "planted_chapter": 1},
                {"id": "f2", "status": "未回收", "planted_chapter": 3},
                {"id": "f3", "status": "已回收", "planted_chapter": 5},
            ]
        },
    }
    if overrides:
        _deep_update(base, overrides)
    return base


def _deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
            _deep_update(d[k], v)
        else:
            d[k] = v


def _write_state(tmpdir, state):
    webnovel = tmpdir / ".webnovel"
    webnovel.mkdir()
    (webnovel / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _write_memory_scratchpad(tmpdir, entries):
    webnovel = tmpdir / ".webnovel"
    webnovel.mkdir(exist_ok=True)
    data = []
    for i, entry in enumerate(entries):
        item = {
            "id": f"mem-{i}",
            "layer": "semantic",
            "category": "character_state",
            "subject": "test",
            "field": "test",
            "value": "test",
            "status": entry.get("status", "active"),
            "source_chapter": 1,
            "evidence": [],
            "updated_at": "2026-05-01",
        }
        item.update(entry)
        data.append(item)
    (webnovel / "memory_scratchpad.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_contract(tmpdir, chapter):
    chapters = tmpdir / ".story-system" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / f"chapter_{chapter:04d}.json").write_text("{}", encoding="utf-8")


def test_strand_quest_too_long():
    """quest 连续超过 5 章应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "strand_tracker": {
                "chapters_since_switch": 6,
                "history": [
                    {"chapter": 16, "dominant": "quest"},
                    {"chapter": 17, "dominant": "quest"},
                    {"chapter": 18, "dominant": "quest"},
                    {"chapter": 19, "dominant": "quest"},
                    {"chapter": 20, "dominant": "quest"},
                    {"chapter": 21, "dominant": "quest"},
                ],
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "strand_balance")
        assert check["passed"] is False
        assert check["severity"] == "blocking"


def test_strand_constellation_absent():
    """constellation 从未激活且超过 10 章应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "strand_tracker": {
                "last_constellation_chapter": 0,
                "chapters_since_switch": 2,
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "strand_balance")
        assert check["passed"] is False
        assert "从未激活" in check["detail"]


def test_strand_ok():
    """正常 strand 状态应通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "strand_balance")
        assert check["passed"] is True


def test_entity_freshness_stale():
    """主角位置落后 >= 3 章应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "protagonist_state": {
                "location": {"current": "废弃工厂", "last_chapter": 17},
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "entity_freshness")
        assert check["passed"] is False
        assert check["severity"] == "blocking"


def test_entity_freshness_ok():
    """位置最近更新应通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "protagonist_state": {
                "location": {"current": "废弃工厂", "last_chapter": 21},
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "entity_freshness")
        assert check["passed"] is True


def test_memory_bloat():
    """过期率超过 30% 应 warning"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        _write_contract(root, 22)
        entries = []
        for i in range(10):
            entries.append({"status": "active"})
        for i in range(6):
            entries.append({"status": "outdated"})
        _write_memory_scratchpad(root, entries)
        result = run_checks(root, 22)
        check = _find_check(result, "memory_bloat")
        assert check["passed"] is False
        assert check["severity"] == "warning"


def test_memory_bloat_ok():
    """过期率低于阈值应通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        _write_contract(root, 22)
        entries = []
        for i in range(10):
            entries.append({"status": "active"})
        for i in range(2):
            entries.append({"status": "outdated"})
        _write_memory_scratchpad(root, entries)
        result = run_checks(root, 22)
        check = _find_check(result, "memory_bloat")
        assert check["passed"] is True


def test_debt_burden():
    """未回收伏笔超过 5 条应 warning"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state({
            "plot_threads": {
                "foreshadowing": [
                    {"id": f"f{i}", "status": "未回收", "planted_chapter": i}
                    for i in range(1, 8)
                ]
            }
        })
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "debt_burden")
        assert check["passed"] is False


def test_debt_burden_ok():
    """伏笔数量正常应通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        _write_contract(root, 22)
        result = run_checks(root, 22)
        check = _find_check(result, "debt_burden")
        assert check["passed"] is True


def test_contract_coverage_missing():
    """chapter contract 缺失应 blocking"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        # 不创建 contract
        result = run_checks(root, 22)
        check = _find_check(result, "contract_coverage")
        assert check["passed"] is False
        assert check["severity"] == "blocking"


def test_all_pass():
    """健康项目全部通过"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = _make_state()
        _write_state(root, state)
        _write_contract(root, 22)
        entries = [{"status": "active"} for _ in range(5)]
        _write_memory_scratchpad(root, entries)
        result = run_checks(root, 22)
        assert result["passed"] is True
        for c in result["checks"]:
            assert c["passed"] is True, f"{c['name']} should pass but didn't"


def _find_check(result, name):
    for c in result["checks"]:
        if c["name"] == name:
            return c
    raise KeyError(f"check '{name}' not found in {[c['name'] for c in result['checks']]}")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_structural_checker.py -q --no-cov
```

预期：全部 FAIL（ModuleNotFoundError: No module named 'data_modules.structural_checker'）

- [ ] **Step 3: 实现 structural_checker.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def run_checks(project_root: Path, chapter: int) -> dict[str, Any]:
    """运行五项结构检查，返回 {passed, checks}"""
    checks = []
    state = _load_state(project_root)

    # 1. strand_balance
    checks.append(_check_strand_balance(state, chapter))

    # 2. entity_freshness
    checks.append(_check_entity_freshness(state, chapter))

    # 3. memory_bloat
    checks.append(_check_memory_bloat(project_root))

    # 4. debt_burden
    checks.append(_check_debt_burden(state))

    # 5. contract_coverage
    checks.append(_check_contract_coverage(project_root, chapter))

    passed = not any(c["severity"] == "blocking" and not c["passed"] for c in checks)
    return {"chapter": chapter, "passed": passed, "checks": checks}


def _load_state(project_root: Path) -> dict:
    state_file = project_root / ".webnovel" / "state.json"
    if state_file.is_file():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def _check_strand_balance(state: dict, chapter: int) -> dict:
    tracker = state.get("strand_tracker") or {}
    history = tracker.get("history") or []
    result = {
        "name": "strand_balance",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }

    if not history:
        return result

    # 计算连续相同 dominant 的章数
    if history:
        last = history[-1].get("dominant", "")
        consecutive = 0
        for entry in reversed(history):
            if entry.get("dominant") == last:
                consecutive += 1
            else:
                break
        if last == "quest" and consecutive > 5:
            result["passed"] = False
            result["detail"] = f"quest 连续主导 {consecutive} 章（上限 5 章）"
            result["fix"] = "切换到 Fire（感情线）或 Constellation（世界观线）"
            return result

    # constellation 检查
    last_const = _safe_int(tracker.get("last_constellation_chapter"))
    gap = chapter - last_const if last_const > 0 else chapter
    if last_const == 0 and chapter > 10:
        result["passed"] = False
        result["detail"] = f"constellation 从未激活（当前第{chapter}章），最高容忍 15 章"
        result["fix"] = "本章或下一章必须安排世界观展开：新势力/新地点/设定揭示/身世线索"
    elif gap > 10:
        result["passed"] = False
        result["detail"] = f"constellation 已 {gap} 章未出现（上限 10 章）"
        result["fix"] = "安排世界观展示内容"

    return result


def _check_entity_freshness(state: dict, chapter: int) -> dict:
    result = {
        "name": "entity_freshness",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }
    protag = state.get("protagonist_state") or {}
    location = protag.get("location") or {}
    last_chapter = _safe_int(location.get("last_chapter"))
    if last_chapter <= 0:
        return result

    gap = chapter - last_chapter
    if gap >= 3:
        result["passed"] = False
        result["detail"] = f"主角位置 {gap} 章未更新（最后: 第{last_chapter}章）"
        result["fix"] = "data-agent 需输出 location.current state_delta（即使位置未变）"
    return result


def _check_memory_bloat(project_root: Path) -> dict:
    result = {
        "name": "memory_bloat",
        "passed": True,
        "severity": "warning",
        "detail": "",
        "fix": "",
    }
    mem_file = project_root / ".webnovel" / "memory_scratchpad.json"
    if not mem_file.is_file():
        return result

    try:
        data = json.loads(mem_file.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return result

    if not entries:
        return result

    outdated = sum(1 for e in entries if isinstance(e, dict) and e.get("status") == "outdated")
    ratio = outdated / len(entries)
    if ratio > 0.30:
        result["passed"] = False
        result["detail"] = f"记忆过期率 {ratio:.1%}（{outdated}/{len(entries)}），超过 30% 阈值"
        result["fix"] = "运行 memory-compact 清理过期条目"
    return result


def _check_debt_burden(state: dict) -> dict:
    result = {
        "name": "debt_burden",
        "passed": True,
        "severity": "warning",
        "detail": "",
        "fix": "",
    }
    foreshadowing = (state.get("plot_threads") or {}).get("foreshadowing") or []
    unresolved = [f for f in foreshadowing if f.get("status") == "未回收"]
    if len(unresolved) > 5:
        result["passed"] = False
        result["detail"] = f"未回收伏笔 {len(unresolved)} 条（阈值 5 条）"
        result["fix"] = "检查逾期伏笔，近期章节安排偿还或标记废弃"
    return result


def _check_contract_coverage(project_root: Path, chapter: int) -> dict:
    result = {
        "name": "contract_coverage",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }
    contract = project_root / ".story-system" / "chapters" / f"chapter_{chapter:04d}.json"
    if not contract.is_file():
        result["passed"] = False
        result["detail"] = f"缺少 chapter_{chapter:04d}.json 合同"
        result["fix"] = "运行 story-system 生成本章合同"
    return result


def _safe_int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="结构自检（写前阻断）")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--chapter", type=int, required=True, help="目标章节号")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    result = run_checks(project_root, args.chapter)

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

    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_structural_checker.py -q --no-cov
```

预期：11 passed

- [ ] **Step 5: 在实际项目上手动测试**

```bash
python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" checkers structural --chapter 22 --format text
```

预期：输出 strand_balance constellation 从未激活 + entity_freshness 位置过期（如果还没修复的话）

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/data_modules/structural_checker.py .opencode/scripts/data_modules/tests/test_structural_checker.py
git commit -m "feat: add structural_checker with 5 deterministic pre-write checks"
```

---

### Task 2: 注册到 webnovel.py CLI

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: 添加 checkers 子命令注册**

在 `p_knowledge` 注册之后（约 line 391），`# 兼容` 注释之前，插入：

```python
    # structural checker
    checkers_parser = sub.add_parser("checkers", help="结构自检（写前阻断）")
    checkers_sub = checkers_parser.add_subparsers(dest="checkers_action")

    p_structural = checkers_sub.add_parser("structural", help="运行五项结构检查")
    p_structural.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_structural.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
```

- [ ] **Step 2: 添加 dispatch 逻辑**

在 `tool == "knowledge"` 处理附近，添加：

```python
    if tool == "checkers":
        forward_args = ["--project-root", str(project_root), *rest]
        raise SystemExit(_run_data_module("structural_checker", forward_args))
```

project_root 变量需从外层作用域获取。检查现有代码中 `project_root` 的解析方式——在 main() 函数中，project_root 通过 `_resolve_root(args.project_root)` 获取。确保 dispatch 块能访问到它。

- [ ] **Step 3: 验证 CLI 注册**

```bash
python -X utf8 ".opencode/scripts/webnovel.py" --help
```

预期：输出中包含 `checkers` 子命令

```bash
python -X utf8 ".opencode/scripts/webnovel.py" checkers structural --help
```

预期：输出中包含 `--chapter` 和 `--format` 参数

- [ ] **Step 4: 在实际项目上端到端测试**

```bash
python -X utf8 ".opencode/scripts/webnovel.py" --project-root "D:\workspace\凡尘之舞\凡尘之舞" checkers structural --chapter 22 --format json
```

预期：输出有效 JSON，包含 5 个检查项

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: register 'checkers structural' CLI subcommand"
```

---

### Task 3: 集成到 webnovel-write SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: 在合同树刷新后添加 structural check**

在 Step 1（刷新合同树）的 bash 代码块之后，Step 2（context-agent）之前，插入：

```markdown
### 准备：结构自检

```bash
CHECK_RESULT=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" checkers structural --chapter {chapter_num} --format json)
echo "$CHECK_RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(f'passed: {d[\"passed\"]}')"

# 提取 blocking 问题
BLOCKING=$(echo "$CHECK_RESULT" | python -c "
import json,sys
d=json.load(sys.stdin)
blocking=[c for c in d['checks'] if c['severity']=='blocking' and not c['passed']]
for b in blocking:
    print(f\"  ❌ {b['name']}: {b['detail']}\")
    print(f\"     → {b['fix']}\")
print(f'BLOCKING_COUNT={len(blocking)}')
")
echo "$BLOCKING"

# 如果存在 blocking 问题，停止并输出修复建议。不得跳过。
if echo "$BLOCKING" | grep -q "BLOCKING_COUNT=[1-9]"; then
  echo "❌ 结构自检未通过，请先修复上述问题再继续。"
  exit 1
fi
```
```

- [ ] **Step 2: 在 Step 3（审查）中注入自检状态**

修改 Agent(reviewer) 的 prompt，在末尾追加自检状态：

原始 prompt：
```
"chapter={chapter_num}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON..."
```

修改为：
```
"chapter={chapter_num}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。

【自检系统状态 - 审查时需额外关注】
{将上一步 CHECK_RESULT 中 passed=false 的 warning 级别条目转为自然语言提醒，blocking 已被阻断不应出现在这里}

严格输出 reviewer schema JSON..."
```

编排器在调用 reviewer 前，从 CHECK_RESULT 中提取 warning 级别且 passed=false 的检查项，转为一行自然语言追加到 prompt。

- [ ] **Step 3: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "feat(write): integrate structural_checker into single-chapter flow"
```

---

### Task 4: 集成到 webnovel-write-batch SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: 在逐章 Step 1 后添加 structural check**

在 Step 1（刷新合同树）的 bash 代码块之后，Step 2（context-agent）之前，插入与 Task 3 Step 1 相同的 structural check 代码段（用 {N} 替换 {chapter_num}）。

- [ ] **Step 2: 在 Step 4（审查）中注入自检状态**

与 Task 3 Step 2 相同的 reviewer prompt 注入逻辑。

- [ ] **Step 3: 在 Step 8 中添加写后校验**

在 Step 8 的 chapter-commit 之后、备份之前，插入：

```markdown
#### 写后校验

```bash
# 1. 验证本章 commit 已生成
COMMIT_FILE="${PROJECT_ROOT}/.story-system/commits/chapter_$(printf '%04d' ${N}).commit.json"
if [ ! -s "$COMMIT_FILE" ]; then
  echo "❌ commit 缺失: $COMMIT_FILE"
else
  echo "✅ commit 已生成"
fi

# 2. 验证 projection 已提交
python -c "
import json
state = json.load(open('${PROJECT_ROOT}/.webnovel/state.json'))
status = state.get('progress', {}).get('chapter_status', {}).get(str($N))
if status != 'chapter_committed':
    raise SystemExit(f'chapter_status={status}, 期望 committed')
print('✅ projection 已提交')
"

# 3. 验证 index.db 覆盖
python -c "
import sqlite3
db = sqlite3.connect('${PROJECT_ROOT}/.webnovel/index.db')
row = db.execute('SELECT COUNT(*) FROM chapters WHERE chapter_num=?', ($N,)).fetchone()
if row[0] == 0:
    print(f'⚠️ 第${N}章未在 index.db 中')
else:
    print('✅ index.db 已覆盖')
"
```
```

- [ ] **Step 4: Commit**

```bash
git add .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat(batch): integrate structural_checker + post-write validation"
```

---

## Self-Review

**Spec coverage:**
- Component 1 (structural_checker.py + CLI) → Tasks 1 + 2 ✅
- Component 2 (写后校验) → Task 4 Step 3 ✅
- Component 3 (reviewer prompt 注入) → Task 3 Step 2 + Task 4 Step 2 ✅
- Test plan (7+1 manual tests) → Task 1 ✅

**Placeholder scan:** No TBD/TODO found.

**Type consistency:** `run_checks()` signature matches between Task 1 (implementation) and imported in tests. JSON output schema matches what the skills parse. CLI args `--chapter` and `--format` are consistent.
