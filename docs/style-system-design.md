# 文风系统设计文档

## 1. 概述

### 1.1 设计理念

- **CSV 是输入源，DB 是运行时权威。** Agent 走 DB API，不读 CSV 文件。
- **9 个 CSV 知识库 → 2 张 DB 表 → 前端 16 个 tab + Agent API**
- 数据从 CSV 导入后，所有运行时查询统一走 SQLite API，保证单一数据源、可搜索、可过滤

### 1.2 数据流

```
CSV 文件 (9个)
  │
  ├─ import_to_reference() → reference_entries 表
  └─ import_from_csv()     → writing_techniques 表
        │
        ▼
  SQLite DB (wenfeng.db)
        │
        ├─ GET /api/techniques/search?q=&source=&category=&skill=&genre=
        ├─ GET /api/reference/search?source=&q=
        ├─ GET /api/reference/sources
        ├─ GET /api/techniques/grouped
        └─ GET /api/style/active
              │
              ▼
    ┌─────────┴─────────┐
    │                    │
  Frontend (16 tabs)   Agent (director / chapter-writer / skills)
```

---

## 2. 数据层

### 2.1 CSV 文件（9 个）

| CSV | 编号前缀 | 行数 | 归属表 | 前端 tab | 说明 |
|-----|---------|------|--------|---------|------|
| 写作技法 | WT- | 104 | writing_techniques | 写作技法 | 技法定义、何时使用、正反例 |
| 场景写法 | SP- | 96 | reference_entries | 场景写法 | 各类场景的写作模板 |
| 桥段套路 | TR- | 108 | reference_entries | 桥段套路 | 经典情节模式与变体 |
| 人设与关系 | CH- | 101 | reference_entries | 人设模板 | 角色原型、关系模式 |
| 爽点与节奏 | PA- | 104 | reference_entries | 爽点节奏 | 爽点类型、章节节奏控制 |
| 金手指与设定 | SY- | 104 | reference_entries | 金手指库 | 金手指类型与设定模板 |
| 命名规则 | NR- | 79 | reference_entries | 命名规则 | 人物、地点、势力命名规范 |
| 题材与调性推理 | GR- | 26 | reference_entries | 题材路由 | 题材分类与调性匹配 |
| 裁决规则 | RS- | 17 | reference_entries | 裁决规则 | 质量审查标准与判定规则 |

### 2.2 DB 表结构

#### writing_techniques（写作技法专用表，20+ 列）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| name | TEXT | 技法名称 |
| category | TEXT | 原 CSV 分类（如 "人物塑造"） |
| primary_category | TEXT | 一级分类（如 "人物写法"、"情节技法"、"语言修辞"） |
| sub_category | TEXT | 二级子分类 |
| description | TEXT | 技法简要描述 |
| when_to_use | TEXT | 适用场景 / 何时使用 |
| example | TEXT | 正面示例 |
| anti_pattern | TEXT | 反面模式 / 毒点 |
| difficulty | TEXT | 难度等级 |
| keywords | TEXT | 搜索关键词 |
| intent_synonyms | TEXT | 意图同义词，扩展 Agent 意图匹配 |
| applicable_genres | TEXT | 适用题材 |
| model_instruction | TEXT | 大模型指令，用于注入 Agent system prompt |
| detailed_description | TEXT | 详细展开说明 |
| skill_tags | TEXT | 技能标签 |
| code | TEXT | 编码（如 WT-001） |
| level_name | TEXT | 层级名称 |
| positive_example | TEXT | 正面详细示例 |
| negative_example | TEXT | 反面详细示例 |
| source_csv | TEXT | 来源 CSV 文件名 |

