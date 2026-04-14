# AGENTS.md - Webnovel Writer 开发指南

## 项目要求
- **Python 3.10+**（不是3.9）
- OpenCode 运行环境

## 快速命令
```bash
# 安装
python install.py

# 核心命令
python .opencode/scripts/webnovel.py <command>
python .opencode/scripts/webnovel.py where              # 当前项目根
python .opencode/scripts/webnovel.py checkers list    # 审查器列表

# 测试（设置 PYTHONPATH）
$env:PYTHONPATH=".opencode/scripts"
pytest .opencode/scripts/data_modules/tests/
```

## 项目结构
```
项目目录/
├── .webnovel/          # state.json, index.db
├── 正文/               # 章节 Markdown
├── 设定集/             # 角色/势力设定
├── 大纲/               # 卷纲/章纲
└── .env               # API配置
```

## 架构要点

### 1. 分层审查（Phase 2-3 核心）
- **Code Checkers**：`world-consistency`, `DebtTracker` - 确定性检查，~ms级，critical问题阻断
- **LLM Agents**：通过 `llm_invoker.py` 调用，语义审查
- 分层执行：`run_layered_checkers(run_llm=False)` → 仅Code层；`run_llm=True` → 完整

### 2. 债务系统（Phase 2.2-2.5）
```python
from data_modules.debt_tracker import DebtTracker, DebtPriority
tracker = DebtTracker()
tracker.create_debt('explicit', '神秘玉佩', chapter=1, priority=DebtPriority.HIGH)
tracker.can_write_climax(10, is_climax=True)  # 高潮章节检查
```
- `[伏笔:xxx]` → 自动创建HIGH债务
- `[回收:xxx]` → 自动偿还

### 3. Graph-RAG 持久化（Phase 1 增强）
```python
from data_modules.temporal_graph import TemporalGraphIndex
graph = TemporalGraphIndex()
graph.load_from_db("index.db")  # 优先加载
graph.save_to_db("index.db")     # 持久化
```

### 4. 题材预设（Phase 1.5）
```python
config.world_preset = "xianxia"  # xianxia/urban/fantasy/scifi
```

## 新增模块（Phase 3）
| 模块 | 路径 | 作用 |
|------|------|------|
| `llm_invoker.py` | `data_modules/` | LLM调用封装+降级 |
| `debt_tracker.py` | `data_modules/` | 债务追踪 |
| `checkers_manager.py` | `data_modules/` | 分层审查 |
| `rag_adapter.py` | `data_modules/` | Graph-RAG持久化 |

## 测试覆盖
- 29个测试全部通过：`test_debt_tracker.py`, `test_checkers_manager.py`, `test_temporal_graph.py`

## Key Files
| 文件 | 作用 |
|------|------|
| `scripts/webnovel.py` | CLI入口 |
| `scripts/data_modules/config.py` | 配置+题材预设 |
| `scripts/data_modules/debt_tracker.py` | 债务追踪 |
| `scripts/data_modules/llm_invoker.py` | LLM调用 |
| `checkers/registry.yaml` | 审查器配置 |

## 新手引导
详见 `docs/新手引导.md`（《从零到发布》完整指南）

---

## 功能完成状态
| 模块 | 状态 |
|------|------|
| Phase 1: 基础架构 | ✅ |
| Phase 2: 一致性保障 | ✅ |
| Phase 1.5: 通用化 | ✅ |
| Phase 3: LLM集成 | ✅ |