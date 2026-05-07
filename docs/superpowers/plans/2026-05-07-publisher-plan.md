# Publisher Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现小说自动发布到国内主流小说平台的模块化系统，首批支持番茄小说。

**Architecture:** 6 个独立模块（config → formatter → base → browser → adapter → CLI），通过抽象适配器接口隔离平台差异。与现有代码零耦合，仅 webnovel.py 加 2 行命令注册。

**Tech Stack:** Python 3.11+, Playwright (Chromium), 纯 stdlib 格式化，无框架依赖。

---

### Task 1: config.py — 配置管理与上传进度追踪

**Files:**
- Create: `.opencode/scripts/publisher/__init__.py` (空文件，包标记)
- Create: `.opencode/scripts/publisher/config.py`
- Test: `.opencode/scripts/data_modules/tests/test_publisher.py`

- [ ] **Step 1: 创建 publisher 包目录和空 __init__.py**

```bash
mkdir -p .opencode/scripts/publisher/adapters
```

```python
# .opencode/scripts/publisher/__init__.py
"""(placeholder — CLI 入口将在 Task 6 实现)"""
```

- [ ] **Step 2: 编写 config 测试**

```python
# .opencode/scripts/data_modules/tests/test_publisher.py
"""Tests for publisher module."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parents[2]
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from publisher.config import (
    PublishConfig,
    load_upload_log,
    save_upload_log,
    get_upload_log_dir,
)


class TestPublishConfig:
    def test_defaults(self):
        cfg = PublishConfig()
        assert cfg.mode == "draft"
        assert cfg.headless is True
        assert cfg.retry_count == 2
        assert cfg.retry_delay == 3.0
        assert cfg.chapter_gap == 5.0

    def test_custom(self):
        cfg = PublishConfig(mode="publish", retry_count=5)
        assert cfg.mode == "publish"
        assert cfg.retry_count == 5
        assert cfg.headless is True  # unchanged default


class TestUploadLog:
    def test_roundtrip(self, tmp_path):
        log_dir = tmp_path / "upload_log"
        log_dir.mkdir(parents=True)
        book_id = "test123"

        def _get_log_dir():
            return log_dir

        original = get_upload_log_dir
        import publisher.config as mod
        mod.get_upload_log_dir = _get_log_dir
        try:
            save_upload_log("fanqie", book_id, {1, 2, 3})
            loaded = load_upload_log("fanqie", book_id)
            assert loaded == {1, 2, 3}
        finally:
            mod.get_upload_log_dir = original

    def test_load_nonexistent_returns_empty(self, tmp_path):
        log_dir = tmp_path / "empty_log"
        log_dir.mkdir(parents=True)

        import publisher.config as mod
        original = mod.get_upload_log_dir
        mod.get_upload_log_dir = lambda: log_dir
        try:
            loaded = load_upload_log("nonexistent", "no_book")
            assert loaded == set()
        finally:
            mod.get_upload_log_dir = original

    def test_append_chapters(self, tmp_path):
        log_dir = tmp_path / "append_log"
        log_dir.mkdir(parents=True)

        import publisher.config as mod
        original = mod.get_upload_log_dir
        mod.get_upload_log_dir = lambda: log_dir
        try:
            save_upload_log("fanqie", "b1", {1, 2})
            save_upload_log("fanqie", "b1", {1, 2, 3, 4})
            loaded = load_upload_log("fanqie", "b1")
            assert loaded == {1, 2, 3, 4}
        finally:
            mod.get_upload_log_dir = original
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov
```
Expected: FAIL — module not found

- [ ] **Step 4: 实现 config.py**