#### reference_entries（8 个参考来源共用表，18 列）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| name | TEXT | 条目名称 |
| source_csv | TEXT | 来源 CSV（如 "场景写法"、"桥段套路"） |
| category | TEXT | 分类（原 CSV 列） |
| sub_category | TEXT | 子分类 |
| description | TEXT | 简要描述 |
| keywords | TEXT | 搜索关键词 |
| intent_synonyms | TEXT | 意图同义词 |
| applicable_genres | TEXT | 适用题材 |
| model_instruction | TEXT | 大模型指令 |
| detailed_description | TEXT | 详细描述（含专属列，见 2.3） |
| level_name | TEXT | 层级名称 |
| code | TEXT | 编码（如 SP-001、TR-001） |
| skill_tags | TEXT | 技能标签 |
| positive_example | TEXT | 正面示例 |
| negative_example | TEXT | 反面示例 |
| anti_pattern | TEXT | 毒点 / 反面模式 |
| difficulty | TEXT | 难度等级 |

### 2.3 专属列存储策略

每个 CSV 有各自独特的列（如 "核心动机"、"前置铺垫"、"规则" 等），这些列通过 extra_parts 机制循环存入 `detailed_description`，格式为：

```
【列名】值
```

**示例（桥段套路 TR-001 "退婚流"）：**

```
detailed_description:
退婚流是经典开局套路，通过被退婚制造初始矛盾与逆袭动力。
【核心动机】尊严受损、翻身证明
【前置铺垫】主角隐藏实力/被低估
【转折点】退婚现场公开冲突
【常见变体】宗门退婚、家族联姻退婚、政治联姻退婚
【毒点】退婚理由牵强、打脸太慢、反派降智
```

前端 ReferenceTab 解析 `【xxx】` 标签，将每个标签独立展示为卡片上的专属字段区域。未匹配任何标签的文本作为通用描述显示。

---

## 3. API 层

### 3.1 核心端点

| 端点 | 方法 | 查什么 | 谁用 |
|------|------|--------|------|
| `/api/techniques/search` | GET | writing_techniques + reference_entries（source 参数时） | director-agent (A8b), webnovel-write SKILL (Step 2) |
| `/api/reference/search` | GET | reference_entries（按 source 过滤） | 前端 ReferenceTab |
| `/api/reference/sources` | GET | reference_entries 的 source_csv 去重聚合 | 前端 |
| `/api/style/active` | GET | director_styles + anti_patterns + techniques + reference_sections | director-agent (A8a), webnovel-style SKILL |
| `/api/techniques/grouped` | GET | writing_techniques 按 primary_category 分组 | 前端写作技法 tab |

### 3.2 `/api/techniques/search` 搜索逻辑

```
输入参数:
  q          — 搜索关键词（可选）
  category   — primary_category 精确匹配（可选）
  skill      — skill_tags 模糊匹配（可选）
  genre      — applicable_genres 模糊匹配（可选）
  source     — 来源过滤（可选，影响查询范围）

查询流程:
  1. 在 writing_techniques 表中搜索:
     WHERE name LIKE '%q%'
        OR description LIKE '%q%'
        OR keywords LIKE '%q%'
        OR when_to_use LIKE '%q%'
     + category/skill/genre 过滤条件

  2. 若 source 参数非空且 source != "写作技法":
     追加 reference_entries 表查询:
     WHERE source_csv = source
       AND (name LIKE '%q%' OR description LIKE '%q%' OR keywords LIKE '%q%')
     + category/skill/genre 过滤条件

  3. 合并结果，返回统一 JSON 数组
```

### 3.3 `/api/style/active` 响应结构

```json
{
  "active_style": {
    "name": "...",
    "description": "...",
    "rules": "...",
    "priority": 1
  },
  "anti_patterns": [
    { "name": "...", "description": "..." }
  ],
  "techniques": [
    { "code": "WT-001", "name": "...", "when_to_use": "...", "model_instruction": "..." }
  ],
  "reference_sections": {
    "场景写法": [ { "code": "SP-001", ... } ],
    "桥段套路": [ { "code": "TR-001", ... } ]
  }
}
```

### 3.4 来源映射表（Agent 场景 → 查询）

