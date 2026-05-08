# Stability & Compatibility Fix Spec

## Context

Ch78 写作过程中暴露了 22 个问题，分属编码/SHELL 兼容、故事合同路由、Agent 行为、流程体验四大类。8 个问题已在上一轮修复，本 spec 覆盖剩余 14 个。

## S1: Shell 兼容层 — skill_runner.py

### 问题

skill 命令大量使用 bash 变量 (`$GENRE`, `$CHECK_RESULT`, `$COMMIT_FILE`) 传递 CJK 文本，在 Windows PowerShell 环境下产生双重编码损坏。`test -s` 等 bash 命令在 PowerShell 不可用。

### 方案

新增 `.opencode/scripts/skill_runner.py`，将 skill 中常用的 CJK 敏感操作封装为纯 Python 命令，CJK 全程在 Python 内存中传递。

```python
# 命令模式
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" <action> [--args]

# Actions:
#   story-system    — 从 state.json 读取 genre，执行 story-system 命令
#   check-structural — 运行 structural_checker，解析结果并输出摘要
#   check-commit     — 检查指定章节的 commit 文件是否存在
#   check-index      — 检查指定章节是否在 index.db 中
#   check-file       — 检查文件存在且非空（替代 test -s）
#   write-file       — 写入 JSON 到文件（替代 echo "$json" > file）
```

skill 中的 bash 调用从：
```bash
GENRE="$(python -c "...")"  # CJK 过 shell
python ... story-system "${GENRE}" ...
```
变为：
```bash
python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" story-system --chapter {N} --goal "${CHAPTER_GOAL}"
```

### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `scripts/skill_runner.py` | 新增 | ~200 行，6 个 action |
| `skills/webnovel-write/SKILL.md` | 修改 | 合同、自检、审查段改为 skill_runner 调用 |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | 同上 + post-write 校验改为 skill_runner 调用 |

---

## S2: 合同路由修复 — 复合题材分解

### 问题

故事系统 `题材与调性推理.csv` 只定义了 26 种单题材路由。"末世+异能"、"修仙+硬核科幻" 等复合题材无法匹配，导致 contract_coverage 恒为 blocking。

### 方案

修改 `story_system_engine.py._fallback_row_for_genre`：直接匹配失败时，按 `+` 分割复合题材，从左到右逐个尝试匹配，第一个命中即返回。

```python
# 新增逻辑
if "+" in genre:
    for component in genre.split("+"):
        result = self._direct_match(rows, component.strip())
        if result:
            return result
```

不影响 `resolve_genre` 和 CSV 文件。复合题材按主导题材（第一个组件）路由。

### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `data_modules/story_system_engine.py` | 修改 | `_fallback_row_for_genre` 新增拆解逻辑，~15 行 |

---

## S3: Agent 输出稳定性

### S3a: reviewer JSON 后处理清洗

#### 问题

reviewer agent 同一 prompt 下有时输出纯 JSON，有时夹杂对话文本，导致 `review-pipeline` 解析崩溃。

#### 方案

在 `review_pipeline.py` 解析 JSON 前，加清洗函数。

```python
def clean_reviewer_output(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end+1]
    raise ValueError("reviewer 输出中未找到有效 JSON")
```

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `scripts/review_pipeline.py` | 修改 | 新增 `clean_reviewer_output`，`parse_review_output` 调用前先清洗 |

### S3b: chapter-writer-agent 任务书遵守

#### 问题

context-agent 的硬性约束被 agent 当建议忽略。如 Ch78 要求"增加 Ch77→Ch78 过渡段"，agent 仍直接以"醒来"开头。

#### 方案

修改 chapter-writer-agent 的 `## Step A: 理解任务`，将硬性约束提升为首段清单格式：

```markdown
### Step A: 理解任务

**硬性约束清单（起草前必须逐条确认，遗漏不进 Step B）：**

□ 过渡承接：{来自任务书第 2 段的 chapter_end_open_question}
□ 必须覆盖节点：{must_cover_nodes}
□ 禁区：{forbidden_zones}
□ 字数目标：2000-2500 字

全部确认后，阅读任务书其余部分，再进入 Step B。
```

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `agents/chapter-writer-agent.md` | 修改 | Step A 改为清单格式 |

