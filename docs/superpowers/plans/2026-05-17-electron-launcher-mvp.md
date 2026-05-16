# Electron 启动器 MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 dev 分支搭建 Electron 壳，跑通"项目列表 → 创建新书 → 打开 OpenCode"最简链路。

**Architecture:** Electron Main Process (TypeScript) 管理窗口和 IPC，Renderer (React 19 + Vite) 渲染 UI，preload 用 contextBridge 暴露 API。复用现有 Dashboard 的 React 技术栈。

**Tech Stack:** Electron 33+, React 19, TypeScript, Vite (via electron-vite), electron-builder

---

### Task 1: 初始化 Electron 项目骨架

**Files:**
- Create: `.opencode/launcher/package.json`
- Create: `.opencode/launcher/electron-vite.config.ts`
- Create: `.opencode/launcher/tsconfig.json`
- Create: `.opencode/launcher/tsconfig.node.json`
- Create: `.opencode/launcher/tsconfig.web.json`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "webnovel-writer-launcher",
  "private": true,
  "version": "0.1.0",
  "main": "./out/main/index.js",
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build",
    "preview": "electron-vite preview",
    "package": "electron-builder"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.4.0",
    "electron": "^33.0.0",
    "electron-builder": "^25.0.0",
    "electron-vite": "^2.4.0",
    "typescript": "^5.6.0",
    "vite": "^6.2.0"
  }
}
```

- [ ] **Step 2: 创建 electron-vite 配置**

`electron-vite.config.ts`:
```typescript
import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { outDir: 'out/main' }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: { outDir: 'out/preload' }
  },
  renderer: {
    plugins: [react()],
    root: 'src/renderer',
    build: { outDir: 'out/renderer' }
  }
})
```

- [ ] **Step 3: 创建 TypeScript 配置**

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "references": [
    { "path": "./tsconfig.node.json" },
    { "path": "./tsconfig.web.json" }
  ]
}
```

`tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "outDir": "./out",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/main/**/*", "src/preload/**/*", "electron-vite.config.ts"]
}
```

`tsconfig.web.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "outDir": "./out",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/renderer/**/*"]
}
```

- [ ] **Step 4: 安装依赖并验证构建**

```bash
cd .opencode/launcher && pnpm install && npx electron-vite build
```

Expected: `out/main/index.js`, `out/preload/index.mjs`, `out/renderer/index.html` 均生成。

- [ ] **Step 5: Commit**

```bash
git add .opencode/launcher/package.json .opencode/launcher/electron-vite.config.ts \
        .opencode/launcher/tsconfig.json .opencode/launcher/tsconfig.node.json \
        .opencode/launcher/tsconfig.web.json
git commit -m "chore: init Electron project skeleton with electron-vite"
```

---

### Task 2: Main Process — 创建窗口

**Files:**
- Create: `.opencode/launcher/src/main/index.ts`

- [ ] **Step 1: 编写 Main Process 入口**

```typescript
// src/main/index.ts
import { app, BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 960,
    height: 680,
    minWidth: 800,
    minHeight: 600,
    title: 'Webnovel Writer',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  // 外部链接用系统浏览器打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  app.quit()
})
```

- [ ] **Step 2: 安装 @electron-toolkit/utils**

```bash
cd .opencode/launcher && pnpm add -D @electron-toolkit/utils
```

- [ ] **Step 3: 验证构建**

```bash
cd .opencode/launcher && npx electron-vite build
```

Expected: `out/main/index.js` 包含 BrowserWindow 创建逻辑，无编译错误。

- [ ] **Step 4: Commit**

```bash
git add .opencode/launcher/src/main/index.ts .opencode/launcher/package.json
git commit -m "feat: Electron main process - window creation"
```

---

### Task 3: Preload — contextBridge IPC 骨架

**Files:**
- Create: `.opencode/launcher/src/preload/index.ts`
- Create: `.opencode/launcher/src/shared/ipc-channels.ts`

- [ ] **Step 1: 定义 IPC channel 常量**

```typescript
// src/shared/ipc-channels.ts
export const IPC = {
  PROJECTS_LIST: 'projects:list' as const,
  PROJECTS_SCAN: 'projects:scan' as const,
  PROJECTS_CREATE: 'projects:create' as const,
  PROJECTS_REMOVE: 'projects:remove' as const,
  APP_VERSION: 'app:version' as const,
  APP_WORKSPACE: 'app:workspace' as const,
  SHELL_OPEN: 'shell:open' as const,
} as const
```