| 写作场景 | 推荐来源 | API 调用 |
|---------|---------|---------|
| 写对话 | 写作技法 | `/api/techniques/search?category=对话写法` |
| 写战斗 | 场景写法 | `/api/techniques/search?source=场景写法` |
| 设悬念 | 桥段套路 | `/api/techniques/search?source=桥段套路` |
| 设人物 | 人设与关系 | `/api/techniques/search?source=人设与关系` |
| 控节奏 | 爽点与节奏 | `/api/techniques/search?source=爽点与节奏` |
| 选金手指 | 金手指与设定 | `/api/techniques/search?source=金手指与设定` |
| 起名字 | 命名规则 | `/api/techniques/search?source=命名规则` |
| 选题材 | 题材与调性推理 | `/api/techniques/search?source=题材与调性推理` |
| 做审查 | 裁决规则 | `/api/techniques/search?source=裁决规则` |

---

## 4. 前端层

### 4.1 Tab 组织（按写作阶段）

| 阶段 | Tab | 数据来源 |
|------|-----|---------|
| 全局配置 | 自定义文风·规则 | `/api/style/active` → director_styles |
| 全局配置 | 全局文风 | `/api/style/active` → director_styles |
| 全局配置 | 禁止模式 | `/api/style/active` → anti_patterns |
| 设定构思 | 人设模板 | `/api/reference/search?source=人设与关系` |
| 设定构思 | 金手指库 | `/api/reference/search?source=金手指与设定` |
| 设定构思 | 命名规则 | `/api/reference/search?source=命名规则` |
| 设定构思 | 题材路由 | `/api/reference/search?source=题材与调性推理` |
| 剧情构思 | 桥段套路 | `/api/reference/search?source=桥段套路` |
| 剧情构思 | 爽点节奏 | `/api/reference/search?source=爽点与节奏` |
| 写作方法 | 写作技法 | `/api/techniques/grouped` + `/api/techniques/search` |
| 写作方法 | 场景写法 | `/api/reference/search?source=场景写法` |
| 名家参考 | 名家技法 | `/api/reference/search?source=名家技法` |
| 质量把控 | 章级合同 | 项目本地数据 |
| 质量把控 | 审查维度 | 项目本地数据 |
| 质量把控 | 裁决规则 | `/api/reference/search?source=裁决规则` |

### 4.2 参考卡片展示字段

每个参考条目（ReferenceEntry）在卡片上展示以下字段：

- **名称** (name) — 卡片标题
- **编号** (code) — 如 WT-001、SP-005
- **分类** (category) — 所属分类路径
- **描述** (description) — 简要说明
- **关键词** (keywords) — 标签展示
- **适用题材** (applicable_genres)
- **技能标签** (skill_tags)
- **意图与同义词** (intent_synonyms)
- **层级** (level_name)

专属列通过 `【xxx】` 标签独立展示（从 detailed_description 解析），每个标签渲染为一个独立区块。

可折叠区域：
- 正例 / 反例（positive_example / negative_example）
- 毒点（anti_pattern）
- 大模型指令（model_instruction）
- 详细展开（detailed_description 中非 `【xxx】` 标签部分）

---

## 5. Agent 查询路径

### 5.1 director-agent 写作前查询流程

```
Step A8a:
  GET /api/style/active
  → 获取全貌数据:
    - active_style（当前激活文风规则）
    - anti_patterns（全局禁止模式）
    - techniques（关联技法列表）
    - reference_sections（按来源分组的参考条目）

Step A8b:
  GET /api/techniques/search?q=<场景关键词>&source=<来源>
  → 按当前写作场景搜索:
    - 写对话 → source=写作技法, category=对话写法
    - 写战斗 → source=场景写法
    - 设悬念 → source=桥段套路
    - 选金手指 → source=金手指与设定

Step A8c:
  精选 3-5 条最相关技法/参考条目
  → 注入 chapter-writer-agent 的 task book
```

