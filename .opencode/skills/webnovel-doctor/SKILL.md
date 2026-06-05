---
name: webnovel-doctor
description: 项目健康诊断，检查完整性、配置、数据一致性。
compatibility: opencode
---

# 项目诊断

## 目标

检查项目的健康状态，发现潜在问题并提供修复建议。

## 执行流程

### Step 1：运行诊断

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" doctor --format text
```

### Step 2：分析结果

诊断检查以下类别：

| 类别 | 检查内容 | 严重性 |
|------|----------|--------|
| 文件检查 | 必需目录/文件存在性 | blocking |
| JSON 检查 | state.json/MASTER_SETTING.json 解析 | blocking |
| SQLite 检查 | index.db 表存在性/完整性 | warning |
| 投影检查 | 摘要文件/章节状态 | info |
| Python 检查 | 版本/必需模块 | blocking/warning |

### Step 3：修复建议

对于每个 blocking 问题，根据 `repair` 字段执行修复：

```bash
# 常见修复命令
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" story-system  # 生成合同
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" migrate       # 修复数据库
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" ssot rebuild  # 重建投影
```

### Step 4：验证修复

修复后重新运行诊断确认问题已解决：

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" doctor --format text
```

## 输出格式

诊断报告包含：
- 总体状态（健康/存在问题）
- 阻断问题数
- 警告数
- 逐项检查结果（含修复建议）

## 注意事项

- 诊断是只读操作，不会修改任何文件
- blocking 问题必须修复后才能正常写作
- warning 问题建议修复但不阻塞
- `--deep` 模式包含 dashboard 检查
