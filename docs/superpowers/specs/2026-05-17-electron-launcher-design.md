# Webnovel Writer Electron 启动器 — 设计规格

> **日期**: 2026-05-17
> **目标**: 用一个桌面启动器替代终端安装 + OpenCode 手动配置流程，用户 3 分钟内从双击到开始写作。

## 1. 架构

遵循 Electron 标准进程模型：

```text
┌──────────────────────────────────────────┐
│            Electron App                   │
│                                           │
│  ┌──────────────────────────────────┐    │
│  │     Renderer Process (React)      │    │
│  │  contextIsolation: true            │    │
│  │  nodeIntegration: false            │    │
│  │  sandbox: true                     │    │
│  │                                   │    │
│  │  ┌─────────┐  ┌────────────────┐  │    │
│  │  │ 项目列表  │  │  Dashboard     │  │    │
│  │  │ (新增)   │  │ (现有代码复用)  │  │    │
│  │  └─────────┘  └────────────────┘  │    │
│  └────────┬─────────────────────────┘    │
│           │ contextBridge IPC              │
│  ┌────────▼─────────────────────────┐    │
│  │       Preload Script              │    │
│  │  contextBridge.exposeInMainWorld  │    │
│  │  ('electronAPI', { ... })         │    │
│  └────────┬─────────────────────────┘    │
│           │                               │
│  ┌────────▼─────────────────────────┐    │
│  │       Main Process (Node.js)      │    │
│  │  • window 管理 (BrowserWindow)     │    │
│  │  • 项目 CRUD (projects.json)       │    │
│  │  • 子进程管理 (Python/OpenCode)     │    │
│  │  • 自动发现 (.webnovel/state.json) │    │
│  │  • 版本更新检测 (manifest.json)     │    │
│  └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

## 2. 目录结构

```
.opencode/launcher/              # 新增，与现有 .opencode/ 平级
├── package.json                 # Electron + React deps
├── electron-builder.yml         # 打包配置
├── src/
│   ├── main/                    # Main Process
│   │   ├── index.ts             # 入口：窗口创建 + 初始化
│   │   ├── ipc-handlers.ts      # IPC 处理器注册
│   │   ├── project-store.ts     # projects.json 读写
│   │   ├── process-manager.ts   # Python/OpenCode 子进程管理
│   │   ├── update-checker.ts    # manifest.json 版本比对
│   │   └── auto-discover.ts     # 扫描工作区发现书项目
│   ├── preload/
│   │   └── index.ts             # contextBridge 暴露 API
│   └── renderer/                # React 前端
│       ├── index.html
│       ├── index.tsx
│       ├── App.tsx              # 路由: 项目列表 | Dashboard
│       ├── pages/
│       │   ├── ProjectList.tsx  # 首页：项目库
│       │   └── Dashboard.tsx    # 复用现有 dashboard/frontend
│       ├── components/
│       │   ├── ProjectCard.tsx  # 项目卡片
│       │   ├── CreateDialog.tsx # 创建新书对话框
│       │   ├── StatsBar.tsx     # 顶部统计条
│       │   └── StatusBar.tsx    # 底部状态栏
│       └── styles/
│           └── global.css       # 暗色主题全局样式
└── assets/
    └── icon.png                 # 应用图标
```

## 3. IPC 接口设计

遵循 `contextBridge` + `ipcMain.handle` / `ipcMain.on` 规范：

### 3.1 Preload 暴露的 API

```typescript
// src/preload/index.ts
contextBridge.exposeInMainWorld('electronAPI', {
  // 项目管理
  getProjects: () => ipcRenderer.invoke('projects:list'),
  addProject: (path: string) => ipcRenderer.invoke('projects:add', path),
  removeProject: (path: string) => ipcRenderer.invoke('projects:remove', path),
  createProject: (opts: CreateProjectOpts) => ipcRenderer.invoke('projects:create', opts),
  scanWorkspace: () => ipcRenderer.invoke('projects:scan'),

  // 进程管理
  openInOpenCode: (projectPath: string) => ipcRenderer.invoke('opencode:open', projectPath),
  startDashboard: (projectPath: string) => ipcRenderer.invoke('dashboard:start', projectPath),
  getDashboardStatus: () => ipcRenderer.invoke('dashboard:status'),

  // 系统
  getAppVersion: () => ipcRenderer.invoke('app:version'),
  checkForUpdates: () => ipcRenderer.invoke('app:check-updates'),
  getWorkspaceRoot: () => ipcRenderer.invoke('app:workspace-root'),
  openExternalUrl: (url: string) => ipcRenderer.invoke('shell:open', url),

  // 事件监听（Main → Renderer push）
  onDashboardReady: (cb: (port: number) => void) => ipcRenderer.on('dashboard:ready', (_e, port) => cb(port)),
  onUpdateAvailable: (cb: (version: string) => void) => ipcRenderer.on('update:available', (_e, v) => cb(v)),
});
```

### 3.2 Main Process 处理器

```typescript
// src/main/ipc-handlers.ts
ipcMain.handle('projects:list', async () => projectStore.getAll());
ipcMain.handle('projects:create', async (_e, opts) => projectStore.create(opts));
ipcMain.handle('projects:scan', async () => autoDiscover.scan());
ipcMain.handle('opencode:open', async (_e, projectPath) => processManager.openOpenCode(projectPath));
ipcMain.handle('dashboard:start', async (_e, projectPath) => processManager.startDashboard(projectPath));
ipcMain.handle('app:check-updates', async () => updateChecker.check());
```

## 4. 数据流

### 4.1 项目注册表

```json
// ~/.webnovel-writer/projects.json
{
  "schema_version": 1,
  "projects": {
    "D:\\novels\\凡人资本论": {
      "title": "凡人资本论",
      "genre": "都市异能",
      "target_chapters": 50,
      "current_chapter": 17,
      "total_words": 32000,
      "added_at": "2026-05-15T10:30:00Z",
      "last_opened": "2026-05-17T08:00:00Z"
    }
  },
  "workspace_root": "D:\\novels",
  "updated_at": "2026-05-17T08:00:00Z"
}
```

来源：启动时读取；项目创建/打开时更新；自动扫描时追加。每次打开项目时同步 state.json 中的 `progress.current_chapter`、`progress.total_words` 到注册表。

### 4.2 子进程管理

```
Main Process
  ├── spawn Python FastAPI (Dashboard 后端) → http://localhost:8080
  │   命令: python .opencode/dashboard/server.py --port 8080
  │   启动时机: 用户点击"Dashboard"或渲染进程请求
  │   生命周期: idle 5分钟后自动关闭
  │
  └── spawn OpenCode → 独立桌面窗口
      命令: opencode --project-root <书项目路径>
      启动时机: 用户点击"开始写作"
      生命周期: 独立进程，不随启动器退出而关闭
