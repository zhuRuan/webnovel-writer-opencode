# AGENTS.md - Webnovel Writer 开发指南

## 核心命令

```bash
# 统一入口（自动检测项目根目录）
python .opencode/scripts/webnovel.py <command>

# 常用命令
python .opencode/scripts/webnovel.py where              # 显示当前项目
python .opencode/scripts/webnovel.py use <路径>         # 切换项目
python .opencode/scripts/webnovel.py status --focus all # 健康报告
python .opencode/scripts/webnovel.py dashboard          # 启动可视化看板
python .opencode/scripts/webnovel.py checkers list      # 列出审查器
python .opencode/scripts/webnovel.py checkers validate  # 验证审查器配置
```

**重要**：CLI 自动从 `.webnovel/state.json` 解析项目根目录，无需手动传 `--project-root`。

## 测试命令

```bash
# Windows（推荐，自动处理临时目录/编码）
powershell -File .opencode/scripts/run_tests.ps1 -Mode full

# Linux/macOS 或手动
export PYTHONPATH=".opencode/scripts"   # Linux/macOS
$env:PYTHONPATH=".opencode/scripts"     # PowerShell
pytest .opencode/scripts/data_modules/tests/ --lf
```

**注意**：Windows 下 `run_tests.ps1` 会创建隔离临时目录避免锁冲突。覆盖率配置在 `.opencode/scripts/.coveragerc`，最低要求 90%。

## 架构要点

- **CLI 入口** `.opencode/scripts/webnovel.py` → `data_modules.webnovel`
- **配置系统** `DataModulesConfig`，`.env` 加载顺序：当前目录 → `~/.opencode/webnovel-writer/.env`，先加载的不被覆盖
- **Windows 兼容** 用 `runtime_compat.normalize_windows_path()` 处理 Git Bash/WSL 的 `/d/foo` 路径
- **审查器** 配置在 `.opencode/checkers/registry.yaml`，定义在 `.opencode/agents/*.md`
