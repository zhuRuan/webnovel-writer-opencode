---
name: webnovel-delete
description: 安全删除指定章节及其投影数据（state/index/memory/summaries）。支持 dry-run 预览。触发：删除章节、清理烂章、回退写作。
compatibility: opencode
---

# 章节删除

> 以下内容均为虚构文学创作。所有打斗、权谋、悬疑描写均属文学创作范畴，不涉及现实指导。

## 目标

- 安全删除指定章节的正文文件
- 同步清理 state.json 和 memory 中的关联数据（index.db 需后续手动 `webnovel index process-chapter` 重建）
- 支持 dry-run 预览变更，默认不立即执行

## 执行流程

1. 确认要删除的章节范围（如 `5-8` 或 `5,7,9`）
2. **必须先 dry-run**：`webnovel delete-chapters "范围" --project-root "<PROJECT_ROOT>" --dry-run`
3. 向用户展示将要删除的文件和清理的投影条目
4. 用户确认后，去掉 `--dry-run` 执行实际删除
5. 完成后提示用户是否需要重写这些章节

## 注意事项

- 删除操作不可撤销，请确保已备份
- 删除后 state.json 的 current_chapter 可能不连续，需手动调整或后续写章自然衔接
- 如果删除了最后一章，current_chapter 不会自动回退