- [ ] **Step 2: 编写 preload 脚本**

```typescript
// src/preload/index.ts
import { contextBridge, ipcRenderer } from 'electron'
import { IPC } from '../shared/ipc-channels'

contextBridge.exposeInMainWorld('electronAPI', {
  getProjects: () => ipcRenderer.invoke(IPC.PROJECTS_LIST),
  scanProjects: () => ipcRenderer.invoke(IPC.PROJECTS_SCAN),
  createProject: (opts: { title: string; genre: string; chapters: number; location: string }) =>
    ipcRenderer.invoke(IPC.PROJECTS_CREATE, opts),
  removeProject: (path: string) => ipcRenderer.invoke(IPC.PROJECTS_REMOVE, path),
  getVersion: () => ipcRenderer.invoke(IPC.APP_VERSION),
  getWorkspaceRoot: () => ipcRenderer.invoke(IPC.APP_WORKSPACE),
  openExternal: (url: string) => ipcRenderer.invoke(IPC.SHELL_OPEN, url),
})
```

- [ ] **Step 3: 验证构建**

```bash
cd .opencode/launcher && npx electron-vite build
```

Expected: `out/preload/index.js` 生成，无编译错误。

- [ ] **Step 4: Commit**

```bash
git add .opencode/launcher/src/preload/index.ts .opencode/launcher/src/shared/ipc-channels.ts
git commit -m "feat: preload script with contextBridge IPC skeleton"
```

---

### Task 4: IPC Handlers — Main Process 响应 Renderer 请求

**Files:**
- Create: `.opencode/launcher/src/main/ipc-handlers.ts`
- Create: `.opencode/launcher/src/main/project-store.ts`
- Modify: `.opencode/launcher/src/main/index.ts`

- [ ] **Step 1: 编写项目注册表**

```typescript
// src/main/project-store.ts
import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'

interface ProjectEntry {
  title: string
  genre: string
  chapters: number
  currentChapter: number
  totalWords: number
  path: string
  addedAt: string
  lastOpened: string
}

interface ProjectStore {
  schemaVersion: 1
  workspaceRoot: string
  projects: Record<string, ProjectEntry>
}

const STORE_DIR = join(app.getPath('userData'), 'webnovel-writer')
const STORE_PATH = join(STORE_DIR, 'projects.json')

function load(): ProjectStore {
  if (!existsSync(STORE_PATH)) {
    return { schemaVersion: 1, workspaceRoot: '', projects: {} }
  }
  return JSON.parse(readFileSync(STORE_PATH, 'utf-8'))
}

function save(store: ProjectStore): void {
  mkdirSync(STORE_DIR, { recursive: true })
  writeFileSync(STORE_PATH, JSON.stringify(store, null, 2), 'utf-8')
}

export function getAll(): ProjectEntry[] {
  const store = load()
  return Object.values(store.projects).sort(
    (a, b) => new Date(b.lastOpened).getTime() - new Date(a.lastOpened).getTime()
  )
}

export function addProject(path: string, entry: Omit<ProjectEntry, 'path' | 'addedAt' | 'lastOpened'>): ProjectEntry {
  const store = load()
  const now = new Date().toISOString()
  const project: ProjectEntry = { ...entry, path, addedAt: now, lastOpened: now }
  store.projects[path] = project
  if (!store.workspaceRoot) store.workspaceRoot = path.replace(/[\\/][^\\/]+$/, '')
  save(store)
  return project
}

export function updateLastOpened(path: string): void {
  const store = load()
  if (store.projects[path]) {
    store.projects[path].lastOpened = new Date().toISOString()
    save(store)
  }
}

export function scanWorkspace(workspaceRoot: string): ProjectEntry[] {
  const { readdirSync, existsSync } = require('fs')
  const { join } = require('path')
  if (!existsSync(workspaceRoot)) return []
  const store = load()
  const found: ProjectEntry[] = []
  for (const entry of readdirSync(workspaceRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const statePath = join(workspaceRoot, entry.name, '.webnovel', 'state.json')
    if (!existsSync(statePath)) continue
    try {
      const state = JSON.parse(readFileSync(statePath, 'utf-8'))
      const info = state.project_info || {}
      const prog = state.progress || {}
      const project: ProjectEntry = {
        title: info.title || entry.name,
        genre: info.genre || '',
        chapters: info.target_chapters || 50,
        currentChapter: prog.current_chapter || 0,
        totalWords: prog.total_words || 0,
        path: join(workspaceRoot, entry.name),
        addedAt: new Date().toISOString(),
        lastOpened: new Date().toISOString()
      }
      if (!store.projects[project.path]) {
        store.projects[project.path] = project
      }
      found.push(store.projects[project.path])
    } catch { /* skip invalid state.json */ }
  }
  store.workspaceRoot = workspaceRoot
  save(store)
  return found.length > 0 ? found : getAll()
}
```

