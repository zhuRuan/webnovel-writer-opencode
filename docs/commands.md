# 命令详解

## `/webnovel-init`

用途：初始化小说项目（目录、设定模板、状态文件）。

产出：

- `.webnovel/state.json`
- `设定集/`
- `大纲/总纲.md`

## `/webnovel-plan [卷号]`

用途：生成卷级规划与章节大纲。

示例：

```
/webnovel-plan 1
/webnovel-plan 2-3
```

## `/webnovel-write [章号]`

用途：执行完整章节创作流程（上下文 → 草稿 → 审查 → 润色 → 数据落盘）。

示例：

```
/webnovel-write 1
/webnovel-write 45
```

参数：

| 参数 | 说明 |
|------|------|
| `--fast` | 跳过风格转译（Step 2B） |
| `--minimal` | 仅执行基础审查 |

## `/webnovel-write-batch`

用途：连续撰写多章节，在单次回复中完成批量写作流程。

示例：

```
/webnovel-write-batch --range 53-60
/webnovel-write-batch --range 53-60 --review-level minimal
/webnovel-write-batch --resume
```

参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--range` | 章节范围，如 53-60 | 自动解析 |
| `--review-level` | 审查级别（minimal/standard/full） | standard |
| `--resume` | 从断点恢复 | - |
| `--force` | 绕过 20 章上限 | - |

特点：

- 在单次回复中完成所有章节（无需多次调用）
- 每章独立审查和 Git 提交
- 断点自动保存，支持随时中断恢复
- 完成后输出汇总报告

## `/webnovel-review [范围]`

用途：对历史章节做多维质量审查。

示例：

```
/webnovel-review 1-5
/webnovel-review 45
```

## `/webnovel-query [关键词]`

用途：查询角色、伏笔、节奏、状态等运行时信息。

示例：

```
/webnovel-query 萧炎
/webnovel-query 伏笔
/webnovel-query 紧急
```

## `/webnovel-resume`

用途：任务中断后自动识别断点并恢复。

示例：

```
/webnovel-resume
```

## `/webnovel-learn [内容]`

用途：从当前会话或用户输入中提取可复用写作模式，并写入项目记忆。

示例：

```
/webnovel-learn "本章的危机钩设计很有效，悬念拉满"
```

产出：

- `.webnovel/project_memory.json`

## `/webnovel-publish`

用途：通过交互式问答引导，将章节发布到番茄小说平台。

示例：

```
/webnovel-publish
```

交互式流程：

1. **首次配置** - 安装 Playwright 并登录番茄作家后台（只需一次）
2. **获取书籍 ID** - 创建新书或查看已有书单
3. **上传章节** - 选择章节范围和发布模式
4. **完成** - 查看上传结果

参数（也可通过交互式问答指定）：

| 参数 | 说明 |
|------|------|
| `--book-id` | 番茄小说书籍 ID |
| `--range` | 章节范围，如 `1-10`、`1,3,5`、`all` |
| `--mode` | 发布模式：draft（草稿）或 publish（直接发布） |

## `/webnovel-dashboard`

用途：启动可视化小说管理面板（只读 Web Dashboard），实时查看项目状态、实体图谱与章节内容。

示例：

```
/webnovel-dashboard
```

功能：

- 卷结构可视化
- 角色活跃度追踪
- 伏笔状态管理
- 审查分数展示
- 势力版图
- 关系图谱（3D 力导向图）
- 正文/大纲/设定集文件浏览
- 插件数据展示

底层命令：

```bash
python -m opencode.dashboard --project-root <项目路径>
python -m opencode.dashboard --project-root <项目路径> --port 9000 --no-browser
```

参数：

| 参数 | 说明 |
|------|------|
| `--host` | 监听地址（默认 127.0.0.1） |
| `--port` | 监听端口（默认 8765） |
| `--no-browser` | 不自动打开浏览器 |

## `/webnovel-export`

用途：将正文导出为 Markdown/TXT/EPUB 格式。

示例：

```
/webnovel-export
/webnovel-export --format markdown
/webnovel-export --range 1-10 --format epub
/webnovel-export --volume 1 --format txt
/webnovel-export --format epub --cover cover.jpg --style style.css --author "作者名"
```

参数：

| 参数 | 说明 |
|------|------|
| `--format` | 输出格式：markdown（默认）、txt、epub |
| `--range` | 章节范围，如 `1-10`、`1,3,5` |
| `--volume` | 导出指定卷 |
| `--output` | 输出文件路径 |
| `--author` | 作者名（仅 EPUB 需要） |
| `--cover` | 封面图路径（仅 EPUB，默认检测项目根目录/cover.jpg） |
| `--style` | 自定义 CSS 路径（仅 EPUB，默认检测项目根目录/style.css） |
| `--cover-size` | 封面裁剪尺寸（仅 EPUB，格式如 1200x1600） |
