---
name: webnovel-publish
description: 将小说章节自动发布到国内主流小说平台（番茄等）。触发条件："发布小说"、"发布章节"、"上传到番茄"、"自动发布"。
compatibility: opencode
allowed-tools: Read Write Edit Grep Bash Agent
---

# 小说自动发布

## 目标

将已完成小说章节自动发布到目标平台。首次需手动扫码登录，后续全自动运行。

## 支持平台

| 平台 | 标识 | 认证方式 |
|------|------|---------|
| 番茄小说 | fanqie | 扫码登录（一次） |

## 环境设置

```bash
export WORKSPACE_ROOT="${PWD}"
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "❌ PROJECT_ROOT 解析失败"; exit 1; }

# 检查 Playwright
python -c "import playwright" 2>/dev/null || { echo "请先安装: pip install playwright && playwright install chromium"; exit 1; }
```

## 执行流程

### Step 1：首次配置（登录）

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish setup-auth --platform fanqie
```

会弹出浏览器窗口，扫码登录后自动保存认证状态。后续无需重复。

### Step 2：查看书单

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish list-books --platform fanqie
```

### Step 3：创建新书

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish create-book \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"
```

自动从项目信息读取书名、题材、简介、主角名。

### Step 4：上传章节

```bash
# 上传全部章节（草稿模式）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --book-id <book_id> \
  --mode draft \
  --project-root "${PROJECT_ROOT}"

# 指定范围
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --book-id <book_id> \
  --range 1-50 \
  --mode publish \
  --project-root "${PROJECT_ROOT}"
```

已上传章节自动跳过，支持断点续传。

## 充分性闸门

- [ ] Playwright 已安装且 Chromium 可用
- [ ] 平台认证状态有效
- [ ] 目标书籍 book_id 已知
- [ ] 上传日志一致（不会重复上传）

## 常见问题

| 问题 | 解决 |
|------|------|
| 登录超时 | 重新运行 setup-auth，3 分钟内扫码 |
| 认证过期 | 删除 ~/.webnovel-publish/auth/ 重新登录 |
| 浏览器不弹 | 检查显示器配置 |
| Playwright 未安装 | pip install playwright && playwright install chromium |
