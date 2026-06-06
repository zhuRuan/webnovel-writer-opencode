# 看板发展规划 — 2026 Q3-Q4

> **定位**：从写作监控面板演进为 AI 写作指挥中心
> **前提**：Phase 1-3（操作能力、实时监控、质量预警）已完成
> **核心目标**：对抗长篇小说 AI 写作中的"遗忘"和"幻觉"
> **最后更新**：2026-06-06

---

## 实施状态

| Phase | 名称 | 状态 | 完成日期 |
|-------|------|------|----------|
| 1-3 | 操作能力、实时监控、质量预警 | ✅ 已完成 | 2026-05 |
| 4 | Context Health 可视化 | ✅ 已完成 | 2026-06-06 |
| 5 | 实体时间线与一致性检测 | ✅ 已完成 | 2026-06-06 |
| 6 | 审查分析与质量洞察 | ✅ 已完成 | 2026-06-06 |
| 7 | 伏笔生命周期管理 | ✅ 已完成 | 2026-06-06 |
| 8 | 暗色模式与主题系统 | ✅ 已完成 | 2026-06-06 |
| 9 | 章节内联编辑器 | ⏭️ 跳过 | — |
| 10 | 批量操作面板 | ✅ 已完成 | 2026-06-06 |
| 11 | 多项目管理 | ⏭️ 跳过 | — |

---

## 当前状态评估

### 已完成能力

| 模块 | 能力 | 成熟度 |
|------|------|--------|
| 总览 | 统计卡片、审查趋势、字数分布、伏笔 Top5、workflow 进度、伏笔提醒 | ★★★★☆ |
| 上下文健康 | Token 预算、Section 状态、权重分布、历史趋势、关键排除告警 | ★★★★☆ |
| 角色图鉴 | 实体列表、关系图谱（力导向+时间轴）、状态变化历史、**时间线+异常检测** | ★★★★★ |
| 审查分析 | 8 维度雷达图、严重程度分布、趋势折线图、Critical Issues 列表 | ★★★★☆ |
| 节奏雷达 | 钩子强度趋势、Strand 堆叠分布、字数箱线图 | ★★★☆☆ |
| 伏笔追踪 | 甘特图、紧急度排序、筛选过滤 | ★★★☆☆ |
| 文档浏览 | 三目录树、文件预览 | ★★★☆☆ |
| 文风约束 | 自定义提示词、全局文风、禁止模式、写作技法、章级合同、审查维度 | ★★★★☆ |
| 系统状态 | 合同树、提交历史、RAG 环境、运维操作、**批量操作** | ★★★★☆ |
| 系统状态 | 运行态、合同树、commit 历史、RAG 诊断、运维操作 | ★★★★☆ |

### 核心缺口

1. **AI 认知透明度**：作者无法直观看到 AI 在每章"知道什么"和"不知道什么"
2. **一致性主动检测**：只能被动查看，无法主动发现跨章矛盾
3. **写作闭环**：看板只读+运维，无法直接触发写入/审查/修复
4. **数据分析深度**：趋势图为主，缺乏根因分析和模式识别

---

## Phase 4：Context Health 可视化

> **目标**：让作者看到 AI 在每章的"认知边界"——哪些信息被纳入、哪些被挤出、为什么

### 4.1 实际 trace JSON 结构

> **⚠️ 已验证**：以下结构来自 `context_manager.py` 第 132-144 行的 `build_context()` 方法。

```json
{
  "chapter": 42,
  "template": "default",
  "stage": "mid",
  "weights_used": {"global": 0.3, "master": 0.25, "user_prompts": 0.15, ...},
  "sections": {
    "included": ["global", "master", "user_prompts", "characters", "timeline"],
    "excluded": ["vector_context", "rag_context"]
  },
  "ranker": {"enabled": true}
}
```

**关键约束**：
- `sections` 是 `{included: string[], excluded: string[]}`，不是对象数组
- 无 `budget_limit`、无 per-section `tokens`、无 `critical` 标记
- 需要从 `context.json`（配对文件）获取实际 token 数
- "关键 section" 需从配置或硬编码列表定义（如 `global`, `master`, `characters`）

### 4.2 后端：Context Health API

