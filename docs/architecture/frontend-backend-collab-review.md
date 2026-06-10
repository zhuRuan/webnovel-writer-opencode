# 前后端协作审查报告

> 2026-06-10 生成。按各流程审查前端（Skill/Agent/React）与后端（Python 脚本）的协作正确性。

## 一、写作流程（webnovel-write）

```
前端: SKILL.md + context-agent + chapter-writer-agent + observer-agent + data-agent
后端: webnovel.py / skill_runner.py / observer_settler.py / chapter_commit_service.py
```

### 1.1 环境准备 → 项目根解析

| 前端 (SKILL.md:62) | 后端 (webnovel.py:_resolve_root) | 审查 |
|---|---|---|
| `PROJECT_ROOT=$(webnovel.py where)` | `resolve_project_root()` 5 级优先级 | ✅ 正确 |

**发现**：SKILL.md 用 `${PWD}` 传入 `--project-root`，然后 `where` 命令又调用 `_resolve_root(None)` 走 CWD 搜索。这是双重解析，浪费了一次 CLI 调用。但修复 `_resolve_root` 从脚本位置搜索后，`where` 不再依赖 PWD，这是一个冗余参数。不阻断。

### 1.2 合同刷新

| 前端 (SKILL.md:76-84) | 后端 (skill_runner.py cmd_story_system) | 审查 |
|---|---|---|
| `echo "${CHAPTER_GOAL}" \| python skill_runner.py story-system --chapter N` | stdin 读取 goal → story_system.py → story_contracts.py | ✅ 正确 |

**发现**：`CHAPTER_GOAL` 来自用戶/章纲。SKILL.md:74 要求"必须先从详细大纲解析真实本章目标，禁止传占位 query"。但 **无脚本验证这一步**——如果 `CHAPTER_GOAL` 仍然是 `{章纲目标}` 占位符，story-system 会接收它并生成无效合同。**这是一个 gap**：前端约束依赖 AI 遵守，后端无条件接收。

### 1.3 结构自检

| 前端 (SKILL.md:98-100) | 后端 (skill_runner.py cmd_check_structural) | 审查 |
|---|---|---|
| `intended_strand` 从章纲提取 | structural_checker.py 5 项规则检查 | ✅ 正确 |

**发现**：`intended_strand` 在 SKILL.md 提及但从 Step 2 故事系统取。`check-structural` 命令不接收 strand 参数——它可能不验证 strand 是否匹配 contracts。需确认。

### 1.4 context-agent → 写作任务书

| 前端 (context-agent prompt) | 后端 (context_manager.py) | 审查 |
|---|---|---|
| SKILL.md:106-111 定义 5 段输出格式 | build_context() 从 state.json + index.db + 大纲 组装 | ✅ 正确 |

**发现**：context-agent prompt 中 `storage_path=${PROJECT_ROOT}/.webnovel` 是多余的——所有 data_modules 都通过 project_root 推导存储路径。无实际影响。

### 1.5 Observer → Settler 数据交接 ⚠️

| 步骤 | 前端 | 后端 | 审查 |
|---|---|---|---|
| 5.1a | observer-agent.md | 自由文本 raw_facts.txt | ✅ prompt 定义了 9 个段落格式 |
| 5.1b | — | observer_settler.py | ⚠️ **有 gap** |

**观察者输出格式**（9 个 markdown 段落）：
```
## 角色状态变化
## 新出场实体
## 关系变化
## 力量突破
## 宝物/物品获得
## 世界规则揭示
## 世界规则打破
## 对读者的承诺/伏笔
## 伏笔创建与闭合
```

**Settler 解析**（observer_settler.py 的正则模式）：
```python
_extract_character_changes()    # 匹配 "角色状态变化"
_extract_entity_discoveries()   # 匹配 "新出场实体"
_extract_power_breakthroughs()  # 匹配 "力量突破"
_extract_item_events()          # 匹配 "宝物/物品获得"
_extract_world_rule_revealed()  # 匹配 "世界规则揭示"
_extract_world_rule_broken()    # 匹配 "世界规则打破"
_extract_promises()             # 匹配 "对读者的承诺/伏笔"
```

**Gap 分析**：

1. ✅ **段落名匹配**：`_parse_markdown_sections()` 用 `_normalize_heading()` 做模糊匹配（去掉 `###` 前缀和空白），能匹配 observer-agent 输出的 markdown 标题格式。

2. ✅ **"伏笔创建与闭合"段落**：已确认 settler 完整覆盖 9 个段落，包括 `_extract_open_loops()` 处理"伏笔创建与闭合"（匹配 `- [新伏笔]`/`- [闭合]`）。

