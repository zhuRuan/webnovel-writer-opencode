# Webnovel Writer

## 快速命令

```bash
python install.py                              # 安装/更新
python .opencode/scripts/webnovel.py <cmd>     # 唯一 CLI 入口
python .opencode/scripts/run_all_tests.py      # 全量测试
python .opencode/scripts/webnovel.py where     # 当前项目根

## 项目结构

```
项目目录/                 # 小说项目（如 凡尘之舞/）
├── .webnovel/           # state.json, index.db
├── 正文/                # 章节 Markdown（写作产出）
├── 设定集/              # 角色/势力/物品/能力设定
├── 大纲/                # 卷纲/章纲
└── .env                 # API 配置（不提交）

.opencode/               # 引擎核心（install.py 维护）
├── scripts/
│   ├── webnovel.py     # 薄入口 → data_modules.webnovel.main()
│   ├── data_modules/   # 核心数据模块（43个 .py）
│   │   ├── webnovel.py # 真实 CLI + COMMAND_REGISTRY
│   │   ├── config.py   # 配置系统（题材预设）
│   │   ├── rag_adapter.py / rag_backend.py  # RAG 抽象
│   │   ├── state_manager.py / index_manager.py
│   │   ├── exceptions.py    # 统一异常（WebnovelError 基类）
│   │   ├── observability.py # 性能埋点
│   │   └── tests/ (~55 个测试文件)
│   ├── project_locator.py   # 项目根检测（查 .webnovel/state.json）
│   ├── init_project.py      # /webnovel-init 后端（生成 .env + 骨架）
│   └── run_all_tests.py     # pytest data_modules/tests/ -v
├── skills/ (12)       # /webnovel-* 命令对应 skill
├── agents/ (9)        # context-agent, data-agent, 6 个审查器, unified-reviewer
├── checkers/          # registry.yaml + schema.yaml
└── dashboard/         # FastAPI + React 可视化面板
```

## 体系要点

### 唯一 CLI 入口
所有命令走 `python .opencode/scripts/webnovel.py <cmd>`。通过 `COMMAND_REGISTRY` 查表 → 按 `cmd["type"]`（`data_module` | `script` | `special`）路由分发（`webnovel.py:440-476`）。

### 项目检测
`project_locator.py` 通过 `.webnovel/state.json` 定位项目根。分 temp dir 测试失败均因未创建该文件。

### 测试规范
- **无 pytest.ini / pyproject.toml** — 测试由 `run_all_tests.py` 按显式路径发现
- 测试目录 `data_modules/tests/` 含 ~55 个 test_*.py 文件
- 运行单文件：`python -m pytest .opencode/scripts/data_modules/tests/test_xxx.py -v`
- 新增模块测试放 `test_*.py`，统一放 `data_modules/tests/`

### 异常层级
`WebnovelError` ← `StateManagerError | IndexManagerError | APIClientError | ConfigError`  
已定义，但各模块尚未批量迁移（渐进式接入）。

### RAG 后端抽象
```python
from data_modules.rag_backend import BackendFactory
backend = BackendFactory.create("vector")   # str | None
```
`rag_adapter.py` 通过 `get_backend()` / `get_vector_backend()` 委托。`rag_backend.py` 定义了 `VectorSearchBackend` 和 `TemporalGraphBackend` 的 Protocol。

### 分层审查
- **Code Checkers**: `world-consistency`, `DebtTracker` — 确定性阻断
- **LLM Agents** (7个): consistency, continuity, ooc, high-point, pacing, reader-pull, unified-reviewer
  - `unified-reviewer`: 单 Agent 覆盖全部 6 维度，低 token 消耗
- 执行：`run_layered_checkers(run_llm=False)` → 仅 Code 层

### 性能埋点
写入 `{project_root}/.webnovel/observability/data_agent_timing.jsonl`，覆盖 `state_manager.save_state`, `context_manager.build_context`, `api_client.embed`, `checkers_manager.run_layered_checkers`。

### IndexManager
混入模式：`index_chapter_mixin.py` / `index_entity_mixin.py` / `index_debt_mixin.py` / `index_reading_mixin.py` / `index_observability_mixin.py`。通过 `manager.get_service("chapters")` 访问。

### 故事合约引擎
`story_system_engine` → `story_contracts`（数据模型）→ `event_log_store`（事件溯源）→ `event_projection_router`（投影路由）。投影写入器（`vector`/`state`/`summary`/`memory`/`index_projection_writer`）订阅事件，将章节提交重建为各类索引/记忆/摘要。

### 记忆系统
三层记忆架构：工作记忆 / 情节记忆 / 语义记忆。8 个模块位于 `data_modules/memory/`，由 `memory_contract_adapter` 编排。含记忆压缩器 + SQLite 持久化。

### Dashboard
FastAPI + React，首次使用需在 `.opencode/dashboard/frontend/` 执行 `npm install` 构建前端。启动：`python .opencode/scripts/webnovel.py dashboard --port 8765`。

### 项目根定位优先级
`--project-root` 参数 → `CLAUDE_PROJECT_DIR` / `OPENCODE_PROJECT_DIR` 环境变量 → `.opencode/.webnovel-current-project` 指针 → `webnovel-project/` 默认目录 → CWD。必须包含 `.webnovel/state.json` 才被认定为合法项目根。

### 行为准则
`CLAUDE.md` 定义了编码纪律：先思考再编码、极简主义、外科手术式修改、目标驱动执行。修改代码前应先阅读。

### .env 配置
由 `install.py` 从远程下载（合并已有 key），`init_project.py` 为新项目生成。Keys: `EMBED_*`, `RERANK_*`, `IMAGE_*`, `LOG_*`。不提交到版本库。

### 已知限制
- `checkers list` 命令报 `TypeError`（`triggers` 字段类型不匹配）
- 部分 CLI 测试在 temp 目录失败（缺 `.webnovel/state.json`）