```python
# 关键 section 列表（被排除时应告警）
CRITICAL_SECTIONS = {"global", "master", "characters", "timeline", "user_prompts"}

@app.get("/api/context/health/{chapter}")
def context_health(chapter: int):
    """返回指定章的上下文健康度报告。"""
    runtime_dir = _webnovel_dir() / "runtime"
    trace_file = runtime_dir / f"chapter-{chapter:03d}.trace.json"
    context_file = runtime_dir / f"chapter-{chapter:03d}.context.json"

    if not trace_file.is_file():
        raise HTTPException(404, "trace 文件不存在")

    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    sections = trace.get("sections", {})
    included = sections.get("included", [])
    excluded = sections.get("excluded", [])

    # 从 context.json 获取 token 信息（如果有）
    total_tokens = 0
    section_tokens = {}
    if context_file.is_file():
        ctx = json.loads(context_file.read_text(encoding="utf-8"))
        for name, content in ctx.items():
            if isinstance(content, str):
                tokens = len(content) // 2  # 粗略估算：2 字符 ≈ 1 token
                section_tokens[name] = tokens
                total_tokens += tokens

    critical_excluded = [s for s in excluded if s in CRITICAL_SECTIONS]
    health_score = 100 - len(critical_excluded) * 20

    return {
        "chapter": chapter,
        "stage": trace.get("stage", "unknown"),
        "template": trace.get("template", "default"),
        "included": included,
        "excluded": excluded,
        "critical_excluded": critical_excluded,
        "section_tokens": section_tokens,
        "total_tokens": total_tokens,
        "health_score": max(0, health_score),
        "weights_used": trace.get("weights_used", {}),
    }
```

### 4.3 后端：Context History API

```python
@app.get("/api/context/history")
def context_history(limit: int = Query(20, ge=1, le=100)):
    """返回最近 N 章的上下文健康度趋势。"""
    runtime_dir = _webnovel_dir() / "runtime"
    if not runtime_dir.is_dir():
        return {"items": []}

    items = []
    for trace_file in sorted(runtime_dir.glob("chapter-*.trace.json"), reverse=True)[:limit]:
        trace = json.loads(trace_file.read_text(encoding="utf-8"))
        sections = trace.get("sections", {})
        excluded = sections.get("excluded", [])
        critical_excluded = [s for s in excluded if s in CRITICAL_SECTIONS]
        items.append({
            "chapter": trace.get("chapter", 0),
            "stage": trace.get("stage", "unknown"),
            "included_count": len(sections.get("included", [])),
            "excluded_count": len(excluded),
            "critical_excluded_count": len(critical_excluded),
        })
    return {"items": list(reversed(items))}
```

### 4.4 前端：Context Health 页面

新增导航项"上下文健康"，包含：

#### Section 包含状态
- 两列布局：左侧"已包含"、右侧"已排除"
- 每个 section 标签可点击查看详情
- 关键 section 被排除时红色高亮

#### 权重分布图
- 饼图：`weights_used` 中各 section 的权重占比
- 悬停显示权重值

#### 历史趋势
- 折线图：最近 20 章的 `included_count` 和 `excluded_count` 趋势
- 柱状图叠加：`critical_excluded_count`（红色标记）
- 阈值线：关键 section 排除数 > 0 时告警

#### 告警联动
- 当 `critical_excluded.length > 0` 时，在 OverviewPage 横幅显示告警
- 点击跳转到对应章节的 Context Health 详情

### 4.5 实现要点

- token 计数需从 `context.json` 配对文件获取，trace 本身不含 token 数据
- 关键 section 列表应可配置（通过 `.webnovel/dashboard_config.json`）
- 前端图表用 ECharts 的 `bar` + `pie` series
- 需要处理 trace 文件不存在的章节（早期章节可能没有）

### 4.6 验证标准

- [ ] 能看到第 N 章的完整 section 列表和 token 占比
- [ ] 能看到哪些 section 被排除及原因
- [ ] 历史趋势图能显示 token 预算是否逐渐吃紧
- [ ] 关键 section 被排除时触发告警

---

## Phase 5：实体时间线与一致性检测

> **目标**：将实体状态变化可视化，主动发现跨章矛盾

### 5.1 后端：Entity Timeline API

> **⚠️ 已验证**：`scenes.characters` 是 TEXT 列，存储 JSON 字符串（如 `["char_001", "char_002"]`），不能用 LIKE 查询。

```python
@app.get("/api/entities/{entity_id}/timeline")
def entity_timeline(entity_id: str):
    """返回实体的完整状态变化时间线。"""
    with closing(_get_db()) as conn:
        changes = _fetchall_safe(conn,
            "SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter ASC",
            (entity_id,))

        # scenes.characters 是 JSON 数组字符串，需应用层过滤
        all_scenes = _fetchall_safe(conn,
            "SELECT chapter, scene_index, location, summary, characters FROM scenes ORDER BY chapter ASC",
            ())
        appearances = []
        for scene in all_scenes:
            try:
                chars = json.loads(scene.get("characters") or "[]")
                if entity_id in chars:
                    appearances.append({
                        "chapter": scene["chapter"],
                        "scene_index": scene["scene_index"],
                        "location": scene.get("location", ""),
                    })
            except json.JSONDecodeError:
                continue

    return {"changes": changes, "appearances": appearances}
```

### 5.2 后端：Consistency Anomaly Detection

