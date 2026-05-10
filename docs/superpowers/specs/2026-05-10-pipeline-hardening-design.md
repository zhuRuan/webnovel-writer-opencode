# Pipeline Hardening Design

> 基于 23 个 bug 的交叉分析，覆盖管线完整性、Windows 兼容、Agent 可靠性、噪音削减、体验打磨 5 个子系统。

**自检基线** (2026-05-10, 凡尘之舞 Ch28):
- strand_tracker 数据完整，strand_balance **非误报**（constellation 28 章为零，quest 连续 5 章）
- entity_freshness 数据正确（主角位置自 Ch12 后未更新，因为 data-agent 不输出不变的 location）
- contract_coverage 缺口: Ch1-7、11-15、27 无 chapter directive
- Pipeline-4 确认: filter_structural_checks 返回 passed=false 但 skill 层无阻断逻辑
- BUG-016 已过时（check-index 使用正确的 `chapter` 列名）
- aiohttp 泄漏确认: ModalAPIClient.close() 在 chapter-commit 路径从未被调用

---

## A. 管线完整性 (Pipeline Integrity)

### A1. PROJECT_ROOT 自动发现嵌套目录

**文件**: `.opencode/scripts/project_locator.py`

`_candidate_roots()` 在 yield CWD 和祖先目录后，额外扫描 CWD 下所有含 `.webnovel/state.json` 的直接子目录。这样 `凡尘之舞/` (无 .webnovel) → 自动发现 `凡尘之舞/凡尘之舞/` (有 .webnovel)。

```python
# 在 _candidate_roots() 中，yield 完现有候选后新增:
if cwd.is_dir():
    try:
        for child in sorted(cwd.iterdir()):
            if child.is_dir() and _is_project_root(child):
                yield child
    except OSError:
        pass
```

### A2. preflight 增加 fs_state_sync 检查

**文件**: `.opencode/scripts/data_modules/webnovel.py` (`_build_preflight_report`)

新检查项 `fs_state_sync`:
- 扫描 `正文/` 目录 regex `第(\d+)章` 获得文件系统章节号集合
- 对比 `state.json` 中 `progress.chapter_status` 的 key 集合
- 输出孤文件（有文件无状态）和幽灵章（有状态无文件）
- 严重度: warning，不阻断

### A3. 合同树前置检查

**文件**: `.opencode/agents/chapter-writer-agent.md`

在 Step A 硬性约束确认清单中增加一项:

```
□ 合同树: .story-system/chapters/chapter_{NNN}.json 必须存在。
  若不存在，输出 "❌ 合同树缺失: 请先运行 story-system 刷新合同" 并退出。
```

**文件**: `.opencode/skills/webnovel-write/SKILL.md`、`.opencode/skills/webnovel-write-batch/SKILL.md`

Step 1（刷新合同树）之后增加判定: `story-system` 返回非 0 即阻断。contract_coverage 已被 filter_structural_checks 降级为 warning，需要在 skill 层面补硬关卡。

### A4. 结构自检阻断 + 阈值优化

**文件**: `.opencode/scripts/data_modules/structural_checker.py`

`_check_strand_balance`: constellation 阈值从 15 章降到 **8 章**（15 章太高，28 章才发现问题太晚）。

`_check_entity_freshness`: 阈值从 3 章升到 **5 章**，且增加 `detail` 信息指明是 data-agent 未输出位置还是主角真的没移动。当上一章无显式位置更新时，如果前 5 章内有任意位置记录则 passed=true。

**文件**: `.opencode/skills/webnovel-write/SKILL.md`、`.opencode/skills/webnovel-write-batch/SKILL.md`

Step 1b（结构自检）之后增加硬关卡:

```bash
python -c "
import json, sys
d = json.load(open('$CHECK_RESULT_FILE'))
if not d.get('passed'):
    print('❌ 结构自检未通过，停止流程')
    for c in d['checks']:
        if c['severity'] == 'blocking' and not c['passed']:
            print(f'  BLOCKING: {c[\"name\"]}: {c[\"detail\"]}')
    sys.exit(1)
" || exit 1
```

（批量 skill 同样位置同样关卡。）

**文件**: `.opencode/agents/data-agent.md`

在现有 "必须输出 protagonist location" 要求中强化: 即使位置未变，也必须输出 `location.current` state_delta，值同上一章位置。这确保 `protagonist_state.location.last_chapter` 每章更新，entity_freshness 检查不会因 data-agent 遗漏而误报。

---

## B. Windows 兼容性

### B1. 全局 UTF-8

**文件**: `.opencode/scripts/webnovel.py`

在 `if __name__ == "__main__":` 块开头（parse_args 之前）调用 `enable_windows_utf8_stdio()`。