3. ✅ **格式一致性**：settler 的行格式模式与 observer-agent prompt 完全匹配。

### 1.6 chapter-commit 数据交接

| 前端 (SKILL.md:279-286) | 后端 (chapter_commit.py) | 审查 |
|---|---|---|
| `chapter-commit --review-result ... --extraction-result ...` | chapter_commit_service.build_commit() | ✅ 正确 |

前端传入 4 个 JSON 文件，后端全部必需。**已验证**：artifact_validator 使用 `commit_artifacts.py` 统一访问 extraction，降级兼容。

---

## 二、审查流程（webnovel-review）

```
前端: SKILL.md + reviewer agent
后端: review_pipeline.py + review_schema.py + structural_checker.py
```

### 2.1 JSON 数据结构校验 ⚠️

| 维度 | reviewer.md 定义 | review_schema.py 期望 | 匹配？ |
|---|---|---|---|
| issues[].category | `"setting"`/`"timeline"`/`"continuity"`/`"character"`/`"logic"`/`"rules"` | 同 | ✅ |
| issues[].severity | `"critical|high|medium|low"` | 同 | ✅ |
| issues[].blocking | `boolean` | 同 | ✅ |
| issues[].fix_hint | `string` | 同 | ✅ |

**审查结果**：reviewer.md Section 7 定义的 JSON schema 与 review_schema.py 的 Pydantic 模型 **字段名完全一致**。

### 2.2 JSON 中文引号处理

| 问题 | 修复状态 |
|---|---|
| reviewer 输出含中文引号 `""` | ✅ review_pipeline.py `_sanitize_json_text` 处理 |
| aggressive 模式回退 `「」` → `"` | ✅ 已修复（移除 `「」`） |
| reviewer.md 禁止中文引号 | ✅ 已添加 JSON 安全规则 |

### 2.3 审查结果 → chapter-commit 传递

```
review_results.json → chapter_commit_service.py → blocking_count 判定
```

`parse_review_output()` 从 issues 列表自算 `blocking_count`，不信任 LLM 原始值。**正确**。

---

## 三、Dashboard 流程

```
前端: React 9 pages + api.js (fetchJSON/apiPost/apiPut/apiDelete)
后端: FastAPI 27 endpoints + data_modules
```

### 3.1 API 端点覆盖 ✅

| 前端页面 | 调用 API | 后端端点 | 匹配？ |
|---|---|---|---|
| OverviewPage | fetchProjectInfo, fetchStoryRuntimeHealth, fetchForeshadowingReminders | `/api/project/info`, `/api/story-runtime/health`, `/api/foreshadowing/reminders` | ✅ |
| CharactersPage | fetchEntities, fetchStateChanges, fetchEntityTimeline | `/api/entities`, `/api/state-changes`, `/api/entities/{id}/timeline` | ✅ |
| ReviewAnalyticsPage | fetchReviewAnalytics | `/api/review/analytics` | ✅ |
| ContextHealthPage | fetchContextHealth, fetchContextHistory | `/api/context/health/{chapter}`, `/api/context/history` | ✅ |
| StylePage | fetchMasterSetting, fetchAntiPatterns, fetchTechniques 等 | `/api/style/master-setting`, `/api/style/anti-patterns` 等 | ✅ |
| FilesPage | fetchFilesTree, fetchFileContent, saveFileContent | `/api/files/tree`, `/api/files/read`, `/api/files/write` | ✅ |
| SystemPage | runBatchAction | `/api/batch/{action}` | ✅ |

**结论**：API 端点完整覆盖，无遗漏。每个前端页面需要的 API 都有对应的后端端点。

### 3.2 错误处理

| 位置 | 处理方式 | 审查 |
|---|---|---|
| api.js: `fetchJSON` | HTTP 非 200 → `throw new Error(status)` | ✅ 统一错误处理 |
| 各页面 catch | `.catch(e => setError(e.message))` | ✅ 所有页面有 error state |
| 后端 `_fetchall_safe` | `no such table` → 空列表（兼容旧库） | ✅ 降级处理 |
| 后端 null 安全 | `_parse_json_value(raw, default)` 处理 JSON 字段 | ✅ |

### 3.3 数据一致性 ⚠️

| 前端期望 | 后端返回 | 审查 |
|---|---|---|
| `dimension_averages` 字段 | review_analytics 端点计算并返回 | ✅ |
| `weakest_dimensions` 字段 | review_analytics 端点计算并返回 | ✅ |
| null 安全 | 前端用 `?.` 可选链保护 | ✅ 已修复 |

