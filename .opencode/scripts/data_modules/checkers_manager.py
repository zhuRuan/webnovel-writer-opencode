#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查器配置管理器

功能：
- 加载审查器注册表（registry.yaml）
- 列出审查器（支持按模式、类别过滤）
- 验证配置完整性
- 创建新审查器模板
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from .condition_evaluator import ConditionEvaluator, TriggerCondition

logger = getLogger(__name__)


class CodeCheckerProtocol:
    """Code Checker 协议接口"""
    
    def check_chapter(self, chapter: int, content: str, chapter_context: Dict = None) -> List[Dict]:
        """检查章节并返回问题列表"""
        raise NotImplementedError


@dataclass
class CodeCheckerResult:
    """Code Checker 执行结果"""
    checker_id: str
    passed: bool
    issues: List[Dict]
    blocked: bool = False  # 是否硬阻塞（critical 问题）


class CheckersManager:
    """审查器配置管理器"""
    
    # 预注册的 code checkers
    _code_checkers: Dict[str, Tuple[Callable, Dict]] = {}

    def __init__(self, checkers_dir: Optional[Path] = None):
        if checkers_dir is None:
            checkers_dir = Path(__file__).resolve().parent.parent.parent / "checkers"
        self.checkers_dir = checkers_dir
        self.registry_path = checkers_dir / "registry.yaml"
        self.schema_path = checkers_dir / "schema.yaml"
        self.agents_dir = checkers_dir / "agents"
        self.templates_dir = checkers_dir / "templates"

    @classmethod
    def register_code_checker(
        cls,
        checker_id: str,
        checker_func: Callable,
        config: Optional[Dict] = None
    ) -> None:
        """
        注册 code checker（运行在 LLM agent 之前的确定性检查层）
        
        Args:
            checker_id: 唯一标识符
            checker_func: 检查函数 (chapter, content, chapter_context) -> List[Dict]
            config: 配置参数 {severity_threshold, block_on_critical, ...}
        """
        if config is None:
            config = {}
        cls._code_checkers[checker_id] = (checker_func, config)
        logger.info(f"注册 code checker: {checker_id}")

    @classmethod
    def register_world_consistency_checker(
        cls,
        config: Optional[Dict] = None
    ) -> None:
        """
        注册 WorldConsistencyChecker 作为 code checker
        
        Args:
            config: 配置参数
        """
        from .world_consistency_checker import WorldConsistencyChecker
        
        def world_checker_wrapper(
            chapter: int,
            content: str,
            chapter_context: Optional[Dict] = None
        ) -> List[Dict]:
            from .world_state_tracker import WorldStateTracker
            tracker = WorldStateTracker()
            checker = WorldConsistencyChecker(config, tracker)
            issues = checker.check_chapter(chapter, content, chapter_context)
            return [
                {
                    "issue_id": issue.issue_id,
                    "severity": issue.severity,
                    "message": issue.message,
                    "location": issue.location,
                    "suggestion": issue.suggestion,
                }
                for issue in issues
            ]
        
        default_config = {
            "severity_threshold": "high",
            "block_on_critical": True,
        }
        if config:
            default_config.update(config)
        
        cls.register_code_checker(
            "world-consistency",
            world_checker_wrapper,
            default_config
        )

    @classmethod
    def run_code_checkers(
        cls,
        chapter: int,
        content: str,
        chapter_context: Optional[Dict] = None
    ) -> List[CodeCheckerResult]:
        """
        运行所有已注册的 code checkers
        
        Args:
            chapter: 章节号
            content: 章节内容
            chapter_context: 章节上下文
        
        Returns:
            执行结果列表
        """
        results = []
        for checker_id, (checker_func, config) in cls._code_checkers.items():
            try:
                issues = checker_func(chapter, content, chapter_context)
                severity_threshold = config.get("severity_threshold", "critical")
                block_on_critical = config.get("block_on_critical", True)
                
                has_blocking = False
                if block_on_critical:
                    for issue in issues:
                        if issue.get("severity") in ["critical", "high"]:
                            has_blocking = True
                            break
                
                results.append(CodeCheckerResult(
                    checker_id=checker_id,
                    passed=len(issues) == 0,
                    issues=issues,
                    blocked=has_blocking
                ))
            except Exception as e:
                logger.error(f"Code checker {checker_id} 执行失败: {e}")
                results.append(CodeCheckerResult(
                    checker_id=checker_id,
                    passed=False,
                    issues=[{"error": str(e)}],
                    blocked=False
                ))
        
        return results

    @classmethod
    def get_code_checkers(cls) -> Dict[str, Tuple[Callable, Dict]]:
        """获取已注册的 code checkers"""
        return cls._code_checkers.copy()

    @classmethod
    def run_layered_checkers(
        cls,
        chapter: int,
        content: str,
        chapter_context: Optional[Dict] = None,
        mode: str = "standard",
        run_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        分层运行审查器：Code Layer → LLM Agents
        
        1. 先运行 code checkers（确定性检查，快速）
        2. 若有 blocked=True → 立即返回阻塞结果
        3. 否则运行 LLM agents（可选）
        
        Args:
            chapter: 章节号
            content: 章节内容
            chapter_context: 章节上下文
            mode: 审查模式 (standard/minimal/full)
            run_llm: 是否运行 LLM agents
        
        Returns:
            {
                "layer": "code" | "llm" | "fallback",
                "blocked": bool,
                "code_results": [...],
                "llm_results": [...],
                "issues": [...],
            }
        """
        code_results = cls.run_code_checkers(chapter, content, chapter_context)
        
        blocked_results = [r for r in code_results if r.blocked]
        if blocked_results:
            logger.warning(f"[CheckersManager] CODE LAYER BLOCKING: {len(blocked_results)} issues")
            return {
                "layer": "code",
                "blocked": True,
                "code_results": code_results,
                "llm_results": [],
                "issues": [
                    issue
                    for r in blocked_results
                    for issue in r.issues
                ],
            }
        
        if not run_llm:
            logger.debug(f"[CheckersManager] Code layer passed, LLM skipped")
            return {
                "layer": "code",
                "blocked": False,
                "code_results": code_results,
                "llm_results": [],
                "issues": [],
            }
        
        logger.info(f"[CheckersManager] === LLM Layer Start: chapter={chapter}, mode={mode} ===")
        llm_results = cls.run_llm_agents(chapter, content, chapter_context, mode)
        
        has_blocking_llm = any(
            r.get("passed") is False and r.get("overall_score", 100) < 60
            for r in llm_results
        ) if llm_results else False
        
        logger.info(f"[CheckersManager] === LLM Layer End: blocked={has_blocking_llm}, agents={len(llm_results)} ===")
        
        return {
            "layer": "llm",
            "blocked": has_blocking_llm,
            "code_results": code_results,
            "llm_results": llm_results,
            "issues": [
                issue
                for r in llm_results
                for issue in r.get("issues", [])
            ],
        }

    @classmethod
    def run_llm_agents(
        cls,
        chapter: int,
        content: str,
        chapter_context: Optional[Dict] = None,
        mode: str = "standard",
    ) -> List[Dict]:
        """
        运行 LLM agents
        
        Args:
            chapter: 章节号
            content: 章节内容
            chapter_context: 章节上下文
            mode: 审查模式
        
        Returns:
            LLM agents 执行结果列表
        """
        try:
            from .llm_invoker import LLMInvoker, AgentInput
        except ImportError:
            logger.warning("LLMInvoker 不可用")
            return []
        
        invoker = LLMInvoker()
        if not invoker.is_enabled():
            logger.info("LLM 不可用，跳过 LLM agents")
            return []
        
        registry = cls().load_registry()
        checkers = registry.get("checkers", {})
        
        llm_agents = []
        for checker_id, config in checkers.items():
            if not config.get("enabled", True):
                continue
            if config.get("category") == "llm":
                llm_agents.append(checker_id)
        
        results = []
        for agent_id in llm_agents:
            agent_file = cls().agents_dir / f"{agent_id}.md"
            if not agent_file.exists():
                continue
            
            logger.debug(f"[LLM Agent] 调用: {agent_id}")
            
            prompt = agent_file.read_text(encoding="utf-8")
            input_data = AgentInput(
                chapter=chapter,
                chapter_title=chapter_context.get("title", "") if chapter_context else "",
                content=content,
                project_root=chapter_context.get("project_root", "") if chapter_context else "",
                context=chapter_context or {},
            )
            
            output = invoker.invoke(agent_id, prompt, input_data)
            
            logger.debug(f"[LLM Agent] 完成: {agent_id}, score={output.overall_score}, passed={output.passed}")
            
            results.append({
                "agent_id": output.agent_id,
                "chapter": output.chapter,
                "overall_score": output.overall_score,
                "passed": output.passed,
                "issues": output.issues,
                "summary": output.summary,
            })
        
        return results

    def load_registry(self) -> Dict[str, Any]:
        """加载审查器注册表"""
        if not self.registry_path.exists():
            raise FileNotFoundError(f"注册表不存在: {self.registry_path}")
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_schema(self) -> Dict[str, Any]:
        """加载 Schema 定义"""
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema 不存在: {self.schema_path}")
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_checkers(
        self,
        mode: Optional[str] = None,
        category: Optional[str] = None,
        enabled_only: bool = True,
        format: str = "text"
    ) -> List[Dict[str, Any]]:
        """
        列出审查器

        Args:
            mode: 审查模式 (standard/minimal/full)
            category: 类别 (core/conditional)
            enabled_only: 只显示启用的
            format: 输出格式 (text/json)
        """
        registry = self.load_registry()
        checkers = registry.get("checkers", {})
        modes = registry.get("modes", {})

        result: List[Dict[str, Any]] = []

        for checker_id, checker_config in checkers.items():
            if enabled_only and not checker_config.get("enabled", True):
                continue

            if category and checker_config.get("category") != category:
                continue

            # 按模式过滤
            if mode and mode in modes:
                mode_config = modes[mode]
                include_categories = mode_config.get("include_categories", [])
                force_conditional = mode_config.get("force_conditional", False)

                # core 类型
                if checker_config.get("category") == "core":
                    if "core" not in include_categories:
                        continue

                # conditional 类型
                elif checker_config.get("category") == "conditional":
                    if "conditional" not in include_categories:
                        continue
                    # full 模式下强制启用 conditional
                    if not force_conditional and checker_config.get("category") == "conditional":
                        # 需要检查触发条件，这里简化处理
                        pass

            result.append({
                "id": checker_id,
                "name": checker_config.get("name", checker_id),
                "category": checker_config.get("category", "unknown"),
                "description": checker_config.get("description", ""),
                "triggers": checker_config.get("triggers", []),
                "enabled": checker_config.get("enabled", True),
            })

        return result

    def get_checkers_for_mode(self, mode: str) -> List[str]:
        """
        获取指定模式应启用的审查器 ID 列表

        Args:
            mode: standard | minimal | full

        Returns:
            审查器 ID 列表
        """
        registry = self.load_registry()
        modes = registry.get("modes", {})
        checkers = registry.get("checkers", {})

        if mode not in modes:
            raise ValueError(f"未知模式: {mode}，可用模式: {list(modes.keys())}")

        mode_config = modes[mode]
        include_categories = mode_config.get("include_categories", [])
        force_conditional = mode_config.get("force_conditional", False)

        result: List[str] = []
        for checker_id, checker_config in checkers.items():
            if not checker_config.get("enabled", True):
                continue

            category = checker_config.get("category", "unknown")
            if category == "core" and "core" in include_categories:
                result.append(checker_id)
            elif category == "conditional" and "conditional" in include_categories:
                if force_conditional:
                    result.append(checker_id)
                else:
                    # standard 模式下需要根据触发条件决定
                    # 这里返回所有 conditional，调用方需要进一步判断
                    result.append(checker_id)

        return result

    def validate(self) -> Dict[str, Any]:
        """
        验证配置完整性

        Returns:
            验证结果
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 检查注册表是否存在
        if not self.registry_path.exists():
            errors.append(f"注册表不存在: {self.registry_path}")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # 检查 Schema 是否存在
        if not self.schema_path.exists():
            warnings.append(f"Schema 不存在: {self.schema_path}")

        registry = self.load_registry()
        checkers = registry.get("checkers", {})
        modes = registry.get("modes", {})

        # 检查是否有审查器
        if not checkers:
            errors.append("注册表中没有定义任何审查器")

        # 检查每个审查器
        for checker_id, checker_config in checkers.items():
            # 检查必需字段
            if "name" not in checker_config:
                warnings.append(f"审查器 {checker_id} 缺少 name 字段")
            if "file" not in checker_config:
                errors.append(f"审查器 {checker_id} 缺少 file 字段")
            if "category" not in checker_config:
                errors.append(f"审查器 {checker_id} 缺少 category 字段")

            # 检查文件是否存在
            if "file" in checker_config:
                agent_file = self.checkers_dir / checker_config["file"]
                if not agent_file.exists():
                    errors.append(f"审查器文件不存在: {agent_file}")

            # 检查 category
            if "category" in checker_config:
                if checker_config["category"] not in ["core", "conditional"]:
                    errors.append(f"审查器 {checker_id} 的 category 必须是 core 或 conditional")

        # 检查模式配置
        for mode_name, mode_config in modes.items():
            if "include_categories" not in mode_config:
                errors.append(f"模式 {mode_name} 缺少 include_categories 字段")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checker_count": len(checkers),
            "mode_count": len(modes),
        }

    def should_trigger_checker(
        self,
        checker_id: str,
        chapter_context: Dict[str, Any]
    ) -> bool:
        """
        判断 conditional 审查器是否应该触发
        
        Args:
            checker_id: 审查器 ID
            chapter_context: 章节上下文
        
        Returns:
            是否应该触发
        """
        registry = self.load_registry()
        checkers = registry.get("checkers", {})
        
        if checker_id not in checkers:
            return False
        
        checker_config = checkers[checker_id]
        if checker_config.get("category") != "conditional":
            return True
        
        triggers = checker_config.get("triggers", [])
        if not triggers:
            return True
        
        evaluator = ConditionEvaluator(chapter_context)
        
        conditions = []
        for trigger in triggers:
            if isinstance(trigger, str):
                conditions.append(TriggerCondition(type="condition", expression=trigger))
            elif isinstance(trigger, dict):
                trigger_type = trigger.get("type", "condition")
                if trigger_type == "condition":
                    conditions.append(TriggerCondition(
                        type="condition",
                        expression=trigger.get("expression", "")
                    ))
                elif trigger_type == "keyword":
                    conditions.append(TriggerCondition(
                        type="keyword",
                        keywords=trigger.get("keywords", []),
                        min_count=trigger.get("min_count", 1)
                    ))
        
        return evaluator.evaluate(conditions)

    def get_schema_for_checker(self, checker_id: str) -> Optional[Dict[str, Any]]:
        """获取指定审查器的 metrics Schema"""
        schema = self.load_schema()
        return schema.get("metrics_definitions", {}).get(checker_id)

    def create_checker(
        self,
        checker_id: str,
        name: str,
        category: str = "core",
        description: str = "",
        triggers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        创建新审查器

        Args:
            checker_id: 审查器 ID
            name: 审查器名称
            category: core | conditional
            description: 描述
            triggers: 触发条件列表

        Returns:
            创建结果
        """
        # 检查 ID 是否已存在
        registry = self.load_registry()
        if checker_id in registry.get("checkers", {}):
            return {
                "success": False,
                "error": f"审查器 {checker_id} 已存在",
            }

        # 创建审查器文件
        template_path = self.templates_dir / "agent-template.md"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            agent_content = template_content.replace("{checker-id}", checker_id)
            agent_content = agent_content.replace("{中文名称}", name)
            agent_content = agent_content.replace("{检查功能描述}", description)
        else:
            agent_content = f"""---
description: {description}
mode: subagent
temperature: 0.1
permission:
  read: allow
  grep: allow
  edit: deny
  bash: ask
---

# {checker_id} ({name})

> **职责**: {description}
> **输出格式**: 遵循 `../schema.yaml` 统一 Schema

## 检查范围
...

## 执行流程
...

## metrics 定义
```json
{{"metrics": {{}}}}
```

## 禁止事项
...

## 成功标准
...
"""

        agent_file = self.agents_dir / f"{checker_id}.md"
        agent_file.write_text(agent_content, encoding="utf-8")

        # 更新注册表
        new_checker = {
            "name": name,
            "file": f"agents/{checker_id}.md",
            "category": category,
            "enabled": True,
            "description": description,
            "triggers": triggers or [],
        }

        registry.setdefault("checkers", {})[checker_id] = new_checker

        with open(self.registry_path, "w", encoding="utf-8") as f:
            yaml.dump(registry, f, allow_unicode=True, default_flow_style=False)

        return {
            "success": True,
            "agent_file": str(agent_file),
            "checker_id": checker_id,
        }


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
    except FileNotFoundError as e:
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
            if checker.get("triggers"):
                print(f"    触发: {', '.join(checker['triggers'][:2])}")
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
    p_list.add_argument("--mode", "-m", choices=["standard", "minimal", "full"], help="审查模式")
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
