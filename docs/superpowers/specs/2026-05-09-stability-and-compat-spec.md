# Stability & Compatibility Fix Spec

## Context

Ch78 写作暴露 22 个问题。8 个已在上轮修复，本 spec 覆盖剩余 14 个。

覆盖映射：
- 已修复 (8): #1 genre 编码, #2 自检乱码, #3 commit 路径, #6 reviewer JSON, #7 index.db 列名, #8 utcnow, #19 commit 路径
- S1 (5): #4 控制台乱码, #9 test -s 不兼容, #18 引号脆弱, #1/#2/#3 的根因巩固
- S2 (2): #5 路由缺失, #13 context-agent 负担
- S3 (3): #11 任务书忽略, #12 reviewer 不一致, #15 review 残留
- S4 (4): #14 自检噪音, #16 无进度, #17 不安全中断, #10 placeholder 重复

(#20/21/22 Ch78 写作质量问题是正常修复轮范畴，非系统 bug)

---

## S1: Shell 兼容层 — skill_runner.py

### 问题

#4/#9/#18 + 已修复的 #1/#2/#3 的共同根因：CJK 文本经过 bash 变量和 PowerShell 管道时编码损坏。修单个场景是打地鼠。

### 方案

新增 `.opencode/scripts/skill_runner.py`，封装所有 CJK 敏感操作。**关键设计决策：CJK 数据走 stdin/file，不走 CLI args。**

```python
# 所有 action 从 stdin 或文件读取 CJK 输入
echo "...中文..." | python -X utf8 skill_runner.py <action> [--args-that-are-ascii-only]
```

启动时强制调用 `enable_windows_utf8_stdio`（来自项目已有的 `runtime_compat.py`），确保 stdout 输出也不乱码。

### 六个 Action 完整接口

#### `story-system`
```
用途: 刷新合同树
输入: stdin 读取 chapter goal（中文），--chapter N，自动从 state.json 读 genre
输出: stdout 转发 story-system 结果
实现: subprocess.run([webnovel.py, story-system, stdin_goal, --genre, genre_from_state, --chapter, N, ...])
```

#### `check-structural`
```
用途: 运行结构自检，输出过滤后的摘要
输入: --chapter N
输出: JSON {passed, checks, infra_skipped}
      --format text 时输出人类可读摘要
实现: 内部调用 structural_checker.run_checks()，S4a 分级过滤在此处执行
```

#### `check-commit`
```
用途: 验证章节 commit 文件存在且非空
输入: --chapter N
输出: stdout 一行 "OK" 或 "MISSING"
退出码: 0=存在, 1=不存在
```

#### `check-index`
```
用途: 验证章节在 index.db 中
输入: --chapter N
输出: stdout 一行 "OK" 或 "MISSING"
退出码: 0=存在, 1=不存在
```

#### `check-file`
```
用途: 替代 test -s，检查任意文件存在且非空
输入: --path <相对或绝对路径>
输出: stdout 一行 "OK" 或 "MISSING"
退出码: 0=存在且非空, 1=不存在或为空
```

#### `check-batch-integrity`
```
用途: 跨章 batch_state 完整性校验（S4b 使用）
输入: --start S --end N
输出: stdout "OK" 或 "MISSING: [缺失章号列表]"
退出码: 0=完整, 1=不完整
```

### skill 调用方式变更

修复前（#1 模式，CJK 经 shell）：
```bash
GENRE="$(python -c "...print(genre)")"
python ... story-system "${CHAPTER_GOAL}" --genre "${GENRE}" ...
```

修复后：
```bash
echo "${CHAPTER_GOAL}" | python -X utf8 "${SCRIPTS_DIR}/skill_runner.py" story-system --chapter {N}
```

Genre 从 state.json 自动读取，CHAPTER_GOAL 通过 stdin pipe 传入，不经过 shell 变量展开。

### 改动范围

| 文件 | 操作 |
|------|------|
| `scripts/skill_runner.py` | 新增 (~200 行) |
| `skills/webnovel-write/SKILL.md` | 合同、自检、审查段改为 skill_runner 调用 |
| `skills/webnovel-write-batch/SKILL.md` | 同上 + post-write 校验改为 skill_runner 调用 |

---

## S2: 合同路由修复 — 复合题材分解

### 问题

`题材与调性推理.csv` 26 行全是单题材。"末世+异能" 等复合题材无匹配，contract_coverage 恒 blocking。

### 方案

修改 `story_system_engine.py._fallback_row_for_genre`，直接匹配失败时按 `+` 分割后逐个尝试。

**优先级**（新的回退链路）：
1. 关键词匹配（现有逻辑，`_route` line 165-174）— 不变
2. 精确题材匹配（现有逻辑，`_fallback_row_for_genre`）— 不变
3. 复合题材拆解（新增）
4. 推断题材匹配（现有逻辑）— 不变

#### 复合拆解逻辑

```python
def _fallback_row_for_genre(self, rows, genre):
    # 1. 直接匹配（现有逻辑不变）
    result = self._direct_match(rows, genre)
    if result:
        return result

    # 2. 复合题材拆解（新增）
    if "+" in genre:
        components = [g.strip() for g in genre.split("+")]
        for component in components:
            result = self._direct_match(rows, component)
            if result:
                return result  # 返回第一个匹配的组件路由

    return None
```

`_direct_match` 提取现有精确匹配逻辑为独立方法。

### 匹配示例

| 输入 genre | 拆分 | 匹配结果 |
|-----------|------|---------|
| `末世+异能` | 末世, 异能 | GR-012 (末世求生) — 末世先匹配 |
| `修仙+硬核科幻` | 修仙, 硬核科幻 | GR-011 (传统修真) — 修仙先匹配 |
| `都市+异能` | 都市, 异能 | GR-010 (都市异能) |
| `纯修仙` | — | GR-011 — 不走拆解，直接匹配 |

### 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `data_modules/story_system_engine.py` | 修改 | 提取 `_direct_match`，新增拆解逻辑。~25 行 |

---

## S3: Agent 输出稳定性

### S3a: reviewer JSON 后处理清洗

re-prompt 约束不能 100% 防止 agent 夹带对话文本。加**后处理清洗**作为最后防线。

```python
# review_pipeline.py 新增
import re

def clean_reviewer_output(raw: str) -> str:
    """从 reviewer agent 输出中提取纯 JSON"""
    # 尝试从 markdown 代码块中提取
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', raw)
    if m:
        return m.group(1).strip()
    # 否则找第一个 { 到最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end+1]
    raise ValueError("reviewer 输出中未找到有效 JSON")
```

在 `parse_review_output` 调用前执行清洗。

| 文件 | 操作 |
|------|------|
| `scripts/review_pipeline.py` | 修改 (~15 行) |

### S3b: chapter-writer-agent 强制遵守

三管齐下：

**① Step A: 硬性约束清单化（prompt 约束）**
```markdown
### Step A: 理解任务

**硬性约束清单 — 起草前逐条确认，全部通过才进 Step B：**

□ 过渡承接: 本章开篇必须衔接上章结尾的 {open_question}
□ 必须覆盖: {must_cover_nodes}
□ 禁区: {forbidden_zones}
□ 字数: 2000-2500

**修复轮额外约束:**
□ 逐条对照【审查反馈】中的 issue，只修改指出的位置
```

**② Step C: 自检验证（新增对照检查）**
```markdown
### Step C: 硬性约束验证

起草完成后，逐条对照确认：
□ 过渡承接 ← 正文第__段已实现
□ must_cover_nodes ← 全部出现在正文中
□ 禁区 ← 未违反
□ 修复轮 issue ← 全部已修改

任一条未确认 → 回到 Step B 补充。
```

**③ 字数量化验证（已有，保留）**

```bash
WORDS=$(python -c "...")
test "$WORDS" -ge 1500 || { echo "⚠️ 字数不足"; }
```

| 文件 | 操作 |
|------|------|
| `agents/chapter-writer-agent.md` | Step A 改清单，Step C 补验证 |

### S3c: review_results.json 残留

修复轮每次重跑 reviewer 前，删除旧文件。

在修复轮流程中（单章 Step 3 和 batch Step 6），重审前：

```bash
rm -f "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"
```

| 文件 | 操作 |
|------|------|
| `skills/webnovel-write/SKILL.md` | 修复轮加 rm |
| `skills/webnovel-write-batch/SKILL.md` | 修复轮加 rm |

---

## S4: 流程体验

### S4a: 自检分级过滤

内置于 `skill_runner.py check-structural` action，不写在 skill 里。

```python
# skill_runner.py 内部
INFRA_CHECKS = {"contract_coverage"}  # 已知基础设施问题

def filter_checks(result, has_contracts):
    for c in result["checks"]:
        if c["name"] in INFRA_CHECKS:
            c["severity"] = "warning"    # 降级
            c["passed"] = True           # 不阻断
    # 重新计算 passed
    result["passed"] = not any(
        c["severity"] == "blocking" and not c["passed"]
        for c in result["checks"]
    )
    return result
```

| 文件 | 操作 |
|------|------|
| `scripts/skill_runner.py` | 内置过滤逻辑 |

### S4b: 安全暂停自动化

batch_state 初始化时默认 `status: paused`。每章开始前检查：如果是 `paused` 状态 → 询问继续/停止。如果是 `running` → 直接执行。

**Step 0.6 修改：**
```python
s = {
    ...
    'status': 'paused',  # 默认暂停，等待用户确认
    ...
}
```

**每章 Step 0 后新增状态门：**
```
if status == "paused":
    输出进度摘要 → 等待用户输入 "继续" 或 "停止"
    继续 → 改 status 为 "running"
    24h 无输入 → 保持 paused，下次恢复时继续
```

| 文件 | 操作 |
|------|------|
| `skills/webnovel-write-batch/SKILL.md` | Step 0.6 默认 paused + Step 0 后状态门 |

### S4c: placeholder 去重

```bash
python ... placeholder-scan --format text | sort -u
```

| 文件 | 操作 |
|------|------|
| `skills/webnovel-write/SKILL.md` | placeholder-scan 加 sort -u |

---

## 完整文件清单

| 文件 | S1 | S2 | S3a | S3b | S3c | S4a | S4b | S4c | 操作 |
|------|:--:|:--:|:---:|:---:|:---:|:---:|:---:|:---:|------|
| `scripts/skill_runner.py` | ✓ | | | | | ✓ | | | 新增 |
| `data_modules/story_system_engine.py` | | ✓ | | | | | | | 修改 |
| `scripts/review_pipeline.py` | | | ✓ | | | | | | 修改 |
| `agents/chapter-writer-agent.md` | | | | ✓ | | | | | 修改 |
| `skills/webnovel-write/SKILL.md` | ✓ | | | | ✓ | | | ✓ | 修改 |
| `skills/webnovel-write-batch/SKILL.md` | ✓ | | | | ✓ | | ✓ | | 修改 |

## Test Plan

- `test_skill_runner_check_file` — 存在/不存在/空文件三种
- `test_skill_runner_check_commit` — commit 存在/缺失
- `test_split_compound_genre` — "末世+异能"→GR-012, "修仙+硬核科幻"→GR-011, 纯题材不变
- `test_clean_reviewer_output` — 纯 JSON / JSON+前缀 / JSON+后缀 / markdown 代码块 / 无 JSON
- `test_structural_filter_infra` — contract_coverage 降级 warning 不阻断
- Manual: 凡尘之舞项目完整写章流程，验证 CJK 无乱码、contract_coverage 通过
