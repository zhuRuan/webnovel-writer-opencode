# Webnovel Writer 安装指示

请执行以下步骤完成 Webnovel Writer 安装：

## 步骤 1：清理旧的安装脚本（如有）

如果之前已下载过 install.py，请先删除：
- Windows: `del install.py`
- Linux/macOS: `rm install.py`

## 步骤 2：下载安装脚本

从 https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py 下载内容，保存为 install.py

## 步骤 3：运行安装

执行 `python install.py`

脚本会自动：
- 增量更新 .env 配置（保留您的 API Key）
- 覆盖安装 .opencode（更新到最新版本）

## 完成

确认安装成功：
- .opencode 目录已创建
- .env 文件存在（保留原有配置）
