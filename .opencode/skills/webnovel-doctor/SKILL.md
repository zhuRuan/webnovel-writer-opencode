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

诊断检查 5 类：文件检查、JSON 检查、SQLite 检查、投影检查、Python 检查。blocking 问题根据 `repair` 字段执行修复，warning 建议修复但不阻塞。

### Step 3：验证修复

修复后重新运行诊断确认问题已解决。

## 注意事项

- 诊断是只读操作，不会修改任何文件
- blocking 问题必须修复后才能正常写作
- warning 问题建议修复但不阻塞
- `--deep` 模式包含 dashboard 检查
