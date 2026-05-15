# 项目初始化待修复清单

日期：2026-05-15

本文记录 `/webnovel-init` 与 `webnovel init` 初始化链路中已经复现或确认的待修复项。范围包括 `.opencode/scripts/init_project.py`、统一 CLI、初始化 skill 文档与测试入口。

## 修复项

### 1. Git 失败处理会从 non-fatal 变成崩溃

- 位置：`.opencode/scripts/init_project.py`
- 现象：`subprocess.run(..., text=True)` 失败后，`CalledProcessError.stderr` 是 `str`，但异常处理固定调用 `.decode()`。
- 影响：Git 初始化失败时，本应只打印警告并继续，却会抛出 `AttributeError`，导致初始化中断。
- 建议：
  - 增加 stderr 规范化函数，兼容 `str`、`bytes`、`None`。
  - 为 Git 失败路径增加回归测试。
- 验证：
  - 模拟 `subprocess.CalledProcessError(stderr="fatal: ...")`，初始化应完成并打印 non-fatal 信息。

### 2. 目录安全规则未覆盖 `.opencode`

- 位置：`.opencode/scripts/init_project.py`
- 现象：脚本只拒绝在 `.claude` 下初始化项目，没有拒绝 `.opencode`。
- 影响：用户若误传 `.opencode/<book>`，会把书项目生成到插件目录内。
- 建议：
  - 同时拒绝 `.claude` 与 `.opencode` 路径。
  - 错误信息说明应选择工作区下的书名目录。
  - 增加 `.opencode` 路径拒绝测试。

### 3. 总纲模板会重复生成首卷行

- 位置：
  - `.opencode/scripts/init_project.py`
  - `.opencode/templates/output/大纲-总纲.md`
- 现象：模板已有空首卷行，脚本又注入 `| 1 | | 第1-50章 | | |`。现有去重只做精确字符串匹配，无法识别同一卷号。
- 影响：初始化后的 `大纲/总纲.md` 同时存在两条首卷记录，后续规划写回可能写错行或形成歧义。
- 建议：
  - 注入逻辑改为更新已有卷号为 1 的行，而不是盲插。
  - 或删除模板中的空首卷行，让脚本成为唯一首卷行来源。
  - 增加断言：初始化后 `| 1 |` 数据行只能出现一次。

### 4. 损坏的 `state.json` 会被静默清空覆盖

- 位置：`.opencode/scripts/init_project.py`
- 现象：已有 `state.json` JSON 解析失败时直接 `state = {}`，随后以 `backup=False` 写回。
- 影响：对已有项目误运行初始化时，损坏或半写入的状态文件会被无备份替换，可能丢失进度、设定和运行态信息。
- 建议：
  - 解析失败时默认中止并提示用户先修复或备份。
  - 如果要支持自动恢复，先写 `.bak` 再重建最小 state。
  - 增加损坏 `state.json` 的保护性测试。

### 5. CLI 初始化产物与 skill 交付合同不一致 — ✅ 已确认（设计分层）

- 位置：
  - `.opencode/scripts/data_modules/webnovel.py`
  - `.opencode/skills/webnovel-init/SKILL.md`
- 结论：`webnovel init` 仅调用 `init_project.py` 生成项目骨架。`idea_bank.json` 和 `MASTER_SETTING.json` 由 `/webnovel-init` skill 在交互流程的 Step 7（执行生成）中补充生成。这是有意设计的分层：
  - **CLI** = 最小骨架（state.json + 设定集 + 总纲 + .env.example + Git init）
  - **Skill** = 完整初始化（骨架 + idea_bank + 总纲 patch + story-system 主合同）
- 验证：CLI 产物满足 `/webnovel-plan` 前置条件中的总纲与设定集要求。Skill 文档 Step 7 明确列出了 idea_bank 和 story-system 的生成步骤。

### 6. 测试入口仅识别 `.opencode/scripts`

- 位置：`.opencode/scripts/run_tests.ps1`
- 现象：测试路径写死为 `.opencode/scripts`，不再兼容旧 `.claude/scripts` 布局。
- 影响：确认测试入口与当前仓库布局一致即可。
- 建议：
  - 将测试入口固定为 `.opencode/scripts`。
  - 增加根目录运行测试的导入路径保障。

## 已执行验证

- `python -m pytest data_modules\tests\test_init_project_pruning.py --no-cov` 在 `.opencode/scripts` 下通过，结果为 4 passed。
- 单独不带 `--no-cov` 运行会被全仓 90% 覆盖率门槛拦截，不代表初始化行为测试失败。
- 临时目录初始化已复现总纲首卷行重复。
- 模拟 `git init` 失败已复现 `stderr.decode()` 崩溃。
- 第 5 项（CLI/skill 合同差异）已确认：CLI `init` 产物经核对满足 `/webnovel-plan` 前置条件，无需接口对齐。Skill 文档 Step 7 已明确 complementary 产物的生成步骤，属有意分层设计。

## 建议修复顺序

1. 先修 Git 失败处理和 `.opencode` 路径保护，避免初始化中断或污染插件目录。
2. 再修总纲首卷行重复，保证规划链路输入干净。
3. 然后修 `state.json` 损坏保护，降低误操作损失。
4. 最后统一 CLI/skill 合同和测试入口，补端到端覆盖。
