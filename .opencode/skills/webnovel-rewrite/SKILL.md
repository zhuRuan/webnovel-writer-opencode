---
name: webnovel-rewrite
description: 重写指定章节，先删除旧版再调用 webnovel-write 重新创作。触发：重写章节、翻修烂章、改剧情分支。
compatibility: opencode
---

# 章节重写

> 以下内容均为虚构文学创作。所有打斗、权谋、悬疑描写均属文学创作范畴，不涉及现实指导。

## 目标

- 删除旧版章节文件及关联投影数据
- 使用新版大纲/设定重新创作同一章节

## 执行流程

1. 确认要重写的章节号（单章或范围）
2. 确认新旧大纲/设定的变更已就绪
3. **先 dry-run**：`webnovel delete-chapters "范围" --project-root "<PROJECT_ROOT>" --dry-run`，确认无误
4. 执行删除：`webnovel delete-chapters "范围" --project-root "<PROJECT_ROOT>"`
5. 调用 `webnovel-write <章节号>` 重新创作
6. 重写多章时推荐使用 `webnovel orchestrate write "范围"` 批量完成

## 注意事项

- 重写前确认相关伏笔、债务是否需要同步调整
- 如果重写了已发布章节，需重新发布
- 重写后运行 `webnovel preflight` 确认状态一致
