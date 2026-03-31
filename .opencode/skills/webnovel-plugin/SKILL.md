---
name: webnovel-plugin
description: 插件管理命令。用于安装、卸载、列出、查看插件信息，或重新加载插件。支持从 Git URL 或本地路径安装插件。配合 /webnovel-plugin list 查看已安装插件，/webnovel-plugin install <source> 安装新插件，/webnovel-plugin remove <id> 卸载插件。
allowed-tools: Read Write Edit Grep Bash
---

# 插件管理 Skill

## 快速参考

| 命令 | 说明 |
|------|------|
| `/webnovel-plugin list` | 列出已安装的插件 |
| `/webnovel-plugin info <id>` | 查看插件详情 |
| `/webnovel-plugin install <source>` | 安装插件（Git URL 或本地路径） |
| `/webnovel-plugin remove <id>` | 卸载插件 |
| `/webnovel-plugin reload` | 重新加载所有插件 |
| `/webnovel-plugin reload <id>` | 重新加载指定插件 |

## 路径工具

插件 CLI 路径：
```bash
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
```

## 核心约束

- **禁止跳步**：插件操作必须调用 CLI 命令
- **中文输出**：所有输出使用中文
- **安全卸载**：卸载前确认插件 ID

## 执行流程

### 列出插件

```bash
# 列出所有已安装插件
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI list
```

### 查看插件详情

```bash
# 查看指定插件信息
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI info <plugin-id>
```

### 安装插件

```bash
# 从 Git URL 安装
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI install https://github.com/user/plugin.git

# 从本地路径安装
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI install ../my-plugin
```

### 卸载插件

```bash
# 卸载指定插件
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI remove <plugin-id>
```

### 重新加载

```bash
# 重新加载所有插件
PLUGIN_CLI="python -X utf8 \"${SCRIPTS_DIR}/webnovel.py\" plugin"
$PLUGIN_CLI reload

# 重新加载指定插件
$PLUGIN_CLI reload <plugin-id>
```

## 常见问题

1. **安装失败**：检查网络连接，或确保插件包含 manifest.json
2. **权限错误**：部分插件需要额外依赖，按提示安装
3. **卸载后不生效**：需要重启 OpenCode

## 输出示例

```
已安装的插件:

📦 敏感词检查器 (v1.0.0)
   ID: com.example.sensitive-checker
   作者: 测试作者
   描述: 检查章节中是否包含敏感词
```
