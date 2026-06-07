# Dashboard API 参考

## 写入 API

| Endpoint | Method | 功能 |
|----------|--------|------|
| `/api/style/master-setting` | PUT | 更新 `master_constraints` |
| `/api/style/anti-patterns` | POST | 追加反模式（自动去重） |
| `/api/style/anti-patterns` | DELETE | 按文本删除反模式 |
| `/api/style/prompts` | POST | 创建提示词文件 |
| `/api/style/prompts/{filename}` | PUT | 更新提示词内容 |
| `/api/style/prompts/{filename}` | DELETE | 删除提示词文件 |
| `/api/actions/{action}` | POST | 运维操作（ssot-verify/rebuild, entity-clean） |
| `/api/batch/{action}` | POST | 批量操作（write/delete，async 不阻塞） |

写入操作通过 `atomic_write_json` 原子写入，带文件锁防并发。批量操作使用 `asyncio.create_subprocess_exec` 避免阻塞 FastAPI 线程。

## 只读 API

| Endpoint | 功能 |
|----------|------|
| `/api/context/health/{chapter}` | 上下文健康度报告（Section 状态、Token 估算、关键排除告警） |
| `/api/context/history` | 最近 N 章上下文健康趋势 |
| `/api/entities/{id}/timeline` | 实体状态变化时间线 + 出场记录 |
| `/api/consistency/anomalies` | 实体状态异常检测（值回退、无变化） |
| `/api/review/analytics` | 审查维度分析（8 维度趋势、严重程度、weakest 3） |
| `/api/foreshadowing/reminders` | 即将到期的伏笔提醒 |

## 配置

可通过 `.webnovel/dashboard_config.json` 自定义关键 Section 列表：

```json
{
  "critical_sections": ["core", "scene", "story_contract", "user_prompts", "memory"]
}
```

不配置时默认使用 `{"core", "scene", "story_contract", "user_prompts"}`。支持运行时修改（无需重启）。
