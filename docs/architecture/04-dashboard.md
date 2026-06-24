# Dashboard 可视化面板 — 模块设计

> 版本: 2.9 | 更新: 2026-06 | 父文档: [00-master-architecture.md](00-master-architecture.md)

## 概述

FastAPI + React 19 + ECharts 的网文创作管理面板。提供项目状态监控、角色管理、审查分析、文风编辑等功能。91 个 API 端点，11 个前端页面。

## 架构

```
Browser → React 19 SPA (Vite, 端口 5173)
              │ 代理 /api/* → 端口 8765
              ▼
         FastAPI (app.py, 端口 8765)
              │
              ├── 91 个 REST 端点 (GET/POST/PUT/DELETE)
              ├── SSE /api/events 实时推送
              │
              ▼
         DAO 层 (8 个 DAO) → SQLite (.webnovel/index.db)
```

### 启动命令

```bash
# 后端
python -m .opencode.dashboard

# 前端（独立终端）
cd .opencode/dashboard/frontend && npm run dev
```

## 页面清单（11 页）

| 路由 | 页面 | 文件 | 功能 |
|------|------|------|------|
| `/` | 总览 | `OverviewPage.jsx` | 统计卡片、审查趋势、字数分布、伏笔提醒 |
| `/context` | 上下文健康 | `ContextHealthPage.jsx` | Token 预算、Section 状态、权重分布 |
| `/characters` | 角色图鉴 | `CharactersPage.jsx` | 5 Tab: 实体列表/关系图谱/时间线/势力图谱/角色计划 |
| `/knowledge` | 知识库 | `KnowledgePage.jsx` | 结构化知识浏览 |
| `/knowledge-base` | 知识库管理 | `KnowledgeBasePage.jsx` | 知识库编辑管理 |
| `/review` | 审查分析 | `ReviewAnalyticsPage.jsx` | 8 维度雷达图、严重程度分布、趋势折线图 |
| `/foreshadowing` | 伏笔追踪 | `ForeshadowingPage.jsx` | 伏笔甘特图、债务表 |
| `/files` | 文档浏览 | `FilesPage.jsx` | 文件树、正文预览、保存并同步 |
| `/style` | 文风约束 | `StyleEditorPage.jsx` | 6 Tab: 自定义提示词/全局文风/禁止模式/写作技法/章级合同/审查维度 |
| `/pacing` | 节奏雷达 | `PacingPage.jsx` | 钩子强度趋势、Strand 堆叠分布、字数箱线图 |
| `/system` | 系统状态 | `SystemPage.jsx` | 合同树、提交历史、RAG 环境、批量操作 |

## 关键交互

### 角色详情面板

角色图鉴页 → 点击角色 → 侧边栏展开:
- 实体信息（名称/别名/类型/势力/等级）
- 角色知识（theater 知识域 + skills 技能树）
- 角色记忆（按 retention 排序的 top-K 记忆）
- 活跃计划（进行中 + 逾期计划）

### 异常分级

| 级别 | 颜色 | 含义 |
|------|------|------|
| 致命 | 红 | 阻塞性错误（审查 blocking=true 未通过） |
| 严重 | 橙 | 需关注（伏笔逾期、角色 OOC） |
| 轻微 | 黄 | 建议优化（节奏偏差、字数异常） |

### 技能色阶

三角洲收藏品等级映射:
白 → 绿 → 蓝 → 紫 → 金 → 红 → 深红

### 保存并同步

文档浏览页编辑文件后:
1. 保存到文件系统
2. 自动解析变更（diff 检测）
3. 同步到 `index.db` 和 `state.json`
4. 触发 Markdown 投影重渲染

## DAO 集成

所有 91 个 API 端点通过 DAO 层访问数据库，不再使用原始 SQL:

```
app.py API 端点
    ├── /api/entities/*        → EntityDAO
    ├── /api/relationships/*   → RelationshipDAO
    ├── /api/factions/*        → FactionDAO
    ├── /api/memories/*        → MemoryDAO
    ├── /api/character-state/* → StateDAO
    ├── /api/character-events/*→ CharacterEventDAO
    ├── /api/knowledge/*       → KnowledgeDAO
    ├── /api/director/*        → DirectorDAO
    └── /api/techniques/*      → DirectorDAO
```

## 实时推送

SSE 端点 `/api/events` 推送以下事件:
- 章节提交完成
- 审查结果更新
- 伏笔状态变更
- 角色计划逾期告警
- 批量操作进度

## 批量操作

系统状态页支持批量操作，使用 `asyncio.create_subprocess_exec` 避免阻塞:
- 批量重审章节
- 批量重建投影
- 批量导出章节
- SSOT 一致性校验

## 项目根目录解析

5 级优先级:
1. CLI 参数 `--project-root`
2. 环境变量 `WEBNOVEL_PROJECT_ROOT`
3. 脚本位置向上搜索 `.webnovel/state.json`
4. CWD 向上搜索
5. 指针文件/注册表

## 前端技术栈

- React 19 (lazy-loaded 路由)
- React Router (客户端路由)
- ECharts (力导向图、雷达图、甘特图、折线图、箱线图)
- Vite (HMR 开发服务器，代理 `/api` 到 8765)
- CSS Modules (亮色/暗色主题切换)