```python
@app.get("/api/consistency/anomalies")
def consistency_anomalies(chapter: Optional[int] = None):
    """检测实体状态异常跳变。"""
    with closing(_get_db()) as conn:
        query = "SELECT * FROM state_changes ORDER BY chapter ASC, id ASC"
        rows = _fetchall_safe(conn, query)

    anomalies = []
    entity_states = {}  # entity_id → {field: last_value}

    for row in rows:
        eid = row.get("entity_id")
        field = row.get("field")
        old_val = row.get("old_value")
        new_val = row.get("new_value")

        if eid not in entity_states:
            entity_states[eid] = {}
        prev = entity_states[eid].get(field)

        # 检测异常：值回退、数值大幅跳变、枚举值非法
        if prev is not None and new_val == prev:
            anomalies.append({
                "type": "no_change",
                "entity_id": eid,
                "field": field,
                "chapter": row.get("chapter"),
                "detail": f"{field} 从 {old_val} 变为 {new_val}，但值未实际改变",
            })

        entity_states[eid][field] = new_val

    if chapter:
        anomalies = [a for a in anomalies if a.get("chapter") == chapter]

    return {"anomalies": anomalies, "total": len(anomalies)}
```

### 5.3 前端：实体时间线组件

#### 时间线视图（CharactersPage 新增 Tab）
- 横轴：章节号
- 纵轴：字段名（如修为、境界、状态）
- 每个变化点用圆点标记，悬停显示 old→new
- 鼠标点击跳转到对应章节的文档预览

#### 异常高亮
- 红色标记：值回退（如修为从金丹降到筑基）
- 黄色标记：数值大幅跳变（如好感度从 50 跳到 100）
- 灰色标记：无实际变化的状态更新

#### 实体对比视图
- 选择两个实体，对比同一字段的变化趋势
- 适用于：主角 vs 反派的修为对比、势力实力对比

### 5.4 实现要点

- `state_changes` 表的 `field` 字段需要标准化（当前可能是中文或英文）
- 时间线组件可用 ECharts 的 `scatter` + `custom` series
- 异常检测规则需要可配置（阈值、白名单）

### 5.5 验证标准

- [ ] 能看到实体的完整状态变化时间线
- [ ] 异常跳变被自动标记
- [ ] 点击时间线节点能跳转到对应章节
- [ ] 能对比两个实体的同一字段变化

---

## Phase 6：审查分析与质量洞察

> **目标**：从"看分数"升级到"看根因"——知道哪类问题最频繁、哪个维度最薄弱

### 6.1 实际 review_metrics 表结构

> **⚠️ 已验证**：来自 `index_manager.py` 第 542 行。

| 列名 | 类型 | 说明 |
|------|------|------|
| `start_chapter` | INTEGER | 起始章（复合主键） |
| `end_chapter` | INTEGER | 结束章（复合主键） |
| `overall_score` | REAL | 总分（默认 0） |
| `dimension_scores` | TEXT | JSON 字符串，`Dict[str, float]` |
| `severity_counts` | TEXT | JSON 字符串，`Dict[str, int]` |
| `critical_issues` | TEXT | JSON 字符串，`List[str]`（纯描述文本） |

**8 个维度**（来自 `review_schema.py` 的 `SCORE_CATEGORIES`）：
`continuity`, `setting`, `character`, `timeline`, `ai_flavor`, `logic`, `pacing`, `other`

**评分规则**：从 100 起步，按 severity 扣分：critical=-35, high=-15, medium=-6, low=-2

**4 个 severity 级别**：`critical`, `high`, `medium`, `low`

### 6.2 后端：Review Analytics API

```python
@app.get("/api/review/analytics")
def review_analytics(limit: int = Query(50, ge=1, le=200)):
    """返回审查结果的深度分析。"""
    with closing(_get_db()) as conn:
        rows = _fetchall_safe(conn,
            "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?", (limit,))

    if not rows:
        return {"items": [], "summary": {}}

    # 维度得分趋势（8 个维度）
    dimension_trends = {}  # dimension → [{chapter, score}]
    severity_totals = {}   # severity → count
    all_critical_issues = []  # 所有 critical issue 描述

    for row in rows:
        chapter = row.get("end_chapter", 0)
        scores = row.get("dimension_scores", {})
        if isinstance(scores, str):
            try:
                scores = json.loads(scores)
            except json.JSONDecodeError:
                scores = {}

        for dim, score in scores.items():
            if dim not in dimension_trends:
                dimension_trends[dim] = []
            dimension_trends[dim].append({"chapter": chapter, "score": score})

        sev = row.get("severity_counts", {})
        if isinstance(sev, str):
            try:
                sev = json.loads(sev)
            except json.JSONDecodeError:
                sev = {}
        for s, count in sev.items():
            severity_totals[s] = severity_totals.get(s, 0) + count

        # critical_issues 是 List[str]（纯描述文本），不是 List[dict]
        issues = row.get("critical_issues", [])
        if isinstance(issues, str):
            try:
                issues = json.loads(issues)
            except json.JSONDecodeError:
                issues = []
        all_critical_issues.extend(issues)

    # 计算各维度平均分
    dimension_averages = {}
    for dim, points in dimension_trends.items():
        scores = [p["score"] for p in points if p["score"] is not None]
        dimension_averages[dim] = sum(scores) / len(scores) if scores else 0

    # 找出最薄弱维度
    weakest = sorted(dimension_averages.items(), key=lambda x: x[1])[:3]

    return {
        "dimension_trends": dimension_trends,
        "dimension_averages": dimension_averages,
        "weakest_dimensions": [{"dimension": d, "avg_score": s} for d, s in weakest],
        "severity_totals": severity_totals,
        "critical_issues": all_critical_issues[:20],  # 最近 20 条
        "total_reviews": len(rows),
    }
```

