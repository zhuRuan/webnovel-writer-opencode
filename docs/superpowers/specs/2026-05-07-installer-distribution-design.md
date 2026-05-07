# Installer & Distribution Design

> **状态**: 已确认  
> **日期**: 2026-05-07  
> **分发渠道**: GitHub 仓库（OpenCode 插件市场后续）

## 目标

将 webnovel-writer 以一键安装方式分发给用户，覆盖三种安装路径：

| 路径 | 说明 |
|------|------|
| `git clone` 仓库作为 OpenCode 工作区 | 即开即用，.opencode/ 已在仓库内 |
| `python install.py` 一键安装 | 下载 .opencode/ 到当前目录 |
| `python install.py --update` 增量更新 | 对比 manifest.json 只下载变更文件 |

## 核心约束

1. **不丢用户数据**：`.env`、用户配置永不覆盖
2. **不破坏运行中进程**：OpenCode 占用 `.opencode/` 时使用 staging + apply 两阶段
3. **中国大陆网络可用**：自动 GitHub 镜像切换
4. **跨平台**：Windows / macOS / Linux，行为一致
5. **安装幂等**：重复运行安全

---

## 架构

```
install.py (引导 ~120行)
  │ 内置: urllib 裸下载 + 镜像自动切换
  │ 不依赖数据层，纯标准库
  │
  ├─ 下载 GitHub repo zip → 解压出 .opencode/installer/
  ├─ 委托 installer/preflight.py
  │
  ▼
.opencode/installer/     ← repo zip 中提取，是 .opencode/ 的子集
  preflight.py           ← 编排主流程（首次安装）或 update.py（更新）
  check.py               ← 系统预检
  fetch.py               ← 下载管理
  update.py              ← 版本管理 (manifest.json diff)
  deps.py                ← 依赖安装
  ui.py                  ← 终端 UI
```

**首次安装**：从 repo zip 中直接提取完整 `.opencode/`，无需 staging。  
**更新**：从 repo zip 提取 `.opencode/` 到 `.opencode_staging/`，再决定直接替换或 `--apply`。  
installer 模块自身在 `.opencode/installer/` 下，随 repo zip 一起更新。

---

## 两阶段安装（Staging + Apply）

### 阶段 1：下载 & 准备

- 所有下载/构建输出到 `.opencode_staging/`
- 依赖直接安装（pip/npm 与文件锁无关）
- 检测 OpenCode 进程状态（仅告警，不阻断）

### 阶段 2：应用（install.py --apply）

- 再次检测 OpenCode 进程 → 仍在运行则拒绝执行
- `mv .opencode → .opencode_backup`
- `mv .opencode_staging → .opencode`
- `.env` 在工作区根目录（不在 .opencode/ 内），替换目录不会丢失，无需合并
- `rm -rf .opencode_backup`
- 任一步失败 → 回滚

### 全新安装

`.opencode/` 不存在 → 直接安装，无需 staging。

### 更新判断

| 条件 | 行为 |
|------|------|
| `.opencode/` 不存在 | 全新安装 |
| `.opencode/` 存在 + OpenCode 未运行 | 直接替换 |
| `.opencode/` 存在 + OpenCode 运行中 | staging + 提示 --apply |

---

## 跨平台进程检测

分层检测，按平台适配：

```
is_opencode_running()

  层1 [全平台] 进程名扫描:
    Windows: tasklist | findstr "OpenCode Code"
    Linux:   pgrep -f "opencode"（匹配命令行，不扫裸进程名）
    macOS:   ps aux | grep -i "OpenCode\|opencode"

  层2 [Windows] 文件锁检测:
    os.rename('.opencode', '.opencode_lock_test')
    成功 → 改回 → 返回 not_running
    失败 → 返回 locked (100% 确认占用)

  层3 [全平台] 端口检测:
    仅 dashboard: lsof -i :8765（可选辅助）
```

进程名配置：

```python
KNOWN_OPENCODE_PROCESSES = {
    "windows": ["OpenCode.exe", "Code.exe"],
    "linux":   [],  # 只用 pgrep -f opencode
    "darwin":  ["OpenCode", "Electron"],
}
```

---

## 镜像支持

