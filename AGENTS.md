# AGENTS.md - Webnovel Writer 开发指南

## 项目概述

Webnovel Writer 是基于 OpenCode 的长篇网文 AI 创作系统，降低 AI 写作中的"遗忘"和"幻觉"，支持长周期连载创作。

## 快速开始

```bash
# 推荐：跨平台安装（Linux/macOS/Windows）
python install.py
```

## 构建/测试/开发命令

```bash
# 安装依赖
pip install -e .

# 运行所有测试
pytest

# 运行单个测试（推荐方式）
pytest .opencode/scripts/data_modules/tests/test_config.py::test_config_paths_and_defaults

# 运行特定测试文件
pytest .opencode/scripts/data_modules/tests/test_api_client.py

# 运行测试并生成覆盖率报告（最低要求 90%）
pytest --cov --cov-report=term-missing .opencode/scripts/data_modules/tests/

# 只运行失败的测试
pytest --lf

# 运行 publisher 模块测试（需要先安装 playwright）
pip install playwright
pytest .opencode/scripts/data_modules/tests/test_publisher.py -v

# Windows: 运行测试脚本
powershell -File .opencode/scripts/run_tests.ps1

# Lint 检查
python -m py_compile .opencode/scripts/webnovel.py
python -m py_compile .opencode/scripts/publisher/*.py
```

**测试配置**:
- 测试路径: `.opencode/scripts/data_modules/tests`
- Python 路径: `.opencode/scripts`
- 覆盖率要求: 最低 90%

## 代码风格规范