### 6.3 前端：审查分析页面

#### 维度雷达图
- 8 维度（continuity, setting, character, timeline, ai_flavor, logic, pacing, other）
- 当前值 vs 历史平均值对比
- 颜色编码：>80 绿色、60-80 黄色、<60 红色

#### 维度趋势折线图
- 每个维度一条线
- 可切换显示/隐藏特定维度
- 低分区段红色背景标记

#### Critical Issues 列表
- 按时间倒序显示最近的 critical issue 描述
- 每条 issue 链接到对应的审查记录（通过 end_chapter）

#### 质量改进建议
- 根据最薄弱维度自动生成建议（如"设定一致性得分低，建议检查 state.json 与正文的一致性"）
- 链接到对应的审查记录和修复工具

### 6.4 实现要点

- `dimension_scores` 有 8 个维度，雷达图需要 8 个轴
- `critical_issues` 是 `List[str]`（纯描述），不是 `List[dict]`，无法按类型分类
- 雷达图用 ECharts 的 `radar` series
- 趋势图需要处理缺失章节（某些章可能没有审查记录）

### 6.5 验证标准

- [ ] 能看到 8 个维度的平均得分和趋势
- [ ] 能识别最薄弱的 3 个维度
- [ ] issue 类型分布图正确显示
- [ ] 点击维度能查看对应的审查记录

---

## Phase 7：伏笔生命周期管理

> **目标**：从被动查看升级为主动管理——创建、编辑、追踪、提醒

### 7.1 实际 chase_debt 表结构

> **⚠️ 已验证**：来自 `index_manager.py` 第 441 行。注意：表中**无 `note` 列**。

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键自增 |
| `debt_type` | TEXT | NOT NULL（伏笔类型） |
| `original_amount` | REAL | 默认 1.0（原始金额/权重） |
| `current_amount` | REAL | 默认 1.0（当前金额/权重） |
| `interest_rate` | REAL | 默认 0.1（利率/增长率） |
| `source_chapter` | INTEGER | NOT NULL（埋设章） |
| `due_chapter` | INTEGER | NOT NULL（目标章） |
| `override_contract_id` | INTEGER | FK → override_contracts(id) |
| `status` | TEXT | 默认 'active' |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

**状态值**：`active`, `overdue`, `paid`, `resolved`

**关键约束**：表中无 `note`/`content` 列，伏笔内容需通过 `debt_type` 或关联的 `override_contract_id` 获取。

### 7.2 后端：Foreshadowing CRUD API

```python
@app.post("/api/foreshadowing")
def create_foreshadowing(request: dict):
    """创建新伏笔。"""
    debt_type = (request.get("debt_type") or "").strip()
    source_chapter = request.get("source_chapter")
    due_chapter = request.get("due_chapter")
    if not debt_type:
        raise HTTPException(400, "debt_type 不能为空")
    if not isinstance(due_chapter, int) or due_chapter <= 0:
        raise HTTPException(400, "due_chapter 必须为正整数")

    with closing(_get_db()) as conn:
        conn.execute(
            """INSERT INTO chase_debt
               (debt_type, source_chapter, due_chapter, original_amount, current_amount, interest_rate, status)
               VALUES (?, ?, ?, 1.0, 1.0, 0.1, 'active')""",
            (debt_type, source_chapter or _load_state_payload().get("progress", {}).get("current_chapter", 0), due_chapter))
        conn.commit()

    return {"ok": True}

@app.put("/api/foreshadowing/{debt_id}")
def update_foreshadowing(debt_id: int, request: dict):
    """更新伏笔状态或属性。"""
    with closing(_get_db()) as conn:
        existing = _fetchall_safe(conn, "SELECT * FROM chase_debt WHERE id = ?", (debt_id,))
        if not existing:
            raise HTTPException(404, "伏笔不存在")

        updates = []
        params = []
        if "debt_type" in request:
            updates.append("debt_type = ?")
            params.append(request["debt_type"])
        if "status" in request:
            updates.append("status = ?")
            params.append(request["status"])
        if "due_chapter" in request:
            updates.append("due_chapter = ?")
            params.append(request["due_chapter"])
        if "current_amount" in request:
            updates.append("current_amount = ?")
            params.append(request["current_amount"])

        if updates:
            params.append(debt_id)
            conn.execute(f"UPDATE chase_debt SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
            conn.commit()

    return {"ok": True}
```

