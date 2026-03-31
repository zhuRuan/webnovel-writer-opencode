# 插件开发指南

本文档详细介绍如何为 Webnovel Writer 开发自定义插件。

## 概述

插件系统允许开发者通过扩展点机制为 Webnovel Writer 添加自定义功能，支持四种扩展类型：

- **Agent**: 智能代理，处理特定创作任务
- **Skill**: 技能命令，通过斜杠命令调用
- **Checker**: 审查器，检查章节质量
- **Publisher**: 发布平台，上传章节到第三方平台

## 目录结构

```
my_plugin/
├── manifest.json          # 必需：插件元数据
├── __init__.py           # 必需：Python 包入口
├── requirements.txt      # 可选：额外依赖
├── README.md             # 可选：插件说明
├── agents/               # 可选：自定义 Agent
│   └── my_agent.py
├── skills/               # 可选：自定义 Skill
│   └── my_skill.py
├── checkers/             # 可选：自定义 Checker
│   └── my_checker.py
├── publishers/          # 可选：自定义 Publisher
│   └── my_publisher.py
└── templates/            # 可选：自定义模板
    └── my_genre.yaml
```

## manifest.json 规范

```json
{
  "id": "com_example_my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能描述",
  "author": "作者名",
  "license": "MIT",
  "core_api_version": ">=2.0.0,<3.0.0",
  "dependencies": {
    "plugins": [],
    "python_packages": []
  },
  "entry_points": {
    "agents": [
      {
        "id": "my-agent",
        "class": "agents.my_agent.MyAgent",
        "description": "我的智能代理"
      }
    ],
    "skills": [
      {
        "id": "my-skill",
        "command": "/my-skill",
        "class": "skills.my_skill.MySkill",
        "description": "我的技能命令"
      }
    ],
    "checkers": [
      {
        "id": "my-checker",
        "class": "checkers.my_checker.MyChecker",
        "category": "core",
        "description": "我的审查器"
      }
    ],
    "publishers": [
      {
        "id": "my-platform",
        "name": "我的平台",
        "class": "publishers.my_publisher.MyPublisher"
      }
    ]
  },
  "permissions": [
    "read:chapters",
    "write:chapters"
  ]
}
```

### 核心字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 插件唯一标识，使用下划线分隔（如 `com_example_xxx`） |
| `name` | string | 是 | 插件显示名称 |
| `version` | string | 是 | 语义化版本号 |
| `core_api_version` | string | 否 | 兼容的核心版本规范（如 `>=2.0.0,<3.0.0`） |
| `entry_points` | object | 否 | 扩展点定义 |
| `permissions` | array | 否 | 权限声明列表 |

### 权限列表

| 权限 | 说明 |
|------|------|
| `read:chapters` | 读取章节内容 |
| `write:chapters` | 写入/修改章节内容 |
| `read:settings` | 读取配置 |
| `network:requests` | 发起网络请求 |

## 基类接口

### BaseChecker

```python
from data_modules.plugin_base import BaseChecker
from typing import Dict, Any

class MyChecker(BaseChecker):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        # 初始化配置

    async def check(self, chapter_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查章节质量

        Args:
            chapter_text: 章节正文
            context: 上下文信息

        Returns:
            检查结果字典，包含 passed/issues/score/suggestions
        """
        issues = []
        
        # 检查逻辑...
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "score": 100,
            "suggestions": []
        }
```

### BaseSkill

```python
from data_modules.plugin_base import BaseSkill
from typing import Dict, Any, List

class MySkill(BaseSkill):
    command = "/my-skill"

    def __init__(self, context: Dict[str, Any]):
        super().__init__(context)

    async def execute(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """执行技能命令"""
        return {
            "message": "执行结果",
            "status": "success"
        }

    def get_help(self) -> str:
        """返回帮助信息"""
        return "用法: /my-skill <参数>"
```

### BaseAgent

```python
from data_modules.plugin_base import BaseAgent
from typing import Dict, Any

class MyAgent(BaseAgent):
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Agent 任务"""
        return {
            "result": "处理结果",
            "data": {}
        }
```

### BasePublisher

```python
from data_modules.plugin_base import BasePublisher
from typing import Dict, Any, List

class MyPublisher(BasePublisher):
    async def authenticate(self, credentials: Dict[str, str]) -> bool:
        """登录验证"""
        self.authenticated = True
        return True

    async def get_books(self) -> List[Dict[str, Any]]:
        """获取书籍列表"""
        return []

    async def create_book(self, title: str, genre: str, synopsis: str) -> Dict[str, Any]:
        """创建新书"""
        return {"id": "book_id"}

    async def upload_chapter(self, book_id: str, chapter: Dict[str, Any]) -> Dict[str, Any]:
        """上传章节"""
        return {"success": True}
```

