---
title: Webnovel Writer 插件开发完整指南
last_updated: 2026-04-01
compatible_core_version: >=2.0.0,<3.0.0
---

# Webnovel Writer 插件开发完整指南

## 1. 概述

Webnovel Writer 的插件系统允许开发者以标准化的方式扩展 AI 创作功能。插件可以新增以下四种扩展点：

- **Agent**：智能代理，用于检索上下文、生成内容等复杂任务。
- **Skill**：命令技能，通过斜杠命令（如 `/my-command`）在 OpenCode 中调用。
- **Checker**：审查器，用于检查章节质量（一致性、OOC、爽点等）。
- **Publisher**：发布平台，支持将章节上传到第三方写作平台（如番茄、起点）。

插件以独立目录的形式存放在 `.opencode/plugins/` 下，通过 `manifest.json` 声明元数据和扩展点。系统会自动加载插件，并提供热重载、依赖管理等功能。

---

## 2. 插件结构

一个标准的插件目录结构如下：

```
my-plugin/
├── manifest.json           # 必需：插件元数据
├── __init__.py             # 必需：Python 包标识（可空）
├── requirements.txt        # 可选：Python 依赖
├── README.md               # 可选：插件说明
├── agents/                 # 可选：Agent 实现
│   └── my_agent.py
├── skills/                 # 可选：Skill 实现
│   └── my_skill.py
├── checkers/               # 可选：Checker 实现
│   └── my_checker.py
├── publishers/             # 可选：Publisher 实现
│   └── my_publisher.py
├── templates/              # 可选：题材模板
│   └── my_genre.yaml
└── static/                 # 可选：Dashboard 静态资源
    └── my_widget.js
```

**重要**：所有 Python 文件应使用 UTF-8 编码，并遵循 PEP 8 规范。

---

## 3. manifest.json 规范

`manifest.json` 是插件的核心配置文件，必须位于插件根目录。

### 3.1 完整字段示例

```json
{
  "id": "com.example.my-plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能描述",
  "author": "作者名",
  "license": "GPL-3.0",
  "core_api_version": ">=2.0.0,<3.0.0",
  "dependencies": {
    "plugins": ["com.example.other-plugin@^1.0.0"],
    "python_packages": ["requests>=2.25.0"]
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
        "category": "content",
        "description": "我的审查器"
      }
    ],
    "publishers": [
      {
        "id": "my-platform",
        "name": "我的平台",
        "class": "publishers.my_publisher.MyPublisher"
      }
    ],
    "templates": [
      {
        "id": "my-genre",
        "path": "templates/my_genre.yaml",
        "description": "我的题材模板"
      }
    ]
  },
  "permissions": [
    "read:chapters",
    "write:chapters",
    "read:settings",
    "network:requests"
  ],
  "hooks": [
    {
      "hook": "before_chapter_write",
      "handler": "hooks.before_write"
    }
  ],
  "dashboard_widgets": [
    {
      "id": "my-widget",
      "title": "我的组件",
      "component": "static/widget.js"
    }
  ]
}
```

### 3.2 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 插件唯一标识，推荐使用反向域名格式（如 `com.example.my-plugin`）。 |
| `name` | string | 是 | 插件显示名称。 |
| `version` | string | 是 | 语义化版本号（如 `1.0.0`）。 |
| `description` | string | 否 | 简要描述插件功能。 |
| `author` | string | 否 | 作者名称或 GitHub 账号。 |
| `license` | string | 否 | 开源许可证标识（如 `MIT`, `GPL-3.0`）。 |
| `core_api_version` | string | 是 | 兼容的核心 API 版本范围，使用 `packaging` 解析。例如 `>=2.0.0,<3.0.0`。 |
| `dependencies` | object | 否 | 声明依赖的其他插件或 Python 包。 |
| `entry_points` | object | 是 | 注册扩展点。各扩展点类型需提供相应配置。 |
| `permissions` | array | 否 | 插件需要的权限列表（如 `read:chapters`），用于未来权限沙箱。 |
| `hooks` | array | 否 | 注册生命周期钩子（预留功能）。 |
| `dashboard_widgets` | array | 否 | 向 Dashboard 添加自定义 UI 组件。 |

### 3.3 权限说明

**当前版本**：`permissions` 字段仅作为声明，尚未强制校验，插件实际能访问的资源取决于其代码。我们计划在后续版本中引入基于权限声明的沙箱机制，届时插件将受到更严格的限制。建议插件作者只声明必要的权限，为未来兼容做好准备。

---

## 4. 扩展点实现

### 4.1 Agent

Agent 负责复杂的上下文处理、内容生成等任务。基类定义：

```python
# agents/my_agent.py
from data_modules.plugin_base import BaseAgent

class MyAgent(BaseAgent):
    async def execute(self, input_data: dict) -> dict:
        """
        input_data 结构：
        {
            "context": {...},    # 当前写作上下文（章节、设定等）
            "user_input": "..."  # 用户输入
        }
        """
        # 实现你的逻辑
        result = {
            "context": {...},    # 返回增强后的上下文
            "suggestions": [...] # 可选的建议内容
        }
        return result
```

