# Webnovel Writer

## 快速命令

```bash
python install.py                              # 安装/更新
python .opencode/scripts/webnovel.py <cmd>     # 唯一 CLI 入口
python .opencode/scripts/run_all_tests.py      # 全量测试 (306 pass / 15 fail*)
python .opencode/scripts/run_new_tests.py      # 仅新增模块测试 (28 pass)
python .opencode/scripts/webnovel.py where     # 当前项目根
```

> `*` 15 个失败全是预存问题（temp dir 缺 `.webnovel/state.json` / 编码），非本次改动引入。

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
│   │   └── tests/ (39 个测试文件)
│   ├── project_locator.py   # 项目根检测（查 .webnovel/state.json）
│   ├── init_project.py      # /webnovel-init 后端（生成 .env + 骨架）
│   └── run_all_tests.py     # pytest data_modules/tests/ -v
├── skills/ (12)       # /webnovel-* 命令对应 skill
├── agents/ (8)        # context-agent, data-agent, 6 个审查器
├── checkers/          # registry.yaml + schema.yaml
└── dashboard/         # FastAPI + React 可视化面板
```

## 体系要点

### 唯一 CLI 入口
所有命令走 `python .opencode/scripts/webnovel.py <cmd>`。内部分派依赖 `COMMAND_REGISTRY`（`data_modules/webnovel.py:38`），但实际调度仍是 `if tool == "x"` 链（尚未收敛到 registry）。

### 项目检测
`project_locator.py` 通过 `.webnovel/state.json` 定位项目根。分 temp dir 测试失败均因未创建该文件。

### 测试规范
- **无 pytest.ini / pyproject.toml** — 测试由 `run_all_tests.py` 按显式路径发现
- 运行单测试文件：`python -m pytest .opencode/scripts/data_modules/tests/test_exceptions.py -v`
- 新增模块测试放 `test_*.py`，统一放 `data_modules/tests/`
- `run_new_tests.py` 仅跑 `test_exceptions` 和 `test_rag_backend`

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
- **LLM Agents** (6个): consistency, continuity, ooc, high-point, pacing, reader-pull
- 执行：`run_layered_checkers(run_llm=False)` → 仅 Code 层

### 性能埋点
写入 `{project_root}/.webnovel/observability/data_agent_timing.jsonl`，覆盖 `state_manager.save_state`, `context_manager.build_context`, `api_client.embed`, `checkers_manager.run_layered_checkers`。

### IndexManager
混入模式：`index_chapter_mixin.py` / `index_entity_mixin.py` / `index_debt_mixin.py` / `index_reading_mixin.py` / `index_observability_mixin.py`。通过 `manager.get_service("chapters")` 访问。

### .env 配置
由 `install.py` 从远程下载（合并已有 key），`init_project.py` 为新项目生成。Keys: `EMBED_*`, `RERANK_*`, `IMAGE_*`, `LOG_*`。不提交到版本库。

### 已知限制
- `checkers list` 命令报 `TypeError`（`triggers` 字段类型不匹配）
- `COMMAND_REGISTRY` 已定义但调度未收敛（`data_modules/webnovel.py:323-386`）
- 部分 CLI 测试在 temp 目录失败（缺 `.webnovel/state.json`）