```

### 4.3 版本更新

```
启动时 fetch:
  https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/manifest.json
  → 取 version 字段
  → 比对本地的 .opencode/version.json
  → 有差异 → 状态栏显示提示 + 通知 Renderer
```

## 5. UI 页面设计

### 5.1 项目列表（首页）

见 mockup: `launcher-mockup.html`

核心元素：
- 顶部：Logo + 标题 + 操作按钮（创建新书 / 更多菜单）
- 统计条：总字数、已完成章节、项目数、版本号
- 快速操作：3 个卡片（继续写作 / 审查 / 阅读）
- 项目列表：每本书一张卡片，含进度条、快捷操作菜单
- 底部状态栏：Python 状态、OpenCode 状态、API 配额、工作区路径

### 5.2 Dashboard

复用现有 `.opencode/dashboard/frontend/` 的 React 代码。通过 Electron IPC 获取 project_path，渲染时传参。

### 5.3 空状态（首次使用）

```
┌──────────────────────────────────────────┐
│           📚                              │
│                                            │
│      还没有书项目                            │
│      创建你的第一本书，开始 AI 辅助写作         │
│                                            │
│         [ 创建新书 ]   [ 找到已有项目 ]       │
└──────────────────────────────────────────┘
```

"找到已有项目"触发自动扫描：遍历工作区目录，找所有包含 `.webnovel/state.json` 的子文件夹。

## 6. 安装 & 分发

### 6.1 PyInstaller 打包（短期）

```
.github/workflows/build-launcher.yml

触发: push tag v*
产出:
  - Webnovel-Writer-Setup-x64.exe  (Windows NSIS installer)
  - Webnovel-Writer.dmg            (macOS)
  - Webnovel-Writer.AppImage       (Linux)
```

打包内容：
- 嵌入式 Python 3.12
- .opencode/ 完整插件代码
- 所有 pip 依赖预装
- Electron 启动器

### 6.2 启动流程

```
用户双击 .exe
  → Electron Main Process 启动
  → 检查 Python 可用性（内置或系统）
  → 检查 .opencode/ 是否存在
  → 扫描工作区项目
  → 打开 BrowserWindow → 显示项目列表
```

## 7. 与现有系统的关系

| 现有组件 | 在新启动器中的角色 |
|---------|-----------------|
| `install.py` | 保留，供命令行用户和 CI 使用；启动器内置"安装可选模块"功能调用它 |
| `.opencode/dashboard/` | 前端 React 代码被启动器复用；FastAPI 后端作为子进程启动 |
| `.opencode/scripts/` | 所有 CLI 保持不变，启动器通过子进程调用 |
| `manifest.json` | 版本更新检测源 |
| `installer/` | Electron 打包时预装所有依赖，installer 模块不进入启动器 |

## 8. 技术选型

| 层 | 选择 | 理由 |
|---|------|------|
| 桌面壳 | Electron | 跨平台、复用现有 React 代码 |
| 前端 | React + TypeScript | 复用 Dashboard 技术栈 |
| 打包 | electron-builder | 主流、配置简单、NSIS/dmg/AppImage 三平台 |
| Main Process | TypeScript (+ ts-node) | 类型安全，与前端共享类型 |
| 依赖管理 | pnpm | 更快、磁盘友好 |
| 自举 (bootstrap) | PyInstaller | 单文件打包 Python+依赖 |

## 9. 自检

- [x] 无 TBD/TODO
- [x] IPC 遵循 contextBridge 规范
- [x] contextIsolation + sandbox 安全配置
- [x] 项目注册表与 state.json 同步策略明确
- [x] 子进程生命周期明确
- [x] 首次使用空状态处理
- [x] 与现有 install.py / Dashboard / CLI 的关系明确
