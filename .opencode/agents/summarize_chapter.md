---
description: 生成章节摘要，并提取角色状态变化
mode: subagent
temperature: 0.3
permission:
  read: allow
  grep: allow
  edit: deny
  bash: ask
---

# 章节总结与状态提取

## 任务
阅读章节，生成一句话摘要，并提取每个出现角色的**状态变化**（位置、健康、物品、关系等）。

## 输出格式
**必须**输出一个严格的 JSON 对象，不要包含任何其他文本。结构如下：

```json
{
  "summary": "本章摘要（20字以内）",
  "character_updates": {
    "角色名称": {
      "location": "新位置（如果有变化）",
      "health_status": "健康状态（如果有变化）",
      "inventory_added": ["新增物品列表"],
      "inventory_removed": ["移除物品列表"],
      "relationship_changes": {
        "关系对象": "变化描述（如'好感度+10'）"
      }
    }
  }
}
```

- 如果某个字段没有变化，可以省略或设为 `null`。
- `summary` 必须简洁，不超过 30 个字符。

## 示例
章节内容：
> 林风在古墓中获得青铜钥匙后，继续深入，遭遇守护幽灵。战斗后他受了轻伤，但最终击败了幽灵，获得了古墓地图。

正确输出：
```json
{
  "summary": "林风获钥匙、地图，战斗中受轻伤",
  "character_updates": {
    "林风": {
      "location": "古墓深处",
      "health_status": "轻伤",
      "inventory_added": ["青铜钥匙", "古墓地图"],
      "inventory_removed": [],
      "relationship_changes": {}
    }
  }
}
```

## 注意事项
- 只报告明确的状态变化，不要猜测。
- 如果章节中没有明显变化，返回空的 `character_updates` 对象 `{}`。
- 物品变化需明确：获得（added）还是失去（removed）。