### 5.2 chapter-writer-agent

chapter-writer-agent 不直接查询 DB API。它从 director-agent 写入的 task book 中读取 `style_techniques` 字段，按照其中的 model_instruction 和 example 来指导写作。

```
task book
  ├─ plot_outline: ...
  ├─ character_states: ...
  ├─ style_techniques: [      ← director-agent A8c 注入
  │     { "code": "WT-012", "name": "...", "model_instruction": "..." },
  │     { "code": "TR-003", "name": "...", "model_instruction": "..." }
  │   ]
  └─ constraints: ...
```

### 5.3 webnovel-write SKILL

```
Step 2 (原 reference_search.py 逻辑):
  GET /api/techniques/search?source=xxx&q=xxx
  → 替代原来的 CSV 直接读取 + reference_search.py 脚本
  → 结果注入 Step 3 的写作 prompt
```

### 5.4 webnovel-style SKILL

```
一次性调用:
  GET /api/style/active
  → 获取全部文风数据（规则 + 禁止模式 + 技法 + 参考条目）
  → 加载到 director-agent 上下文中
  → 不再需要逐个查询其他端点
```

### 5.5 webnovel-collect SKILL

名家文风采集结果写入 `director_style` 表后，通过 `/api/style/active` 即可被其他 Agent 自动感知，无需额外配置。

---

## 6. 运维

### 6.1 数据导入

```bash
# 从 9 个 CSV 重新导入全部数据
# 清空 writing_techniques + reference_entries 表后重新写入
cd .opencode && python3 scripts/import_techniques.py --force
```

**导入流程：**

1. 读取 `.opencode/data/csv/` 下所有 CSV 文件
2. 识别 CSV 类型（通过文件名映射到 source_csv）
3. "写作技法" → writing_techniques 表（20+ 列完整映射）
4. 其余 8 个 CSV → reference_entries 表（18 列 + extra_parts → detailed_description）
5. `--force` 参数先清空两表再导入（幂等操作）

### 6.2 API 验证命令

```bash
# 启动 dashboard 后端
bash restart.sh

# 搜索写作技法
curl "http://127.0.0.1:8765/api/techniques/search?q=退婚&source=桥段套路"

# 按分类搜索
curl "http://127.0.0.1:8765/api/techniques/search?category=人物写法"

# 获取所有参考来源
curl "http://127.0.0.1:8765/api/reference/sources"

# 按来源搜索参考条目
curl "http://127.0.0.1:8765/api/reference/search?source=金手指与设定"

# 获取当前激活文风（Agent 使用）
curl "http://127.0.0.1:8765/api/style/active"

# 写作技法分组查询
curl "http://127.0.0.1:8765/api/techniques/grouped"
```

### 6.3 数据库文件位置

```
.opencode/dashboard/wenfeng.db  → SQLite 数据库
.opencode/data/csv/             → CSV 源文件（9 个）
.opencode/scripts/import_techniques.py  → 导入脚本
```

---

## 7. 设计原则

1. **DB 是唯一运行时数据源。** Agent 不直接读 CSV 文件，不走 `reference_search.py` 脚本。所有查询统一通过 Dashboard API。
2. **字段完整性。** CSV 的所有列都存储到 DB，通过 extra_parts 兜底机制保证不会有列被丢弃。
3. **搜索覆盖性。** `/api/techniques/search` 覆盖全部 9 个 CSV 来源，source 参数控制跨表查询。
4. **展示一致性。** 前端 ReferenceTab 统一解析 `detailed_description` 中的 `【xxx】` 标签实现专属列展示，各来源共用同一组件。
5. **导入幂等性。** `--force` 清空重导，保证数据一致；无 `--force` 时增量追加。
6. **Agent 隔离。** chapter-writer-agent 不直接访问 API，通过 task book 接收 director-agent 精选后的技法数据，减少 token 消耗。