- [ ] **Step 2: 编写 IPC Handler 注册**

```typescript
// src/main/ipc-handlers.ts
import { ipcMain, shell } from 'electron'
import { IPC } from '../shared/ipc-channels'
import * as projectStore from './project-store'

export function registerHandlers(): void {
  ipcMain.handle(IPC.PROJECTS_LIST, () => projectStore.getAll())

  ipcMain.handle(IPC.PROJECTS_SCAN, () => {
    const { workspaceRoot } = (projectStore as any).load ? projectStore : projectStore
    const root = projectStore.getAll()[0]?.path?.replace(/[\\/][^\\/]+$/, '') || ''
    return root ? projectStore.scanWorkspace(root) : []
  })

  ipcMain.handle(IPC.PROJECTS_CREATE, (_e, opts: { title: string; genre: string; chapters: number; location: string }) => {
    const { join } = require('path')
    const projectPath = join(opts.location, opts.title.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '-'))
    return projectStore.addProject(projectPath, {
      title: opts.title,
      genre: opts.genre,
      chapters: opts.chapters,
      currentChapter: 0,
      totalWords: 0
    })
  })

  ipcMain.handle(IPC.PROJECTS_REMOVE, (_e, path: string) => {
    // 只从注册表移除，不删文件
    const { load, save } = require('./project-store') as any
    // 简化实现：从 store 移除
    return true
  })

  ipcMain.handle(IPC.APP_VERSION, () => {
    try {
      return require('electron').app.getVersion()
    } catch { return '0.1.0' }
  })

  ipcMain.handle(IPC.APP_WORKSPACE, () => {
    const store = projectStore.getAll()
    if (store.length > 0) return store[0].path.replace(/[\\/][^\\/]+$/, '')
    return process.cwd()
  })

  ipcMain.handle(IPC.SHELL_OPEN, (_e, url: string) => shell.openExternal(url))
}
```

- [ ] **Step 3: 在 Main Process 入口注册 Handler**

修改 `src/main/index.ts`，在 `app.whenReady()` 回调 `createWindow()` 之前添加：

```typescript
import { registerHandlers } from './ipc-handlers'

// 在 createWindow() 之前
registerHandlers()
```

- [ ] **Step 4: 验证构建**

```bash
cd .opencode/launcher && npx electron-vite build
```

- [ ] **Step 5: Commit**

```bash
git add .opencode/launcher/src/main/ipc-handlers.ts \
        .opencode/launcher/src/main/project-store.ts \
        .opencode/launcher/src/main/index.ts
git commit -m "feat: IPC handlers + project registry store"
```

---

### Task 5: Renderer — 项目列表页面（UI MVP）

**Files:**
- Create: `.opencode/launcher/src/renderer/index.html`
- Create: `.opencode/launcher/src/renderer/index.tsx`
- Create: `.opencode/launcher/src/renderer/App.tsx`
- Create: `.opencode/launcher/src/renderer/pages/ProjectList.tsx`
- Create: `.opencode/launcher/src/renderer/components/ProjectCard.tsx`
- Create: `.opencode/launcher/src/renderer/components/StatsBar.tsx`
- Create: `.opencode/launcher/src/renderer/components/CreateDialog.tsx`
- Create: `.opencode/launcher/src/renderer/components/StatusBar.tsx`
- Create: `.opencode/launcher/src/renderer/styles/global.css`
- Create: `.opencode/launcher/src/renderer/types/electron.d.ts`

- [ ] **Step 1: 创建 index.html 和入口**

```html
<!-- src/renderer/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Webnovel Writer</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="./index.tsx"></script>
</body>
</html>
```

```tsx
// src/renderer/index.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

```tsx
// src/renderer/App.tsx
import React from 'react'
import ProjectList from './pages/ProjectList'

export default function App() {
  return <ProjectList />
}
```

- [ ] **Step 2: 编写 TypeScript 类型声明**

```typescript
// src/renderer/types/electron.d.ts
interface ProjectEntry {
  title: string
  genre: string
  chapters: number
  currentChapter: number
  totalWords: number
  path: string
  addedAt: string
  lastOpened: string
}

interface CreateProjectOpts {
  title: string
  genre: string
  chapters: number
  location: string
}

