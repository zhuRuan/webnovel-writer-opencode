# 自动修复问题章节工作流

当章节出现连续性断裂、OOC 偏离、设定矛盾等问题时，按以下流程自动修复。

## 诊断

```bash
webnovel status --focus all             # 全局健康扫描
webnovel workflow status                # 查看所有章节阶段状态
webnovel workflow interrupted           # 查找中断未完成的章节
```

## 修复单个章节

```bash
webnovel orchestrate heal "42" --project-root "<PROJECT>"   # 重审查+重提交
webnovel preflight                                           # 验证修复结果
```

## 批量修复

```bash
# Dry-run 先预览
webnovel delete-chapters "40-45" --project-root "<PROJECT>" --dry-run

# 确认后执行删除+重写
webnovel delete-chapters "40-45" --project-root "<PROJECT>"
webnovel orchestrate write "40-45" --project-root "<PROJECT>"
```

## 设定冲突修复

```bash
# 查看世界规则变更
webnovel override list --project-root "<PROJECT>"

# 记录一条新规则覆盖
webnovel override add \
  --constraint-id "power.realm_limit" \
  --old-rule "金丹期修士无法在城市中使用法术" \
  --new-rule "获得混沌珠后，主角可无视城市禁制施法" \
  --rationale "混沌珠吸收禁制能量，详见第128章" \
  --chapter 128 \
  --domain "world_rule" \
  --project-root "<PROJECT>"

# 生成上下文提示给 AI
webnovel override context --chapter 129 --project-root "<PROJECT>"
```

## SSOT 一致性校验

```bash
webnovel ssot verify --project-root "<PROJECT>"    # 检查投影是否与事件日志一致
webnovel ssot rebuild --project-root "<PROJECT>"   # 从事件日志重建所有投影
webnovel ssot events --project-root "<PROJECT>"    # 查看完整事件历史
```

## 脏实体清理

```bash
webnovel entity-clean --project-root "<PROJECT>"           # 扫描脏实体（dry-run）
webnovel entity-clean --project-root "<PROJECT>" --mark-invalid  # 标记待修复
```