**文件**: `.opencode/scripts/skill_runner.py`

同样在 `if __name__ == "__main__":` 块开头调用。

**文件**: `.opencode/skills/webnovel-write/SKILL.md`、`.opencode/skills/webnovel-write-batch/SKILL.md`

在 Step 0 环境变量设置中添加 `$env:PYTHONUTF8 = 1`，确保所有子进程 Python 默认 UTF-8。

### B2. 验证命令统一为 Python/skill_runner

**文件**: `.opencode/scripts/skill_runner.py`

新增 `verify-chapter-files` action:
- 参数: `--project-root`, `--chapter`
- 行为: 检查正文文件存在且非空、commit 文件存在、projection 状态五项全部 done/skipped
- 输出: `OK` 或 `FAIL: <reason>`
- 返回码: 0/1

```python
def cmd_verify_chapter_files(args):
    root = Path(args.project_root)
    ch = int(args.chapter)
    errors = []
    
    # 正文文件
    text_dir = root / "正文"
    chapter_files = list(text_dir.rglob(f"第*{ch:03d}*章*.md")) or list(text_dir.rglob(f"第*{ch}*章*.md"))
    if not chapter_files:
        errors.append(f"章节文件缺失: 第{ch}章")
    elif not chapter_files[0].stat().st_size:
        errors.append(f"章节文件为空: 第{ch}章")
    
    # commit 文件
    commit_file = root / ".story-system" / "commits" / f"chapter_{ch:03d}.commit.json"
    if not commit_file.is_file():
        errors.append(f"commit 文件缺失: chapter_{ch:03d}.commit.json")
    else:
        commit = json.loads(commit_file.read_text("utf-8"))
        proj = commit.get("projection_status", {})
        for name in ("state", "index", "summary", "memory", "vector"):
            status = proj.get(name, "missing")
            if status not in ("done", "skipped"):
                errors.append(f"projection {name}={status}")
    
    if errors:
        print("FAIL: " + "; ".join(errors))
        return 1
    print("OK")
    return 0
```

**文件**: `.opencode/skills/webnovel-write/SKILL.md`、`.opencode/skills/webnovel-write-batch/SKILL.md`

Step 8 写后校验中的 4 个 bash 命令替换为单一 `skill_runner.py verify-chapter-files` 调用。

所有 `test -s` / `export` / `echo $VAR` bash 语法替换为等价的 Python 单行或 skill_runner 调用。

### B3. 中文路径原则

**文件**: `.opencode/skills/webnovel-write/SKILL.md`

在 "硬规则" 区域增加:

> 所有文件存在性验证必须用 Python (`python -c "..."` 或 skill_runner) 而非 PowerShell 原生命令。中文路径在 PowerShell 的 `Test-Path` 和 Python 的 `os.path.isfile` 之间编码不一致。

---

## C. Agent 可靠性

### C1. 加强 Agent 后文件校验

**文件**: `.opencode/skills/webnovel-write/SKILL.md`

在 context-agent、chapter-writer-agent、reviewer、data-agent 每步 Agent 调用后，增加:

```bash
# 不依赖 Agent 返回文本，直接校验输出文件
sleep 1  # 给文件系统 1 秒落地
python -c "
from pathlib import Path
# 根据步骤检查对应输出文件
...
"
```

（批量 skill 已有此逻辑，不需要重复修改。）

---

## D. 噪音削减

### D1. placeholder-scan 已知占位符过滤

**文件**: `.opencode/scripts/data_modules/webnovel.py`

`placeholder-scan` 命令增加 `--ignore-file` 参数，默认值 `.webnovel/known_placeholders.json`。

**文件**: 新建 `known_placeholders.json` 管理逻辑在 `placeholder-scan` 模块中。

占位符格式:
```json
{
  "ignored": [
    {"file": "设定集/角色库/反派角色/掠夺者团伙.md", "line": 4, "text": "（暂名）", "reason": "角色名持续讨论中"}
  ]
}
```

扫描时若命中 ignore 列表则从输出中过滤。ignore 列表为空时行为不变。

### D2. index.db 列名: 无需修复

`check-index` 已使用正确的 `chapter` 列名（确认于 `skill_runner.py:101`）。BUG-016 为旧版本残留，标记为已修复。

---

## E. 体验打磨

### E1. 批处理进度可视化

**文件**: `.opencode/skills/webnovel-write-batch/SKILL.md`

逐章循环中，每步执行前打印:

```
[Ch{N} Step {M}/9] {step_name}...
```

`step_name` 映射: 0=环境变量, A=上章完整性, 1=合同刷新, 1b=结构自检, 2=context-agent, 3=写作, 4=审查, 5=pipeline, 6=修复轮, 7=data-agent, 8=commit+验证, 9=更新状态

