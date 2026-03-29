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

## 项目结构

```
项目目录/
├── .opencode/              # OpenCode 配置
│   ├── skills/            # 9个 Skills
│   ├── agents/           # 8个 Agents（context-agent, data-agent, 6个 Checker）
│   ├── checkers/         # 审查器配置驱动
│   ├── scripts/          # Python 核心脚本
│   ├── references/      # 参考文档
│   ├── genres/          # 题材参考（38+）
│   └── templates/       # 输出模板
├── opencode.json          # Agents 配置
├── .env                   # API 配置
└── init.sh / init.bat    # 安装脚本
```
