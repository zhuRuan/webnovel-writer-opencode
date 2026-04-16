# 项目结构与运维

## 目录层级

```
WORKSPACE_ROOT/
├── .opencode/            # OpenCode 配置（Skills/Scripts/References）
├── opencode.json         # Agents 配置
├── prompts/              # Agent 提示词
├── .env                  # API 配置
└── 小说项目/             # 用户小说项目
    ├── .webnovel/        # 运行时数据
    ├── 正文/              # 正文章节
    ├── 大纲/              # 总纲与卷纲
    └── 设定集/            # 世界观、角色、力量体系
```

## .opencode 目录结构

```
.opencode/
├── skills/              # 12个 Skills
│   ├── webnovel-init/
│   ├── webnovel-plan/
│   ├── webnovel-write/
│   ├── webnovel-write-batch/
│   ├── webnovel-review/
│   ├── webnovel-export/
│   ├── webnovel-publish/
│   ├── webnovel-dashboard/
│   ├── webnovel-query/
│   ├── webnovel-resume/
│   ├── webnovel-learn/
│   └── webnovel-image-gen/    # 图片生成
├── dashboard/           # 可视化面板（FastAPI + React 独立模块）
│   ├── app.py          # FastAPI 应用入口
│   ├── server.py       # 服务器配置
│   ├── watcher.py      # 文件监听
│   ├── publish_bridge.py # 发布数据桥接
│   └── frontend/       # React 前端
├── dicts/               # 自定义词典（中文分词优化）
│   └── webnovel_dict.txt
├── scripts/             # Python 核心脚本
│   ├── data_modules/    # 核心模块
│   │   ├── condition_evaluator.py  # 条件评估器
│   │   ├── temporal_graph.py      # 时间图谱
│   │   ├── image_generator.py     # ModelScope 图片生成
│   │   └── tests/               # 测试文件
│   │       ├── test_condition_evaluator.py
│   │       ├── test_temporal_graph.py
│   │       └── test_tokenizer_improvement.py
│   ├── publisher/       # 番茄小说发布模块
│   ├── webnovel.py     # CLI 入口
│   ├── sync_chapters_to_db.py   # 章节同步到数据库
│   ├── sync_missing_chapters.py # 缺失章节同步
│   └── verify_chapters.py       # 章节验证
├── references/          # 参考文档
│   ├── shared/         # 共享规范
│   ├── creativity/      # 创意约束
│   └── worldbuilding/   # 世界观设计
├── genres/              # 题材参考（38+）
└── templates/           # 输出模板
    ├── genres/         # 题材模板
    └── output/         # 输出格式
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENCODE_HOME` | OpenCode 全局配置目录 | `~/.opencode` |
| `OPENCODE_PROJECT_DIR` | 工作区根目录 | 当前目录 |
| `WEBNOVEL_CLAUDE_HOME` | Claude 兼容配置目录 | `~/.claude` |

`.env` 加载顺序：
1. 项目目录 `.env`（最高优先级）
2. `~/.opencode/webnovel-writer/.env`
3. `~/.claude/webnovel-writer/.env`（兼容）

## 常用运维命令

详细命令说明见 [rag-and-config.md](./rag-and-config.md) 和 [commands.md](./commands.md)。

```bash
# 进入小说项目目录后

# 索引重建
python .opencode/scripts/webnovel.py index process-chapter --chapter 1

# 索引统计
python .opencode/scripts/webnovel.py index stats

# 健康报告（Markdown）
python .opencode/scripts/webnovel.py status --focus all

# 健康报告（JSON）
python .opencode/scripts/status_reporter.py --json --pretty --project-root <项目路径>

# 向量重建
python .opencode/scripts/webnovel.py rag index-chapter --chapter 1
python .opencode/scripts/webnovel.py rag stats

# 番茄小说发布
python .opencode/scripts/webnovel.py publish setup-browser
python .opencode/scripts/webnovel.py publish list-books --project-root <项目路径>
python .opencode/scripts/webnovel.py publish upload --book-id <ID> --range "1-10" --mode draft --project-root <项目路径>

# 可视化看板
python -m opencode.dashboard --project-root <项目路径>

# 章节同步
python .opencode/scripts/sync_chapters_to_db.py --project-root <项目路径>
python .opencode/scripts/sync_missing_chapters.py --project-root <项目路径>

# 章节验证
python .opencode/scripts/verify_chapters.py --project-root <项目路径>
```

## 测试

```bash
# 运行所有测试
pytest

# 运行单个测试
pytest .opencode/scripts/data_modules/tests/test_config.py::test_config_paths_and_defaults

# 运行条件评估器测试
pytest .opencode/scripts/data_modules/tests/test_condition_evaluator.py

# 运行时间图谱测试
pytest .opencode/scripts/data_modules/tests/test_temporal_graph.py

# 运行分词器改进测试
pytest .opencode/scripts/data_modules/tests/test_tokenizer_improvement.py

# 覆盖率报告
pytest --cov .opencode/scripts/data_modules/tests/
```