### S3c: review_results.json 残留

#### 问题

修复轮中 agent 改完正文后，旧 `review_results.json` 还在，pipeline 读到旧问题。

#### 方案

在修复轮流程（两个 SKILL.md 的 Step 6）中，重新运行 reviewer 前先删除旧文件：

```bash
rm -f "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"
```

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `skills/webnovel-write/SKILL.md` | 修改 | Step 3 修复轮流程，加 rm |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | Step 6 修复轮流程，加 rm |

---

## S4: 流程体验

### S4a: 自检分级过滤

#### 问题

structural_checker 的 3 个 blocking 全是基础设施问题（contract_coverage, strand_balance, entity_freshness），没有写作层面的阻塞，产生噪音。

#### 方案

在 skill 中，structural_checker 结果解析时区分"可忽略"和"需阻断"：

- `contract_coverage`：合同缺失是已知问题（S2 修复后不应再出现）→ 降级为 warning，不阻断
- `strand_balance` 和 `entity_freshness`：保留 blocking，但仅在有 contracts 的项目中生效（合同缺失时这些检查无意义）
- 基础设施问题汇总为一条提示，不逐条重复

```bash
# 解析后处理
python -c "
import json, sys
d = json.load(sys.stdin)
infra_issues = [c for c in d['checks'] if not c['passed'] and c['name'] == 'contract_coverage']
writing_issues = [c for c in d['checks'] if not c['passed'] and c['name'] != 'contract_coverage']
if infra_issues and not writing_issues:
    print('⚠️ 基础设施问题（不影响本章写作）：')
    for c in infra_issues:
        print(f'  - {c[\"detail\"]}')
    print('✅ 跳过阻断，继续写作')
    d['passed'] = True
print(json.dumps(d, ensure_ascii=False))
"
```

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `skills/webnovel-write/SKILL.md` | 修改 | 结构自检段，加分级过滤 |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | 同上 |

### S4b: 批处理进度 + 安全暂停

#### 问题

批量模式无运行时进度条。用户说"停下"后需手动写 paused 状态。

#### 方案

- **进度条**：现有的 `✅ 第{N}章完成 | 进度: {N-S+1}/{E-S+1}` 已足够。不需额外改动。
- **安全暂停**：在 3 章暂停点增加指令——"处理中收到停止指令时，先完成当前章 Step 9 写入 batch_state，再将 status 改为 paused"。

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `skills/webnovel-write-batch/SKILL.md` | 修改 | 暂停点加"收到停止指令"处理说明 |

### S4c: placeholder 去重

#### 问题

`placeholder-scan` 每章都输出同样的占位符，无新信息。

#### 方案

在 skill 调用 `placeholder-scan --format text` 后面加 `| sort -u`，至少消除重复行。或者改为只在第一章时运行一次。

#### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `skills/webnovel-write/SKILL.md` | 修改 | placeholder-scan 加 sort -u |

---

## 完整文件清单

| 文件 | S1 | S2 | S3a | S3b | S3c | S4a | S4b | S4c | 操作 |
|------|:--:|:--:|:---:|:---:|:---:|:---:|:---:|:---:|------|
| `scripts/skill_runner.py` | ✓ | | | | | | | | 新增 |
| `data_modules/story_system_engine.py` | | ✓ | | | | | | | 修改 |
| `scripts/review_pipeline.py` | | | ✓ | | | | | | 修改 |
| `agents/chapter-writer-agent.md` | | | | ✓ | | | | | 修改 |
| `skills/webnovel-write/SKILL.md` | ✓ | | | | ✓ | ✓ | | ✓ | 修改 |
| `skills/webnovel-write-batch/SKILL.md` | ✓ | | | | ✓ | ✓ | ✓ | | 修改 |

## Test Plan

- `test_skill_runner_story_system` — 验证 genre 自动从 state.json 读取并传递
- `test_skill_runner_check_file` — 存在/不存在/空文件三种情况
- `test_split_compound_genre` — "末世+异能" 匹配 GR-012，"修仙+硬核科幻" 匹配 GR-011
- `test_clean_reviewer_output` — 纯 JSON / JSON+前缀 / JSON+后缀 / JSON in markdown 四种
- Manual: 凡尘之舞项目执行完整写章流程，验证 CJK 无乱码
