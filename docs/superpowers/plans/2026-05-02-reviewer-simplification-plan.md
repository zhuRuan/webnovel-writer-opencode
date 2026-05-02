# 审查器精简 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将7+1 Agent多层审查体系精简为单Agent + Pipeline模式，对齐原项目 webnovel-writer-master 的简洁实现。

**Architecture:** 删除6专项Agent/3代码检查器/registry/schema/条件触发引擎；用原项目 reviewer.md 替代 unified-reviewer.md；补齐 review_pipeline.py 的 report 渲染和 anti_patterns 回流；更新 skill 工作流。

**Tech Stack:** Python 3.11+, dataclasses, argparse, json, pathlib

---

### Task 1: 删除 checker 基础设施文件

**Files:**
- Delete: `.opencode/checkers/registry.yaml`
- Delete: `.opencode/checkers/schema.yaml`
- Delete: `.opencode/checkers/templates/agent-template.md`
- Delete: `.opencode/scripts/data_modules/checkers_manager.py`
- Delete: `.opencode/scripts/data_modules/checkers_cli.py`
- Delete: `.opencode/scripts/data_modules/condition_evaluator.py`

- [ ] **Step 1: 删除文件**

```bash
rm -rf .opencode/checkers/
rm .opencode/scripts/data_modules/checkers_manager.py
rm .opencode/scripts/data_modules/checkers_cli.py
rm .opencode/scripts/data_modules/condition_evaluator.py
```

- [ ] **Step 2: 提交**

```bash
git add -A
git commit -m "refactor: remove checker infrastructure (registry, schema, manager, cli, evaluator)"
```

---

### Task 2: 删除专项审查 Agent

**Files:**
- Delete: `.opencode/agents/consistency-checker.md`
- Delete: `.opencode/agents/continuity-checker.md`
- Delete: `.opencode/agents/ooc-checker.md`
- Delete: `.opencode/agents/reader-pull-checker.md`
- Delete: `.opencode/agents/high-point-checker.md`
- Delete: `.opencode/agents/pacing-checker.md`

- [ ] **Step 1: 删除文件**

```bash
rm .opencode/agents/consistency-checker.md
rm .opencode/agents/continuity-checker.md
rm .opencode/agents/ooc-checker.md
rm .opencode/agents/reader-pull-checker.md
rm .opencode/agents/high-point-checker.md
rm .opencode/agents/pacing-checker.md
```

- [ ] **Step 2: 提交**

```bash
git add -A
git commit -m "refactor: remove 6 specialized checker agents"
```

---

### Task 3: 删除代码检查器和关联文件

**Files:**
- Delete: `.opencode/scripts/data_modules/world_consistency_checker.py`
- Delete: `.opencode/scripts/data_modules/world_state_tracker.py`
- Delete: `.opencode/scripts/data_modules/debt_tracker.py`
- Delete: `.opencode/scripts/golden_three_checker.py`

- [ ] **Step 1: 删除文件**

```bash
rm .opencode/scripts/data_modules/world_consistency_checker.py
rm .opencode/scripts/data_modules/world_state_tracker.py
rm .opencode/scripts/data_modules/debt_tracker.py
rm .opencode/scripts/golden_three_checker.py
```

- [ ] **Step 2: 提交**

```bash
git add -A
git commit -m "refactor: remove code checkers (world_consistency, debt_tracker, golden_three)"
```

---

### Task 4: 更新 webnovel.py 移除 checkers 命令

**File:** `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: 从 COMMAND_REGISTRY 移除 checkers 条目**

删除第 48 行:
```python
    "checkers": {"type": "data_module", "target": "checkers_cli", "needs_root": False},
```

- [ ] **Step 2: 移除 argparse sub-parser 中的 checkers 块**

删除第 373-375 行:
```python
    # checkers 子命令（审查器配置管理）
    p_checkers = sub.add_parser("checkers", help="审查器配置管理")
    p_checkers.add_argument("args", nargs=argparse.REMAINDER)