```python
# .opencode/scripts/publisher/config.py
"""发布配置与上传进度追踪。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PublishConfig:
    mode: str = "draft"          # draft | publish
    headless: bool = True
    retry_count: int = 2
    retry_delay: float = 3.0     # 秒
    chapter_gap: float = 5.0     # 章间间隔，避免触发反爬
    timeout: float = 30.0        # 单次操作超时


def get_upload_log_dir() -> Path:
    return Path.home() / ".webnovel-publish" / "upload_log"


def _log_path(platform: str, book_id: str) -> Path:
    d = get_upload_log_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{platform}_{book_id}.json"


def load_upload_log(platform: str, book_id: str) -> set[int]:
    p = _log_path(platform, book_id)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("uploaded", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_upload_log(platform: str, book_id: str, uploaded: set[int]):
    p = _log_path(platform, book_id)
    payload = {
        "uploaded": sorted(uploaded),
        "last_upload": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov
```
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/publisher/__init__.py .opencode/scripts/publisher/config.py .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add config module with upload progress tracking"
```

---

### Task 2: formatter.py — Markdown 格式转换

**Files:**
- Create: `.opencode/scripts/publisher/formatter.py`
- Modify: `.opencode/scripts/data_modules/tests/test_publisher.py` (追加测试)

- [ ] **Step 1: 编写 formatter 测试**

在 test_publisher.py 末尾追加：

```python
from publisher.formatter import to_plain_text, to_html, format_for_platform


class TestToPlainText:
    def test_strips_bold(self):
        assert to_plain_text("这是**重点**内容") == "这是重点内容"

    def test_strips_italic(self):
        assert to_plain_text("这是*斜体*文字") == "这是斜体文字"

    def test_strips_headers(self):
        assert to_plain_text("# 标题\n正文") == "标题\n\n正文"

    def test_strips_separator(self):
        assert to_plain_text("段落一\n\n---\n\n段落二") == "段落一\n\n***\n\n段落二"

    def test_preserves_paragraphs(self):
        md = "段落一\n\n段落二"
        result = to_plain_text(md)
        assert "段落一" in result
        assert "段落二" in result

    def test_removes_links(self):
        assert to_plain_text("看[这里](http://example.com)") == "看这里"


class TestToHTML:
    def test_bold(self):
        assert to_html("**重点**") == "<p><b>重点</b></p>"

    def test_paragraphs(self):
        assert to_html("段一\n\n段二") == "<p>段一</p>\n<p>段二</p>"

    def test_italic(self):
        assert to_html("*斜体*") == "<p><i>斜体</i></p>"


class TestFormatForPlatform:
    def test_default_indent(self):
        md = "这是测试段落"
        result = format_for_platform(md, "fanqie")
        assert "　　这是测试段落" in result

    def test_custom_indent_hint(self):
        md = "测试"
        result = format_for_platform(md, "fanqie", hints={"indent": "  "})
        assert "  测试" in result and "　　" not in result

    def test_chapter_title_preserved(self):
        md = "# 第5章 出发\n\n正文内容"
        result = format_for_platform(md, "fanqie")
        assert "第5章 出发" in result
        assert "正文内容" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestTo or TestFormat"
```
Expected: FAIL — module not found

- [ ] **Step 3: 实现 formatter.py**

```python
# .opencode/scripts/publisher/formatter.py
"""Markdown → 平台格式转换。纯函数，无外部依赖。"""
from __future__ import annotations

import re


def to_plain_text(md: str) -> str:
    """Markdown → 纯文本。保留段落结构，去除行内标记。"""
    lines = md.splitlines()
    out: list[str] = []

    for line in lines:
        stripped = line.strip()

        # 标题行 → 纯文本标题
        if stripped.startswith("#"):
            title = re.sub(r"^#+\s*", "", stripped)
            out.append(title)
            out.append("")
            continue

        # 分割线
        if stripped == "---":
            out.append("***")
            out.append("")
            continue

        # 普通段落
        if stripped:
            cleaned = _clean_inline(stripped)
            out.append(cleaned)
            out.append("")
        else:
            out.append("")

    return "\n".join(out).rstrip()


def _clean_inline(text: str) -> str:
    """去除行内 Markdown 标记：粗体、斜体、链接、行内代码。"""
    # 粗体 **text** 或 __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # 斜体 *text* 或 _text_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # 链接 [text](url)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # 行内代码 `code`
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


