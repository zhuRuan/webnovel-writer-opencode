# 审查器开发指南

本文档说明如何为 Webnovel Writer 添加新的审查器。

## 审查器架构

审查器采用配置驱动架构，由两部分组成：

| 组件 | 路径 | 说明 |
|------|------|------|
| 注册表 | `.opencode/checkers/registry.yaml` | 审查器**配置**，包含列表、分类、触发条件、agent 文件路径 |
| Agent 文件 | `.opencode/agents/xxx-checker.md` | 审查器**实现**，包含 prompt 模板和输出格式定义 |
| Schema | `.opencode/checkers/schema.yaml` | 输出格式定义 |

> **关键概念**：registry.yaml 的 `file` 字段指定 agent 文件路径（如 `../agents/consistency-checker.md`），代码会根据此路径加载审查器实现。

## 快速开始

### 方式一：使用 CLI 命令创建

```bash
python .opencode/scripts/webnovel.py checkers create \
  --id new-checker \
  --name "新检查器" \
  --category core \
  --description "检查功能描述"
```

CLI 命令会自动：
1. 创建 Agent 文件 `.opencode/agents/new-checker.md`
2. 注册到 `registry.yaml`

### 方式二：手动创建

手动创建需要以下步骤：

1. 创建 Agent 文件
2. 注册审查器
3. （可选）扩展 Schema
4. 验证配置

---

## 步骤一：创建 Agent 文件

在 `.opencode/agents/` 目录下创建新审查器文件，例如 `new-checker.md`。

### 文件模板

```markdown
---
description: 新检查功能描述
mode: subagent
temperature: 0.1
permission:
  read: allow
  grep: allow
  edit: deny
  bash: ask
---

# new-checker (新检查器)

> **职责**: 一句话描述检查功能
> **输出格式**: 遵循 `../checkers/schema.yaml` 统一 Schema

## 检查范围

**输入参数**:
{
  "chapter": 100,
  "chapter_file": "正文/第0100章-{title}.md",
  "project_root": "{PROJECT_ROOT}"
}

## 执行流程

### 第一步: 加载参考资料

并行读取：
- 目标章节正文
- state.json（主角状态、进度）
- 设定集相关文件

### 第二步: 执行检查

根据检查类型执行对应逻辑...

### 第三步: 生成报告

{
  "agent": "new-checker",
  "chapter": 100,
  "overall_score": 85,
  "pass": true,
  "issues": [
    {
      "id": "ISSUE_001",
      "type": "问题类型",
      "severity": "high",
      "description": "问题描述",
      "location": "第5段",
      "suggestion": "修复建议"
    }
  ],
  "metrics": {},
  "summary": "一句话总结"
}

## 禁止事项

❌ 禁止事项 1
❌ 禁止事项 2

## 成功标准

- 成功标准 1
- 成功标准 2
```

---

## 步骤二：注册审查器

编辑 `.opencode/checkers/registry.yaml`，添加审查器配置：

```yaml
checkers:
  new-checker:
    name: 新检查器名称
    name_en: New Checker
    file: ../agents/new-checker.md
    category: core  # 或 conditional
    enabled: true
    description: 检查功能描述
    triggers: []   # conditional 类型需要填写
    invoke_template: |
      对第 {chapter} 章执行新检查。
      - 章节文件：{chapter_file}
      - 项目根：{PROJECT_ROOT}
      - 审查器定义见：.opencode/agents/new-checker.md
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 中文名称 |
| `name_en` | 否 | 英文名称 |
| `file` | 是 | Agent 文件路径（相对于 checkers/ 目录） |
| `category` | 是 | `core`（核心）或 `conditional`（条件） |
| `enabled` | 否 | 是否启用，默认 true |
| `description` | 否 | 功能描述 |
| `triggers` | 否 | 触发条件（仅 conditional 需要） |
| `invoke_template` | 否 | 调用模板 |

### category 说明

| 类型 | 说明 |
|------|------|
| `core` | 核心审查器，始终执行 |
| `conditional` | 条件审查器，满足 triggers 时执行 |

### triggers 示例

```yaml
triggers:
  - 非过渡章
  - 有明确未闭合问题/期待锚点
  - 用户显式要求"追读力审查"