### 7.3 后端：Foreshadowing Reminders

```python
@app.get("/api/foreshadowing/reminders")
def foreshadowing_reminders(threshold: int = Query(5, ge=1, le=20)):
    """返回即将到期的伏笔提醒。"""
    current_chapter = _load_state_payload().get("progress", {}).get("current_chapter", 0)
    with closing(_get_db()) as conn:
        rows = _fetchall_safe(conn,
            """SELECT * FROM chase_debt
               WHERE status IN ('active', 'overdue')
               AND due_chapter <= ? AND due_chapter >= ?
               ORDER BY due_chapter ASC""",
            (current_chapter + threshold, current_chapter))
    return {"reminders": rows, "current_chapter": current_chapter}
```

### 7.4 前端：伏笔管理增强

#### 伏笔创建表单
- 类型输入框（debt_type）
- 埋设章选择器（source_chapter，默认当前章）
- 目标章选择器（due_chapter）

#### 伏笔编辑面板
- 点击伏笔行展开编辑
- 修改类型、目标章、状态
- 标记为已解决（resolved）或已偿还（paid）

#### 提醒横幅
- OverviewPage 顶部显示即将到期的伏笔（status=active/overdue）
- 点击跳转到伏笔详情

#### 伏笔与章节双向关联
- 章节详情页显示关联的伏笔（source_chapter 或 due_chapter）
- 伏笔详情页显示埋设章节和目标章节

### 7.5 实现要点

- 表中无 `note` 列，伏笔描述需通过 `debt_type` 字段或关联 `override_contract` 获取
- 状态流转：`active` → `overdue`（自动，当 due_chapter < current_chapter）→ `resolved`/`paid`
- 前端表单需要验证（due_chapter > source_chapter）
- `debt_type` 建议使用结构化格式（如 "foreshadow:混沌珠觉醒"）

### 7.6 验证标准

- [ ] 能从看板创建新伏笔
- [ ] 能编辑伏笔类型和目标章
- [ ] 即将到期的伏笔在 OverviewPage 显示提醒
- [ ] 伏笔详情页显示关联章节

---

## Phase 8：暗色模式与主题系统

> **目标**：支持暗色模式，为未来主题定制打基础

### 8.1 CSS 变量扩展

```css
:root {
  /* 现有亮色主题 */
  --bg-main: #fff7e8;
  --bg-panel: #fffdf6;
  --bg-card: #fffaf0;
  --bg-card-2: #fff3d5;
  --text-main: #2a220f;
  --text-sub: #5d5035;
  --text-mute: #8f7f5c;
  /* ... */
}

[data-theme="dark"] {
  --bg-main: #1a1a2e;
  --bg-panel: #16213e;
  --bg-card: #0f3460;
  --bg-card-2: #1a1a4e;
  --text-main: #e0e0e0;
  --text-sub: #b0b0b0;
  --text-mute: #808080;
  --accent: var(--accent-blue);
  --accent-blue: #4fc3f7;
  --accent-purple: #b388ff;
  --accent-green: #69f0ae;
  --accent-amber: #ffd54f;
  --accent-red: #ff5252;
  --accent-cyan: #84ffff;
  --border-main: #e0e0e0;
  --border-soft: #424242;
  --shadow-main: 6px 6px 0 rgba(0,0,0,0.3);
  --shadow-soft: 3px 3px 0 rgba(0,0,0,0.2);
}
```

### 8.2 主题切换组件

```jsx
function ThemeToggle() {
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem('theme') || 'light'
    })

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme)
        localStorage.setItem('theme', theme)
    }, [theme])

    return (
        <button
            className="theme-toggle"
            onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
            title={theme === 'light' ? '切换到暗色模式' : '切换到亮色模式'}
        >
            {theme === 'light' ? '🌙' : '☀️'}
        </button>
    )
}
```

### 8.3 实现要点

- 所有颜色必须使用 CSS 变量，禁止硬编码
- 图表颜色需要动态切换（ECharts 支持 theme 切换）
- 图片和图标需要暗色模式适配

### 8.4 验证标准

- [ ] 暗色模式下所有文字可读
- [ ] 图表颜色在暗色模式下清晰
- [ ] 主题切换无闪烁
- [ ] 主题偏好持久化到 localStorage

---

## Phase 9：章节内联编辑器

> **目标**：将看板从"监控面板"升级为"写作工作台"

### 9.1 技术选型

