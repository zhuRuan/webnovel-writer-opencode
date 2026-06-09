# project_phase.py 同步计划

> **来源**：原项目 `webnovel-writer/scripts/data_modules/project_phase.py`（398 行）
> **目标**：同步项目阶段感知模块，增强 write_gates 门禁

---

## 一、同步内容

### 1.1 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `data_modules/project_phase.py` | 398 | 项目阶段检测模块 |
| `tests/test_project_phase.py` | ~120 | 配套测试（7 个用例） |

### 1.2 依赖状态

| 依赖 | 位置 | 状态 |
|------|------|------|
| `chapter_outline_loader` | `.opencode/scripts/` | ✅ 存在 |
| `chapter_paths` | `.opencode/scripts/` | ✅ 存在 |
| `projection_log` | `.opencode/scripts/data_modules/` | ✅ 已同步 |

### 1.3 冲突检查

- 本项目无 `project_phase.py`、`resolve_project_phase`、`ProjectPhaseSnapshot`
- 零命名冲突

---

## 二、实施步骤

### Step 1：复制 project_phase.py

**操作**：从原项目直接复制，零修改。

```bash
cp "外部参考/webnovel-writer 原项目/webnovel-writer/scripts/data_modules/project_phase.py" \
   ".opencode/scripts/data_modules/project_phase.py"
```

**验证**：`python -c "import ast; ast.parse(open('.opencode/scripts/data_modules/project_phase.py').read()); print('OK')"`

### Step 2：复制并适配测试文件

**操作**：从原项目复制测试文件，调整路径 helper。

原项目测试文件中 `_ensure_scripts_on_path` 使用 `parents[2]` 指向 `scripts/`。本项目需要指向 `.opencode/scripts/`。

**适配**：
```python
# 原项目
scripts_dir = Path(__file__).resolve().parents[2] / "scripts"

# 本项目
scripts_dir = Path(__file__).resolve().parents[2]  # .opencode/scripts/
```

**验证**：`python -m pytest .opencode/scripts/data_modules/tests/test_project_phase.py -q -p no:cov -o "addopts="`

### Step 3：运行全量测试

**验证**：`python -m pytest .opencode/scripts/data_modules/tests/ -q -p no:cov -o "addopts=" --ignore=.opencode/scripts/data_modules/tests/test_publisher.py`

确认 7 个新测试通过，且现有 729 个测试不受影响。

### Step 4：提交

```bash
git add .opencode/scripts/data_modules/project_phase.py .opencode/scripts/data_modules/tests/test_project_phase.py
git commit -m "refactor: 同步 project_phase.py — 项目阶段感知模块"
```

---

## 三、后续集成（可选，独立任务）

### 3.1 prewrite gate 增强

在 `prewrite.py` 中添加阶段守卫：

```python
from ..project_phase import resolve_project_phase, PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED

def run_prewrite_gate(project_root: Path, chapter: int) -> dict:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    if snapshot.phase in (PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED):
        return gate_report("prewrite", errors=[issue(
            "invalid_phase", "error",
            f"项目阶段 {snapshot.phase} 不允许写入",
            repair="先完成初始化或修复缺失文件",
        )], warnings=[])
    # ... 现有检查逻辑
```

### 3.2 precommit gate 增强

在 `precommit.py` 中添加阶段守卫：

```python
BLOCKED_PRECOMMIT_PHASES = {PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED, PHASE_PROJECTION_FAILED}

def run_precommit_gate(project_root: Path, chapter: int) -> dict:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    if snapshot.phase in BLOCKED_PRECOMMIT_PHASES:
        return gate_report("precommit", errors=[issue(
            "invalid_phase", "error",
            f"项目阶段 {snapshot.phase} 阻断提交",
            repair="先修复阻断问题",
        )], warnings=[])
    # ... 现有检查逻辑
```

### 3.3 postcommit gate 增强

在 `postcommit.py` 中注入 phase 诊断上下文：

```python
def run_postcommit_gate(project_root: Path, chapter: int) -> dict:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    # ... 现有检查逻辑
    result["phase"] = snapshot.phase
    result["blocking"] = list(snapshot.blocking)
    result["warnings"] = list(snapshot.warnings)
    return result
```

### 3.4 doctor.py 增强

在 `doctor.py` 中使用 `resolve_project_phase` 做阶段判断，替代自行实现的检查逻辑。

---

## 四、风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 依赖缺失 | 无 | 三个依赖全部存在 |
| 路径不兼容 | 无 | try/except 双路径已覆盖 |
| 测试破坏 | 无 | 纯新增模块 |
| 功能回归 | 无 | 不修改现有文件 |
| 测试路径适配 | 低 | 仅需调整 1 行 |

---

## 五、验证清单

- [ ] `project_phase.py` 复制成功，语法检查通过
- [ ] `test_project_phase.py` 适配后 7 个测试全部通过
- [ ] 现有 729 个测试不受影响
- [ ] `resolve_project_phase(project_root)` 返回正确的阶段
- [ ] 缺失文件/目录被正确检测
- [ ] projection_log 优先级逻辑正确