```

---

## 步骤三：扩展 Schema（可选）

如果新审查器有特殊 metrics，在 `.opencode/checkers/schema.yaml` 中添加：

```yaml
metrics_definitions:
  new-checker:
    fields:
      field_name:
        type: integer
        description: 字段说明
```

---

## 步骤四：验证配置

```bash
# 验证配置完整性
python .opencode/scripts/webnovel.py checkers validate

# 列出审查器
python .opencode/scripts/webnovel.py checkers list

# 查看特定审查器 Schema
python .opencode/scripts/webnovel.py checkers schema new-checker
```

---

## 审查器分类

### Code Checkers（代码层）

运行在 LLM 之前，用于快速阻断严重问题。确定性检查，执行速度快（~ms）：

| 检查器 | 说明 | 阻塞级别 |
|--------|------|----------|
| `world-consistency` | 战力/道具/时间线一致性 | critical 阻断 |
| `DebtTracker` | 债务追踪（伏笔/承诺/偿还） | high 阻断 |

**特点**：
- 无需 LLM 调用，纯 Python 逻辑
- 优先于 LLM Agents 执行
- critical/high 问题可硬阻塞后续流程

**使用方式**：

```python
from data_modules.checkers_manager import CheckersManager

# 注册 code checker
CheckersManager.register_code_checker(
    "my-checker",
    lambda chapter, content, ctx: [{"severity": "high", "message": "test"}],
    {"block_on_critical": True}
)

# 运行分层审查
result = CheckersManager.run_layered_checkers(chapter, content, context)
# blocked=True → 立即终止，不调用 LLM
```

### 核心审查器（Core）

始终执行：

| 审查器 | 说明 |
|--------|------|
| `consistency-checker` | 设定一致性 |
| `continuity-checker` | 连贯性 |
| `ooc-checker` | 人物 OOC |

### LLM Agents（语言模型层）

满足触发条件时执行：

| 审查器 | 触发条件 |
|--------|---------|
| `reader-pull-checker` | 非过渡章、有未闭合问题 |
| `high-point-checker` | 关键章/高潮章、有战斗/打脸 |
| `pacing-checker` | 章号 >= 10、节奏失衡风险 |

---

## 债务追踪（DebtTracker）

债务追踪用于管理网文中的"债务"（伏笔、承诺、断章钩子）：

### 创建债务

在正文中使用显式标签：

```
[伏笔:神秘玉佩]  # 自动创建 Debt，priority=HIGH
```

### 偿还债务

```
[回收:神秘玉佩]  # 自动标记 repaid=True
```

### 硬约束

```python
from data_modules.debt_tracker import DebtTracker

tracker = DebtTracker()

# 检查是否可以写高潮章节
can_write, reason = tracker.can_write_climax(chapter_num)
# - 高优先级债务未偿还 → False
# - >3 活跃债务 → False
```

### 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `context_debt_aware_budget_enabled` | True | 启用债务感知预算 |
| `context_debt_aware_threshold` | 2 | 触发阈值 |
| `context_debt_aware_foreshadow_weight` | 0.15 | 15% Token 重分配 |

---

## 输出格式约束

所有审查器必须返回统一格式：

```json
{
  "agent": "审查器ID",
  "chapter": 章节号,
  "overall_score": 0-100,
  "pass": true/false,
  "issues": [
    {
      "id": "ISSUE_001",
      "type": "问题类型",
      "severity": "critical|high|medium|low",
      "description": "问题描述",
      "location": "位置",
      "suggestion": "修复建议"
    }
  ],
  "metrics": {},
  "summary": "一句话总结"
}
```

### 关键字段要求

| 字段 | 要求 |
|------|------|
| `overall_score` | 必须使用此字段（不是 `score`） |
| `severity` | 使用 `critical/high/medium/low`（全小写） |
| `issues` | 数组，每个 issue 必须包含 `severity` 和 `suggestion` |
