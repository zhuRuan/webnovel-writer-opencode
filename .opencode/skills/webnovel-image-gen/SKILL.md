---
name: webnovel-image-gen
description: 使用 ModelScope Qwen-Image 生成小说封面和角色图片。立即使用此 skill 当用户说：生成图片、生成封面、角色图、小说封面、人物画像。无论是单个角色还是批量从设定集扫描，都使用此 skill。
allowed-tools: Read Write Edit Bash Task
---

# 图片生成

## 快速开始

```bash
# 交互式图片生成
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg

# 命令行生成
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg gencover --novel "小说名" --desc "描述"
```

## 目标

使用 ModelScope API 生成小说相关图片：
- 小说封面
- 角色头像/全身像
- 自动从设定集扫描识别角色

## 环境设置

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="$(cd "$(dirname "$0")/../../.opencode/scripts" && pwd)"

# 获取项目根目录
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where
export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## .env 配置

在项目根目录 `.env` 中配置：

```env
# Image Generation (ModelScope)
IMAGE_BASE_URL=https://api-inference.modelscope.cn/v1
IMAGE_MODEL=Qwen/Qwen-Image-2512
IMAGE_API_KEY=your_modelscope_sdk_token
IMAGE_SIZE=1:1
```

**获取 API Key**：
1. 访问 https://modelscope.cn/
2. 注册/登录账号
3. 进入"我的_access_token"创建 Token
4. 填入 `IMAGE_API_KEY`

## 执行流程

### Step 1：生成小说封面

自动从项目文件读取信息生成封面：
- `大纲/总纲.md` - 故事一句话、题材
- `设定集/世界观.md` - 世界观、场景
- `设定集/主角卡.md` - 核心标签

```bash
# 自动读取（推荐）
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg gencover

# 手动指定
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg gencover \
  --novel "末世修仙" \
  --desc "普通大学生在末日中获得修仙传承"
```

参数说明：
| 参数 | 说明 | 示例 |
|------|------|------|
| `--novel` | 小说标题（可选） | "末世修仙" |
| `--desc` | 小说描述（可选） | "大学生修仙末世求生" |
| `--size` | 图片尺寸，默认 1:1 | `16:9`, `1:1` |

### Step 2：生成单个角色图片

```bash
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg genchar \
  --name "陈默" \
  --desc "19岁大学生，谨慎、孤独、身穿破旧运动服"
```

参数说明：
| 参数 | 说明 | 示例 |
|------|------|------|
| `--name` | 角色名 | "陈默" |
| `--desc` | 角色描述 | "白衣少年，面容坚毅" |
| `--size` | 图片尺寸，默认 1:1 | `1:1`, `9:16` |

### Step 3：批量生成角色图（从设定集）

扫描设定集目录，自动识别角色文件并生成图片：

```bash
python .opencode/scripts/webnovel.py --project-root "${PROJECT_ROOT}" genimg genchars \
  --dir 设定集 \
  --max 20
```

参数说明：
| 参数 | 说明 | 示例 |
|------|------|------|
| `--dir` | 设定集目录 | `设定集`, `设定集/角色库` |
| `--file` | 单个角色文件 | `设定集/主角卡.md` |
| `--max` | 最大生成数量 | 默认 20 |
| `--size` | 图片尺寸，默认 1:1 | `1:1`, `9:16` |

## 角色识别规则

自动扫描识别以下文件：

| 文件/目录 | 示例 | 说明 |
|-----------|------|------|
| `主角卡.md` | 陈默 | 从"姓名："字段提取 |
| `女主卡.md` | 苏雨 | 从"姓名："字段提取 |
| `反派设计.md` | 反派角色 | 从"名称："字段提取 |
| `角色库/**/*.md` | 林晓、老王 | 次要角色和反派角色 |

**跳过目录**：
- `物品库/` - 物品设定
- `其他设定/` - 地点设定
- `力量体系.md` - 力量体系
- `世界观.md` - 世界观

## 输出位置

生成图片保存到：
- 封面：`{PROJECT_ROOT}/图片/封面/`
- 角色：`{PROJECT_ROOT}/图片/角色/`

## 充分性闸门

完成前必须验证：

- [ ] `.env` 中 `IMAGE_API_KEY` 已配置
- [ ] 命令返回码为 0
- [ ] 图片文件已生成在 `图片/` 目录

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 404 page not found | API URL 错误 | 使用 `https://api-inference.modelscope.cn/v1` |
| 401 Unauthorized | API Key 错误 | 检查 `.env` 中的 `IMAGE_API_KEY` |
| No characters found | 设定集目录无角色文件 | 检查文件是否在正确路径 |
| Unsupported size | 尺寸不支持 | 使用 `1:1`, `16:9`, `9:16` 等 |

## 依赖

- Python 3.10+
- `aiohttp`（已安装）
- `pyyaml`（可选，仅 YAML 格式需要）

## 图片尺寸参考

| 比例 | 尺寸 | 适用场景 |
|------|------|----------|
| 1:1 | 1328x1328 | 方形，默认值 |
| 16:9 | 1664x928 | 横向封面 |
| 9:16 | 928x1664 | 竖向角色全身像 |
| 4:3 | 1472x1104 | 横向 |
| 3:4 | 1104x1472 | 竖向 |
| 3:2 | 1584x1056 | 横向 |
| 2:3 | 1056x1584 | 竖向 |

**使用示例**：
```bash
# 使用比例格式
python .opencode/scripts/webnovel.py genimg gencover --novel "小说" --desc "描述" --size 16:9

# 或使用像素格式
python .opencode/scripts/webnovel.py genimg gencover --novel "小说" --desc "描述" --size 1664x928
```