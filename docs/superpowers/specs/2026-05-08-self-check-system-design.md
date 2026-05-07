# Self-Check System Design

## Context

凡尘之舞项目诊断发现：strand 连续 5 章 quest 主导且 constellation 从未激活、主角位置 9 章未更新、记忆系统 41% 过期条目、伏笔追踪（debt_tracker）完全空转。这些问题 reviewer（LLM）偶尔能发现但依赖运气——第 20 章审查报告中的 entity_state 过期问题是 reviewer 偶然对比 state.json 和大纲才发现的。

**核心问题**：缺少确定性、跨章统计的写前阻断机制。

## Architecture

```
写前                                     写后
────                                     ────
structural_checker (CLI, 新增)           skill 内 bash 校验
├─ strand_balance       blocking         ├─ projection 五项
├─ entity_freshness     blocking         ├─ batch_state 跨章
├─ memory_bloat         warning          └─ index.db 覆盖
├─ debt_burden          warning
└─ contract_coverage    blocking
        │
        ▼
reviewer prompt 注入（审查时带上自检状态）
```

## Component 1: `structural_checker.py`

### 位置

`.opencode/scripts/data_modules/structural_checker.py`

### 接口

```python
def run_checks(project_root: Path, chapter: int) -> dict:
    """返回 {"passed": bool, "checks": [...]}"""
```

### 五项检查

| # | 检查项 | 数据源 | 严重度 | 阈值 | 逻辑 |
|---|--------|--------|--------|------|------|
| 1 | `strand_balance` | state.json > strand_tracker | **blocking** | quest 连续>5 / constellation 缺席>10 | 读 history 计算连续相同 dominant 的章数；读 last_constellation_chapter 算间隔 |
| 2 | `entity_freshness` | state.json > protagonist_state.location | **blocking** | last_chapter 落后≥3 章 | 直接比较 location.last_chapter 与传入 chapter |
| 3 | `memory_bloat` | memory_scratchpad.json | warning | outdated 占比>30% | 统计 status=="outdated" 的条目比例 |
| 4 | `debt_burden` | state.json > plot_threads.foreshadowing | warning | 未回收>5 条且最近 10 章无偿还 | 统计 status=="未回收" 的数量 |
| 5 | `contract_coverage` | .story-system/chapters/chapter_{NNNN}.json | **blocking** | 文件不存在 | path.is_file() |

### 检查 #2 细节

只检查主角（`protagonist_state.location.last_chapter`）。v1 不扩展至所有 entity_state 实体——index.db 的 `state_changes` 表已记录所有变更历史，后续可通过 SQL 查询扩展。

### 输出 JSON schema

```json
{
  "chapter": 21,
  "passed": false,
  "checks": [
    {
      "name": "strand_balance",
      "passed": false,
      "severity": "blocking",
      "detail": "constellation 从未激活（当前第21章），最高容忍 15 章",
      "fix": "本章或下一章必须安排世界观展开：新势力/新地点/设定揭示/身世线索"
    }
  ]
}
```

### CLI 集成

`webnovel.py` 新增 subcommand：

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" checkers structural --chapter {N} --format json
```

- `--format json`：返回 JSON，供 skill 解析
- `--format text`：人类可读输出，供手动调试

### 与 prewrite_validator 的关系

`structural_checker` 补充 `prewrite_validator`，两者不重叠：

| prewrite_validator | structural_checker |
|---|---|
| disambiguation_pending | strand_balance |
| contract 存在性（master/volume/chapter/review 四个文件） | contract_coverage（单个 chapter contract） |
| placeholder 扫描 | entity_freshness |
| forbidden_zones 提取 | memory_bloat |
| | debt_burden |

`prewrite_validator` 在 Step 1（刷新合同树）之前运行，`structural_checker` 在 Step 1 之后（有了 chapter contract 之后）运行。

## Component 2: 写后校验增强

### 位置

直接写在 `webnovel-write-batch/SKILL.md` 的 Step 8 内，不单独建文件。

### 校验内容

```bash
# 1. 验证本章 commit 已生成
COMMIT_FILE="${PROJECT_ROOT}/.story-system/commits/chapter_$(printf '%04d' ${N}).commit.json"
test -s "$COMMIT_FILE" || echo "❌ commit 缺失"

# 2. 验证 projection 五项
python -c "
import json
state = json.load(open('${PROJECT_ROOT}/.webnovel/state.json'))
status = state.get('progress', {}).get('chapter_status', {}).get(str($N))
assert status == 'chapter_committed', f'chapter_status={status}, 期望 committed'
print('✅ projection 已提交')
"

# 3. 验证 index.db 覆盖
python -c "
import sqlite3
db = sqlite3.connect('${PROJECT_ROOT}/.webnovel/index.db')
row = db.execute('SELECT COUNT(*) FROM chapters WHERE chapter_num=?', ($N,)).fetchone()
assert row[0] > 0, f'第${N}章未在 index.db 中'
print('✅ index.db 已覆盖')
"

# 4. batch_state 跨章完整性（已在 Step 9 中实现）
```

## Component 3: Reviewer Prompt 注入

### 位置

`webnovel-write/SKILL.md` Step 3（审查）和 `webnovel-write-batch/SKILL.md` Step 4，Agent(reviewer) 调用前的 prompt 组装。

### 注入方式

在 reviewer agent 的 prompt 末尾追加自检状态块：

```text
Agent(
  subagent_type: "reviewer",
  prompt: "chapter={N}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。

【自检系统状态 - 审查时需额外关注】
{structural_checker 输出中 passed=false 的条目，转为自然语言}

严格输出 reviewer schema JSON..."
)
```

注入时只包含 `passed=false` 的检查项，每个翻译为一行提醒：
- strand_balance blocking → "本章应注意情节线平衡：{detail}"
- entity_freshness blocking → "审查时确认 data-agent 能提取位置/状态变化：{detail}"

## Files Changed

| 文件 | 操作 | 说明 |
|------|------|------|
| `data_modules/structural_checker.py` | 新增 | 五项检查核心逻辑 |
| `data_modules/webnovel.py` | 修改 | 注册 `checkers structural` 子命令 |
| `skills/webnovel-write/SKILL.md` | 修改 | Step 1 后加 structural 检查；Step 3 注入 reviewer prompt |
| `skills/webnovel-write-batch/SKILL.md` | 修改 | 逐章 Step 1 后加检查；Step 4 注入 reviewer prompt；Step 8 加写后校验 |

不变更：`prewrite_validator.py`、所有 agent 定义、`data-agent.md`、`context-agent.md`。

## Test Plan

- `test_structural_checker_strand_balance` — quest 连续 6 章时 blocking
- `test_structural_checker_strand_constellation_absent` — constellation 从未激活且 chapter>10 时 blocking
- `test_structural_checker_entity_freshness` — location.last_chapter 落后 3+ 章时 blocking
- `test_structural_checker_memory_bloat` — outdated 占比>30% 时 warning
- `test_structural_checker_debt_burden` — 未回收伏笔>5 时 warning
- `test_structural_checker_contract_coverage` — contract 缺失时 blocking
- `test_structural_checker_all_pass` — 健康项目全部通过
- Manual: 在凡尘之舞项目运行 `webnovel.py checkers structural --chapter 21`，验证实际输出
