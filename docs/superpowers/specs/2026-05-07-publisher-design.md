# Publisher Module Design

## Context

实现小说章节自动发布到国内主流小说平台。完全重写，不依赖旧 `webnovel-publish` 代码。采用模块化架构，平台适配器通过统一抽象接口接入，格式化独立于发布操作。

**隔离原则**：`publisher/` 目录自包含，对现有代码只加 2 行（webnovel.py 的命令注册 + dispatch）。

## Architecture

```
publisher/
  __init__.py          ← CLI 入口 + 平台注册表 + argparse
  base.py              ← 平台适配器抽象接口
  formatter.py         ← MD→平台格式转换，纯函数，无外部依赖
  browser.py           ← Playwright 生命周期管理
  adapters/
    fanqie.py          ← 番茄小说适配器
  config.py            ← 发布配置 + 上传进度追踪
```

### Integration Point

`webnovel.py` 仅加：

```python
# 注册
p_publish = sub.add_parser("publish", help="发布章节到小说平台")
p_publish.add_argument("args", nargs=argparse.REMAINDER)

# dispatch
if tool == "publish":
    raise SystemExit(_run_script("publisher/__init__.py", [*forward_args, *rest]))
```

完全相同于 export 模块的接入模式。不修改 `data_modules/`、`story-system`、`.webnovel/` 等任何现有代码。

### Data Flow

```
CLI 命令
  → __init__.py 解析参数、加载章节文件
    → formatter.py 转换格式（MD→平台所需格式）
    → browser.py 获取已认证的浏览器 page
    → adapter.upload_chapter(page, book_id, formatted_content)
      → config.py 记录上传进度
```

章节源文件由 CLI 层读取并传给 formatter。平台适配器只接收格式化后的文本内容，不直接访问项目文件系统。

## Module Specifications

### base.py — 抽象接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class BookMeta:
    title: str
    genre: str           # 平台分类标签
    synopsis: str        # 简介（50-200字）
    protagonist: str     # 主角名
    tags: list[str]      # 标签

@dataclass
class Chapter:
    index: int           # 章节序号
    title: str
    content: str         # 已格式化的正文
    volume_title: str = ""

@dataclass
class UploadResult:
    success: bool
    chapter_index: int
    message: str = ""
    url: str = ""

class BasePlatform(ABC):
    """平台适配器抽象接口"""

    name: str = ""              # "fanqie"
    display_name: str = ""      # "番茄小说"
    login_url: str = ""

    @abstractmethod
    async def setup_auth(self, page) -> bool:
        """引导用户完成登录，返回 True 表示登录成功"""
        ...

    @abstractmethod
    async def list_books(self, page) -> list[dict]:
        """获取该作者已有的书籍列表"""
        ...

    @abstractmethod
    async def create_book(self, page, meta: BookMeta) -> str:
        """创建新书，返回 book_id"""
        ...

    @abstractmethod
    async def upload_chapter(self, page, book_id: str, chapter: Chapter) -> UploadResult:
        """上传单章。优先尝试 API 直传，失败则降级到浏览器模拟"""
        ...
```

### browser.py — 浏览器管理

职责：启动/停止 Chromium、管理登录状态持久化。不提供高层操作封装（适配器直接用 Playwright API）。

```python
class Browser:
    """Playwright 浏览器单例"""

    def __init__(self, headless: bool = True, platform: str = ""):
        ...

    async def start(self) -> Page:
        """启动浏览器。优先从磁盘加载已保存的认证状态。
        Linux root 环境自动追加 --no-sandbox。"""
        ...

    async def save_auth_state(self):
        """保存当前认证状态到 ~/.webnovel-publish/auth/{platform}.json"""
        ...

    async def close(self):
        ...
```

认证状态存储路径：`~/.webnovel-publish/auth/{platform_name}.json`

跨平台注意事项：
- Windows/Linux/Mac 三平台统一使用 `pathlib.Path.home()` 解析路径
- Linux 下检测 `os.geteuid() == 0` 时自动追加 `--no-sandbox`
- headless 模式作为默认，`--headed` flag 可切换
- 所有文件读写显式使用 `encoding='utf-8'`

### formatter.py — 格式转换

纯函数模块。MD→各平台所需的目标格式。

```python
def to_plain_text(md: str) -> str:
    """Markdown → 纯文本（去标记、保留段落结构）"""
    ...

def to_html(md: str) -> str:
    """Markdown → 简单 HTML（用于支持富文本导入的平台）"""
    ...

def format_for_platform(md: str, platform: str, hints: dict | None = None) -> str:
    """平台感知格式化。hints 可覆盖默认行为（如缩进方式）。
    默认将 MD 转纯文本，段落间空一行，段首全角缩进两个字符。"""
    ...