| 方案 | 优点 | 缺点 |
|------|------|------|
| Monaco Editor | 功能强大、语法高亮 | 体积大（~2MB） |
| CodeMirror 6 | 轻量、可扩展 | 学习曲线高 |
| 简单 textarea | 零依赖、最小体积 | 无语法高亮 |

**推荐**：CodeMirror 6。理由：
- 体积适中（~200KB gzipped）
- 支持 Markdown 语法高亮
- 支持自定义扩展（字数统计、段落折叠）
- 活跃维护

### 9.2 后端：Chapter Save API

```python
@app.put("/api/chapters/{chapter}/content")
def save_chapter_content(chapter: int, request: dict):
    """保存章节内容。"""
    content = (request.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "content 不能为空")

    # 查找章节文件
    story_dir = _get_project_root() / "正文"
    if not story_dir.is_dir():
        raise HTTPException(404, "正文目录不存在")

    # 查找匹配的文件
    import glob
    pattern = str(story_dir / f"*_{chapter:03d}.md")
    matches = glob.glob(pattern)
    if not matches:
        raise HTTPException(404, f"第 {chapter} 章文件不存在")

    file_path = Path(matches[0])
    file_path.write_text(content, encoding="utf-8")

    # 触发 SSE 通知
    try:
        _watcher._dispatch(json.dumps({
            "type": "chapter-saved", "chapter": chapter, "ts": time.time(),
        }))
    except Exception:
        pass

    return {"ok": True, "path": str(file_path), "word_count": len(content)}
```

### 9.3 前端：编辑器组件

```jsx
import { EditorView, basicSetup } from 'codemirror'
import { markdown } from '@codemirror/lang-markdown'

function ChapterEditor({ chapter, initialContent, onSave }) {
    const editorRef = useRef(null)
    const viewRef = useRef(null)

    useEffect(() => {
        if (!editorRef.current) return

        const view = new EditorView({
            doc: initialContent,
            extensions: [
                basicSetup,
                markdown(),
                EditorView.updateListener.of(update => {
                    if (update.docChanged) {
                        // 实时字数统计
                    }
                }),
            ],
            parent: editorRef.current,
        })

        viewRef.current = view
        return () => view.destroy()
    }, [chapter])

    const handleSave = async () => {
        const content = viewRef.current.state.doc.toString()
        await onSave(chapter, content)
    }

    return (
        <div className="chapter-editor">
            <div className="editor-toolbar">
                <button onClick={handleSave}>保存</button>
                <span className="word-count">{/* 字数 */}</span>
            </div>
            <div ref={editorRef} className="editor-content" />
        </div>
    )
}
```

### 9.4 实现要点

- 编辑器需要处理大文件（单章可能 >10KB）
- 保存前需要防抖（避免频繁请求）
- 需要撤销/重做支持
- 需要与 chapter-commit 流程集成

### 9.5 验证标准

- [ ] 能在看板内编辑章节内容
- [ ] 保存后文件内容正确更新
- [ ] 编辑器支持 Markdown 语法高亮
- [ ] 实时字数统计

---

## Phase 10：批量操作面板

> **目标**：将 CLI 批量命令暴露给非技术用户

### 10.1 后端：Batch Operation API

```python
@app.post("/api/batch/write")
def batch_write(request: dict):
    """批量写入章节。"""
    chapters = request.get("chapters")  # 如 "1-5" 或 [1, 2, 3, 4, 5]
    if not chapters:
        raise HTTPException(400, "chapters 不能为空")

    cmd = [
        sys.executable, "-X", "utf8",
        str(SCRIPTS_DIR / "webnovel.py"),
        "--project-root", str(_get_project_root()),
        "orchestrate", "write", str(chapters),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "批量写入超时（5 分钟）")

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.returncode,
    }

@app.post("/api/batch/delete")
def batch_delete(request: dict):
    """批量删除章节（dry-run）。"""
    chapters = request.get("chapters")
    confirm = request.get("confirm", False)

    if not chapters:
        raise HTTPException(400, "chapters 不能为空")

    cmd = [
        sys.executable, "-X", "utf8",
        str(SCRIPTS_DIR / "webnovel.py"),
        "--project-root", str(_get_project_root()),
        "delete-chapters", str(chapters),
    ]

    if not confirm:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "批量删除超时")

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.returncode,
        "dry_run": not confirm,
    }
```

### 10.2 前端：批量操作面板

#### 批量写入
- 章节范围选择器（起始章 - 结束章）
- 预览：将要写入的章节数量
- 执行按钮（带确认）
- 进度显示（SSE 推送）

#### 批量删除
- 章节范围选择器
- Dry-run 预览（显示将要删除的文件列表）
- 确认按钮（二次确认）
- 执行结果

#### 批量重建投影
- 选择重建范围（全部 / 指定章节）
- 进度显示
- 结果摘要

### 10.3 实现要点

