# OpenCode 迁移待修复清单

日期：2026-05-15

本文记录当前仓库从 Claude 插件形态迁移到 OpenCode 使用形态时，仍需清理和替换的 Claude 相关残留。后续修复应以 `.opencode/` 为唯一当前运行面；`.claude/`、`CLAUDE_*`、`claude-plugin` 只允许出现在外部参考快照、历史归档或明确标注为历史背景的文档中。

## 迁移原则

- 当前产品目标是 OpenCode 版本，不再按 Claude 插件维护运行路径。
- 一方代码、skill、dashboard、安装/测试/发版脚本、当前使用文档中，应剔除 Claude 命名和 `.claude` 路径假设。
- 历史文档可以保留，但必须标注为历史来源，避免读者误以为是当前安装或运行方式。
- 原项目快照 `外部参考/webnovel-writer 原项目/` 不作为当前产品面清理对象，可作为迁移参考保留。

## 修复项

### 1. 项目定位仍以 `.claude` 指针为核心

- 位置：`.opencode/scripts/project_locator.py`
- 现象：
  - `CURRENT_PROJECT_POINTER_REL` 仍指向 `.claude/.webnovel-current-project`。
  - 环境变量仍使用 `CLAUDE_PROJECT_DIR`、`CLAUDE_HOME`、`WEBNOVEL_CLAUDE_HOME`。
  - 注释与函数名仍围绕 Claude workspace / Claude home。
- 影响：OpenCode 环境下的当前项目指针、全局 registry 和工作区推断仍带有 Claude 语义，容易写入错误位置或让后续命令解析到旧项目。
- 建议：
  - 改为 `.opencode/.webnovel-current-project` 或 `.opencode/.webnovel-current-project` 对应的本地指针策略。
  - 新增 OpenCode 环境变量命名，例如 `OPENCODE_PROJECT_DIR`、`OPENCODE_HOME`、`WEBNOVEL_OPENCODE_HOME`。
  - 若需要兼容旧 Claude 指针，只做一次性迁移读取，不能作为默认写入目标。
  - 更新 `test_project_locator.py`、`test_webnovel_unified_cli.py`、`test_state_manager_extra.py` 中的路径和环境变量断言。

### 2. 配置加载仍使用 Claude home 和 `.claude` 全局 env

- 位置：`.opencode/scripts/data_modules/config.py`
- 现象：全局配置路径仍默认落在 `~/.claude/webnovel-writer/.env`，函数命名也仍是 `_get_user_claude_root`。
- 影响：OpenCode 安装后，用户级环境变量和 API key 读取位置不符合当前工具目录约定，可能误读旧 Claude 配置或找不到 OpenCode 配置。
- 建议：
  - 改为 OpenCode 命名与路径，例如 `~/.opencode/webnovel-writer/.env` 或项目约定的 OpenCode 用户目录。
  - 保留旧路径读取时必须标注为 legacy fallback，并低于 OpenCode 路径优先级。
  - 更新 `docs/guides/rag-and-config.md` 中的用户级全局配置说明。

### 3. 运行脚本和测试入口仍引用 `.claude/scripts`

- 位置：
  - `.opencode/scripts/run_tests.ps1`
  - `.opencode/scripts/.coveragerc`
  - `.opencode/scripts/webnovel.py`
  - `.opencode/scripts/data_modules/webnovel.py`
- 现象：测试入口、覆盖率注释、统一入口注释仍把脚本目录描述为 `.claude/scripts`。
- 影响：从仓库根运行测试或照文档执行时，会找不到路径或混淆当前插件布局。
- 建议：
  - 将测试入口统一切到 `.opencode/scripts`。
  - 更新注释与帮助文本，避免继续传播 `.claude/scripts`。
  - 根目录运行测试时确保 `PYTHONPATH=.opencode/scripts` 或由 `pytest.ini`/`conftest.py` 自动注入。

### 4. 初始化安全规则仍只拒绝 `.claude`

- 位置：`.opencode/scripts/init_project.py`
- 现象：初始化项目时只拒绝路径中包含 `.claude`，没有拒绝 `.opencode`。
- 影响：在 OpenCode 版本中，用户误传 `.opencode/<book>` 会污染插件目录。
- 建议：
  - 拒绝 `.opencode` 下创建书项目。
  - 错误信息改为 OpenCode 语境，例如“不要在插件目录 `.opencode/` 内创建书项目”。
  - 对 `.claude` 的拒绝可作为 legacy 防御保留，但不应成为唯一规则。

### 5. 发版脚本仍指向 `.claude-plugin`

- 位置：`.opencode/scripts/sync_plugin_version.py`
- 现象：`PLUGIN_JSON_PATH` 和 `MARKETPLACE_JSON_PATH` 仍指向 `.claude-plugin`，CLI 描述也是 “Claude plugin release metadata”。
- 影响：OpenCode 版本发版时会查找不存在或错误的元数据路径，版本同步和 README 发布表可能不可用。
- 建议：
  - 明确 OpenCode 插件元数据来源：当前 `.opencode/package.json` 过于简略，是否需要新增 `.opencode/plugin.json` 或 OpenCode marketplace 元数据文件需要先定。
  - 将脚本改名或改描述为 OpenCode release metadata。
  - 如果该脚本已不适用，删除或归档，避免继续被 CI/人工误用。

