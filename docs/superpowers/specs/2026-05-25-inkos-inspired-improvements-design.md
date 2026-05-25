# inkOS 借鉴改进 — 设计文档

> 设计日期：2026-05-25
> 来源：inkOS 架构分析 → 6 项借鉴建议 → 精选 3 项落地方案
> 状态：待实现

## 概述

借鉴 inkOS（https://github.com/Narcooo/inkos）的 3 个核心设计：

1. **运行时产物持久化** — 每章的上下文 pack 和 trace 落盘为 JSON，可事后审计
2. **Observer→Reflector 双段提取** — 将 data-agent 拆成"自由提取"+"schema 校验落盘"
3. **真相文件 Markdown 投影** — 从 state.json + index.db 自动渲染人类可读的故事状态文件

三项可独立交付。实现顺序：#1 → #2 → #3。

---

## 设计 #1：运行时产物持久化

### 目标

让每章 AI 写作时"实际看到的上下文"可追溯。当前 context_manager.build_context() 的输出是一次性的——用完就丢。事后章节出现质量问题时，无法精确复现 AI 看到了什么。

### 产物

**文件 1：`chapter-NNN.context.json`**

`_assemble_json_payload()` 的完整输出。包含 meta / core / story_contract / genre_profile / writing_guidance / override_hints / prewrite_validation 等所有 section。与注入 writer 的 pack 完全相同。

**文件 2：`chapter-NNN.trace.json`**

上下文选入/排除的元信息：

```json
{
  "chapter": 42,
  "template": "webnovel-write-v3",
  "stage": "mid",
  "weights_used": {"core": 0.40, "story_contract": 0.35, "...": "..."},
  "sections": {
    "included": ["core", "story_contract", "genre_profile"],
    "excluded": ["preferences", "memory", "alerts"]
  },
  "ranker": {
    "enabled": true,
    "items_kept": 18,
    "items_dropped": 5
  }
}
```

### 落盘位置

```
.webnovel/runtime/
├── chapter-042.context.json
├── chapter-042.trace.json
├── chapter-043.context.json
└── ...
```

### 代码改动

- 文件：`.opencode/scripts/data_modules/context_manager.py`
- 方法：`build_context()` — 在 `return payload` 前增加 `write_json()` 落盘
- 新增 import：`from .story_contracts import write_json`
- 改动量：~30 行

### 破坏性

零。纯增量——在返回前多写两个文件。不改变 `build_context()` 的返回值。

---

## 设计 #2：Observer→Reflector 双段提取

### 问题

当前 data-agent 同时承担三个认知任务：读正文、理解故事、按 Pydantic schema 结构化输出。LLM 在结构化输出时天然保守——为了避免 schema 校验失败而减少边缘事实的提取。

### 方案（inkOS 标准版）

**Observer Agent**（不做结构化，只做提取）

- 输入：正文 + 极简实体目录（entity_id / 名称 / 类型，纯文本，无 schema）
- 输出：自由文本，9 个 markdown 段落（角色状态变化 / 新实体 / 关系变化 / 力量突破 / 宝物获得 / 世界规则揭示/打破 / 承诺创建/偿还 / 伏笔创建/闭合）
- 指令核心："宁可多提，不要遗漏。不确定的实体可以写描述而不是精确 ID"

**Settler（Python 脚本，无 LLM 调用）**

- 输入：observer 的 raw_facts.txt + 已知实体列表
- 处理：模式匹配（正则/关键词）→ 实体消歧 → 组装 StoryEvent dict → Pydantic 校验
- 输出：`extraction_result.json`（与当前 data-agent 输出格式兼容）
- 拒绝的不合法事件静默丢弃（settler 不做推理）

### observer-agent 文件

位置：`.opencode/agents/observer-agent.md`

与当前 data-agent.md 的差异：

| | data-agent（当前） | observer-agent（新） |
|---|---|---|
| 输出格式 | Pydantic StoryEvent JSON | 自由文本 markdown 段落 |
| 实体引用 | 必须用精确 entity_id | 推荐用，不确定时写描述 |
| 提取策略 | 准确优先 | 覆盖优先 |
| Schema 约束 | 理解全部 10 event_type + 字段定义 | 只理解 9 类事实的语义 |

### settler 脚本

位置：`.opencode/scripts/data_modules/observer_settler.py`

```python
def settle(raw_facts_path: Path, project_root: Path, chapter: int) -> dict:
    """Parse observer output → validated StoryEvent list."""
    text = raw_facts_path.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(text)
    known_entities = _load_known_entities(project_root)
    
    events = []
    events.extend(_extract_character_state_changes(sections, known_entities))
    events.extend(_extract_relationships(sections, known_entities))
    events.extend(_extract_power_breakthroughs(sections, known_entities))
    # ... all 10 event types
    
    validated = []
    for evt in events:
        try:
            validated.append(StoryEvent.model_validate(evt).model_dump())
        except ValidationError:
            pass
    
    return {"accepted_events": validated, "entity_deltas": [...], ...}
```