### 文件头
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块描述（中文）
"""
```

### 导入顺序: 标准库 → 第三方 → 本地（相对导入）
```python
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

import aiohttp
import pytest

try:
    from ..runtime_compat import normalize_windows_path
except ImportError:
    from runtime_compat import normalize_windows_path

from .config import get_config
```

### 类型注解: 始终使用显式类型注解
```python
def process_entities(entities: List[EntityState]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    return result
```

### 错误处理: 捕获具体异常，避免裸 except
```python
try:
    config = DataModulesConfig.from_project_root(project_root)
except ValueError as e:
    logger.error("Invalid project root: %s", e)
    raise
except PermissionError as e:
    logger.error("Permission denied: %s", e)
    raise
```

### 日志记录: 使用 `logging.getLogger(__name__)`
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Processing chapter %d", chapter_num)
logger.warning("Missing field: %s", field_name)
logger.exception("Unexpected error: %s", e)
```

### 命名约定
- 函数/方法: `snake_case` (如 `load_state`, `process_chapter`)
- 类名: `PascalCase` (如 `StatusReporter`, `FanqieClient`)
- 常量: `UPPER_SNAKE_CASE` (如 `MAX_RETRIES`, `DEFAULT_PORT`)
- 私有变量: `_private_var` (单下划线前缀)

### 路径处理: 使用 pathlib
```python
from pathlib import Path
config_dir = project_root / ".webnovel"
state_file = config_dir / "state.json"
```

### 异常兼容: 使用 try/except 处理跨平台兼容
```python
try:
    from ..runtime_compat import normalize_windows_path
except ImportError:
    from runtime_compat import normalize_windows_path
```

### 文档注释: 所有公共方法添加 docstring
```python
def load_state(self) -> bool:
    """
    加载 state.json 文件。

    Returns:
        True 表示加载成功，False 表示失败。

    Raises:
        FileNotFoundError: state.json 不存在
        json.JSONDecodeError: JSON 格式错误
    """
```

## 项目结构

```
项目目录/
├── .opencode/              # OpenCode 配置
│   ├── agents/           # Agent 定义
│   ├── checkers/         # 审查器配置驱动
│   ├── skills/           # 10个 Skills
│   │   ├── webnovel-publish/  # 番茄小说发布
│   │   └── webnovel-dashboard/ # 看板
│   ├── scripts/          # Python 核心脚本
│   │   ├── publisher/  # 番茄发布模块
│   │   └── data_modules/ # 核心模块
│   ├── references/       # 参考文档
│   ├── genres/           # 38+ 题材参考
│   └── templates/        # 输出模板
├── opencode.json        # Agent 配置
├── .env                 # API 配置（模板）
├── install.py          # 跨平台安装脚本
└── requirements.txt    # Python 依赖
```

## 关键约定

1. **状态管理**: 使用 `DataModulesConfig` 进行配置；使用 `StateManager` 管理小说状态
2. **RAG 流程**: 查询 → 检索 → 重排 → 构建上下文
3. **实体追踪**: 所有新实体必须通过 `EntityLinker` 注册
4. **文件编码**: 所有文件使用 UTF-8
5. **中文文档**: 所有用户面向的字符串和文档使用中文
6. **审查器**: 通过 registry.yaml 配置，由 agents/*.md 实现
7. **插件系统**: 通过 manifest.json 注册扩展点，支持 Agent/Skill/Checker/Publisher

## 插件系统

### 目录结构
```
.opencode/plugins/<plugin-id>/
├── manifest.json    # 必需：插件元数据
├── __init__.py     # 必需：Python 包入口
├── checkers/      # 可选：自定义审查器
├── skills/        # 可选：自定义技能命令
├── publishers/    # 可选：自定义发布平台
└── templates/     # 可选：自定义题材模板
```

### manifest.json 关键字段
- `id`: 插件唯一标识（使用下划线，如 `com_example_my_plugin`）
- `name`: 插件名称（中文）
- `version`: 语义化版本（如 `1.0.0`）
- `core_api_version`: 兼容的核心版本（如 `>=2.0.0,<3.0.0`）
- `entry_points`: 扩展点定义
- `permissions`: 权限声明

### 扩展点类型
- **agents**: 自定义 Agent（继承 `BaseAgent`）
- **skills**: 自定义 Skill（继承 `BaseSkill`）
- **checkers**: 自定义 Checker（继承 `BaseChecker`）
- **publishers**: 自定义 Publisher（继承 `BasePublisher`）

### 插件管理命令
```bash
# 列出已安装插件
python .opencode/scripts/webnovel.py plugin list

# 安装插件（Git URL 或本地路径）
python .opencode/scripts/webnovel.py plugin install https://github.com/user/plugin.git

# 查看插件详情
python .opencode/scripts/webnovel.py plugin info <plugin-id>

# 卸载插件
python .opencode/scripts/webnovel.py plugin remove <plugin-id>

# 重新加载所有插件
python .opencode/scripts/webnovel.py plugin reload

# 重新加载指定插件
python .opencode/scripts/webnovel.py plugin reload <plugin-id>

# 在 OpenCode 中使用
/webnovel-plugin list
/webnovel-plugin install <source>
```

## 测试最佳实践

1. 使用 `tmp_path` fixture 进行文件系统测试
2. 使用 `monkeypatch` 进行环境变量模拟
3. 测试成功和错误路径
4. 异步测试需要 `@pytest.mark.asyncio` 装饰器
5. 测试函数命名: `test_function_name_when_condition()`
6. 使用 pytest.skip 跳过需要可选依赖的测试

## 常用运维命令

```bash
# 索引重建
python .opencode/scripts/webnovel.py index process-chapter --chapter 1

# 索引统计
python .opencode/scripts/webnovel.py index stats

# 健康报告（Markdown）
python .opencode/scripts/webnovel.py status --focus all

# 健康报告（JSON）
python .opencode/scripts/status_reporter.py --json --pretty --project-root <path>

# 向量重建
python .opencode/scripts/webnovel.py rag index-chapter --chapter 1

# 番茄小说发布
python .opencode/scripts/webnovel.py publish setup-browser
python .opencode/scripts/webnovel.py publish upload --book-id <id> --range "1-10" --project-root <path>

# 插件管理
python .opencode/scripts/webnovel.py plugin list
python .opencode/scripts/webnovel.py plugin install <source>
python .opencode/scripts/webnovel.py plugin remove <plugin-id>
```

## Git 工作流

```bash
# 提交前运行测试
pytest

# 提交信息规范
git commit -m "type: description"

# type: feat, fix, docs, refactor, test, chore
```
