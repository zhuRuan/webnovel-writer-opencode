# 看板演进实现计划 — Phase 1~3

> **目标**：将看板从只读观察窗升级为可操作的写作指挥中心
> **顺序**：Phase 1（操作能力）→ Phase 2（实时监控）→ Phase 3（质量预警）

---

## Phase 1：操作能力——安全写入口

### 目标

在看板 UI 上暴露低风险 CLI 操作，不改写核心 pipeline。所有危险操作带二次确认。

### 后端改动

#### 1.1 新增 POST 端点

`app.py` 当前声明"仅提供 GET 接口"。新增 4 个 POST 端点，每个操作在 Python 进程中执行对应 CLI 命令：

| 端点 | CLI 等价 | 风险等级 |
|------|---------|---------|
| `POST /api/actions/ssot-verify` | `webnovel ssot verify` | 只读 |
| `POST /api/actions/ssot-rebuild` | `webnovel ssot rebuild` | 低（可逆） |
| `POST /api/actions/entity-clean` | `webnovel entity-clean --mark-invalid` | 低 |
| `POST /api/actions/chapter-delete` | `webnovel delete-chapters "{chapters}" --dry-run` | 中（需确认） |

实现模式：每个端点调用 `subprocess.run()` 执行 `webnovel.py` 子命令，返回 stdout + stderr + exit_code。

```python
@app.post("/api/actions/{action}")
def run_action(action: str, payload: dict | None = None):
    """Execute a low-risk CLI action and return output."""
    ALLOWED = {"ssot-verify", "ssot-rebuild", "entity-clean", "chapter-delete"}
    if action not in ALLOWED:
        raise HTTPException(403, f"不允许的操作: {action}")
    
    cmd = ["python", "-X", "utf8", str(SCRIPTS_DIR / "webnovel.py"),
           "--project-root", str(_get_project_root())]
    # ... dispatch to specific subcommand
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
```

`SCRIPTS_DIR` 在 `_ensure_scripts_dir_on_path()` 中已解析。

#### 1.2 SSE 事件扩展

操作完成后推送 SSE 事件通知前端刷新：

```python
_watcher._dispatch(json.dumps({"type": "action-done", "action": action, "ts": time.time()}))
```

### 前端改动

#### 1.3 SystemPage 新增"运维操作"面板

在 SystemPage 底部新增卡片组：

- **SSOT 一致性检查**按钮 → 调用 `/api/actions/ssot-verify` → 展示漂移结果表格
- **重建投影**按钮（带确认）→ `/api/actions/ssot-rebuild` → 进度提示
- **脏实体扫描**按钮 → `/api/actions/entity-clean` → 展示结果列表

#### 1.4 章节列表增加操作入口

OverviewPage 的章节趋势表中，每行增加操作图标（…菜单）：
- "查看详情" → 跳转章节页面
- "删除此章" → 二次确认 → 调用 `/api/actions/chapter-delete`

### 安全约束

- Chapter delete 默认 dry-run，需要额外参数 `--confirm` 才真正执行
- POST 端点加入请求频率限制（1 次/秒）
- 操作历史记录到 `index.db` 的 `tool_call_stats` 表

### 测试

- 每个 POST 端点单元测试（mock subprocess）
- SSE 事件推送验证

---

## Phase 2：写作会话实时监控

### 目标

将 5 阶段 workflow 状态机、审查结果、上下文预算可视化到看板。

### 后端改动

#### 2.1 新增 SSE 事件类型

`watcher.py` 在文件变更基础上，增加定时轮询推送：

| SSE 事件 | 数据源 | 推送频率 |
|----------|--------|----------|
| `workflow-status` | `workflow checkpoint status` | 30s |
| `review-update` | `review_metrics` 表最新行 | 按变更 |
| `context-budget` | `chapter-NNN.trace.json` | 按章 |
| `debt-due` | `chase_debt` 表 active/pending | 60s |

实现：扩展现有 `_dispatch` 机制，新增一个定时轮询协程在 lifespan 中启动。

#### 2.2 新增 API 端点

```python
@app.get("/api/workflow/status")
def workflow_status():
    """返回所有章节的 5 阶段状态。"""
    checkpoint_file = _webnovel_dir() / "workflow_checkpoints.json"
    if not checkpoint_file.is_file():
        return {"stages": {}, "interrupted": []}
    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    return data

@app.get("/api/context/budget/{chapter}")
def context_budget(chapter: int):
    """返回指定章的上下文预算使用情况。"""
    trace_file = _webnovel_dir() / "runtime" / f"chapter-{chapter:03d}.trace.json"
    if not trace_file.is_file():
        raise HTTPException(404, "trace 文件不存在")
    return json.loads(trace_file.read_text(encoding="utf-8"))
```