### SKILL.md 改动

`.opencode/skills/webnovel-write/SKILL.md` 的 Step 5.1 拆成三步：

```
5.1a: Agent(observer-agent) → .webnovel/runtime/chapter-NNN.raw_facts.txt
5.1b: python observer_settler --raw-facts ... → .webnovel/tmp/extraction_result_NNN.json
5.1c: Agent(data-agent) → fulfillment_result + disambiguation_result（复用 extraction）
```

data-agent 不再负责提取——仅产出 fulfillment（大纲履约 diff）和 disambiguation（消歧）。

**data-agent 改造后的输入变化：**
- 旧：正文 → data-agent → extraction + fulfillment + disambiguation
- 新：正文 + settler 的 extraction_result.json → data-agent → fulfillment + disambiguation
- data-agent 收到 settler 已提取的事实列表，只需做"大纲要求了什么 vs 实际提取了什么"的 diff
- chapter-commit CLI 的 `--extraction-result` 参数改为指向 settler 的输出路径

### 兼容策略

- data-agent 保留完整提取能力（`--fast` 模式或 observer 不可用时回退）
- `webnovel-write --fast` 跳过 observer，直接用 data-agent 老逻辑
- 渐进迁移：先在 `webnovel-write` 默认流程启用，batch/rewrite 后续跟进

### 测试

- settler 是纯 Python，单元测试覆盖全部 10 种 event_type 的提取
- 测试 fixture：模拟 observer 输出文本，验证 settler 输出的 accepted_events

---

## 设计 #3：真相文件 Markdown 投影

### 目标

从 state.json + index.db 自动渲染人类可读的 markdown 文件，让作者无需打开 JSON 就能了解故事状态。

### 产物

| Markdown 文件 | 数据来源 |
|---------------|----------|
| `story/世界观状态.md` | state.json: entities_v3.current_state, protagonist_state, world_rules |
| `story/伏笔面板.md` | state.json: foreshadowing, index.db: debts（状态=active） |
| `story/角色关系矩阵.md` | state.json: relationships, entities_v3 |
| `story/力量体系.md` | entities_v3.current_state（过滤 realm/power 字段）+ world_rules |
| `story/章节摘要.md` | 已有 `summaries/*.md` 汇总索引 + chapter_status |

每个文件头部标注：`> 此文件由系统自动生成，请勿手动编辑。数据源: state.json + index.db`

### 新增模块

位置：`.opencode/scripts/data_modules/state_projection_renderer.py`

```python
def render_all_projections(project_root: Path) -> dict[str, Path]:
    """从结构化数据渲染人类可读的 markdown 投影。"""
    state = json.loads((project_root / ".webnovel" / "state.json").read_text("utf-8"))
    
    renderers = {
        "世界观状态.md": _render_world_state,
        "伏笔面板.md": _render_foreshadowing_panel,
        "角色关系矩阵.md": _render_character_matrix,
        "力量体系.md": _render_power_system,
        "章节摘要.md": _render_chapter_index,
    }
    
    output_dir = project_root / "story"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    for filename, renderer in renderers.items():
        path = output_dir / filename
        path.write_text(renderer(state, project_root), encoding="utf-8")
        results[filename] = path
    
    return results
```

### 触发时机

- `chapter-commit` 成功后自动渲染（`apply_projections` 末尾）
- `ssot rebuild` 后自动渲染
- 手动：`webnovel state render` 新增 CLI 子命令

### 约束

- 纯读操作，不修改 state.json 或 index.db
- 渲染逻辑无 LLM 调用——纯 Python 字符串拼接
- 不照搬 inkOS 的 7 文件（只渲染 webnovel-writer 实际有数据的维度）
- 每个 renderer 接收 `(state: dict, project_root: Path)` 签名——`project_root` 参数允许个别 renderer 读 index.db 做补充查询（如伏笔面板读 debts 表、章节摘要索引 summaries/*.md 目录）

### 测试

- 构造最小 state.json fixture，验证每个渲染函数产出非空 markdown
- 空 state 不崩溃——渲染 `（暂无数据）` 占位文本

---

## 实现顺序

| 序号 | 项目 | 风险 | 改动量 |
|------|------|------|--------|
| **#1** | 运行时产物持久化 | 零 | ~30 行 context_manager.py |
| **#2** | Observer→Reflector | 中 | ~200 行 + 1 agent 文件 |
| **#3** | Markdown 投影 | 零 | ~200 行新模块 |

每项独立可交付，不互相阻塞。
