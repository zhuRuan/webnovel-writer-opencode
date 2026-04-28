# Review System Foundation Reinforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix agents_dir path bug, consolidate dimension_mapping, split checkers_manager.py into 3 focused files.

**Architecture:** Three sequential tasks, each self-contained. Task 1 fixes a 1-line path bug. Task 2 removes duplicate dimension_mapping from schema.yaml. Task 3 extracts CLI commands from the 838-line checkers_manager.py into a new checkers_cli.py.

**Tech Stack:** Python 3.10+, PyYAML, argparse

---

### Task 1: Fix agents_dir path bug

**Files:**
- Modify: `.opencode/scripts/data_modules/checkers_manager.py:62,675`

- [ ] **Step 1: Fix agents_dir in __init__**

Line 62 (inside `__init__`, under `self.schema_path`):
```python
# OLD:
self.agents_dir = checkers_dir / "agents"
# NEW:
self.agents_dir = checkers_dir.parent / "agents"
```

- [ ] **Step 2: Fix file path in create_checker**

Line 675 (inside `create_checker`, the `new_checker` dict):
```python
# OLD:
"file": f"agents/{checker_id}.md",
# NEW:
"file": f"../agents/{checker_id}.md",
```

- [ ] **Step 3: Verify**

```bash
python .opencode/scripts/webnovel.py checkers validate
python -m pytest .opencode/scripts/data_modules/tests/test_checkers_manager.py -v
```

Expected: validate passes, 7 tests pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/checkers_manager.py
git commit -m "fix: correct agents_dir path from checkers/agents to agents"
```

---

### Task 2: Consolidate dimension_mapping

**Files:**
- Modify: `.opencode/checkers/schema.yaml`
- Modify: `.opencode/scripts/data_modules/checkers_manager.py`

- [ ] **Step 1: Remove dimension_mapping from schema.yaml (line 137-143 of registry.yaml stays)**

In `schema.yaml`, delete lines 203-209 (the `dimension_mapping:` block inside `aggregation_schema`):
```yaml
# DELETE this block:
  dimension_mapping:
    爽点密度: [high-point-checker]
    设定一致性: [consistency-checker]
    节奏控制: [pacing-checker]
    人物塑造: [ooc-checker]
    连贯性: [continuity-checker]
    追读力: [reader-pull-checker]
