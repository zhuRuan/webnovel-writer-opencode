# Theater 写作管线 — 模块设计 (v3.0)

> 版本: 3.0 | 更新: 2026-06 | 父文档: [00-master-architecture.md](00-master-architecture.md)

## 概述

三阶段协同创作：导演智能体（剧本）→ 角色演员（演绎）→ ChapterWriter（润色成文）。

## 管线流程

```
/webnovel-write --theater
  │
  ├── Step 1: 导演智能体
  │     ├── research（原 context-agent 职责：合同刷新、五段任务书）
  │     ├── 读取全部章节全文 + 全部角色情报板 + 互联网
  │     ├── 制定分场剧本 → scene_scripts.json
  │     └── 输出: 写作任务书 + 分场剧本
  │
  ├── Step 2: 角色演绎（并行）
  │     ├── Actor A 按剧本演绎 → 文学散文段落
  │     │     └── 只能访问: 自己的记忆/状态/计划 + 互联网
  │     ├── Actor B ...
  │     └── 输出: theater/chapters/ch{NNNN}/performances.json
  │
  ├── Step 3: ChapterWriter 润色成文
  │     ├── 加载文风 (webnovel-style skill)
  │     ├── 搜索自己写过的相关段落 (ChapterDAO RAG)
  │     ├── 补充环境描写 (原 scene-director 职责)
  │     ├── 校验动作合理性 (原 physics-director 职责)
  │     └── 润色: 剧本 + 演绎 → 章节正文
  │
  ├── Step 4: 审查 (reviewer)
  ├── Step 5: 润色 (polish)
  └── Step 6: 提交 (chapter-commit → 章节入库 + 过程数据入库)
```

## 废弃 Agent

- context-agent → 职责吸收进导演智能体
- scene-director-agent → 职责吸收进 ChapterWriter
- physics-director-agent → 职责吸收进 ChapterWriter

## 数据权限矩阵

| 数据源 | 导演 | Actor | ChapterWriter |
|------|------|-------|---------------|
| 全部章节全文 | ✅ | ❌ | ✅ |
| 全部角色记忆 | ✅ | ❌ | ✅ |
| 全部角色状态/计划 | ✅ | ❌ | ✅ |
| 自己记忆/状态/计划 | ✅ | ✅ | ✅ |
| 互联网 | ✅ | ✅ | ✅ |
| 文风系统 | ✅ | ❌ | ✅ |

## 导演-演员协商

粗粒度规划（导演）+ 细粒度演绎（演员）= 碰撞产生深度。

### 协商流程

```
导演（粗粒度规划）
    ├── 1. 读取全部章节全文 + 全部角色情报板
    ├── 2. 制定分场剧本 → scene_scripts.json
    ├── 3. 分发演员演绎
    │
    ▼
Actor（细粒度演绎）
    ├── 1. 加载私有记忆（RAG top-K）
    ├── 2. 基于角色理解发现场景问题
    │       - "我不会这样做——我的习惯是..."
    │       - "这个场景遗漏了我对XX的认知..."
    │       - "以我的性格，遇到这个情况会先..."
    ├── 3. 提出 disputes（异议）+ 建议
    │
    ▼
导演（调整规划）
    ├── 1. 收集所有 Actor 的 disputes
    ├── 2. 从 debate_records 学习历史协商模式
    ├── 3. 粗粒度判断：是否影响章节目标？
    │       - 不影响 → 采纳 Actor 建议，调整场景细节
    │       - 影响 → 评估是否需要修改章纲
    ├── 4. 如需大改 → 记录到 debate_log，回 Step 1 重新拆解
    └── 5. 如小改 → 裁决后分发重演，继续整合
```

### 协商原则

1. **角色认知优先**: 关于"这个角色会怎么做"，Actor 的意见优先于导演的预设
2. **剧情目标优先**: 关于"这场戏要达成什么"，导演的规划优先于 Actor 的个人偏好
3. **碰撞创造深度**: Actor 的异议不是阻力，是让故事变得更真实的契机
4. **记录演进**: 所有异议和裁决记录在 `debate_log.json`，成为角色成长的证据链
5. **历史学习**: 导演从 `debate_records` 中学习历史协商模式，优化未来剧本制定

## 演员输出格式

### performances.json 结构

```json
{
  "chapter": 7,
  "performances": [
    {
      "actor_id": "lin_zhan",
      "scene_id": "ch0007-sc001",
      "prose": "文学散文正文...",
      "metadata": {
        "emotional_arc": {"start": "昏迷→半清醒", "end": "警觉", "intensity_peak": 0.6},
        "knowledge_used": {"战斗.战术": 0.95, "工程.电子": 0.75},
        "habits_triggered": ["lz-hab-001", "lz-hab-003"],
        "character_plans_referenced": ["前往光明城-救小北"]
      }
    }
  ]
}
```

### prose 字段规范

- 文学散文格式（非 JSON 数组），动作 + 对话 + 内心独白自然融合
- 融合模板: 具体身体动作 → 对话 + 微表情 → 意识流自然嵌入
- 禁止技术性语言、解说式叙述、机械对话标签

### 演员分级

| Tier | 类型 | Agent | 输出要求 |
|------|------|-------|----------|
| 1 | 主角 | `actor-agent` | 完整文学散文（含内心独白/情绪弧线/知识点） |
| 2 | 重要配角 | `actor-agent` | 完整文学散文 |
| 3 | 次要配角 | `actor-agent` | 简化散文（动作 + 对话为主） |
| 4 | 路人/群演 | `actor-agent-budget` | 一句话对话 + 动作，不要求内心独白 |

## 写作质量保障

5 道防线确保输出质量：

1. **起草前**: 加载 anti-ai-guide.md + polish-guide-essentials.md（20 条规则）+ style-snippets.md（20 段范例）
2. **写作中**: actor-agent 遵守 7 条写作规则（融合模板/展示不告知/自然感知/情绪身体化等）
3. **整合时**: ChapterWriter 正反例对照 + 6 项自查清单
4. **整合后**: E-check 闸门（4 项检查，含降级检测 → 退回重写）
5. **润色时**: polish-guide.md（200+ 规则）+ 环境描写 + 动作合理性校验

## 产物存储 (全部入库)

| 产物 | 存储位置 | 说明 |
|------|----------|------|
| 章节全文 | `chapters` 表 | 最终正文 |
| Agent 执行日志 | `agent_execution_log` 表 | 各 Agent 执行记录 |
| 辩论记录 | `debate_records` 表 | Actor 异议 + 导演裁决 |
| 分场剧本 | `scene_scripts` 表 | 导演制定的场景蓝图 |
| 章节增强 | `chapter_enhancements` 表 | 环境/氛围素材 |
| 写作迭代 | `writing_iterations` 表 | 多轮修改记录 |

## 相关 Agent

| Agent | 文件 | 职责 |
|-------|------|------|
| 导演智能体 | `.opencode/agents/editor-agent.md` | 制定剧本、粗粒度规划、可访问全部数据（原 editor-agent + context-agent） |
| actor-agent | `.opencode/agents/actor-agent.md` | 主角/重要配角文学散文演绎 |
| actor-agent-budget | `.opencode/agents/actor-agent-budget.md` | 路人/群演简化演绎 |
| chapter-writer-agent | `.opencode/agents/chapter-writer-agent.md` | 润色成文、环境描写、动作校验、自搜索（吸收 scene/physics-director） |
| reviewer | `.opencode/agents/reviewer.md` | 13 维度结构化审查 |