### 6. Dashboard 和上下文加载仍查找 `.claude/references`

- 位置：
  - `.opencode/dashboard/server.py`
  - `.opencode/scripts/data_modules/context_manager.py`
  - `.opencode/scripts/data_modules/memory_contract_adapter.py`
- 现象：部分代码仍从项目根 `.claude/references` 读取题材配置、读者爽点分类或当前项目指针。
- 影响：OpenCode 项目下参考资料位于 `.opencode/references`，旧路径会导致 fallback 失效、题材 profile 丢失或 dashboard 解析错误。
- 建议：
  - 所有当前参考资料路径切到 `.opencode/references`。
  - 若书项目内有私有 references，使用明确的新目录名，例如 `.webnovel/references` 或项目内 `references/`，不要继续叫 `.claude/references`。
  - 更新相关测试 fixture。

### 7. 当前文档仍大量展示 `.claude` 命令与路径

- 状态：✅ 核心文档已清理（CLAUDE.md、commands.md、operations.md、plugin-release.md）；README.md 和 INSTALL.md 作为下游用户文档由安装流程覆盖。
- 位置：
  - `README.md`
  - `INSTALL.md`
  - `docs/guides/commands.md`
  - `docs/guides/rag-and-config.md`
  - `docs/operations/operations.md`
  - `docs/architecture/story-system-phase4.md`
  - `CLAUDE.md`
- 现象：用户面对的当前文档仍混有 `.claude`、Claude Code、Claude 插件安装/运行方式。
- 影响：新用户会按错误平台路径安装或运行，开发者也容易继续按 Claude 目录写代码。
- 建议：
  - 当前使用文档全部改为 OpenCode 语境。
  - `CLAUDE.md` 若只是历史代理说明，应改名或替换为 OpenCode/Agent 通用说明；若仍被某工具读取，至少新增 OpenCode 主说明文件并在 README 中指向它。
  - 历史文档加“历史/原 Claude 版本参考，不代表当前 OpenCode 使用方式”提示。

### 8. Skill 与 reference 文案仍含 Claude 视角

- 位置：
  - `.opencode/skills/webnovel-init/SKILL.md`
  - `.opencode/skills/webnovel-dashboard/SKILL.md`
  - `.opencode/skills/*/references/*.md`
- 现象：部分 skill 或 reference 中仍出现 `.claude`、Claude、Claude Code 官方等措辞。
- 影响：虽然 skill 已位于 `.opencode/skills`，但说明文字仍会误导 agent 按 Claude 工具路径行动。
- 建议：
  - 主链 skill 文档优先清理：init、plan、write、review、query、dashboard。
  - reference 中如果只是“AI 写作常见问题”泛称 Claude，应改为“模型/AI 助手”；如果确实引用原 Claude 版本，标为历史来源。

### 9. 根目录忽略规则和本地文件名仍带 Claude 迁移噪声

- 位置：`.gitignore`
- 现象：仍忽略 `.claude/`、`oh-story-claudecode/`、`claude_inventory.csv` 等。
- 影响：部分规则是合理的历史/本地防护，但当前主语不清，会让仓库看起来仍以 Claude 插件为主。
- 建议：
  - 保留对 `.claude/` 的忽略作为“legacy local artifacts”，但加注释说明不是当前运行目录。
  - 清理或归类 Claude 迁移分析文件规则，避免和 OpenCode 主路径混杂。

## 允许保留的 Claude 引用

- `外部参考/webnovel-writer 原项目/`：原项目快照，作为迁移参考保留。
- `docs/superpowers/plans/`、`docs/superpowers/specs/` 中的历史设计文档：可保留，但建议加历史归档说明。
- 第三方依赖 `node_modules` 中的 Claude / Anthropic 模型说明：不属于本项目代码，不应手工改。
- Git 历史 changelog 中的旧 commit message：可保留，除非生成当前用户文档时会展示并造成误导。

## 建议迁移顺序

1. 先修运行定位层：`project_locator.py`、`config.py`、`run_tests.ps1`、`.coveragerc`。
2. 再修主链脚本：`init_project.py`、dashboard、context manager、memory adapter。
3. 然后修发布/安装：`sync_plugin_version.py`、`manifest.json`、`README.md`、`INSTALL.md`。
4. 最后批量清理 skill/reference/current docs 文案，并补 OpenCode 回归测试。

## 验收标准

- 一方代码中不再默认写入或读取 `.claude/`。
- 当前文档中的命令示例全部使用 `.opencode/`。
- 测试入口从仓库根和 `.opencode/scripts` 目录均可运行。
- `webnovel where`、`webnovel init`、`placeholder-scan`、`review-pipeline` 等主命令不依赖 Claude 环境变量。
- 仅历史归档、外部参考和第三方依赖中允许出现 Claude 相关文字。