```
连接 GitHub 直连
  │
  ├─ 成功 → 使用直连
  └─ 超时 5s → 切换镜像
                │
                ├─ ghproxy.com
                └─ mirror.ghproxy.com
```

`--mirror <URL>` 可指定自定义镜像。

---

## 增量更新机制

### manifest.json（存于 GitHub 仓库根目录）

```json
{
  "version": "v1.2.0",
  "files": {
    ".opencode/skills/webnovel-write/SKILL.md": {
      "sha256": "abc123...",
      "size": 5432
    },
    ".opencode/scripts/webnovel.py": {
      "sha256": "def456...",
      "size": 1024
    }
  }
}
```

### 更新流程

1. 下载最新 `manifest.json`
2. 对比本地 `version.json`（install.py 用户）或 `git describe --tags`（clone 用户）
3. 计算需要更新的文件列表（SHA256 不同）
4. 只下载变更文件，打包 zip 或逐个下载
5. 写入 staging 目录

### version.json（install.py 安装时写入，加入 .gitignore）

```json
{
  "version": "v1.2.0",
  "installed_at": "2026-05-07T10:30:00Z",
  "channel": "install.py"
}
```

clone 用户不写此文件，用 `git describe --tags` 获取版本。

### manifest.json 生成

由 GitHub Actions 在每次 release 时自动生成，遍历 `.opencode/` 下所有文件计算 SHA256。也提供本地生成脚本：

```bash
python .opencode/scripts/gen_manifest.py > manifest.json
```

### installer 模块自更新

installer 模块自身也在 `.opencode/installer/` 下，是 manifest.json 追踪的一部分。更新时先从旧版 installer 运行 update 逻辑，下载新版 installer 到 staging，--apply 后下次运行即为新版。

---

## 依赖安装

### 核心依赖

```
pip install -r .opencode/scripts/requirements.txt
```

### Dashboard 依赖

```
pip install -r .opencode/dashboard/requirements.txt
```

### 发布功能（可选）

- playwright + chromium 浏览器
- `--skip-playwright` 跳过

### 虚拟环境

- `--venv` 参数自动创建 `.venv/` 并激活
- 冲突检测：安装前检查已有包版本，冲突则警告

---

## 安装后验证

安装完成后自动运行：

```
python -X utf8 .opencode/scripts/webnovel.py preflight
```

验证项：
- Python 版本 >= 3.10
- 核心依赖可导入（aiohttp, pydantic, filelock）
- .opencode/ 目录完整性
- 输出诊断报告

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `install.py` | 重写 | 轻量引导 + staging/apply 支持 |
| `.opencode/installer/__init__.py` | 创建 | 模块入口 |
| `.opencode/installer/preflight.py` | 创建 | 编排主流程 |
| `.opencode/installer/check.py` | 创建 | 系统预检 + 进程检测 |
| `.opencode/installer/fetch.py` | 创建 | 下载管理 |
| `.opencode/installer/update.py` | 创建 | 版本管理 |
| `.opencode/installer/deps.py` | 创建 | 依赖安装 |
| `.opencode/installer/ui.py` | 创建 | 终端 UI |
| `.opencode/version.json` | 创建 | 版本记录（加入 .gitignore） |
| `manifest.json` | 创建 | 文件清单 |
| `.opencode/scripts/gen_manifest.py` | 创建 | manifest.json 生成脚本 |
| `INSTALL.md` | 更新 | skill 定义适配新流程 |
| `README.md` | 更新 | 安装说明 |
| `.gitignore` | 更新 | 加 version.json |
| `.opencode/scripts/tests/test_installer.py` | 创建 | 安装器测试 |

---

## 充分性闸门

- [ ] `python install.py` 全新安装成功（跨平台）
- [ ] `python install.py --update` 增量更新成功
- [ ] OpenCode 运行中执行更新 → staging 模式 + 提示 --apply
- [ ] `--apply` 正确替换目录 + 保留用户配置
- [ ] GitHub 不可达时自动切镜像
- [ ] 安装后 `preflight` 通过
- [ ] clone 用户 `git pull` 正常（不受 installer 影响）
- [ ] 重复安装幂等（.env 不丢、依赖不重装）
- [ ] 所有测试通过