### 4.2 Skill

Skill 对应 OpenCode 中的斜杠命令。基类定义：

```python
# skills/my_skill.py
from data_modules.plugin_base import BaseSkill

class MySkill(BaseSkill):
    command = "/my-skill"  # 命令名称

    async def execute(self, args: list, **kwargs) -> dict:
        """
        args: 命令参数列表，如 ["arg1", "arg2"]
        kwargs: 可能包含 --flag 等参数
        """
        # 处理命令
        return {
            "message": "命令执行结果",
            "status": "success"
        }
```

### 4.3 Checker

Checker 用于审查章节质量。基类定义：

```python
# checkers/my_checker.py
from data_modules.plugin_base import BaseChecker

class MyChecker(BaseChecker):
    async def check(self, chapter_text: str, context: dict) -> dict:
        """
        chapter_text: 章节正文
        context: 上下文（包含设定、前文等）
        """
        issues = []
        # 检查逻辑
        if "敏感词" in chapter_text:
            issues.append({
                "type": "sensitive",
                "position": chapter_text.find("敏感词"),
                "severity": "error",
                "message": "包含敏感词"
            })
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "score": max(0, 100 - len(issues) * 10),
            "suggestions": ["请移除敏感词"] if issues else []
        }
```

### 4.4 Publisher

Publisher 负责将章节发布到第三方平台。基类定义：

```python
# publishers/my_publisher.py
from data_modules.plugin_base import BasePublisher

class MyPublisher(BasePublisher):
    async def authenticate(self, credentials: dict) -> bool:
        # 登录验证
        self.authenticated = True
        return True

    async def get_books(self) -> list:
        # 返回书籍列表
        return [{"id": "123", "title": "我的小说"}]

    async def create_book(self, title: str, genre: str, synopsis: str) -> dict:
        # 创建新书
        return {"id": "456", "title": title}

    async def upload_chapter(self, book_id: str, chapter: dict) -> dict:
        # 上传章节
        return {"success": True, "chapter_id": "789"}
```

### 4.5 生命周期钩子（可选）

如果插件需要在加载或卸载时执行清理操作，可以实现 `on_load` 和 `on_unload` 方法：

```python
class MyChecker(BaseChecker):
    async def on_load(self, plugin_manager):
        # 初始化资源
        pass

    async def on_unload(self):
        # 释放资源
        pass
```

---

## 5. 开发与调试

### 5.1 本地开发环境

1. 确保已安装 Webnovel Writer 核心（通过 `python install.py` 或从 GitHub 克隆）。
2. 在项目根目录下创建插件目录（如 `my-plugin`），按上述结构组织文件。
3. 使用符号链接或直接放置于 `.opencode/plugins/` 下进行开发：
   ```bash
   ln -s /path/to/my-plugin .opencode/plugins/my-plugin
   ```

### 5.2 热重载

开发过程中，修改插件代码后无需重启 OpenCode，使用热重载命令即可生效：

```bash
# 重载所有插件
python .opencode/scripts/webnovel.py plugin reload

# 重载指定插件（推荐，仅影响当前插件）
python .opencode/scripts/webnovel.py plugin reload com.example.my-plugin
```

### 5.3 调试输出

插件中的 `print` 或日志会输出到控制台（如果使用 OpenCode 运行，则显示在终端）。推荐使用 Python 标准 `logging`：

```python
import logging
logger = logging.getLogger(__name__)
logger.info("插件加载成功")
```

日志级别可通过环境变量 `LOG_LEVEL` 控制。

### 5.4 常见错误

- **无法导入模块**：检查 `__init__.py` 是否存在，以及 `manifest.json` 中的 `class` 路径是否正确（相对于插件根目录）。
- **依赖缺失**：在 `requirements.txt` 中列出依赖，系统会在加载插件时自动安装。
- **版本不兼容**：确保 `core_api_version` 与当前核心版本匹配。可通过 `python webnovel.py --version` 查看核心版本。

---

## 6. 发布插件到市场

### 6.1 准备独立仓库

1. 在 GitHub（或其他 Git 托管平台）创建一个公共仓库，名称建议与插件 ID 相关，如 `demo-checker`。
2. 将插件代码推送到仓库，确保仓库根目录包含 `manifest.json`、`__init__.py` 等文件。
3. 为每个发布版本打上 Git 标签，例如 `v1.0.0`。标签名应符合语义化版本。

### 6.2 提交到官方市场

1. 访问官方插件市场索引仓库：https://github.com/webnovel-writer/plugins
2. Fork 该仓库，并在本地克隆。
3. 编辑 `plugins.json` 文件，在 `plugins` 数组中添加你的插件条目：
   ```json
   {
     "id": "com.example.my-plugin",
     "name": "我的插件",
     "description": "插件功能描述",
     "author": "你的 GitHub 用户名",
     "license": "MIT",
     "repo": "https://github.com/你的用户名/你的插件仓库.git",
     "tags": ["checker", "utility"]
   }
   ```
4. 提交 Pull Request，等待审核。
5. 审核通过后，你的插件即可被其他用户通过市场安装。