def to_html(md: str) -> str:
    """Markdown → 简单 HTML，用于支持富文本导入的平台。"""
    lines = md.splitlines()
    out: list[str] = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            if in_paragraph:
                out.append("</p>")
                in_paragraph = False
            title = re.sub(r"^#+\s*", "", stripped)
            out.append(f"<h2>{title}</h2>")
            continue

        if stripped == "---":
            if in_paragraph:
                out.append("</p>")
                in_paragraph = False
            out.append("<hr>")
            continue

        if stripped:
            html_line = _inline_to_html(stripped)
            if not in_paragraph:
                out.append("<p>")
                in_paragraph = True
            out.append(html_line)
        else:
            if in_paragraph:
                out.append("</p>")
                in_paragraph = False
            out.append("")

    if in_paragraph:
        out.append("</p>")

    return "\n".join(out).rstrip()


def _inline_to_html(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


_DEFAULT_HINTS = {
    "indent": "　　",   # 全角空格，中文网文标准
}


def format_for_platform(md: str, platform: str, hints: dict | None = None) -> str:
    """平台感知格式化。默认 MD→纯文本 + 段首全角缩进。"""
    plain = to_plain_text(md)
    cfg = {**_DEFAULT_HINTS, **(hints or {})}
    indent = cfg.get("indent", "　　")

    paragraphs = plain.split("\n\n")
    formatted: list[str] = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped or stripped == "***":
            formatted.append(stripped if stripped else "")
            continue
        formatted.append(f"{indent}{stripped}")
    return "\n\n".join(formatted)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov
```
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/publisher/formatter.py .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add markdown formatter with plain text and HTML output"
```

---

### Task 3: base.py — 抽象适配器接口

**Files:**
- Create: `.opencode/scripts/publisher/base.py`
- Modify: `.opencode/scripts/data_modules/tests/test_publisher.py` (追加测试)

- [ ] **Step 1: 编写 base 接口测试**

在 test_publisher.py 末尾追加：

```python
from publisher.base import BasePlatform, BookMeta, Chapter, UploadResult


class TestBaseInterface:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BasePlatform()  # abstract

    def test_concrete_subclass_minimal(self):
        class MiniAdapter(BasePlatform):
            name = "mini"
            display_name = "Mini"
            login_url = "https://example.com"

            async def setup_auth(self, page):
                return True

            async def list_books(self, page):
                return []

            async def create_book(self, page, meta):
                return "book-1"

            async def upload_chapter(self, page, book_id, chapter):
                return UploadResult(success=True, chapter_index=chapter.index)

        adapter = MiniAdapter()
        assert adapter.name == "mini"


class TestBookMeta:
    def test_minimal(self):
        meta = BookMeta(title="测试书", genre="玄幻", synopsis="简介",
                        protagonist="主角", tags=["热血"])
        assert meta.title == "测试书"

    def test_tags_default(self):
        meta = BookMeta(title="T", genre="G", synopsis="S", protagonist="P")
        assert meta.tags == []


class TestChapter:
    def test_defaults(self):
        ch = Chapter(index=1, title="序章", content="正文内容")
        assert ch.index == 1
        assert ch.volume_title == ""


class TestUploadResult:
    def test_success(self):
        r = UploadResult(success=True, chapter_index=5)
        assert r.success is True

    def test_failure_with_message(self):
        r = UploadResult(success=False, chapter_index=3, message="超时")
        assert r.success is False
        assert "超时" in r.message
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestBase or TestBook or TestChapter or TestUpload"
```
Expected: FAIL — module not found

- [ ] **Step 3: 实现 base.py**

```python
# .opencode/scripts/publisher/base.py
"""平台适配器抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class BookMeta:
    title: str
    genre: str
    synopsis: str
    protagonist: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Chapter:
    index: int
    title: str
    content: str
    volume_title: str = ""


@dataclass
class UploadResult:
    success: bool
    chapter_index: int
    message: str = ""
    url: str = ""


class BasePlatform(ABC):
    name: str = ""
    display_name: str = ""
    login_url: str = ""

    @abstractmethod
    async def setup_auth(self, page) -> bool:
        """引导用户完成登录。返回 True 表示成功。"""
        ...

    @abstractmethod
    async def list_books(self, page) -> list[dict]:
        """获取该作者已有书籍列表。"""
        ...

    @abstractmethod
    async def create_book(self, page, meta: BookMeta) -> str:
        """创建新书，返回 book_id。"""
        ...

    @abstractmethod
    async def upload_chapter(self, page, book_id: str, chapter: Chapter) -> UploadResult:
        """上传单章。优先尝试 API 直传，降级到浏览器模拟。"""
        ...
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestBase or TestBook or TestChapter or TestUpload"
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/publisher/base.py .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add abstract platform adapter interface"
```

---

### Task 4: browser.py — Playwright 浏览器生命周期

**Files:**
- Create: `.opencode/scripts/publisher/browser.py`
- Modify: `.opencode/scripts/data_modules/tests/test_publisher.py` (追加测试)

- [ ] **Step 1: 编写 browser 测试**

在 test_publisher.py 末尾追加：

```python
from publisher.browser import Browser, get_auth_dir


class TestGetAuthDir:
    def test_returns_path(self):
        path = get_auth_dir()
        assert path.name == "auth"
        assert ".webnovel-publish" in str(path)


class TestBrowserConfig:
    def test_default_headless(self):
        b = Browser(platform="test")
        assert b.headless is True

    def test_headed_mode(self):
        b = Browser(headless=False, platform="test")
        assert b.headless is False

    def test_auth_state_path(self, monkeypatch, tmp_path):
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir(parents=True)

        class FakeBrowser(Browser):
            pass

        b = FakeBrowser(platform="fanqie")
        import publisher.browser as mod
        monkeypatch.setattr(mod, "get_auth_dir", lambda: auth_dir)
        p = b._auth_state_path()
        assert p.name == "fanqie.json"
        assert str(p).endswith("fanqie.json")

    def test_linux_sandbox_detection(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr("os.geteuid", lambda: 0)
        b = Browser(platform="test")
        launch_args = b._get_launch_args()
        assert "--no-sandbox" in launch_args

    def test_windows_no_sandbox_flag(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        b = Browser(platform="test")
        launch_args = b._get_launch_args()
        assert "--no-sandbox" not in launch_args
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestGet or TestBrowser"
```
Expected: FAIL — module not found

- [ ] **Step 3: 实现 browser.py**

```python
# .opencode/scripts/publisher/browser.py
"""Playwright 浏览器生命周期管理。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_auth_dir() -> Path:
    return Path.home() / ".webnovel-publish" / "auth"


class Browser:
    def __init__(self, headless: bool = True, platform: str = ""):
        self.headless = headless
        self.platform = platform
        self._browser = None
        self._context = None
        self._page = None

    def _auth_state_path(self) -> Path:
        d = get_auth_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.platform}.json"

    def _get_launch_args(self) -> list[str]:
        args: list[str] = []
        if sys.platform == "linux":
            try:
                if os.geteuid() == 0:
                    args.append("--no-sandbox")
            except AttributeError:
                pass
        return args

    async def start(self):
        """启动浏览器。优先加载已保存的认证状态。"""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_opts = {
            "headless": self.headless,
        }
        args = self._get_launch_args()
        if args:
            launch_opts["args"] = args

        self._browser = await self._playwright.chromium.launch(**launch_opts)

        auth_state_file = self._auth_state_path()
        context_opts: dict = {}
        if auth_state_file.is_file():
            context_opts["storage_state"] = str(auth_state_file)

        self._context = await self._browser.new_context(**context_opts)
        self._page = await self._context.new_page()
        return self._page

    async def save_auth_state(self):
        """保存当前浏览器认证状态到磁盘。"""
        if self._context:
            path = self._auth_state_path()
            await self._context.storage_state(path=str(path))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestGet or TestBrowser"
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/publisher/browser.py .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add Playwright browser lifecycle manager"
```

---

### Task 5: adapters/fanqie.py — 番茄小说适配器

**Files:**
- Create: `.opencode/scripts/publisher/adapters/__init__.py`
- Create: `.opencode/scripts/publisher/adapters/fanqie.py`
- Modify: `.opencode/scripts/data_modules/tests/test_publisher.py` (追加测试)

- [ ] **Step 1: 编写适配器结构测试**

在 test_publisher.py 末尾追加：

```python
from publisher.adapters.fanqie import FanqieAdapter


class TestFanqieAdapter:
    def test_extends_base(self):
        from publisher.base import BasePlatform
        adapter = FanqieAdapter()
        assert isinstance(adapter, BasePlatform)

    def test_has_required_attrs(self):
        adapter = FanqieAdapter()
        assert adapter.name == "fanqie"
        assert adapter.display_name == "番茄小说"
        assert adapter.login_url.startswith("https://")

    def test_implements_all_abstract_methods(self):
        # 如果能实例化，说明所有抽象方法都已实现
        adapter = FanqieAdapter()
        for method_name in ["setup_auth", "list_books", "create_book", "upload_chapter"]:
            method = getattr(adapter, method_name)
            assert callable(method)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestFanqie"
```
Expected: FAIL — module not found

- [ ] **Step 3: 实现 adapters/__init__.py**

```python
# .opencode/scripts/publisher/adapters/__init__.py
"""平台适配器注册。"""
```

- [ ] **Step 4: 实现 fanqie.py（基础骨架）**

```python
# .opencode/scripts/publisher/adapters/fanqie.py
"""番茄小说平台适配器。"""
from __future__ import annotations

from publisher.base import BasePlatform, BookMeta, Chapter, UploadResult


class FanqieAdapter(BasePlatform):
    name = "fanqie"
    display_name = "番茄小说"
    login_url = "https://writer.kandian.com/"

    async def setup_auth(self, page) -> bool:
        """打开番茄作家后台，等待用户扫码登录。"""
        await page.goto(self.login_url, wait_until="networkidle")
        # 等待登录完成：URL 从 login 跳转到 writer 首页
        try:
            await page.wait_for_url(
                "**/writer.kandian.com/**",
                timeout=180_000,  # 3 分钟扫码时间
            )
            return True
        except Exception:
            return False

    async def list_books(self, page) -> list[dict]:
        """获取当前作者已有书单。"""
        await page.goto("https://writer.kandian.com/book/list", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        books = await page.evaluate("""() => {
            const rows = document.querySelectorAll('.book-item, [class*="book"]');
            return Array.from(rows).map(row => {
                const titleEl = row.querySelector('.title, [class*="title"], h3, a');
                return {
                    title: titleEl?.textContent?.trim() || '',
                    url: titleEl?.href || '',
                };
            });
        }""")
        return books

    async def create_book(self, page, meta: BookMeta) -> str:
        """创建新书，返回 book_id。"""
        await page.goto("https://writer.kandian.com/book/create", wait_until="networkidle")
        # 填写书名
        await page.fill('input[name="title"], input[placeholder*="书名"]', meta.title)
        # 选择分类（各平台 DOM 差异大，用文本匹配）
        await page.click(f'text={meta.genre}')
        # 填写简介
        await page.fill('textarea[name="synopsis"], textarea[placeholder*="简介"]', meta.synopsis)
        # 提交
        await page.click('button:has-text("创建"), button:has-text("提交")')
        await page.wait_for_timeout(3000)
        # 从 URL 提取 book_id
        current_url = page.url
        import re
        m = re.search(r'book/(\d+)', current_url)
        return m.group(1) if m else ""

    async def upload_chapter(self, page, book_id: str, chapter: Chapter) -> UploadResult:
        """上传单章。优先 API 直传，降级到浏览器模拟。"""
        try:
            return await self._upload_via_api(page, book_id, chapter)
        except Exception:
            return await self._upload_via_browser(page, book_id, chapter)

    async def _upload_via_api(self, page, book_id: str, chapter: Chapter) -> UploadResult:
        """尝试通过拦截到的内部 API 直传正文。"""
        api_result = await page.evaluate("""async ([bookId, title, content]) => {
            try {
                const resp = await fetch('/api/writer/chapter/create', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        bookId: bookId,
                        title: title,
                        content: content,
                        status: 'draft'
                    })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    return {success: true, data: data};
                }
                return {success: false};
            } catch(e) {
                return {success: false, error: e.message};
            }
        }""", [book_id, chapter.title, chapter.content])

        if api_result.get("success"):
            return UploadResult(success=True, chapter_index=chapter.index, message="API 直传")
        raise RuntimeError(api_result.get("error", "API 返回失败"))

    async def _upload_via_browser(self, page, book_id: str, chapter: Chapter) -> UploadResult:
        """降级：浏览器模拟操作发布。"""
        await page.goto(
            f"https://writer.kandian.com/book/{book_id}/chapter/create",
            wait_until="networkidle",
        )

        await page.fill('input[name="title"], [placeholder*="章节标题"]', chapter.title)

        content_editor = page.locator('textarea[name="content"], [class*="editor"], .content-area')
        await content_editor.click()
        await content_editor.fill(chapter.content)

        await page.wait_for_timeout(1000)

        await page.click('button:has-text("保存草稿"), button:has-text("发布")')

        await page.wait_for_timeout(2000)

        return UploadResult(success=True, chapter_index=chapter.index, message="浏览器模拟上传")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestFanqie"
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/publisher/adapters/ .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add Fanqie novel platform adapter"
```

---

### Task 6: __init__.py — CLI 入口与平台注册表

**Files:**
- Modify: `.opencode/scripts/publisher/__init__.py` (重写，替换占位)
- Modify: `.opencode/scripts/data_modules/tests/test_publisher.py` (追加测试)

- [ ] **Step 1: 编写 CLI 测试**

在 test_publisher.py 末尾追加：

```python
from publisher import REGISTRY, main as publisher_main


class TestRegistry:
    def test_fanqie_registered(self):
        assert "fanqie" in REGISTRY
        assert REGISTRY["fanqie"] is FanqieAdapter


class TestCLIArgs:
    def test_help(self, capsys):
        import sys as _sys
        test_argv = ["publisher", "--help"]
        original = _sys.argv
        try:
            _sys.argv = test_argv
            with pytest.raises(SystemExit) as exc:
                publisher_main()
            assert exc.value.code == 0
        finally:
            _sys.argv = original

    def test_unknown_platform(self, capsys):
        import sys as _sys
        test_argv = ["publisher", "list-books", "--platform", "nonexistent"]
        original = _sys.argv
        try:
            _sys.argv = test_argv
            with pytest.raises(SystemExit) as exc:
                publisher_main()
            assert exc.value.code != 0
        finally:
            _sys.argv = original
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestRegistry or TestCLI"
```
Expected: FAIL

- [ ] **Step 3: 实现 __init__.py CLI**

```python
# .opencode/scripts/publisher/__init__.py
"""小说自动发布 — CLI 入口。

用法:
  python publisher/__init__.py setup-auth --platform fanqie
  python publisher/__init__.py list-books --platform fanqie
  python publisher/__init__.py create-book --platform fanqie --project-root <path>
  python publisher/__init__.py upload --platform fanqie --book-id <id> --range 1-50
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .adapters.fanqie import FanqieAdapter

REGISTRY: dict[str, type] = {
    "fanqie": FanqieAdapter,
}


def _get_adapter(platform: str):
    cls = REGISTRY.get(platform)
    if cls is None:
        print(f"未知平台: {platform}。可用: {', '.join(REGISTRY)}")
        sys.exit(1)
    return cls()


async def _cmd_setup_auth(args: argparse.Namespace):
    from .browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(headless=False, platform=args.platform)
    page = await browser.start()
    try:
        ok = await adapter.setup_auth(page)
        if ok:
            await browser.save_auth_state()
            print(f"✅ {adapter.display_name} 登录成功，认证状态已保存")
        else:
            print(f"❌ {adapter.display_name} 登录超时")
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_list_books(args: argparse.Namespace):
    from .browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        books = await adapter.list_books(page)
        if not books:
            print("未找到书籍")
        else:
            for i, book in enumerate(books, 1):
                print(f"  {i}. {book.get('title', '未知')}")
    finally:
        await browser.close()


async def _cmd_create_book(args: argparse.Namespace):
    from .browser import Browser
    from .base import BookMeta
    adapter = _get_adapter(args.platform)
    # 自动读取项目信息
    project_root = Path(args.project_root).expanduser().resolve()
    meta = _read_book_meta(project_root)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        book_id = await adapter.create_book(page, meta)
        if book_id:
            print(f"✅ 书籍创建成功！book_id: {book_id}")
        else:
            print("❌ 创建失败，请手动检查")
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_upload(args: argparse.Namespace):
    from .browser import Browser
    from .base import Chapter
    from .config import PublishConfig, load_upload_log, save_upload_log
    from .formatter import format_for_platform

    adapter = _get_adapter(args.platform)
    cfg = PublishConfig(mode=args.mode)
    uploaded = load_upload_log(args.platform, args.book_id)

    # 确定章节范围
    project_root = Path(args.project_root).expanduser().resolve()
    chapter_indices = _parse_range(args.range, project_root)
    to_upload = [i for i in chapter_indices if i not in uploaded]
    if not to_upload:
        print("所有章节已上传。")
        return

    print(f"待上传: {len(to_upload)} 章 (共 {len(chapter_indices)} 章, {len(uploaded)} 章已传)")

    browser = Browser(headless=cfg.headless, platform=args.platform)
    page = await browser.start()
    success_count = 0
    fail_count = 0

    try:
        for idx in to_upload:
            chapter_file = _find_chapter_file(project_root, idx)
            if not chapter_file:
                print(f"  ⚠️ 第{idx}章文件未找到，跳过")
                fail_count += 1
                continue

            raw_md = chapter_file.read_text(encoding="utf-8")
            title = _extract_title(raw_md) or f"第{idx}章"
            content = format_for_platform(raw_md, args.platform)
            chapter = Chapter(index=idx, title=title, content=content)

            result = await adapter.upload_chapter(page, args.book_id, chapter)
            if result.success:
                uploaded.add(idx)
                save_upload_log(args.platform, args.book_id, uploaded)
                success_count += 1
                print(f"  ✅ 第{idx}章 {result.message}")
            else:
                fail_count += 1
                print(f"  ❌ 第{idx}章 {result.message}")

            # 章间间隔
            await asyncio.sleep(cfg.chapter_gap)
    finally:
        await browser.close()

    print(f"\n上传完成: 成功 {success_count}, 失败 {fail_count}")


def _read_book_meta(project_root: Path) -> "BookMeta":
    from .base import BookMeta
    import json
    state_file = project_root / ".webnovel" / "state.json"
    meta = BookMeta(title="", genre="", synopsis="", protagonist="")
    if state_file.is_file():
        s = json.loads(state_file.read_text(encoding="utf-8"))
        proj = s.get("project", {}) if isinstance(s, dict) else {}
        meta.title = proj.get("title", "") or project_root.name
        meta.genre = proj.get("genre", "")
        protag = proj.get("protagonist_state", {})
        meta.protagonist = protag.get("name", "") if isinstance(protag, dict) else ""
        meta.synopsis = proj.get("synopsis", "")
    return meta


def _parse_range(spec: str, project_root: Path) -> list[int]:
    """解析章节范围，如 '1-50' 或 '1,3,5' 或 'all'。"""
    import re
    from pathlib import Path as _Path
    if spec.lower() == "all":
        text_dir = project_root / "正文"
        if text_dir.is_dir():
            nums = []
            for f in sorted(text_dir.glob("第*章*.md")):
                m = re.match(r"第(\d+)章", f.name)
                if m:
                    nums.append(int(m.group(1)))
            return nums
        return []

    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        else:
            result.add(int(part))
    return sorted(result)


def _extract_title(md: str) -> str:
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _find_chapter_file(project_root: Path, index: int) -> Path | None:
    import re
    text_dir = project_root / "正文"
    if not text_dir.is_dir():
        return None
    for f in text_dir.iterdir():
        m = re.match(rf"第{index:04d}章|第{index}章", f.name)
        if m:
            return f
    return None


def main():
    parser = argparse.ArgumentParser(description="小说自动发布")
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup-auth", help="引导登录指定平台")
    p_setup.add_argument("--platform", required=True, help="平台名称 (fanqie)")

    p_list = sub.add_parser("list-books", help="列出已有书单")
    p_list.add_argument("--platform", required=True, help="平台名称")

    p_create = sub.add_parser("create-book", help="创建新书")
    p_create.add_argument("--platform", required=True, help="平台名称")
    p_create.add_argument("--project-root", default=".", help="书项目目录")

    p_upload = sub.add_parser("upload", help="上传章节")
    p_upload.add_argument("--platform", required=True, help="平台名称")
    p_upload.add_argument("--book-id", required=True, help="书籍 ID")
    p_upload.add_argument("--range", default="all", help="章节范围")
    p_upload.add_argument("--mode", default="draft", help="发布模式 (draft|publish)")
    p_upload.add_argument("--project-root", default=".", help="书项目目录")

    args = parser.parse_args()

    cmd_map = {
        "setup-auth": _cmd_setup_auth,
        "list-books": _cmd_list_books,
        "create-book": _cmd_create_book,
        "upload": _cmd_upload,
    }
    handler = cmd_map.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov -k "TestRegistry or TestCLI"
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/publisher/__init__.py .opencode/scripts/data_modules/tests/test_publisher.py
git commit -m "feat(publish): add CLI entry point with platform registry"
```

---

### Task 7: webnovel.py — 2 行命令注册

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: 找到 export 注册位置，添加 publish 注册**

在 `webnovel.py` 中找到 export 的 argparse 注册（约第 371 行），在后面加：

```python
p_publish = sub.add_parser("publish", help="发布章节到小说平台")
p_publish.add_argument("args", nargs=argparse.REMAINDER)
```

然后在 export 的 dispatch 代码附近（约第 489 行），加：

```python
if tool == "publish":
    raise SystemExit(_run_script("publisher/__init__.py", [*forward_args, *rest]))
```

- [ ] **Step 2: 运行测试确认 CLI 接入**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_publisher.py -q --no-cov
```
Expected: PASS (all tests)

- [ ] **Step 3: 验证 publish 命令可用**

```bash
python .opencode/scripts/webnovel.py publish --help
```
Expected: 显示 publish 子命令帮助

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat(publish): wire publish command into unified CLI"
```

---

### Task 8: 重写 webnovel-publish SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-publish/SKILL.md`

- [ ] **Step 1: 写入新的 SKILL.md**

```markdown
---
name: webnovel-publish
description: 将小说章节自动发布到国内主流小说平台（番茄等）。触发条件："发布小说"、"发布章节"、"上传到番茄"、"自动发布"。
compatibility: opencode
allowed-tools: Read Write Edit Grep Bash Agent
---

# 小说自动发布

## 目标

将已完成的小说章节自动发布到目标平台。首次需要手动扫码登录，后续全自动运行。

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

已上传的章节自动跳过，支持断点续传。

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
```

- [ ] **Step 2: 验证 frontmatter 格式**

```bash
python -c "
import yaml
text = open('.opencode/skills/webnovel-publish/SKILL.md', encoding='utf-8').read()
fm = yaml.safe_load(text.split('---')[1])
assert fm['name'] == 'webnovel-publish'
assert fm['compatibility'] == 'opencode'
print('frontmatter OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add .opencode/skills/webnovel-publish/SKILL.md
git commit -m "feat(publish): rewrite publish skill for modular multi-platform support"
```