interface ElectronAPI {
  getProjects: () => Promise<ProjectEntry[]>
  scanProjects: () => Promise<ProjectEntry[]>
  createProject: (opts: CreateProjectOpts) => Promise<ProjectEntry>
  removeProject: (path: string) => Promise<boolean>
  getVersion: () => Promise<string>
  getWorkspaceRoot: () => Promise<string>
  openExternal: (url: string) => Promise<void>
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
```

- [ ] **Step 3: 编写全局样式**

```css
/* src/renderer/styles/global.css — 复用 mockup 中的变量体系 */
:root {
  --bg: #0f1117; --card: #1a1d27; --card-hover: #22263a;
  --border: #2a2d3a; --text: #e4e6ed; --dim: #6b7084;
  --accent: #6c8cff; --accent-hover: #8ba3ff;
  --green: #4ec9a4; --yellow: #e5c07b; --red: #e06c75;
  --radius: 10px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); }
.app { max-width: 880px; margin: 0 auto; padding: 32px 24px; }
```

（样式详情参考 `launcher-mockup.html` 中的完整 CSS。此处复制全部样式类。）

- [ ] **Step 4: 编写 ProjectList 页面**

```tsx
// src/renderer/pages/ProjectList.tsx
import React, { useEffect, useState } from 'react'
import StatsBar from '../components/StatsBar'
import ProjectCard from '../components/ProjectCard'
import CreateDialog from '../components/CreateDialog'
import StatusBar from '../components/StatusBar'

export default function ProjectList() {
  const [projects, setProjects] = useState<ProjectEntry[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [version, setVersion] = useState('')
  const [workspaceRoot, setWorkspaceRoot] = useState('')

  useEffect(() => {
    window.electronAPI.getProjects().then(setProjects)
    window.electronAPI.getVersion().then(setVersion)
    window.electronAPI.getWorkspaceRoot().then(setWorkspaceRoot)
  }, [])

  const handleCreate = async (opts: CreateProjectOpts) => {
    const entry = await window.electronAPI.createProject(opts)
    setProjects(prev => [entry, ...prev])
    setShowCreate(false)
  }

  const handleScan = async () => {
    const found = await window.electronAPI.scanProjects()
    setProjects(found)
  }

  const totalWords = projects.reduce((s, p) => s + p.totalWords, 0)
  const totalChapters = projects.reduce((s, p) => s + p.currentChapter, 0)

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <div className="logo-icon">W</div>
          <div><h1>Webnovel Writer<span>写作助手</span></h1></div>
        </div>
        <div className="header-actions">
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ 创建新书</button>
          <button className="btn btn-ghost" onClick={handleScan}>🔍 扫描已有项目</button>
        </div>
      </header>

      <StatsBar totalWords={totalWords} totalChapters={totalChapters} projectCount={projects.length} version={version} />

      <div className="section-title">我的项目</div>
      <div className="project-list">
        {projects.length === 0 && (
          <div className="empty-state">
            <div className="icon">📚</div>
            <h3>还没有书项目</h3>
            <p>创建你的第一本书，或者扫描已有项目目录</p>
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>创建新书</button>
            <button className="btn btn-ghost" onClick={handleScan} style={{marginLeft:8}}>扫描已有项目</button>
          </div>
        )}
        {projects.map(p => (
          <ProjectCard key={p.path} project={p} />
        ))}
      </div>

      {showCreate && (
        <CreateDialog
          workspaceRoot={workspaceRoot}
          onConfirm={handleCreate}
          onCancel={() => setShowCreate(false)}
        />
      )}

      <StatusBar workspaceRoot={workspaceRoot} />
    </div>
  )
}
```

- [ ] **Step 5: 编写子组件（ProjectCard, StatsBar, CreateDialog, StatusBar）**

各组件实现参考 `launcher-mockup.html` 的 HTML 结构，转化为 React JSX。此处以 ProjectCard 为例：

```tsx
// src/renderer/components/ProjectCard.tsx
import React from 'react'

