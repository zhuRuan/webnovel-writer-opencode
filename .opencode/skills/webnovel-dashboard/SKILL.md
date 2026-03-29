---
name: webnovel-dashboard
description: 小说架构看板 - 可视化展示小说的卷结构、角色状态、伏笔追踪、审查报告、时间线和势力版图。支持任意webnovel项目。
version: 1.1.0
author: opencode
tags:
  - 看板
  - 可视化
  - 小说管理
  - 审查
---

# webnovel-dashboard

小说架构看板 - 可视化展示小说的各项数据

## 特性

- **通用设计**: 适用于任何使用 webnovel 项目结构的小说
- **自动检测**: 自动查找项目中的数据文件
- **实时刷新**: 点击刷新按钮即可更新最新数据
- **审查集成**: 直接展示章节审查分数和维度评分

## 数据要求

项目根目录需包含以下文件之一：
- `.webnovel/state.json` - 主要数据文件
- `novel.txt` - 备用数据文件

## 使用方式

### 1. 基本启动

在任意位置运行：
```bash
python /path/to/webnovel-dashboard/dashboard/dashboard_server.py
```

### 2. 指定项目目录

```bash
python /path/to/webnovel-dashboard/dashboard/dashboard_server.py /path/to/your/novel/project
```

### 3. 浏览器访问

启动后浏览器自动打开，或手动访问：
```
http://localhost:8085
```

## 功能模块

| 模块 | 说明 |
|------|------|
| 统计概览 | 已完成章节、字数、进度百分比 |
| 卷结构 | 显示各卷进度 |
| 角色状态 | 主角、女主、其他角色、场景、物品 |
| 伏笔追踪 | 伏笔列表及状态 |
| 审查报告 | 章节审查分数、维度评分、问题统计 |
| 角色图谱 | D3.js 交互式关系图 |
| 时间线 | 故事时间线 |
| 势力版图 | 势力分布卡片 |

## 文件结构

```
webnovel-dashboard/
├── SKILL.md
└── dashboard/
    ├── index.html          # 看板主页面
    └── dashboard_server.py # 启动脚本
```

## 数据来源

看板从以下位置读取数据（按优先级）：
1. `config.js` - 配置文件（由启动脚本生成）
2. `.webnovel/state.json` - webnovel 项目标准数据文件

### state.json 期望结构

```json
{
  "project": {
    "title": "小说标题",
    "genre": "小说类型",
    "target_words": 1000000
  },
  "progress": {
    "current_chapter": 31,
    "total_words": 74528
  },
  "protagonist_state": {
    "name": "主角名",
    "power": { "realm": "境界", "layer": 1 },
    "location": { "current": "位置" },
    "golden_finger": { "name": "金手指名", "level": 1 }
  },
  "relationships": {
    "角色名": { "type": "类型", "role": "角色/地点/物品" }
  },
  "chapter_meta": {
    "1": { "title": "第1章 标题", "countdown": "D-60", "time_anchor": "时间锚点" }
  },
  "review_checkpoints": [
    {
      "chapters": "1-2",
      "overall_score": 82,
      "dimension_scores": {
        "爽点密度": 8.0,
        "设定一致性": 9.0,
        "节奏控制": 7.5,
        "人物塑造": 8.5,
        "连贯性": 8.0,
        "追读力": 8.0
      },
      "severity_counts": {
        "critical": 0,
        "high": 1,
        "medium": 3,
        "low": 2
      },
      "critical_issues": [],
      "reviewed_at": "2026-03-20"
    }
  ]
}
```

## 故障排除

### 数据无法加载
- 确保在正确的项目目录下运行
- 检查 `.webnovel/state.json` 文件是否存在

### 端口被占用
- 修改 `dashboard_server.py` 中的 `PORT` 变量