### 6.3 版本更新

当你发布新版本时（如 `v1.1.0`），需要更新 `plugins.json` 中的 `repo` 字段不需要修改（因为 Git 仓库会自动包含所有版本）。用户安装时默认会拉取最新代码。

**注意**：当前版本不支持版本锁定（`@version` 语法），安装时默认拉取最新代码。该功能计划在后续版本中实现。

---

## 7. 插件管理命令

用户可以通过以下命令管理插件（CLI 和 OpenCode Skill 均可使用）。

### 7.1 CLI 命令

```bash
# 列出已安装插件
python .opencode/scripts/webnovel.py plugin list

# 查看插件详情
python .opencode/scripts/webnovel.py plugin info com.example.my-plugin

# 从市场安装（按名称或ID）
python .opencode/scripts/webnovel.py plugin install 我的插件
python .opencode/scripts/webnovel.py plugin install com.example.my-plugin

# 从 Git URL 安装
python .opencode/scripts/webnovel.py plugin install https://github.com/user/plugin.git

# 从本地路径安装
python .opencode/scripts/webnovel.py plugin install /path/to/plugin

# 卸载插件
python .opencode/scripts/webnovel.py plugin remove com.example.my-plugin

# 重载插件（热重载）
python .opencode/scripts/webnovel.py plugin reload                # 重载所有
python .opencode/scripts/webnovel.py plugin reload com.example.my-plugin  # 重载单个
```

### 7.2 OpenCode Skill

在 OpenCode 中，可以使用 `/webnovel-plugin` 命令进行类似操作：

```
/webnovel-plugin list
/webnovel-plugin info com.example.my-plugin
/webnovel-plugin install 我的插件
/webnovel-plugin install https://github.com/user/plugin.git
/webnovel-plugin remove com.example.my-plugin
/webnovel-plugin reload
/webnovel-plugin reload com.example.my-plugin
```

---

## 8. 最佳实践

1. **唯一标识**：使用反向域名作为插件 ID，避免冲突。
2. **版本管理**：严格遵循语义化版本（SemVer），明确兼容的核心版本范围。
3. **错误处理**：在扩展点实现中捕获异常，返回友好的错误信息，避免导致核心崩溃。
4. **文档**：在插件仓库中提供 README，说明功能、使用方法、配置项。
5. **权限声明**：即使当前未强制沙箱，也应在 `permissions` 中声明所需权限，为未来安全增强做准备。
6. **依赖管理**：尽量使用轻量级依赖，避免引入不必要的包。如果依赖较大，请在文档中说明。
7. **测试**：建议编写单元测试，确保插件在不同环境下稳定运行。

---

## 9. 示例插件

项目提供了示例插件 `demo-checker`，位于 `.opencode/plugins/demo_checker/`。你可以参考其实现来开发自己的插件。

该插件实现了敏感词检查功能，包含：
- 完整的 `manifest.json`
- 简单的 `checker` 实现
- 在 `requirements.txt` 中声明依赖（无额外依赖）

你可以通过以下命令安装示例插件（如果尚未安装）：
```bash
python .opencode/scripts/webnovel.py plugin install demo-checker
```

---

## 10. 常见问题（FAQ）

**Q: 插件安装后没有生效？**  
A: 请检查插件目录是否在 `.opencode/plugins/` 下，`manifest.json` 格式是否正确，核心版本是否兼容。运行 `plugin list` 查看插件状态，如果未显示，可尝试手动加载：`plugin reload`。

**Q: 插件依赖的 Python 包安装失败怎么办？**  
A: 系统会在加载插件时自动执行 `pip install -r requirements.txt`。如果失败，可手动安装依赖后重试。也可在插件仓库的 README 中说明依赖安装方法。

**Q: 如何调试插件代码？**  
A: 在插件代码中插入 `import pdb; pdb.set_trace()` 即可在终端进入交互式调试。注意，OpenCode 可能会将标准输出重定向，建议使用日志记录。

**Q: 插件是否可以修改项目文件？**  
A: 可以，但需遵守权限声明。当前系统未做强制限制，但恶意插件可能损坏项目。请只安装来源可靠的插件。

**Q: 如何让插件支持配置？**  
A: 插件可以通过读取项目根目录下的 `.env` 文件或自己的配置文件（如 `my-plugin-config.yaml`）来获取用户配置。建议在文档中说明配置方式。

---

## 11. 未来扩展

- **钩子系统**：允许插件在核心流程（如写作前/后、审查前/后）注入代码。
- **权限沙箱**：基于审计钩子限制插件行为，确保安全。
- **Dashboard 插件**：允许插件添加自定义可视化组件。
- **多语言支持**：插件文档和元数据国际化。

---

## 12. 贡献与反馈

欢迎开发者提交插件到官方市场。如有问题，请在 GitHub 提交 Issue 或参与讨论。

- 核心项目：https://github.com/lujih/webnovel-writer-opencode
- 插件市场：https://github.com/webnovel-writer/plugins
- 插件开发讨论：https://github.com/lujih/webnovel-writer-opencode/discussions

祝你开发愉快！
