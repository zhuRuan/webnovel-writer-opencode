# 大纲规划待修复清单

日期：2026-05-15

本文记录 `/webnovel-plan`、`master-outline-sync`、章纲加载与规划状态更新链路中已经复现或确认的待修复项。范围包括 `.opencode/skills/webnovel-plan/SKILL.md`、`.opencode/scripts/update_master_outline.py`、`.opencode/scripts/chapter_outline_loader.py`、`.opencode/scripts/data_modules/placeholder_scanner.py` 与 `.opencode/scripts/update_state.py`。

## 修复项

### 1. `placeholder-scan` 发现占位仍返回成功

- 位置：
  - `.opencode/scripts/data_modules/placeholder_scanner.py`
  - `.opencode/scripts/data_modules/webnovel.py`
- 现象：扫描到 `[待...]`、`暂名`、`{占位}` 时，JSON 输出为 `ok=false`，但 CLI 退出码仍为 0。
- 影响：`webnovel-plan` 文档把占位扫描作为规划前后闸门，但自动流程只看退出码时无法阻断，可能带着未补齐设定进入拆章或写作。
- 建议：
  - 在 `placeholder_scanner.main()` 中，当 `results` 非空时以 `SystemExit(1)` 退出。
  - 若需要“只报告不阻断”，新增 `--allow-placeholders` 或 `--warn-only`。
  - 更新测试，断言存在占位时 CLI returncode 为 1。
- 验证：
  - 临时项目 `大纲/总纲.md` 写入 `[待补充]` 后运行 `webnovel placeholder-scan --format json`，应输出 `ok=false` 且退出码为 1。

### 2. `master-outline-sync` 只检查规划文件非空，未执行 Step 9 硬验证

- 位置：`.opencode/scripts/update_master_outline.py`
- 现象：同步前只检查 `第N卷-节拍表.md`、`第N卷-时间线.md`、`第N卷-详细大纲.md` 存在且非空。
- 影响：即使文件内容只是占位文本，也能写回总纲并返回 `ok=true`。这绕过了 plan 文档要求的时间字段、时间线单调、倒计时、`BLOCKER=0`、结构化节点等验证。
- 建议：
  - 增加规划产物验证函数，至少检查：
    - 详细大纲中目标范围内每章有时间锚点、章内跨度、与上章时间差或等价字段。
    - 时间线表包含本卷时间跨度和关键事件。
    - 文件内容不包含 `BLOCKER` 未裁决标记。
    - 当前章相关占位扫描为 0。
  - `master-outline-sync` 在验证失败时拒绝写回总纲。
  - 将验证逻辑单独封装，供 skill 流程和测试复用。
- 验证：
  - 三份规划文件只写入“占位但非空”时，`sync_master_outline()` 应失败。
  - 带 `BLOCKER` 或缺少时间字段的详细大纲应失败。

### 3. 通用章纲加载器不识别中文数字章标题

- 位置：`.opencode/scripts/chapter_outline_loader.py`
- 现象：`load_chapter_execution_directive()` 可解析 `### 第一章：...`，但 `load_chapter_outline()` 只匹配 `### 第1章：...`。
- 影响：写作上下文、章节标题提取和部分检查链路会提示“未找到第 N 章的大纲”，但执行指令解析又能拿到部分字段，造成同一章纲在不同链路中的可见性不一致。
- 建议：
  - 让 `_extract_outline_section()` 复用 `_CHAPTER_HEADING_RE` 与 `_parse_chinese_chapter_num()`。
  - 保持阿拉伯数字和中文数字标题都能定位章节范围。
  - 增加 `第一章`、`第十一章`、`第二十章`、`第101章` 的回归测试。
- 验证：
  - `### 第一章：债从天降` 下，`load_chapter_outline(root, 1)` 应返回该章完整段落。

### 4. 下一卷锚点可写入空章节范围，导致下一轮规划自我阻断

- 位置：
  - `.opencode/scripts/update_master_outline.py`
  - `.opencode/skills/webnovel-plan/SKILL.md`
- 现象：`next_volume_anchor` 示例没有 `chapters_range`，代码也允许缺省为空。写回后 V+1 行有卷名、核心冲突、卷末高潮，但章节范围为空。
- 影响：plan 决策树要求总纲缺少章节范围时阻断。完成第 1 卷写回后，第 2 卷规划会因自己刚写入的空章节范围被阻断。
- 建议：
  - 明确设计选择：
    - 如果 V+1 只允许“最小锚点”，则放宽下一轮前置条件，允许目标卷章节范围在 Step 3 补齐。
    - 如果章节范围是硬前置，则 `next_volume_anchor` 必须要求 `chapters_range`。
  - 推荐在写回 JSON 中新增必填 `chapters_range`，并在 `_normalize_anchor()` 校验。
- 验证：
  - 缺少 `chapters_range` 的写回 JSON 应失败，或下一轮 plan 文档不再把 V+1 缺少章节范围列为阻断。

### 5. `--volume-planned --chapters-range` 不校验格式

- 位置：
  - `.opencode/scripts/update_state.py`
  - `.opencode/scripts/chapter_outline_loader.py`
- 现象：`mark_volume_planned()` 直接保存输入字符串；章纲加载器只识别纯 `1-50` 格式，不识别 `第1-50章`。
- 影响：状态中若保存 `第31-80章`，第 40 章无法按 state 定位到第 2 卷，会回退到默认 50 章/卷并找错大纲文件。
- 建议：
  - 在写入 state 前规范化章节范围，统一保存为 `start-end`。
  - 解析器兼容 `第1-50章`、`1至50`、`1~50` 等常见输入。
  - 对非法范围直接失败，避免保存坏状态。
- 验证：
  - 输入 `第31-80章` 应规范化为 `31-80`。
  - 输入 `80-31`、`abc` 应失败。
  - 第 40 章应能定位到 `第2卷-详细大纲.md`。

## 已执行验证

- `python -m pytest data_modules\tests\test_update_master_outline.py data_modules\tests\test_chapter_outline_directive.py --no-cov` 在 `.opencode/scripts` 下通过，结果为 7 passed。
- 临时项目已复现：占位扫描 `ok=false` 但退出码为 0。
- 临时项目已复现：规划产物只要非空，`master-outline-sync` 就能写回。
- 临时项目已复现：`第一章` 可被执行指令解析，但不能被通用章纲加载。
- 临时项目已复现：`第31-80章` 写入 state 后，第 40 章无法定位第 2 卷详细大纲。

## 建议修复顺序

1. 先修占位扫描退出码和 `master-outline-sync` 验证，避免坏规划进入总纲和写作主链。
2. 再修章纲标题解析一致性，保证上下文、标题和执行指令看到同一份章纲。
3. 然后统一章节范围合同，避免规划状态和章纲定位分叉。
4. 最后补齐端到端测试：从总纲写回、状态更新，到下一轮 `load_chapter_outline()` 正确定位。