- 批量操作需要长时间运行，必须用 SSE 推送进度
- 需要取消机制（长时间运行的操作可以中断）
- 需要操作历史记录

### 10.4 验证标准

- [ ] 能选择章节范围并触发批量写入
- [ ] 能预览批量删除的影响
- [ ] 操作进度实时显示
- [ ] 操作结果正确显示

---

## Phase 11：多项目管理

> **目标**：支持多书同写的作者统一管理

### 11.1 后端：Project Discovery

```python
@app.get("/api/projects")
def list_projects():
    """发现所有可用的书项目。"""
    projects = []

    # 从指针文件读取
    pointer_dirs = [
        Path.cwd() / ".opencode",
        Path.cwd() / ".claude",
    ]
    for pointer_dir in pointer_dirs:
        pointer = pointer_dir / ".webnovel-current-project"
        if pointer.is_file():
            target = pointer.read_text(encoding="utf-8").strip()
            if target:
                p = Path(target)
                if _is_valid_project(p):
                    projects.append({
                        "path": str(p),
                        "name": p.name,
                        "source": "pointer",
                    })

    # 从同级目录扫描
    cwd = Path.cwd()
    if (cwd / ".opencode" / "scripts" / "webnovel.py").is_file():
        for sibling in cwd.parent.iterdir():
            if sibling.name.startswith(".") or sibling.name == "webnovel-writer":
                continue
            if _is_valid_project(sibling):
                projects.append({
                    "path": str(sibling),
                    "name": sibling.name,
                    "source": "scan",
                })

    return {"projects": projects}

@app.post("/api/projects/switch")
def switch_project(request: dict):
    """切换当前项目。"""
    project_path = request.get("path")
    if not project_path:
        raise HTTPException(400, "path 不能为空")

    p = Path(project_path)
    if not _is_valid_project(p):
        raise HTTPException(400, "无效的项目路径")

    global _project_root
    _project_root = p.resolve()

    # 更新指针文件
    pointer = Path.cwd() / ".opencode" / ".webnovel-current-project"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(_project_root), encoding="utf-8")

    return {"ok": True, "project_root": str(_project_root)}
```

### 11.2 前端：项目切换器

```jsx
function ProjectSwitcher() {
    const [projects, setProjects] = useState([])
    const [current, setCurrent] = useState(null)

    useEffect(() => {
        fetchProjects().then(data => setProjects(data.projects || []))
    }, [])

    const handleSwitch = async (path) => {
        await switchProject(path)
        window.location.reload() // 切换后需要刷新
    }

    return (
        <div className="project-switcher">
            <select value={current || ''} onChange={e => handleSwitch(e.target.value)}>
                {projects.map(p => (
                    <option key={p.path} value={p.path}>{p.name}</option>
                ))}
            </select>
        </div>
    )
}
```

### 11.3 实现要点

- 项目切换需要重新加载所有数据
- 需要处理项目不存在或损坏的情况
- 需要保存用户的项目偏好

### 11.4 验证标准

- [ ] 能发现所有可用的书项目
- [ ] 能切换项目并刷新数据
- [ ] 项目切换后所有页面正确显示

---

## 实现优先级与时间估算

| Phase | 名称 | 优先级 | 时间估算 | 依赖 |
|-------|------|--------|----------|------|
| 4 | Context Health 可视化 | P0 | 2 周 | 无 |
| 5 | 实体时间线与一致性检测 | P0 | 2 周 | 无 |
| 6 | 审查分析与质量洞察 | P1 | 1.5 周 | 无 |
| 7 | 伏笔生命周期管理 | P1 | 1.5 周 | 无 |
| 8 | 暗色模式与主题系统 | P2 | 1 周 | 无 |
| 9 | 章节内联编辑器 | P2 | 3 周 | 无 |
| 10 | 批量操作面板 | P2 | 1.5 周 | 无 |
| 11 | 多项目管理 | P3 | 1.5 周 | 无 |

**总计**：约 14 周（3.5 个月）

---

## 技术债务与质量保障

### 前端测试

```bash
# 安装测试框架
cd .opencode/dashboard/frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom

# 运行测试
npm run test
```

需要覆盖的测试：
- `api.js`：所有 API 函数的 mock 测试
- `lib/format.js`：格式化函数的单元测试
- `lib/foreshadowing.js`：伏笔计算逻辑的单元测试
- `lib/story.js`：故事相关计算的单元测试

### API 文档

为所有端点添加中文描述和示例：

```python
@app.get("/api/entities", summary="获取实体列表", description="返回所有实体，可按类型过滤")
def list_entities(
    entity_type: Optional[str] = Query(None, alias="type", description="实体类型过滤"),
    include_archived: bool = False, description="是否包含已归档实体"
):
    """..."""
```

### 错误边界

每个页面添加独立的错误边界：