```

- [ ] **Step 2: Update checkers_manager.py to read dimension_mapping from registry**

Search `checkers_manager.py` for `dimension_mapping`. If any code references `schema["dimension_mapping"]` or `aggregation_schema["dimension_mapping"]`, update to read from `registry["dimension_mapping"]` instead (via `self.load_registry()`).

If no code references exist (dimension_mapping is consumed only by skills/agents), skip this step.

- [ ] **Step 3: Verify**

```bash
python .opencode/scripts/webnovel.py checkers validate
python .opencode/scripts/webnovel.py checkers list
python -m pytest .opencode/scripts/data_modules/tests/test_checkers_manager.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add .opencode/checkers/schema.yaml .opencode/scripts/data_modules/checkers_manager.py
git commit -m "refactor: consolidate dimension_mapping to registry.yaml, remove from schema.yaml"
```

---

### Task 3: Split checkers_manager.py into checkers_cli.py

**Files:**
- Create: `.opencode/scripts/data_modules/checkers_cli.py` (~180 lines)
- Modify: `.opencode/scripts/data_modules/checkers_manager.py` (remove lines 694-838)
- Modify: `.opencode/scripts/data_modules/webnovel.py:48` (change target)

- [ ] **Step 1: Create checkers_cli.py**

Write `.opencode/scripts/data_modules/checkers_cli.py` with exact content:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查器 CLI 命令

从 checkers_manager.py 拆分出来的 CLI 入口。
"""

import argparse
import json
import sys

from .checkers_manager import CheckersManager
from .exceptions import ConfigError


def cmd_list(args: argparse.Namespace) -> int:
    """列出审查器命令"""
    manager = CheckersManager()

    try:
        checkers = manager.list_checkers(
            mode=args.mode,
            category=args.category,
            enabled_only=not args.all,
            format=args.format,
        )
    except ConfigError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(checkers, ensure_ascii=False, indent=2))
    else:
        print(f"审查器列表 (共 {len(checkers)} 个):\n")
        for checker in checkers:
            category_label = "[核心]" if checker["category"] == "core" else "[条件]"
            enabled_label = "✓" if checker["enabled"] else "✗"
            print(f"{enabled_label} {category_label} {checker['id']}: {checker['name']}")
            triggers = checker.get("triggers", [])
            if triggers:
                trigger_desc = []
                for t in triggers[:2]:
                    if isinstance(t, dict):
                        expr = t.get("expression") or t.get("keywords", "(条件)")
                        if isinstance(expr, list):
                            expr = ", ".join(expr[:2])
                        trigger_desc.append(str(expr))
                    else:
                        trigger_desc.append(str(t))
                print(f"    触发: {'; '.join(trigger_desc)}")
            print()

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """验证配置命令"""
    manager = CheckersManager()

    result = manager.validate()

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["valid"]:
            print("✓ 配置验证通过")
        else:
            print("✗ 配置验证失败")

        if result["errors"]:
            print("\n错误:")
            for error in result["errors"]:
                print(f"  - {error}")

        if result["warnings"]:
            print("\n警告:")
            for warning in result["warnings"]:
                print(f"  - {warning}")

        print(f"\n审查器数量: {result.get('checker_count', 0)}")
        print(f"模式数量: {result.get('mode_count', 0)}")

    return 0 if result["valid"] else 1


def cmd_create(args: argparse.Namespace) -> int:
    """创建审查器命令"""
    manager = CheckersManager()

    triggers = args.triggers.split(",") if args.triggers else []

    result = manager.create_checker(
        checker_id=args.id,
        name=args.name,
        category=args.category,
        description=args.description or "",
        triggers=triggers,
    )

    if result["success"]:
        print(f"✓ 审查器创建成功: {args.id}")
        print(f"  文件: {result['agent_file']}")
    else:
        print(f"✗ 创建失败: {result.get('error')}")
        return 1

    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    """获取 Schema 命令"""
    manager = CheckersManager()

    schema = manager.get_schema_for_checker(args.checker)
    if schema:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        print(f"未找到审查器 {args.checker} 的 Schema", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="审查器配置管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    # list 命令
    p_list = sub.add_parser("list", help="列出审查器")
    p_list.add_argument("--mode", "-m", choices=["standard", "minimal", "full", "unified_review"], help="审查模式")
    p_list.add_argument("--category", "-c", choices=["core", "conditional"], help="类别")
    p_list.add_argument("--all", "-a", action="store_true", help="显示所有（包括禁用的）")
    p_list.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_list.set_defaults(func=cmd_list)

    # validate 命令
    p_validate = sub.add_parser("validate", help="验证配置")
    p_validate.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_validate.set_defaults(func=cmd_validate)

    # create 命令
    p_create = sub.add_parser("create", help="创建新审查器")
    p_create.add_argument("--id", "-i", required=True, help="审查器 ID")
    p_create.add_argument("--name", "-n", required=True, help="审查器名称")
    p_create.add_argument("--category", choices=["core", "conditional"], default="core", help="类别")
    p_create.add_argument("--description", "-d", default="", help="描述")
    p_create.add_argument("--triggers", "-t", default="", help="触发条件（逗号分隔）")
    p_create.set_defaults(func=cmd_create)

    # schema 命令
    p_schema = sub.add_parser("schema", help="获取审查器 Schema")
    p_schema.add_argument("checker", help="审查器 ID")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Remove CLI code from checkers_manager.py**

Delete lines 694-838 from `checkers_manager.py` (everything from `def cmd_list` to the end, including `main()` and `if __name__ == "__main__"`).

Also remove unused imports if they were only used by CLI code:
- Check if `argparse`, `json`, `sys` are used elsewhere in the file. If not, remove their imports (lines 15-17).

- [ ] **Step 3: Update COMMAND_REGISTRY in webnovel.py**

Line 48, change:
```python
# OLD:
"checkers": {"type": "data_module", "target": "checkers_manager", "needs_root": False},
# NEW:
"checkers": {"type": "data_module", "target": "checkers_cli", "needs_root": False},
```

- [ ] **Step 4: Verify CLI still works**

```bash
python .opencode/scripts/webnovel.py checkers list
python .opencode/scripts/webnovel.py checkers validate
```

Expected: both commands work identically to before the split.

- [ ] **Step 5: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_checkers_manager.py -v
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 7 checkers tests pass, full suite unchanged at 493/12.

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/data_modules/checkers_cli.py .opencode/scripts/data_modules/checkers_manager.py .opencode/scripts/data_modules/webnovel.py
git commit -m "refactor: split checkers CLI commands into checkers_cli.py"
```

---

### Final Verification

- [ ] **Run full suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 493 passed, 12 failed (unchanged, all pre-existing).
