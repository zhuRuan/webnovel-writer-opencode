# v2.7.0 Release Notes

> 2026-05-11 | Pipeline Hardening + Publisher/Review/Structural Fixes
>
> 基于 8 份 bug 报告的交叉分析，修复 ~40 个程序级缺陷

---

## A. 管线完整性 (Pipeline Integrity)

- **PROJECT_ROOT 嵌套目录自动发现** — `where` 命令现在会扫描当前目录的直接子目录，自动定位嵌套项目（如 `凡尘之舞/凡尘之舞/`）
- **preflight fs_state_sync 检查** — 新增文件系统与 state.json 的章节记录对比，识别孤文件（有正文无状态）和幽灵章（有状态无正文）
- **合同树前置门** — chapter-writer-agent 在起草前强制检查 `.story-system/chapters/` 下合同文件是否存在；skill 层面 story-system 返回非零即阻断
- **结构自检阈值收紧 + 阻断门** — constellation 未激活阈值 15→8 章，entity_freshness 阈值 3→5 章；blocking 项现在真正阻止流程继续

## B. Windows 兼容性

- **PYTHONUTF8=1** — 两个 skill 的环境设置中全局启用 UTF-8
- **verify-chapter-files action** — 新增 `skill_runner.py verify-chapter-files` 替代 4 个 bash 验证命令，统一用 Python 做写后校验
- **PROJECT_ROOT 正斜杠归一化** — 解析后 `\\`→`/`，消除 `\b` `\n` 等在 `python -c` 中的转义
- **check-structural --output flag** — 绕过 PowerShell 重定向 `>` 的 UTF-16 编码问题
- **`||` 语法替换** — story-system 和 blocking gate 改为 `if/fi`，兼容 PowerShell 5.1

## C. Agent 可靠性

- **Agent 调用后强制文件校验** — context-agent / reviewer / data-agent 每步后不依赖返回文本，直接校验输出文件存在且非空
- **chapter-writer-agent Write 硬约束** — agent prompt 末尾明确要求必须用 Write 工具写入文件，禁止"返回正文但未写磁盘"

## D. 噪音削减

- **placeholder-scan 忽略列表** — 新增 `known_placeholders.json`，过滤已知无害占位符（如 `（暂名）`），不再每章重复报告

## E. 体验打磨

- **批处理进度可视化** — 每步执行前打印 `[Ch{N} Step {M}/9] {step_name}...`
- **pause-batch action** — `skill_runner.py pause-batch` 安全暂停批量任务
- **preflight 人类可读输出** — `story_runtime` 改为 `主合同链: 第N章 (MASTER_SETTING → volume → chapter)`
- **aiohttp 连接关闭** — chapter-commit 后 `asyncio.run(get_client().close())` 消除 `Unclosed client_session` 警告
- **CLI --mode 参数** — 新增 `--mode default|fast|minimal`（预留参数，当前 no-op）

## Publisher 修复 (8 bugs)

- **upload_chapter POST body 补全 aid/app_name** — 与 `create_book` 保持一致的表单参数
- **_ensure_writer_context 域名检查** — 不仅检查 `about:blank`，还检查是否在 fanqienovel.com 域下
- **_page_fetch 空响应含状态码** — 错误信息现在包含 HTTP status code
- **upload_log book_id 交叉污染防护** ⚠️ **关键** — 日志内嵌 `book_id` 和 `book_name`，上传前校验一致性，防止误用另一本书的 ID（此前已发生 19 章上传到错误书籍的事故）
- **POST 指数退避重试** — 空响应时自动重试（1s → 2s），刷新 writer context
- **登录预热检查** — 首次 POST 前 GET 验证登录态，提前发现会话失效
- **publish mode 提示** — `--mode publish` 时明确告知"当前仅支持草稿保存"

## 审查/评分修复 (4 bugs)

- **中文引号 JSON 容错** — `clean_reviewer_output()` 增加 CJK 引号替换 fallback，解析失败时输出 raw 前 500 字符
- **overall_score 排除系统维度** — `other` 维度独立为 `system_health`，不参与内容质量评分加权（解决"95 分被拉到 28 分"的问题）
- **顶层 score 字段** — `review_results.json` 增加 `score` 字段，兼容 batch_state 读取

## 结构自检设计修复 (2 bugs)

- **intended_strand 意图感知** — 新增 `--intended-strand` 参数，当前章正在修复缺失线体时不报 blocking
- **entity_freshness 值检测** — `location.current` 值存在时，即使 `last_chapter` 陈旧也降级为 warning

## 数据完整性 (3 bugs)

- **batch_state.json UTF-8 BOM 兼容** — 读取用 `utf-8-sig`，写入强制 `encoding='utf-8'`
- **chapter-path CLI 命令** — 补充 skill 文档引用的缺失子命令
- **contract_refs 路径修正** — 改为 `.story-system/` 下的实际路径
- **_read_json BOM 容忍** — chapter_commit 入口改用 `utf-8-sig`

---

**统计**: 27 commits, 13 文件修改, ~500 行新增, ~80 行删除