```

- [ ] **Step 3: 验证 CLI 不报错**

```bash
python .opencode/scripts/webnovel.py --help 2>&1 | Select-String "checkers"
```

Expected: 无输出（checkers 命令已移除）。

- [ ] **Step 4: 提交**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "refactor: remove checkers CLI command from webnovel.py"
```

---

### Task 5: 删除关联测试文件

**Files:**
- Delete: `.opencode/scripts/data_modules/tests/test_checkers_manager.py`
- Delete: `.opencode/scripts/data_modules/tests/test_condition_evaluator.py`
- Delete: `.opencode/scripts/data_modules/tests/test_world_consistency.py`
- Delete: `.opencode/scripts/data_modules/tests/test_debt_tracker.py`

- [ ] **Step 1: 删除测试文件**

```bash
rm .opencode/scripts/data_modules/tests/test_checkers_manager.py
rm .opencode/scripts/data_modules/tests/test_condition_evaluator.py
rm .opencode/scripts/data_modules/tests/test_world_consistency.py
rm .opencode/scripts/data_modules/tests/test_debt_tracker.py
```

- [ ] **Step 2: 跑全量测试确认基线**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 约 510+ passed / 0 failed（砍掉 ~22 个关联测试，从 532 减少）。

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "test: remove tests for deleted checker modules"
```

---

### Task 6: 对齐 review_schema.py

**File:** `.opencode/scripts/data_modules/review_schema.py`

此文件需要补充 `append_ai_flavor_anti_patterns` 函数及其辅助函数。

- [ ] **Step 1: 添加 import**

在文件顶部 `from pathlib import Path` 之后添加:

```python
import json
```

将 `from dataclasses import asdict, dataclass, field` 之后的 import 调整为:

```python
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json
```

（注意：原文件已存在 Path import 和 json import 检查。需要确认并合并。）

- [ ] **Step 2: 在文件末尾（parse_review_output 之后）添加辅助函数和 anti_patterns 函数**

在 `parse_review_output` 函数之后的文件末尾追加:

```python

def _read_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bad JSON in {path}") from exc


def _write_json(path: Path, payload: Any) -> None:
    atomic_write_json(path, payload, backup=True)


