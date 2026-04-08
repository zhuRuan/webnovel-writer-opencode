---
name: webnovel-dashboard
description: 启动可视化小说管理面板（只读 Web Dashboard），实时查看项目状态、实体图谱与章节内容。
allowed-tools: Bash Read
---

# Webnovel Dashboard

## 目标

在本地启动一个 **只读** Web 面板，用于可视化查看当前小说项目的：
- 创作进度与 Strand 节奏分布
- 设定词典（角色/地点/势力等实体）
- 关系图谱
- 章节与大纲内容浏览
- 追读力分析数据

面板通过 `watchdog` 监听 `.webnovel/` 目录变更并实时刷新，不对项目做任何修改。

## 执行步骤

### Step 0：环境确认

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"

# 确定 .opencode 目录位置（优先使用项目级，其次用户级）
if [ -d "${WORKSPACE_ROOT}/.opencode/dashboard" ]; then
  export OPENCODE_DIR="${WORKSPACE_ROOT}/.opencode"
elif [ -d "${HOME}/.opencode/dashboard" ]; then
  export OPENCODE_DIR="${HOME}/.opencode"
else
  echo "ERROR: 未找到 dashboard 模块" >&2
  exit 1
fi
export DASHBOARD_DIR="${OPENCODE_DIR}/dashboard"
export SCRIPTS_DIR="${OPENCODE_DIR}/scripts"
```

### Step 1：安装依赖（首次）

```bash
python -m pip install -r "${DASHBOARD_DIR}/requirements.txt" --quiet
```

### Step 1.5：自动安装前端依赖（首次）

```bash
FRONTEND_DIR="${DASHBOARD_DIR}/frontend"

# 检查前端 package.json 是否存在（pip 安装时可能缺失）
if [ ! -f "${FRONTEND_DIR}/package.json" ]; then
  echo "ERROR: 缺少前端 package.json" >&2
  echo "请从源码复制 .opencode/dashboard/frontend/package.json 到此处。" >&2
  exit 1
fi

# 检查 node_modules 是否存在
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
  echo "首次使用，正在安装前端依赖..."
  cd "${FRONTEND_DIR}"
  npm install
fi

# 检查 dist 目录是否存在（前端构建产物）
if [ ! -f "${FRONTEND_DIR}/dist/index.html" ]; then
  echo "正在构建前端..."
  cd "${FRONTEND_DIR}"
  npm run build
fi

echo "前端依赖就绪。"
```

### Step 2：解析项目根目录

```bash
export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
echo "项目路径: ${PROJECT_ROOT}"
```

### Step 3：启动 Dashboard

推荐方式（通过 webnovel.py 统一入口）：

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" dashboard
```

或直接使用 dashboard 模块：

```bash
# 确保 .opencode 目录在 PYTHONPATH 中
if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="${OPENCODE_DIR}:${PYTHONPATH}"
else
  export PYTHONPATH="${OPENCODE_DIR}"
fi

python -m dashboard.server --project-root "${PROJECT_ROOT}"
```

启动后会自动打开浏览器访问 `http://127.0.0.1:8765`。

如不需要自动打开浏览器，使用：

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" dashboard --no-browser
```

## 注意事项

- Dashboard 为纯只读面板，所有 API 仅 GET，不提供任何修改接口。
- 文件读取严格限制在 `PROJECT_ROOT` 范围内，防止路径穿越。
- 如需自定义端口，添加 `--port 9000` 参数。
