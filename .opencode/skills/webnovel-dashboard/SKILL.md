---
name: webnovel-dashboard
description: 启动小说管理面板，查看项目状态、编辑文风约束。
compatibility: opencode
---

# Webnovel Dashboard

## 目标

在本地启动 Web 面板，查看创作进度、设定词典、关系图谱、章节内容与追读力数据，并可编辑文风约束。

## 功能概览

| 页面 | 路由 | 功能 |
|------|------|------|
| 总览 | `/` | 统计卡片、章节趋势、告警、伏笔提醒 |
| 上下文健康 | `/context` | Token 预算、Section 状态、权重分布、历史趋势 |
| 角色图鉴 | `/characters` | 实体列表、关系图谱、**时间线（状态变化+出场记录+异常检测）** |
| 审查分析 | `/review` | 维度雷达图、严重程度分布、趋势折线图、Critical Issues |
| 节奏雷达 | `/pacing` | 钩子强度、strand 分布、字数箱线图 |
| 伏笔追踪 | `/foreshadowing` | 伏笔甘特图、债务表 |
| 文档浏览 | `/files` | 文件树、正文预览 |
| **文风约束** | `/style` | **编辑文风约束（6 Tab：自定义文风+全局+禁止+技法+合同+审查维度）** |
| 系统状态 | `/system` | 合同树、提交历史、RAG 环境、运维操作、**批量操作** |

### 主题

支持亮色/暗色模式切换（侧边栏右上角 🌙/☀️ 按钮），偏好持久化到 localStorage。

## 文风约束编辑器（/style）

5 个 Tab 对应 5 层文风约束：

| Tab | 数据源 | 读写 |
|-----|--------|------|
| **自定义文风** | `设定集/prompts/*.md` | **读写（新建+编辑+删除）** |
| 全局文风 | `MASTER_SETTING.json` → `master_constraints` | 读写（locked 字段不可改） |
| 禁止模式 | `anti_patterns.json` | 读写（增删） |
| 写作技法 | `写作技法.csv`（104 条） | 只读（搜索+筛选+展开详情） |
| 章级合同 | `.story-system/chapters/chapter_*.json` | 只读（章节选择+详情查看） |
| 审查维度 | `reviewer.md` 6 维度 + `anti_patterns.json` | 只读 |

### 写入 API

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

### 只读 API

| Endpoint | 功能 |
|----------|------|
| `/api/context/health/{chapter}` | 上下文健康度报告（Section 状态、Token 估算、关键排除告警） |
| `/api/context/history` | 最近 N 章上下文健康趋势 |
| `/api/entities/{id}/timeline` | 实体状态变化时间线 + 出场记录 |
| `/api/consistency/anomalies` | 实体状态异常检测（值回退、无变化） |
| `/api/review/analytics` | 审查维度分析（8 维度趋势、严重程度、weakest 3） |
| `/api/foreshadowing/reminders` | 即将到期的伏笔提醒 |

### 配置

可通过 `.webnovel/dashboard_config.json` 自定义关键 Section 列表：

```json
{
  "critical_sections": ["core", "scene", "story_contract", "user_prompts", "memory"]
}
```

不配置时默认使用 `{"core", "scene", "story_contract", "user_prompts"}`。支持运行时修改（无需重启）。

## 环境设置

```bash
# 以下命令假设当前目录为 webnovel-writer 仓库根目录
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export DASHBOARD_DIR="${PWD}/.opencode/dashboard"
test -d "${DASHBOARD_DIR}" || { echo "错误: 未找到 ${DASHBOARD_DIR}，请确保当前目录是 webnovel-writer 仓库根目录"; exit 1; }
```

## 执行流程

### Step 1：安装依赖

```bash
python -m pip install -r "${DASHBOARD_DIR}/requirements.txt" --quiet
```

### Step 2：解析项目路径 + 校验前端

```bash
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PWD}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "错误: PROJECT_ROOT 解析失败，请用 --project-root 显式指定"; exit 1; }
echo "项目路径: ${PROJECT_ROOT}"

test -f "${DASHBOARD_DIR}/frontend/dist/index.html" || { echo "错误: 缺少前端构建产物 ${DASHBOARD_DIR}/frontend/dist/index.html"; exit 1; }
```

### Step 3：启动 Dashboard（后台运行）

> Dashboard 是长运行服务（uvicorn），必须用后台模式启动。命令中设置 `run_in_background: true`。

```bash
PYTHONPATH="${PWD}/.opencode" python -X utf8 -m dashboard.server --project-root "${PROJECT_ROOT}"
```

默认端口 8765，访问 `http://127.0.0.1:8765`。

自定义端口：
```bash
PYTHONPATH="${PWD}/.opencode" python -X utf8 -m dashboard.server --project-root "${PROJECT_ROOT}" --port 9000 --no-browser
```

自动关闭旧进程并启动：
```bash
PYTHONPATH="${PWD}/.opencode" python -X utf8 -m dashboard.server --project-root "${PROJECT_ROOT}" --kill-existing --no-browser
```

### Step 4：验证服务

```bash
curl -s http://127.0.0.1:8765/api/story-runtime/health || echo "服务未启动"
curl -s http://127.0.0.1:8765/api/style/master-setting || echo "文风编辑器不可用"
```

## 项目根目录解析

`server.py` 按以下优先级解析项目根目录：

1. `--project-root` 参数
2. `WEBNOVEL_PROJECT_ROOT` 环境变量
3. CWD 向上搜索（找到包含 `.webnovel/state.json` 的目录）
4. `.opencode/.webnovel-current-project` 指针文件
5. 智能搜索同级目录（支持嵌套结构如 `E:\workspace\webnovel\书名\`）

## 注意事项

- Dashboard 提供只读查询 + 文风约束编辑（写入操作限于 master_constraints 和 anti_patterns）
- uvicorn 默认监听 `127.0.0.1:8765`
- 首次启动可能需安装依赖（`pip install -r requirements.txt`）
- Windows 中文输出乱码：运行 `chcp 65001` 后重试
- 端口被占用时自动检测并提示，可用 `--kill-existing` 自动关闭旧进程

## 失败恢复

| 故障 | 恢复方式 |
|------|---------|
| 依赖安装失败 | 检查 Python 版本，手动 `pip install -r requirements.txt` |
| 前端 `dist/` 缺失 | 确认插件完整安装 |
| PROJECT_ROOT 解析失败 | 显式传 `--project-root` 或设置 `WEBNOVEL_PROJECT_ROOT` 环境变量 |
| 端口占用 | 使用 `--kill-existing` 自动关闭旧进程，或 `--port <其他端口>` |
| 服务被 timeout 终止 | 确保使用后台模式（`run_in_background: true`）启动 |
| 页面空白/数据缺失 | 确认 `.webnovel/` 下有 state.json、index.db 等数据文件 |
