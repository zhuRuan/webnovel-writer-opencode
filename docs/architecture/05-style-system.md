# 文风与写作技法系统 — 模块设计

> 版本: 2.9 | 更新: 2026-06 | 父文档: [00-master-architecture.md](00-master-architecture.md)

## 概述

导演文风规则入库 + 写作技法按 7 大主分类组织 + CSV 自动导入。核心模块：`director_dao.py`（391 行），管理 `director_style`、`writing_techniques`、`chapter_techniques` 三张表。

## 数据库表

### director_style — 文风规则

```sql
CREATE TABLE director_style (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    rules TEXT NOT NULL,              -- JSON 规则数组
    priority INTEGER DEFAULT 5,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### writing_techniques — 技法目录

```sql
CREATE TABLE writing_techniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,           -- 原始子分类
    primary_category TEXT DEFAULT '', -- 7 大主分类之一
    sub_category TEXT,
    description TEXT NOT NULL,
    when_to_use TEXT,
    example TEXT,
    anti_pattern TEXT,
    difficulty INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### chapter_techniques — 章节技法追踪

```sql
CREATE TABLE chapter_techniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    technique_name TEXT NOT NULL,
    technique_category TEXT NOT NULL,
    usage_context TEXT,
    effectiveness TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## 7 大主分类映射

47 个子分类通过 `_PRIMARY_CATEGORY_MAP` 自动映射到 7 个主分类：

| 主分类 | 包含的子分类 |
|--------|-------------|
| **对话** | 对话、对白、潜台词 |
| **情感** | 情感、情绪 |
| **场景** | 场景、环境、描写、感官 |
| **节奏** | 节奏、连载、高潮 |
| **情节** | 情节、冲突、战斗、反转、悬疑、推理、布局、伏笔、智斗、结局、设定、设定执行、规则、种田、快穿、仙侠、幻言、年代、历史、游戏、科幻、短篇、古言、世情、章纲、大纲、整合、衍生、结构、修行、竞技、经营、恐怖 |
| **人物** | 人物、动作、表现 |
| **文笔** | 文笔、修辞、句法、文体、叙事、视角 |

## CSV 导入

- 源文件: `.opencode/references/csv/写作技法.csv`（57 条原始技法）
- 首次 API 调用自动 seed: `DirectorDAO.import_from_csv()` → 104 条记录（含正反例拆分）
- 主分类通过 `_PRIMARY_CATEGORY_MAP` 自动映射
- 导入时自动建表（`_ensure_tables()`），兼容旧 `index.db`

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/techniques/grouped` | 按 7 大主分类分组返回 |
| GET | `/api/techniques?category=对话` | 按主分类检索 |
| GET | `/api/techniques?search=xxx` | 关键词搜索（名称 + 描述） |
| POST | `/api/techniques/track` | 记录章节技法使用 |
| GET | `/api/director/styles` | 文风规则列表 |
| GET | `/api/director/styles/{id}` | 文风规则详情 |
| POST | `/api/director/styles` | 创建文风规则 |
| PUT | `/api/director/styles/{id}` | 更新文风规则 |
| DELETE | `/api/director/styles/{id}` | 删除文风规则 |
| GET | `/api/director/styles/prompt` | 生成可注入 Agent 的文风提示 |

## webnovel-style Skill

- 位置: `.opencode/skills/webnovel-style/SKILL.md`
- 功能: 加载导演文风 + 检索写作技法
- 加载时机:
  - editor-agent Step A（获取上下文时）
  - chapter-writer-agent Step 1（起草前）

## Dashboard 展示

`/style` 页面 → 写作技法 Tab → 7 大类分组展开视图:

```
写作技法
├── 对话 (N 条)  [展开 ▼]
│   ├── 技法名 | 子类 | 描述 | 适用场景
│   └── ...
├── 情感 (N 条)  [展开 ▼]
├── 场景 (N 条)  [展开 ▼]
├── 节奏 (N 条)  [展开 ▼]
├── 情节 (N 条)  [展开 ▼]
├── 人物 (N 条)  [展开 ▼]
└── 文笔 (N 条)  [展开 ▼]
```

每类显示技法数，展开后显示名称、子类、描述、适用场景。前端组件 `StyleEditorPage.jsx` 使用 `fetchGroupedTechniques()` 获取分组数据，替代旧的 `fetchTechniques()` 扁平列表。

## 文风约束 6 Tab

`/style` 页面包含 6 个编辑 Tab:

| Tab | 内容 | 存储位置 |
|-----|------|----------|
| 自定义提示词 | 作者自定义写作指令 | `dashboard_config.json` |
| 全局文风 | 全局风格规则 | `director_style` 表 |
| 禁止模式 | AI 禁用词/句式/模式 | `director_style` 表 (category='禁止模式') |
| 写作技法 | 7 大类技法目录 | `writing_techniques` 表 |
| 章级合同 | 每章独立风格约束 | `story_contracts` |
| 审查维度 | 13 维度审查权重配置 | `dashboard_config.json` |

## 文风提示生成

`DirectorDAO.get_styles_prompt()` 聚合所有活跃文风规则，生成可注入 Agent prompt 的文本块:

```
[文风约束]
1. 规则名 (优先级: N): 描述
2. ...
```

此提示在导演智能体 Step 1 和 ChapterWriter Step 3 自动注入。

## ChapterWriter 文风集成

ChapterWriter 在 Step 3 润色成文时：

1. 调用 webnovel-style skill 加载当前激活的文风规则
2. 通过 ChapterDAO 搜索自己过去写过的相关段落作为参考
3. 将文风规则作为写作 prompt 的一部分注入

### 自搜索流程

```
ChapterWriter 开始润色
  → ChapterDAO.search(query=当前场景关键词, limit=5)
  → 返回过去5章中最相关段落
  → 分析: 上次怎么描写的？这次保持一致的笔法
```