## 开发示例：敏感词检查器

### 1. 创建目录结构

```
my_sensitive_checker/
├── manifest.json
├── __init__.py
└── checkers/
    └── sensitive_checker.py
```

### 2. 编写 manifest.json

```json
{
  "id": "com_example_sensitive_checker",
  "name": "敏感词检查器",
  "version": "1.0.0",
  "description": "检查章节中是否包含敏感词",
  "author": "示例作者",
  "core_api_version": ">=2.0.0,<3.0.0",
  "entry_points": {
    "checkers": [
      {
        "id": "sensitive-word-checker",
        "class": "checkers.sensitive_checker.SensitiveWordChecker",
        "category": "content",
        "description": "敏感词检查"
      }
    ]
  },
  "permissions": ["read:chapters"]
}
```

### 3. 编写审查器代码

```python
# checkers/sensitive_checker.py
from typing import Any, Dict, List
from data_modules.plugin_base import BaseChecker


class SensitiveWordChecker(BaseChecker):
    SENSITIVE_WORDS = {"政治相关": ["敏感词1"], "暴力血腥": ["暴力词1"]}

    async def check(self, chapter_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        issues = []
        
        for category, words in self.SENSITIVE_WORDS.items():
            for word in words:
                if word in chapter_text:
                    issues.append({
                        "type": "sensitive_word",
                        "word": word,
                        "category": category,
                        "severity": "error"
                    })

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "score": max(0, 100 - len(issues) * 10),
            "suggestions": ["请移除敏感词"] if issues else []
        }
```

### 4. 编写入口文件

```python
# __init__.py
from .checkers.sensitive_checker import SensitiveWordChecker

__all__ = ["SensitiveWordChecker"]
```

## 安装与测试

### 本地安装

```bash
# 复制到插件目录
cp -r my_sensitive_checker .opencode/plugins/

# 验证加载
python .opencode/scripts/webnovel.py plugin list
```

### 从 Git 安装

```bash
python .opencode/scripts/webnovel.py plugin install https://github.com/username/plugin.git
```

## 插件市场

### 什么是插件市场

插件市场是一个集中管理插件的索引服务，用户可以通过插件名称一键安装社区插件，无需手动查找 Git 仓库地址。

### 使用市场安装插件

```bash
# 从市场安装插件（插件名）
python .opencode/scripts/webnovel.py plugin install <plugin-name>

# 从市场安装（插件 ID）
python .opencode/scripts/webnovel.py plugin install <plugin-id>

# 强制刷新市场缓存后安装
python .opencode/scripts/webnovel.py plugin install <plugin-name> --force
```

### 从 Git URL 安装（原有方式）

```bash
# 从 Git 仓库安装
python .opencode/scripts/webnovel.py plugin install https://github.com/username/plugin.git

# 从本地路径安装
python .opencode/scripts/webnovel.py plugin install /path/to/plugin
```

### 发布插件到市场

1. 将插件代码推送到独立的 Git 仓库（如 GitHub）。
2. 向插件市场索引仓库提交 PR，在 `plugins.json` 中添加插件条目：

```json
{
  "id": "com_example_my_plugin",
  "name": "我的插件",
  "description": "插件功能描述",
  "author": "作者名",
  "license": "MIT",
  "repo": "https://github.com/username/my-plugin.git",
  "tags": ["checker", "content"]
}
```

3. 等待维护者合并 PR。合并后，用户即可通过市场安装。

### 插件市场索引

- 官方网站：https://github.com/webnovel-writer/plugins
- 缓存位置：`.opencode/cache/plugins.json`

## 调试技巧

1. **查看日志**：插件加载时会输出日志，使用 `--verbose` 查看详细信息

2. **手动加载测试**：
```python
from data_modules.plugin_manager import PluginManager

pm = PluginManager()
pm.load_all_plugins()

# 获取插件
checker_class = pm.get_checker("sensitive-word-checker")
```

3. **清单验证**：
```bash
python .opencode/scripts/webnovel.py plugin info <plugin-id>
```

## 注意事项

1. **命名规范**：插件目录名使用下划线（如 `demo_checker`），ID 使用点分格式（如 `com_example_demo`）

2. **版本兼容性**：声明的 `core_api_version` 应与当前核心版本匹配

3. **权限最小化**：只声明必要的权限

4. **依赖管理**：避免引入大型依赖，优先使用标准库

## 相关链接

- [插件管理命令](/webnovel-plugin)
- [审查器注册表](../checkers/registry.yaml)
