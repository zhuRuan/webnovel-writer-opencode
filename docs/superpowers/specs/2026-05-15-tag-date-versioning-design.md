# Tag + Date-Stamped Versioning Design

> **日期**: 2026-05-15
> **目标**: 版本号跟着 tag 走，tag 内多次推送以日期区分，安装脚本显示更新日志

## 概述

- **Git tag** 是版本号的唯一权威来源（手动操作，CI 不自动创建）
- **Tag 不变时** CI 自动生成日期标记版本（`tag-YYYYMMDD.HHMM`）
- **安装脚本** 区分大版本（tag 变更）和小版本（同 tag 内更新），展示不同级别的更新日志
- **Release Notes** 标题格式：`Webnovel Writer for OpenCode vX.Y.Z`

## 版本号规则

| 版本类型 | 格式 | 示例 | 触发 |
|---------|------|------|------|
| Tag 版本 | `v{MAJOR}.{MINOR}.{PATCH}` | `v2.8.0` | 手动 `git tag` |
| 日期版本 | `{tag}-{YYYYMMDD}.{HHMM}` | `v2.8.0-20260515.1430` | CI 每次 push 到 master |

## manifest.json 格式

```json
{
  "version": "v2.8.0-20260515.1430",
  "tag": "v2.8.0",
  "updated": "2026-05-15T14:30:00Z",
  "changelog": [
    {"hash": "abc1234", "type": "fix", "message": "CJK menu padding"},
    {"hash": "def5678", "type": "chore", "message": "remove manifest self-update"}
  ],
  "files": { ... }
}
```

| 字段 | 说明 |
|------|------|
| `version` | 完整版本号（含日期后缀） |
| `tag` | 最近 git tag，无 tag 时为空字符串 |
| `updated` | CI 生成时间 (ISO 8601 UTC) |
| `changelog` | 自上次 CI 以来的新提交（最多 50 条，倒序） |
| `files` | 不变，文件路径与 SHA256 |

## CI 工作流

### Job 1: `update-manifest` — 每次 push to master

触发条件：push 到 master 且 `.opencode/**` 文件变更（排除 `manifest.json` 和 `.github/**`）

```
1. checkout (含 tags, fetch-depth 0)
2. 读取最新 tag → TAG
3. 生成日期后缀 → YYYYMMDD.HHMM (UTC)
4. 版本号 = {TAG}-{date}（若 TAG 为空则用 "0.0.0"）
5. 读取上次 manifest.json 的 updated 时间
6. git log --since=<上次时间> --format="%h|%s" --no-merges
7. 解析为 changelog 数组 [{hash, type, message}]
8. 生成 manifest.json (version, tag, updated, changelog, files)
9. git commit manifest.json + push (skip ci)
```

**不创建 tag，不创建 Release。**

### Job 2: `release` — 仅在检测到新 tag 时触发

触发条件：push tag 匹配 `v*`

```
1. checkout (含 tags, fetch-depth 0)
2. 读取最新 tag → TAG
3. 读取上一个 tag → PREV_TAG
4. 生成 manifest.json (version = TAG, tag = TAG)
5. changelog = git log PREV_TAG..TAG --format="- %s (%h)" --no-merges
6. 创建 GitHub Release:
   - name: "Webnovel Writer for OpenCode {TAG}"
   - body: changelog
7. 更新 manifest.json 并 commit + push
```

## 安装脚本更新日志

### 版本判断逻辑

```
从 raw.githubusercontent.com 下载 manifest.json
本地版本: 读取 .opencode/version.json

if local.tag != remote.tag:
    → 大版本更新: 显示 "Webnovel Writer for OpenCode {remote.tag}"
    → changelog = remote.changelog (所有条目)
else:
    → 小版本更新: 显示 "{remote.version} (日期更新)"
    → changelog = remote.changelog (自上次安装以来的新条目)
```

### 显示示例

```
┌──────────────────────────────────────────┐
│  Webnovel Writer for OpenCode v2.9.0     │
│  大版本更新                               │
├──────────────────────────────────────────┤
│  - feat: add DOCX/PDF export             │
│  - feat: interactive install menu        │
│  - fix: review JSON corruption           │
│  ...                                     │
└──────────────────────────────────────────┘
```

### 代码位置

- `install.py` 的 `run_selected_action()` 中，在下载/安装前添加版本比较
- `_write_installed_version()` 改为写入完整数据结构（version, tag, updated）
- 新增 `_show_changelog()` 函数

## 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/manifest.yml` | 重写 | 两个 job：日常 manifest + tag release |
| `.opencode/scripts/gen_manifest.py` | 修改 | 支持 --changelog-file 参数 |
| `install.py` | 修改 | 添加版本比较和更新日志显示 |
| `.opencode/installer/update.py` | 修改 | version.json 格式变更 |
| `.opencode/installer/preflight.py` | 修改 | _write_installed_version 写入完整数据 |

## 自检

- [x] 无 TBD/TODO
- [x] version/tag/updated/changelog 字段所有环节一致
- [x] CI 绝不自动打 tag
- [x] 大/小版本判断逻辑明确
- [x] Release 标题格式确认
