# 系统架构与模块设计

## 核心理念

### 防幻觉三定律

| 定律 | 说明 | 执行方式 |
|------|------|---------|
| **大纲即法律** | 遵循大纲，不擅自发挥 | Context Agent 强制加载章节大纲 |
| **设定即物理** | 遵守设定，不自相矛盾 | Consistency Checker 实时校验 |
| **发明需识别** | 新实体必须入库管理 | Data Agent 自动提取并消歧 |

### Strand Weave 节奏系统

| Strand | 含义 | 理想占比 | 说明 |
|--------|------|---------|------|
| **Quest** | 主线剧情 | 60% | 推动核心冲突 |
| **Fire** | 感情线 | 20% | 人物关系发展 |
| **Constellation** | 世界观扩展 | 20% | 背景/势力/设定 |

节奏红线：

- Quest 连续不超过 5 章
- Fire 断档不超过 10 章
- Constellation 断档不超过 15 章

## 总体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenCode                               │
├─────────────────────────────────────────────────────────────┤
│  Skills (10个): init / plan / write / review / export /    │
│                dashboard / query / resume / learn / publish│
├─────────────────────────────────────────────────────────────┤
│  Agents (8个): context-agent / data-agent /                 │
│                 6 维 Checker                                 │
├─────────────────────────────────────────────────────────────┤
│  Data Layer: state.json / index.db / vectors.db            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Dashboard (独立模块)                                        │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Backend + React Frontend                           │
│  ├── app.py          # 应用入口                              │
│  ├── server.py       # 服务器                                │
│  ├── watcher.py      # 文件监听                              │
│  ├── publish_bridge.py # 发布数据桥接                        │
│  └── frontend/       # React SPA                            │
└─────────────────────────────────────────────────────────────┘
```

## 双 Agent 架构

### Context Agent（读）

职责：在写作前构建"创作任务书"，提供本章上下文、约束和追读力策略。

### Data Agent（写）

职责：从正文提取实体与状态变化，更新 `state.json`、`index.db`、`vectors.db`，保证数据链闭环。

## 六维并行审查

| Checker | 检查重点 |
|---------|---------|
| High-point Checker | 爽点密度与质量 |
| Consistency Checker | 设定一致性（战力/地点/时间线） |
| Pacing Checker | Strand 比例与断档 |
| OOC Checker | 人物行为是否偏离人设 |
| Continuity Checker | 场景与叙事连贯性 |
| Reader-pull Checker | 钩子强度、期待管理、追读力 |

## 核心模块

### 条件评估器 (condition_evaluator)

负责评估章节中触发的世界规则条件，判断是否符合预设规则。

### 时间图谱 (temporal_graph)

管理故事内时间线，支持时间锚点解析和时间线一致性检查。

### 自定义词典 (dicts/webnovel_dict.txt)

用于改进中文分词质量，支持网文领域专有名词（人名、功法、势力等）。

## 项目结构

```
项目目录/
├── .opencode/              # OpenCode 配置
│   ├── skills/            # 10个 Skills
│   ├── dashboard/         # 可视化面板（独立模块）
│   │   ├── app.py         # FastAPI 应用
│   │   ├── server.py      # 服务器配置
│   │   ├── watcher.py     # 文件监听
│   │   ├── publish_bridge.py # 发布数据桥接
│   │   └── frontend/      # React 前端
│   ├── agents/           # 8个 Agents（context-agent, data-agent, 6个 Checker）
│   ├── checkers/         # 审查器配置驱动
│   ├── dicts/            # 自定义词典（中文分词优化）
│   ├── scripts/          # Python 核心脚本
│   │   ├── data_modules/ # 核心数据模块
│   │   │   ├── condition_evaluator.py # 条件评估器
│   │   │   └── temporal_graph.py      # 时间图谱
│   │   ├── publisher/    # 番茄发布模块
│   │   ├── sync_chapters_to_db.py   # 章节同步
│   │   ├── sync_missing_chapters.py # 缺失章节同步
│   │   └── verify_chapters.py       # 章节验证
│   ├── references/      # 参考文档
│   ├── genres/          # 题材参考（38+）
│   └── templates/       # 输出模板
├── opencode.json          # Agents 配置
├── .env                   # API 配置
└── install.py             # 跨平台安装脚本
```