```jsx
function PageErrorBoundary({ children, pageName }) {
    return (
        <ErrorBoundary
            fallback={
                <div className="page-error">
                    <h3>页面加载失败</h3>
                    <p>{pageName} 页面发生错误，请刷新重试。</p>
                    <button onClick={() => window.location.reload()}>刷新</button>
                </div>
            }
        >
            {children}
        </ErrorBoundary>
    )
}
```

### 性能优化

- 大数据集分页：实体列表、关系列表、审查记录
- 虚拟滚动：章节列表、伏笔列表
- 图表懒加载：非当前 Tab 的图表延迟渲染
- API 响应缓存：相同参数的请求缓存 5 秒

---

## 风险与约束

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| trace 无 token 计数 | Phase 4 需从 context.json 估算 token | 使用 len(content)//2 粗略估算，或扩展 trace 输出 |
| trace 无 critical 标记 | Phase 4 需硬编码关键 section 列表 | 通过 dashboard_config.json 可配置 |
| scenes.characters 是 JSON 字符串 | Phase 5 不能用 SQL LIKE 查询 | 应用层过滤，或增加 GIN 索引 |
| chase_debt 无 note 列 | Phase 7 无法存储伏笔描述 | 使用 debt_type 字段或关联 override_contract |
| chase_debt 状态值不同于预期 | Phase 7 状态流转逻辑需调整 | 使用 active/overdue/paid/resolved |
| critical_issues 是纯文本列表 | Phase 6 无法按类型分类 | 改为展示最近 issue 列表而非类型分布 |
| dimension_scores 有 8 维度 | Phase 6 雷达图需 8 个轴 | 调整雷达图布局，合并低频维度 |
| CodeMirror 体积 | 首屏加载变慢 | 动态导入 + 代码分割 |
| 多项目切换的状态管理 | 切换后数据不一致 | 切换时完全重置应用状态 |
| 暗色模式的图表适配 | 图表颜色不可读 | ECharts 主题动态切换 |
| /api/context/ 命名空间已占用 | Phase 4 新端点需避免路径歧义 | 使用 /api/context/health/ 子路径 |
| /api/projects/ 与 /api/project/info 语义重叠 | Phase 11 需明确职责 | /api/projects/ 用于多项目管理，/api/project/info 保留为当前项目详情 |

---

## 成功指标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| AI 遗忘发现率 | 关键 section 被排除时 100% 告警 | Phase 4 告警触发率 |
| 一致性问题发现 | 异常跳变 100% 标记 | Phase 5 异常检测率 |
| 审查洞察深度 | 8 维度趋势可视化 + 最近 critical issues 列表 | Phase 6 功能完整性 |
| 伏笔管理闭环 | 创建/编辑/提醒全流程可用 | Phase 7 功能完整性 |
| 写作效率 | 看板内完成 30% 的编辑操作 | Phase 9 使用率 |
| 用户满意度 | 暗色模式使用率 >40% | Phase 8 主题偏好统计 |

---

## 附录：审查修正记录

> 本节记录计划审查过程中发现的关键偏差，供后续实现参考。

### 已修正的问题

| # | Phase | 原始假设 | 实际情况 | 修正 |
|---|-------|----------|----------|------|
| 1 | 4 | trace.sections 是对象数组，含 tokens/included/critical | sections 是 `{included: string[], excluded: string[]}` 字典 | 重写 API 代码 |
| 2 | 4 | trace 有 budget_limit 字段 | 不存在 | 从 context.json 估算 |
| 3 | 4 | sections 有 critical 标记 | 不存在 | 硬编码关键 section 列表 |
| 4 | 5 | scenes.characters 可用 LIKE 查询 | 是 JSON 字符串，需应用层过滤 | 改为全量查询+过滤 |
| 5 | 6 | dimension_scores 有 6 维度 | 实际有 8 维度 | 更新雷达图描述 |
| 6 | 6 | critical_issues 是 List[dict] 含 type 字段 | 实际是 List[str] 纯描述文本 | 改为展示最近 issue 列表 |
| 7 | 7 | chase_debt 有 note 列 | 不存在 | 使用 debt_type 字段 |
| 8 | 7 | 状态值为 pending/urgent/overdue/resolved | 实际为 active/overdue/paid/resolved | 更新状态流转逻辑 |

### 未修正但需注意的事项

1. **token 计数精度**：当前使用 `len(content)//2` 粗略估算，实际 token 数取决于分词器。如需精确计数，需集成 tiktoken 或类似库。
2. **伏笔描述存储**：chase_debt 表无 note 列，伏笔描述需通过 debt_type 字段（建议结构化格式）或关联 override_contract 获取。
3. **API 命名空间**：/api/context/ 已被 budget/{chapter} 占用，新增端点需使用 /api/context/health/ 子路径。
4. **多项目管理**：/api/projects/ 与 /api/project/info 语义重叠，需明确职责划分。