def append_ai_flavor_anti_patterns(project_root: str | Path, result: ReviewResult) -> int:
    root = Path(project_root).expanduser().resolve()
    path = root / ".story-system" / "anti_patterns.json"
    existing = _read_json_if_exists(path) or []
    if not isinstance(existing, list):
        existing = []

    seen_texts = {str(item.get("text") or "").strip() for item in existing if isinstance(item, dict)}
    additions: List[Dict[str, Any]] = []
    for index, issue in enumerate(result.issues, start=1):
        if issue.category != "ai_flavor" or issue.severity not in {"medium", "high", "critical"}:
            continue
        text = (issue.evidence or issue.description or "").strip()[:200]
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        additions.append(
            {
                "text": text,
                "source_table": "review_extracted",
                "source_id": f"ch{int(result.chapter):04d}_issue_{index}",
                "category": issue.category,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, [*existing, *additions])
    return len(additions)
```

- [ ] **Step 3: 确认现有 import 完整性**

文件顶部应包含完整 import:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查结果 schema（v6）。

替代原 checker-output-schema.md 的评分制，改为结构化问题清单。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json
```

- [ ] **Step 4: 运行 review_schema 测试**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_review_schema.py -v
```

Expected: PASS（现有测试不受影响）。

- [ ] **Step 5: 提交**

```bash
git add .opencode/scripts/data_modules/review_schema.py
git commit -m "feat: add append_ai_flavor_anti_patterns to review_schema"
```

---

### Task 7: 对齐 review_pipeline.py

**File:** `.opencode/scripts/review_pipeline.py`

需要补全 report 渲染函数、`_build_review_metrics_record`、anti_patterns 集成。

- [ ] **Step 1: 更新 import**

将第 28 行的 import 替换为:

```python
from data_modules.review_schema import append_ai_flavor_anti_patterns, parse_review_output
```

添加缺少的 typing import（将第 15 行 `from typing import Any, Dict` 改为）:

```python
from typing import Any, Dict, List
```

- [ ] **Step 2: 添加 report 渲染函数（在 `build_review_artifacts` 之前插入）**

在 `_ensure_scripts_path()` 调用之后、`build_review_artifacts` 函数之前，插入以下代码:

```python
def _resolve_report_path(project_root: Path, report_file: str) -> Path:
    root = project_root.expanduser().resolve()
    report_path = Path(report_file).expanduser()
    if not report_path.is_absolute():
        report_path = root / report_path
    report_path = report_path.resolve()
    try:
        report_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("report-file 必须位于 project_root 目录内") from exc
    return report_path


def _format_issue(issue: Dict[str, Any], index: int) -> List[str]:
    description = str(issue.get("description") or "未填写问题描述")
    severity = str(issue.get("severity") or "medium")
    category = str(issue.get("category") or "other")
    location = str(issue.get("location") or "未标注位置")
    evidence = str(issue.get("evidence") or "未提供证据")
    fix_hint = str(issue.get("fix_hint") or "未提供修复方向")
    blocking = "是" if issue.get("blocking") else "否"

    return [
        f"{index}. **{description}**",
        f"   - 严重级别：{severity}",
        f"   - 分类：{category}",
        f"   - 位置：{location}",
        f"   - 阻断：{blocking}",
        f"   - 证据：{evidence}",
        f"   - 修复方向：{fix_hint}",
    ]


def render_review_report(payload: Dict[str, Any]) -> str:
    result = payload["review_result"]
    metrics = payload["metrics"]
    issues = list(result.get("issues", []))
    blocking_issues = [issue for issue in issues if issue.get("blocking")]
    non_blocking_issues = [issue for issue in issues if not issue.get("blocking")]
    severity_counts = metrics.get("severity_counts", {})

    lines: List[str] = [
        f"# 第{payload['chapter']}章审查报告",
        "",
        "## 总览",
        "",
        f"- 问题数：{result.get('issues_count', 0)}",
        f"- 阻断数：{result.get('blocking_count', 0)}",
        f"- 结论：{'需修复后重审' if result.get('has_blocking') else '无阻断问题'}",
    ]
    summary = str(result.get("summary") or "").strip()
    if summary:
        lines.append(f"- 摘要：{summary}")
    if severity_counts:
        ordered = [
            f"{level}={severity_counts.get(level, 0)}"
            for level in ("critical", "high", "medium", "low")
        ]
        lines.append(f"- 严重级别统计：{', '.join(ordered)}")

    lines.extend(["", "## 阻断问题", ""])
    if blocking_issues:
        for index, issue in enumerate(blocking_issues, start=1):
            lines.extend(_format_issue(issue, index))
            lines.append("")
    else:
        lines.append("无。")
        lines.append("")

    lines.extend(["## 其他问题", ""])
    if non_blocking_issues:
        for index, issue in enumerate(non_blocking_issues, start=1):
            lines.extend(_format_issue(issue, index))
            lines.append("")
    else:
        lines.append("无。")
        lines.append("")

    lines.extend(["## 修复方向", ""])
    if issues:
        ordered_issues = [*blocking_issues, *non_blocking_issues]
        for index, issue in enumerate(ordered_issues, start=1):
            description = str(issue.get("description") or "未填写问题描述")
            fix_hint = str(issue.get("fix_hint") or "未提供修复方向")
            lines.append(f"{index}. {description}：{fix_hint}")
    else:
        lines.append("暂无需要修复的问题。")

    return "\n".join(lines).rstrip() + "\n"


def write_review_report(project_root: Path, report_file: str, payload: Dict[str, Any]) -> Path:
    report_path = _resolve_report_path(project_root, report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_review_report(payload), encoding="utf-8")
    return report_path


def _build_review_metrics_record(metrics: Dict[str, Any]):
    from data_modules.index_manager import ReviewMetrics

    return ReviewMetrics(
        start_chapter=int(metrics["start_chapter"]),
        end_chapter=int(metrics["end_chapter"]),
        overall_score=float(metrics.get("overall_score", 0.0)),
        dimension_scores=dict(metrics.get("dimension_scores", {})),
        severity_counts=dict(metrics.get("severity_counts", {})),
        critical_issues=list(metrics.get("critical_issues", [])),
        report_file=str(metrics.get("report_file", "")),
        notes=str(metrics.get("notes", "")),
    )
```

- [ ] **Step 3: 更新 `build_review_artifacts` 添加 anti_patterns 调用**

将现有的 `build_review_artifacts` 函数替换为:

```python
def build_review_artifacts(
    project_root: Path,
    chapter: int,
    review_results_path: Path,
    report_file: str = "",
) -> Dict[str, Any]:
    raw = json.loads(review_results_path.read_text(encoding="utf-8"))
    result = parse_review_output(chapter=chapter, raw=raw)
    anti_patterns_added = append_ai_flavor_anti_patterns(project_root, result)
    metrics = result.to_metrics_dict(report_file=report_file)

    return {
        "chapter": chapter,
        "review_result": result.to_dict(),
        "metrics": metrics,
        "anti_patterns_added": anti_patterns_added,
    }
```

- [ ] **Step 4: 更新 `main()` 中的 `--save-metrics` 逻辑**

将 main() 中第 77-82 行替换为:

```python
    if args.save_metrics:
        from data_modules.config import DataModulesConfig
        from data_modules.index_manager import IndexManager
        config = DataModulesConfig.from_project_root(project_root)
        manager = IndexManager(config)
        manager.save_review_metrics(_build_review_metrics_record(payload["metrics"]))
```

此改动将:
- `manager.save_review_metrics(payload["metrics"])` 改为 `manager.save_review_metrics(_build_review_metrics_record(payload["metrics"]))`
- 修复 dict 直接传给期望 ReviewMetrics 对象的类型不匹配问题

- [ ] **Step 5: 运行 review_pipeline 空闲测试**

```bash
python -c "from pathlib import Path; import sys; sys.path.insert(0, str(Path('.opencode/scripts').resolve())); from data_modules.review_schema import parse_review_output; print('import ok')"
```

Expected: `import ok`，无异常。

- [ ] **Step 6: 提交**

```bash
git add .opencode/scripts/review_pipeline.py
git commit -m "feat: add report rendering and anti_patterns to review_pipeline"
```

---

### Task 8: 替换 unified-reviewer.md 为原项目 reviewer.md

**Files:**
- Modify: `.opencode/agents/unified-reviewer.md`

将整个文件内容替换为原项目 `.opencode/../webnovel-writer-master/webnovel-writer/agents/reviewer.md` 的内容。

- [ ] **Step 1: 复制原项目 reviewer.md 内容**

```bash
cp webnovel-writer-master/webnovel-writer/agents/reviewer.md .opencode/agents/unified-reviewer.md
```

- [ ] **Step 2: 验证文件内容**

```bash
python -c "print(open('.opencode/agents/unified-reviewer.md', encoding='utf-8').read()[:100])"
```

Expected: 文件头包含 `name: reviewer`。

- [ ] **Step 3: 提交**

```bash
git add .opencode/agents/unified-reviewer.md
git commit -m "refactor: replace unified-reviewer with original reviewer agent"
```

---

### Task 9: 对齐 webnovel-review SKILL.md

**File:** `.opencode/skills/webnovel-review/SKILL.md`

将内容替换为对齐原项目的简化版本。

- [ ] **Step 1: 重写 SKILL.md**

使用以下内容完整替换:

```markdown
---
name: webnovel-review
description: 使用审查 Agent 评估章节质量，生成报告并写回审查指标。
allowed-tools: Read Grep Write Edit Bash Task AskUserQuestion
---

# Quality Review Skill

## 目标

- 解析真实书项目根目录，按统一流程完成章节审查。
- 调用统一 `unified-reviewer` 生成结构化问题列表与审查报告。
- 把审查指标写入 `index.db`，并把审查记录写入 `.webnovel/state.json` 兼容投影。
- 若存在关键问题，明确交给用户决定是否立即返工。

## 常见误区

- ❌ 没看 reviewer 原始 JSON 就直接口头总结
- ❌ 有 blocking issue 仍将流程视为通过
- ❌ 把 report 文件生成等同于已落库（`save-review-metrics` 未跑）
- ❌ 主流程伪造 `overall_score` 或审查结论
- ❌ 按需参考一次性全部读完

## 优先级链

1. 用户明确要求（最高）
2. `blocking=true` 硬门槛
3. 项目私有约束（设定集、已有剧情）
4. skill 默认流程
5. reference 建议（最低）

## 决策树入口

- 若项目根不合法或缺少 `.webnovel/state.json` → **阻断**
- 若正文文件不存在 → **阻断**
- 若 reviewer 返回 `blocking=true` issue → 进入 Step 6 用户裁决
- 若所有 issue 均为非 blocking → 正常落库，流程结束

## 执行流程

### Step 1：解析项目根目录并建立环境变量

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SKILL_ROOT=".opencode/skills/webnovel-review"
export SCRIPTS_DIR=".opencode/scripts"
export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" where)"
```

要求：
- `PROJECT_ROOT` 必须包含 `.webnovel/state.json`
- 任一关键目录不存在时立即阻断

### Step 2：按需加载参考资料

#### md 必读

| Trigger | Reference |
|---------|-----------|
| always | `../../references/shared/core-constraints.md` |
| always | `../../references/review-schema.md` |

#### md 按需

| Trigger | Reference |
|---------|-----------|
| 审查涉及爽点或钩子分析 | `../../references/shared/cool-points-guide.md` |
| 审查涉及多线交织 | `../../references/shared/strand-weave-pattern.md` |
| ai_flavor issue ≥ 3 | `../../skills/webnovel-write/references/anti-ai-guide.md` |
| blocking issue 需用户决策 (Step 6) | `../../references/review/blocking-override-guidelines.md` |

### Step 3：加载项目投影状态与待审正文

```bash
cat "${PROJECT_ROOT}/.webnovel/state.json"
```

要求：
- 明确当前章节号与对应正文文件
- 若缺少正文或兼容状态文件，立即阻断

### Step 4：调用统一审查 Agent

必须通过 `Task` 工具调用 `unified-reviewer`，禁止主流程伪造结论。

```text
Task(
  subagent_type: "unified-reviewer",
  prompt: "chapter={chapter_num}; chapter_file={chapter_file}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```

输入：
- `chapter`
- `chapter_file`
- `project_root`
- `scripts_dir`

输出约束：
- 只输出 JSON
- 每个 issue 必须有 `evidence`
- 不输出 `overall_score`

中间产物约定：
- reviewer 原始结果：`${PROJECT_ROOT}/.webnovel/tmp/review_results.json`
- 落库指标：`${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json`

### Step 5：生成审查报告并落库

报告保存到：`审查报告/第{chapter_num}章审查报告.md`

标准文件流：

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter {chapter_num} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第{chapter_num}章审查报告.md"

python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index save-review-metrics \
  --data "@${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json"
```

要求：
- `review-pipeline` 生成的 `review_metrics.json` 必须可直接写入 `review_metrics` 表
- 阻断判断以 reviewer 原始结果中的 `blocking=true` 为准

### Step 6：写入兼容审查记录并处理阻断

先写入兼容审查记录：

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" update-state -- --add-review "{chapter_num}-{chapter_num}" "审查报告/第{chapter_num}章审查报告.md"
```

如存在任意 `blocking=true` 问题，必须使用 `AskUserQuestion` 询问用户：
- 立即修复
- 仅保存报告，稍后处理

若用户选择立即修复：
- 输出返工清单
- 在用户明确授权下做最小修改

若用户选择稍后处理：
- 保留报告与指标记录，结束流程

## 成功标准

1. 已解析真实书项目根目录。
2. 已通过 `unified-reviewer` 输出结构化问题 JSON。
3. 审查报告已生成。
4. `review_metrics` 已写入 `index.db`。
5. 审查记录已写入 `.webnovel/state.json` 兼容投影。
6. 如存在阻断问题，用户已明确选择处理策略。
```

- [ ] **Step 2: 验证 skill 文件格式**

确认 front matter 正确，`allowed-tools` 包含 `Task` 和 `AskUserQuestion`。

- [ ] **Step 3: 提交**

```bash
git add .opencode/skills/webnovel-review/SKILL.md
git commit -m "refactor: simplify webnovel-review skill to single-agent pipeline"
```

---

### Task 10: 更新 webnovel-write SKILL.md 移除 outdated 审查参数

**File:** `.opencode/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: 移除 `--legacy-checkers` 和 `--minimal` 参数引用**

搜索并更新以下位置:

1. 第 15 行: 移除 `--minimal仅统一审查（跳过条件审查器），--legacy-checkers使用6个独立审查agent。`

2. 第 26 行: 移除 `--legacy-checkers` 行
3. 第 27 行: 移除 `--minimal` 行

4. 第 283 行: 移除 `--legacy-checkers` 相关描述

5. 第 295-297 行: 移除 `--legacy-checkers` 和 `--minimal` 审查级别表格行

6. 第 321 行: 移除 `#### 3.3 精细审查执行（'--legacy-checkers' 路径，保留兼容）` 及后续内容

7. 第 419 行: 移除 `硬要求：'--minimal' 也必须产出 'overall_score'` 行

8. 更新 Description: 从 description 中移除 `--minimal仅统一审查（跳过条件审查器），--legacy-checkers使用6个独立审查agent。`

**关键改动**: 在 SKILL.md 中找到所有包含 `--minimal`、`--legacy-checkers`、`legacy.checkers`、`legacy_checkers` 的行，删除或改写为统一审查模式描述。

- [ ] **Step 2: 更新审查相关 Step（保留简化审查流程）**

确认 Step 3 审查部分引用改为:
```
Step 3: 统一审查
  调用 unified-reviewer Agent 审查全部6维度
  参考: skills/webnovel-review/SKILL.md
```

- [ ] **Step 3: 提交**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "docs: remove outdated --minimal/--legacy-checkers from webnovel-write skill"
```

---

### Task 11: 全量测试验证

- [ ] **Step 1: 运行全量测试**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 10
```

Expected: 约 510+ passed / 0 failed（删除 ~22 个 test 后，预计 ~510 个测试）。

- [ ] **Step 2: 如有失败，修复到 0 failed**

分析失败原因并修复。已知可能问题：
- `webnovel-write` skill 引用已删除的参数
- 其他模块导入已删除模块

- [ ] **Step 3: 最终确认全绿**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 3
```

Expected: `X passed / 0 failed`

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "test: verify all tests pass after checker simplification"
```

---

### Task 12: 推送与记录

- [ ] **Step 1: 创建版本标签软指针**

```bash
git tag -f v2.6.0-snapshot
```

- [ ] **Step 2: 推送到远端**

```bash
git push origin master --tags
```

- [ ] **Step 3: 验证远端**

```bash
git log --oneline -5
```

确认所有 commits 已在远端。