### E2. 安全中断

**文件**: `.opencode/scripts/skill_runner.py`

新增 `pause-batch` action:
- 参数: `--project-root`
- 行为: 读取 `PROJECT_ROOT/.webnovel/batch_state.json`，若 status == "running"，改为 "paused" 并输出 `PAUSED at chapter={current_chapter}`。若 status 已为 "paused"，输出 `ALREADY PAUSED`。若文件不存在，输出 `NO_BATCH`。
- 返回码: 0

用户可通过 `python -X utf8 skill_runner.py pause-batch --project-root "$PROJECT_ROOT"` 安全中断。

### E3. preflight 输出清晰化

**文件**: `.opencode/scripts/data_modules/story_runtime_health.py`

`build_story_runtime_health` 返回的 dict 增加 `display_text` 字段:
```
主合同链: 第28章 (MASTER_SETTING → volume_001 → chapter_028), 提交: accepted
```

原 `chapter`、`mainline_ready` 等字段保持不变（向后兼容）。

**文件**: `.opencode/scripts/data_modules/webnovel.py`

`cmd_preflight` 的输出优先使用 `story_runtime.get("display_text")` 替代当前的 `chapter={} mainline_ready={}` 格式。

### E4. aiohttp 连接关闭

**文件**: `.opencode/scripts/chapter_commit.py`

在 `main()` 函数末尾（`apply_projections` 返回之后，`print(json)` 之前）:

```python
from .data_modules.api_client import get_client
get_client().close()
```

不使用 try/finally 包裹整个流程（保持最小变更原则），仅在正常路径关闭。进程退出时 OS 会回收 socket，不会造成资源泄漏，只是消除 stderr 的 warning 噪音。

### E5. CLI mode 参数

**文件**: `.opencode/scripts/data_modules/webnovel.py`

在涉及 skill 执行的命令注册中增加 `--mode` 参数:

```python
parser.add_argument("--mode", choices=["default", "fast", "minimal"], default="default")
```

当前不改变任何行为——`--mode` 参数只做透传准备。实际 mode 调度逻辑留待后续需求。

---

## 影响面总览

| 子系统 | 文件 | 变更类型 |
|--------|------|---------|
| A1 | `project_locator.py` | 修改 ~10 行 |
| A2 | `webnovel.py` (preflight) | 新增 ~30 行 |
| A3 | `chapter-writer-agent.md` | 修改 ~5 行 |
| A3 | `webnovel-write/SKILL.md` | 修改 ~5 行 |
| A3 | `webnovel-write-batch/SKILL.md` | 修改 ~5 行 |
| A4 | `structural_checker.py` | 修改 ~20 行 |
| A4 | `webnovel-write/SKILL.md` | 新增 ~15 行 |
| A4 | `webnovel-write-batch/SKILL.md` | 新增 ~15 行 |
| A4 | `data-agent.md` | 修改 ~5 行 |
| B1 | `webnovel.py` | 修改 ~2 行 |
| B1 | `skill_runner.py` | 修改 ~2 行 |
| B1 | `webnovel-write/SKILL.md` | 修改 ~2 行 |
| B1 | `webnovel-write-batch/SKILL.md` | 修改 ~2 行 |
| B2 | `skill_runner.py` | 新增 ~35 行 |
| B2 | `webnovel-write/SKILL.md` | 修改 ~20 行 |
| B2 | `webnovel-write-batch/SKILL.md` | 修改 ~15 行 |
| B3 | `webnovel-write/SKILL.md` | 新增 ~3 行 |
| C1 | `webnovel-write/SKILL.md` | 新增 ~10 行 |
| D1 | `webnovel.py` | 修改 ~10 行 |
| D1 | placeholder-scan 模块 | 新增 ~20 行 |
| E1 | `webnovel-write-batch/SKILL.md` | 新增 ~15 行 |
| E2 | `skill_runner.py` | 新增 ~15 行 |
| E3 | `story_runtime_health.py` | 修改 ~5 行 |
| E3 | `webnovel.py` | 修改 ~5 行 |
| E4 | `chapter_commit.py` | 修改 ~3 行 |
| E5 | `webnovel.py` | 修改 ~5 行 |

---

## 不变更事项

- `index_manager.py` — schema 正确，无需修改
- `chapter_commit_service.py` — _sync_foreshadowing 逻辑完整
- `state_projection_writer.py` — _apply_strand_tracker 工作正常
- `review_pipeline.py` — clean_reviewer_output 已修 BUG-005
- Agent 框架本身的返回机制 — 不在本项目范围内