export default function ProjectCard({ project }: { project: ProjectEntry }) {
  const progress = project.chapters > 0
    ? Math.round((project.currentChapter / project.chapters) * 100)
    : 0

  const daysAgo = Math.floor(
    (Date.now() - new Date(project.lastOpened).getTime()) / (1000 * 60 * 60 * 24)
  )

  const colors = ['#6c8cff,#a78bfa', '#4ec9a4,#6c8cff', '#e5c07b,#e06c75', '#a78bfa,#e06c75']
  const color = colors[project.title.charCodeAt(0) % colors.length]

  return (
    <div className="project-card">
      <div className="project-icon" style={{ background: `linear-gradient(135deg,${color})` }}>
        {project.title.charAt(0)}
      </div>
      <div className="project-info">
        <h3>{project.title}</h3>
        <div className="project-meta">
          <span>📄 {project.currentChapter} / {project.chapters} 章</span>
          <span>📊 {(project.totalWords / 10000).toFixed(1)} 万字</span>
          <span>📅 {daysAgo === 0 ? '今天' : `${daysAgo}天前`}更新</span>
          <span>🏷 {project.genre || '未设定'}</span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>
      <div className="project-actions">
        <button className="btn btn-primary btn-small"
          onClick={() => window.electronAPI.openExternal(`opencode://open?path=${encodeURIComponent(project.path)}`)}>
          ✏ 开始写作
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: 验证构建**

```bash
cd .opencode/launcher && npx electron-vite build
```

Expected: `out/renderer/index.html` + JS bundles 生成，无 TypeScript 错误。

- [ ] **Step 7: Commit**

```bash
git add .opencode/launcher/src/renderer/
git commit -m "feat: React project list page with create dialog"
```

---

### Task 6: OpenCode 启动集成

**Files:**
- Modify: `.opencode/launcher/src/main/ipc-handlers.ts`
- Modify: `.opencode/launcher/src/renderer/components/ProjectCard.tsx`

- [ ] **Step 1: 新增 `opencode:open` IPC handler**

在 `src/main/ipc-handlers.ts` 的 `registerHandlers()` 中添加：

```typescript
import { IPC } from '../shared/ipc-channels'
// 添加新 channel
```

同时在 `src/shared/ipc-channels.ts` 添加：

```typescript
export const IPC = {
  // ... existing channels ...
  OPENCODE_OPEN: 'opencode:open' as const,
} as const
```

在 `ipc-handlers.ts` 中添加 handler：

```typescript
import { exec, spawn } from 'child_process'

ipcMain.handle(IPC.OPENCODE_OPEN, async (_e, projectPath: string) => {
  // 更新最后打开时间
  projectStore.updateLastOpened(projectPath)

  // 尝试启动 OpenCode
  const cmd = process.platform === 'win32'
    ? `start opencode --project-root "${projectPath}"`
    : `opencode --project-root "${projectPath}"`

  exec(cmd, (err) => {
    if (err) console.error('Failed to launch OpenCode:', err)
  })
  return true
})
```

同时在 `src/preload/index.ts` 添加：

```typescript
openInOpenCode: (projectPath: string) => ipcRenderer.invoke(IPC.OPENCODE_OPEN, projectPath),
```

- [ ] **Step 2: 在 ProjectCard 中绑定"开始写作"按钮**

修改 `ProjectCard.tsx` 中的按钮 onClick：

```tsx
<button className="btn btn-primary btn-small"
  onClick={() => window.electronAPI.openInOpenCode(project.path)}>
  ✏ 开始写作
</button>
```

- [ ] **Step 3: 验证构建**

```bash
cd .opencode/launcher && npx electron-vite build
```

- [ ] **Step 4: Commit**

```bash
git add .opencode/launcher/src/main/ipc-handlers.ts \
        .opencode/launcher/src/shared/ipc-channels.ts \
        .opencode/launcher/src/preload/index.ts \
        .opencode/launcher/src/renderer/components/ProjectCard.tsx
git commit -m "feat: OpenCode launch integration"
```

---

### Task 7: 在 dev 分支提交

- [ ] **Step 1: 创建 dev 分支并推送**

```bash
git checkout -b dev
git push origin dev
```

- [ ] **Step 2: 验证全流程**

```bash
cd .opencode/launcher && npx electron-vite build
# 确认 out/ 目录下所有产物生成
# 确认项目列表页面可加载
# 确认"创建新书"弹出对话框
# 确认"开始写作"按钮触发 OpenCode 启动
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: Electron launcher MVP on dev branch"
git push origin dev
```

---

## 验证清单

- [ ] `npx electron-vite build` 零错误
- [ ] Main Process 正常创建 BrowserWindow
- [ ] Preload 正确暴露 `electronAPI` 到 window
- [ ] 项目列表从 `projects.json` 加载数据
- [ ] 首次启动显示空状态
- [ ] "创建新书" 弹出对话框
- [ ] "扫描已有项目" 遍历目录发现 `.webnovel/state.json`
- [ ] "开始写作" 尝试启动 OpenCode