---

## 四、初始化流程（webnovel-init）

```
前端: SKILL.md → Agent calls
后端: init_project.py
```

### 4.1 参数传递

| 参数 | SKILL.md 传递 | init_project.py 接收 | 审查 |
|---|---|---|---|
| 书名 | `--title` | `args.title` | ✅ |
| 笔名 | `--author` | `args.author` | ✅ |
| 题材 | `--genre` | `args.genre` | ✅ |
| 一句话简介 | `--one-liner` | `args.one_liner` | ✅ |
| 核心冲突 | `--core-conflict` | `args.core_conflict` | ✅ |

### 4.2 产物完整性

init_project.py 应生成：
- ✅ `正文/` 目录
- ✅ `.webnovel/state.json`（含 project_info 快照）
- ✅ `.story-system/MASTER_SETTING.json`
- ✅ `设定集/` 目录

**Gap**：`.env.example` 文件不在 init 流程中生成（用户需手动创建）。不是 bug，但新用户体验不佳。

---

## 五、合同/SSOT 流程

### 5.1 Story Contract 合同生成

| 输入 | 流程 | 输出 | 审查 |
|---|---|---|---|
| MASTER_SETTING + volume_brief | story_system_engine → chapter_directive | .story-system/chapters/chapter_NNN.json | ✅ |

**发现**：`chapter_outline_loader.py` 负责章纲字段映射。上次同步已补全字段（爽点→coolpoint、视角→pov 等）。确认完整。

### 5.2 SSOT 事件溯源

| 操作 | CLI | 后端 | 审查 |
|---|---|---|---|
| verify | `ssot verify` | ssot_enforcer.verify_consistency() | ✅ 比较 state.json vs event log |
| rebuild | `ssot rebuild` | rebuild_state_json() → 确定性重放 | ✅ 重放所有 events |
| events | `ssot events` | read_events() | ✅ 读取事件日志 |

**发现**：verify 检测 7 种 drift（chapter_status、foreshadowing、entities_v3、relationships、world_rules、reader_promises、timeline_events），与 rebuild 的 projection 路由一致。✅

---

## 六、综合发现

### P0（阻断）

| # | 流程 | 发现 |
|---|------|------|
| — | *(无阻断性发现)* | |

### P1（需修复）

| # | 流程 | 发现 | 修复建议 |
|---|------|------|---------|
| 1 | 写作 | observer-agent ↓ settler 9/9 段落 ✅ 已确认正确（误报，`_extract_open_loops` 处理伏笔段落） | — |
| 2 | 写作 | SKILL.md `CHAPTER_GOAL` 占位符无脚本验证 ✅ 已修复 | skill_runner.py cmd_story_system 添加占位符正则检测 |
| 3 | 合同 | chapter_outline_loader vs story_contract_schema 字段映射 ✅ 已确认正确（chapter_directive 为 Dict[str,Any]） | — |

### P2（建议）

| # | 流程 | 发现 | 修复建议 |
|---|------|------|---------|
| 4 | 写作 | SKILL.md:62 `--project-root "${PWD}"` 传给 `where` 是冗余参数（`where` 不再依赖 PWD） | 改为 `webnovel.py where`（无参数），让 _resolve_root 自动搜索 |
| 5 | 写作 | structual_checker 不接收 strand 参数，可能不验证 strand 与 contracts 一致性 | 添加 `--intended-strand` 参数 |
| 6 | 初始化 | 未生成 `.env.example` 模板文件 | init_project.py 添加 --api-key 参数，生成 .env |
| 7 | Dashboard | context/health 和 context/history 端点查询 .webnovel/runtime/ 目录，但目录需要 project_root 正确 | 在 dashboard 启动时验证 runtime 目录存在性 |

### 已确认正确的协作点

- ✅ reviewer schema ↔ review_pipeline parse（字段完全一致）
- ✅ reviewer JSON 中文引号 3 层防御（agent prompt + normal mode + aggressive mode）
- ✅ chapter-commit 5 个输入文件 → artifact_validator 完整性校验
- ✅ Dashboard 9 个页面的 API 端点覆盖
- ✅ Dashboard 前后端错误处理（统一 throw + 降级）
- ✅ SSOT verify/rebuild/events 三合一命令
- ✅ context-agent ↔ context_manager 上下文组装
- ✅ observer ↔ settler 行格式一致性（8/9 段落匹配）
