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
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_opts: dict = {"headless": self.headless}
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
        if self._context:
            path = self._auth_state_path()
            await self._context.storage_state(path=str(path))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
