# .opencode/scripts/publisher/browser.py
"""Playwright 浏览器生命周期管理。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]


def get_auth_dir() -> Path:
    return Path.home() / ".webnovel-publish" / "auth"


class Browser:
    """管理 Playwright 浏览器会话。

    两种模式：
    - 持久化模式（setup-auth / 登录）：使用 persistent context，用户可交互。
    - 短暂模式（publish / 上传）：加载已保存的 storage_state.json。
    """

    def __init__(self, headless: bool = True, platform: str = ""):
        self.headless = headless
        self.platform = platform
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def _auth_state_path(self) -> Path:
        d = get_auth_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.platform}.json"

    def _get_launch_args(self) -> list[str]:
        args = [*_STEALTH_ARGS]
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

        auth_state_file = self._auth_state_path()
        use_storage = auth_state_file.is_file()

        if use_storage:
            # 短暂模式：加载已保存的认证状态
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless, args=self._get_launch_args()
            )
            self._context = await self._browser.new_context(
                storage_state=str(auth_state_file),
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
        else:
            # 持久化模式：用户需手动登录
            user_data_dir = (
                Path.home() / ".webnovel-publish" / "browser_data" / self.platform
            )
            user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = (
                await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=self.headless,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                    args=self._get_launch_args(),
                )
            )

        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        return self._page

    async def save_auth_state(self):
        """保存浏览器认证状态到磁盘。"""
        if self._context:
            path = self._auth_state_path()
            await self._context.storage_state(path=str(path))

    async def close(self):
        if self._context:
            await self._context.close()
            self._context = None
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
