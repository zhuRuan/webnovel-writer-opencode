# AGENTS.md - Webnovel Writer 开发指南

## 项目概述

Webnovel Writer 是基于 OpenCode 的长篇网文 AI 创作系统，降低 AI 写作中的"遗忘"和"幻觉"，支持长周期连载创作。

## 快速开始

```bash
# 推荐：跨平台安装（Linux/macOS/Windows）
python install.py
```

安装后编辑 `.env` 填入 API Key（EMBED_API_KEY、RERANK_API_KEY），然后重启 OpenCode。

## 核心命令

所有操作通过统一 CLI 入口，自动解析项目根目录（查找 `.webnovel/state.json`）：

```bash
# 主入口（推荐，不依赖 PYTHONPATH/cd）
python .opencode/scripts/webnovel.py <command>

# 常用命令
python .opencode/scripts/webnovel.py where              # 显示当前项目根
python .opencode/scripts/webnovel.py use <路径>         # 切换到指定项目
python .opencode/scripts/webnovel.py index stats        # 索引统计
python .opencode/scripts/webnovel.py index process-chapter --chapter 1
python .opencode/scripts/webnovel.py rag index-chapter --chapter 1
python .opencode/scripts/webnovel.py status --focus all # 健康报告（Markdown）
python .opencode/scripts/webnovel.py checkers list      # 列出审查器
python .opencode/scripts/webnovel.py checkers validate  # 验证审查器配置
python .opencode/scripts/webnovel.py dashboard          # 启动可视化看板

# 健康报告（JSON，供程序处理）
python .opencode/scripts/status_reporter.py --json --pretty --project-root <path>
```

**重要**：CLI 会自动注入 `--project-root`，下游命令不要重复传参。

## 项目目录约定

每个网文项目（非本仓库）的结构：

```
项目目录/
├── .webnovel/          # 状态管理
│   ├── state.json      # 小说状态（章节、实体、伏笔等）
│   └── index.db        # 向量索引数据库
├── 正文/               # 章节正文（Markdown）
├── 设定集/             # 角色、势力、能力等设定
└── 大纲/               # 卷纲、章纲
```

## 构建/测试命令

```bash
# 测试前设置 PYTHONPATH
export PYTHONPATH=".opencode/scripts"   # Linux/macOS
$env:PYTHONPATH=".opencode/scripts"     # PowerShell

# 运行所有测试
pytest .opencode/scripts/data_modules/tests/

# 运行单个测试
pytest .opencode/scripts/data_modules/tests/test_config.py::test_config_paths_and_defaults

# 覆盖率测试（最低 90%）
pytest --cov --cov-report=term-missing .opencode/scripts/data_modules/tests/

# 只运行失败测试
pytest --lf

# Windows: 使用 PowerShell 测试脚本（自动处理临时目录/编码/预检）
powershell -File .opencode/scripts/run_tests.ps1            # smoke 模式
powershell -File .opencode/scripts/run_tests.ps1 -Mode full # 完整测试

# Lint 检查
python -m py_compile .opencode/scripts/webnovel.py
```

**测试注意事项**：
- Windows 下 `run_tests.ps1` 会创建隔离临时目录，避免锁冲突
- 异步测试需 `@pytest.mark.asyncio` 装饰器
- 覆盖率配置在 `.opencode/scripts/.coveragerc`

## 架构要点

### 统一 CLI (`webnovel.py`)
- 唯一入口点，通过 `sys.path` 注入后转发到 `data_modules.webnovel`
- 自动从 `.webnovel/state.json` 解析项目根目录，无需手动指定
- `use <路径>` 命令可切换当前工作项目

### 配置系统
- `DataModulesConfig` 管理所有配置（路径、API、并发等）
- `.env` 加载顺序：项目级 `.env`（当前目录）→ 全局 `~/.opencode/webnovel-writer/.env`
- 先加载的环境变量不会被覆盖（显式 > .env 优先级）

### Windows 路径兼容
- 使用 `runtime_compat.normalize_windows_path()` 处理 Git Bash/WSL 的 POSIX 路径（如 `/d/foo` → `D:/foo`）
- Windows 下入口脚本调用 `enable_windows_utf8_stdio()` 确保中文输出正常

### 审查器系统（配置驱动）
- 配置：`.opencode/checkers/registry.yaml`
- 定义：`.opencode/agents/*.md`
- 两类审查器：
  - **core**：始终运行（consistency, continuity, ooc）
  - **conditional**：触发条件运行时（reader-pull, high-point, pacing）
- 三种模式：`minimal`（只 core）、`standard`（core + 条件命中）、`full`（强制全部）
- 新增审查器只需编辑 `registry.yaml`，无需修改代码

### RAG 流程
查询 → 检索（Embedding）→ 重排（Rerank）→ 构建上下文

### 实体追踪
所有新实体必须通过 `EntityLinker` 注册，状态由 `StateManager` 管理

## 发布到番茄小说

```bash
# 首次配置（只需一次）
pip install playwright
playwright install chromium
python .opencode/scripts/webnovel.py publish setup-browser

# 获取/创建书籍
python .opencode/scripts/webnovel.py publish list-books --project-root <path>
python .opencode/scripts/webnovel.py publish create-book --title "标题" --genre "玄幻" --synopsis "简介" --project-root <path>

# 上传章节
python .opencode/scripts/webnovel.py publish upload --book-id <ID> --range "1-10" --mode draft --project-root <path>
```

## 代码约定

- **编码**：所有文件 UTF-8，中文文档
- **导入顺序**：标准库 → 第三方 → 本地（相对导入优先）
- **跨平台兼容**：用 `try/except ImportError` 处理 `runtime_compat` 导入
- **路径处理**：使用 `pathlib.Path`，不用 `os.path`
- **错误处理**：捕获具体异常，避免裸 `except`
- **日志**：使用 `logging.getLogger(__name__)`
- **类型注解**：所有公共函数/方法必须显式标注
- **命名**：函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`

## Git 工作流

```bash
# 提交前运行测试
pytest .opencode/scripts/data_modules/tests/

# 提交信息规范
git commit -m "type: description"
# type: feat, fix, docs, refactor, test, chore
```

## 关键文件索引

| 文件 | 作用 |
|------|------|
| `.opencode/scripts/webnovel.py` | 统一 CLI 入口 |
| `.opencode/scripts/data_modules/config.py` | 配置类 + .env 加载 |
| `.opencode/scripts/data_modules/webnovel.py` | CLI 命令路由 |
| `.opencode/scripts/data_modules/state_manager.py` | 小说状态管理 |
| `.opencode/scripts/data_modules/entity_linker.py` | 实体注册 |
| `.opencode/scripts/runtime_compat.py` | 跨平台路径/编码兼容 |
| `.opencode/checkers/registry.yaml` | 审查器配置 |
| `.opencode/agents/*.md` | 审查器实现定义 |