```

默认输出格式：
- 段落间以空行分隔
- 段首缩进：全角空格 `　　`（中文网络小说标准）
- 章节标题：`第N章 标题` 单独一行
- 移除所有 Markdown 标记（`**粗体**` → 粗体，`*斜体*` → 斜体）
- 保留分割线（`---` → `***`）

### adapters/fanqie.py — 番茄小说

```python
class FanqieAdapter(BasePlatform):
    name = "fanqie"
    display_name = "番茄小说"
    login_url = "https://writer.kandian.com/"
```

上传流程：
1. 打开番茄作家后台 → 导航到目标书籍
2. 点击"新建章节" → 填写标题
3. 优先尝试找到内部 API 直传正文（监控网络请求、尝试 fetch POST）
4. API 不可用时降级：定位编辑器 textarea → 逐段粘贴内容 → 等待渲染
5. 选择发布模式（草稿/直接发布）→ 提交
6. 记录上传结果

重试策略：单章上传失败自动重试 2 次（间隔 3 秒），仍失败则标记并继续。

### config.py — 配置管理

```python
@dataclass
class PublishConfig:
    mode: str = "draft"        # draft | publish
    headless: bool = True
    retry_count: int = 2
    retry_delay: float = 3.0   # 秒
    chapter_gap: float = 5.0   # 章间间隔，避免触发反爬
    timeout: float = 30.0      # 单次操作超时

def load_upload_log(platform: str, book_id: str) -> set[int]:
    """读取已上传的章节序号集合"""
    ...

def save_upload_log(platform: str, book_id: str, uploaded: set[int]):
    """保存已上传章节序号"""
    ...
```

上传日志路径：`~/.webnovel-publish/upload_log/{platform}_{book_id}.json`

格式：
```json
{"uploaded": [1, 2, 3, 4, 5], "last_upload": "2026-05-07T15:30:00"}
```

### __init__.py — CLI 入口

命令结构：

```
webnovel.py publish <subcommand> [options]

子命令:
  setup-auth --platform <name>    引导登录指定平台
  list-books --platform <name>    列出已有书单
  create-book --platform <name>   创建新书（自动读项目信息）
  upload --platform <name>        上传章节
    --book-id <id>                书籍 ID
    --range 1-50                  章节范围
    --mode draft|publish          发布模式
```

平台注册表：
```python
REGISTRY: dict[str, type[BasePlatform]] = {
    "fanqie": FanqieAdapter,
}
```

## Failure Handling

| 场景 | 处理 | 阻断 |
|------|------|------|
| Playwright 未安装 | 提示安装命令后退出 | 阻断 |
| 认证状态过期 | 提示重新 setup-auth | 阻断 |
| 单章上传失败 | 重试 2 次 → 记录失败，继续下一章 | 否 |
| 连续 5 章失败 | 判定平台不可用，停止 | 阻断 |
| 浏览器崩溃 | 重启浏览器 → 恢复认证态 → 从断点继续 | 恢复 |
| API 端点变更 | 降级到浏览器模拟 → 记录警告 | 否 |
| 章节内容超平台限制 | 截断并警告（如番茄单章上限 20000 字） | 否 |

## Cross-Platform Compatibility

| 平台 | Playwright | Chromium | 特殊处理 |
|------|-----------|----------|---------|
| Windows 11 | ✅ | ✅ | 无 |
| macOS | ✅ | ✅ | 无 |
| Linux (desktop) | ✅ | ✅ | 无 |
| Linux (headless/root) | ✅ | ✅ | `--no-sandbox` |
| Linux (Docker) | ✅ | 需预装 | `--no-sandbox --disable-gpu` |

## Test Plan

- `test_formatter_to_plain_text` — MD 去标记正确性
- `test_formatter_to_html` — MD→HTML 正确性
- `test_formatter_chinese_paragraph` — 中文段落缩进
- `test_formatter_platform_hints` — 平台 hints 覆盖默认行为
- `test_config_upload_log_roundtrip` — 上传日志读写一致性
- `test_config_uploaded_chapters_dedup` — 已上传章节去重
- `test_base_interface` — 抽象接口方法完整性
- `test_fanqie_adapter_import` — 适配器可导入且继承正确
- `test_cli_args_parse` — CLI 参数解析正确
- Manual: Playwright 登录番茄 → 创建测试书 → 上传测试章节

## Files NOT Modified

- `data_modules/` — 不碰
- `.webnovel/` — 不碰
- `.story-system/` — 不碰
- 所有现有 skill — 不改（`webnovel-publish` SKILL.md 后续单独重写）