### 前端改动

#### 2.3 新增"写作进度"Widget（OverviewPage 顶部）

一行 5 个圆点表示当前章节的 workflow 状态：
```
●━━●━━●━━○━━○
PLAN  DRAFT  REVIEW  REVISE  COMMIT
```
当前活跃阶段高亮脉冲动画，已完成阶段绿色，未到达阶段灰色。

#### 2.4 审查分数趋势图增强

现有 `chapter-trend` API 已返回 `review_score`。新增：
- 6 维度雷达图（从 `dimension_scores` 渲染）
- 低分章高亮（score < 65 红色标记）

#### 2.5 伏笔偿还倒计时

ForeshadowingPage 新增"即将到期"卡片：
- `due_chapter - current_chapter <= 3` → 黄色
- `due_chapter < current_chapter` → 红色
- 显示内容摘要 + 剩余章数 + 紧迫度条

数据来自 `/api/debts?status=pending`。

---

## Phase 3：质量预警

### 目标

被动展示 → 主动预警，在看板上直接看到需要关注的问题。

### 后端改动

#### 3.1 新增 `/api/alerts` 端点

```python
@app.get("/api/alerts")
def get_alerts():
    """Return prioritized list of quality alerts."""
    state = _load_state_payload()
    alerts = []
    
    # Continuity: consecutive score decline
    recent = _get_recent_review_scores(5)
    if _is_declining(recent, threshold=3):
        alerts.append({"type": "score_decline", "severity": "warning",
                        "detail": f"连续{len(recent)}章审查分下降", "chapters": recent})
    
    # Debt: overdue foreshadowing
    overdue = _get_overdue_debts(state)
    for d in overdue:
        alerts.append({"type": "debt_overdue", "severity": "critical",
                        "detail": d["note"], "due_chapter": d["due_chapter"],
                        "current_chapter": state["progress"]["current_chapter"]})
    
    # Character: long absence
    absent = _get_long_absent_characters(state, threshold=20)
    for c in absent:
        alerts.append({"type": "character_absent", "severity": "info",
                        "detail": f"{c['name']} 已 {c['absent_chapters']} 章未出场"})
    
    # Pacing: strand monotony
    monotony = _check_strand_monotony(state, threshold=5)
    if monotony:
        alerts.append({"type": "strand_monotony", "severity": "info",
                        "detail": f"连续 {monotony['count']} 章同一主线: {monotony['strand']}"})
    
    return {"alerts": alerts, "updated_at": datetime.now(timezone.utc).isoformat()}
```

#### 3.2 预警计算辅助函数

- `_get_recent_review_scores(n)` — 从 `review_metrics` 表取最近 N 章 overall_score
- `_is_declining(scores, threshold)` — 连续 threshold 章单调递减
- `_get_overdue_debts(state)` — 从 index.db `chase_debt` 表查 overdue
- `_get_long_absent_characters(state, threshold)` — 遍历 entities_v3 找 last_appearance 与 current_chapter 差距
- `_check_strand_monotony(state, threshold)` — 从 strand_tracker.history 检测连续重复

### 前端改动

#### 3.3 OverviewPage 顶部新增"预警横幅"

红色/黄色/蓝色横幅水平滚动，显示当前活跃预警。点击展开详情。

#### 3.4 各页面内联预警标记

- CharactersPage：长期未出场角色前加 ⚠ 图标
- ForeshadowingPage：逾期伏笔红色高亮行
- PacingPage：strand 单调区域的黄色背景

---

## 实现顺序与依赖

```
Phase 1 (操作能力)     → 独立，无依赖，~4h
Phase 2 (实时监控)     → 依赖 Phase 1 的 SSE 扩展，~6h
Phase 3 (质量预警)     → 依赖 Phase 2 的数据端点，~4h
```

总计 ~14h，三项独立可交付，每项完成后看板即可用。

---

## 风险与约束

- POST 端点引入写操作，需确保 CSRF 保护（CORS 已限制 localhost，Dashboard 无 cookie 认证）
- 轮询 SSE 在长时间空闲后需要心跳保活（已有 `_dispatch` QueueFull drain）
- 预警阈值（连续 N 章下降、M 章未出场）需可配置，建议默认值可被 `dashboard_config.json` 覆盖
