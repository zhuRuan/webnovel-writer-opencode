#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器生命周期管理
"""

from logging import getLogger
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .exceptions import BrowserError

logger = getLogger(__name__)

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]


class BrowserManager:
    """Playwright 浏览器会话管理器

    两种模式：
    - 持久化上下文（setup-browser / 交互式登录）：使用 Chromium user-data 目录
    - 临时上下文（publish / 自动发布）：加载保存的 cookies + localStorage
    """

    def __init__(self, user_data_dir: str | Path):
        self.user_data_dir = str(user_data_dir)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    @property
    def page(self) -> Page:
        """获取当前页面"""
        if not self._page:
            raise BrowserError("浏览器未启动，请先调用 launch()")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """获取当前浏览器上下文"""
        if not self._context:
            raise BrowserError("浏览器未启动，请先调用 launch()")
        return self._context

    async def launch(
        self,
        headless: bool = False,
        storage_state: Optional[str] = None,
    ) -> None:
        """启动浏览器

        Args:
            headless: 是否无头模式运行
            storage_state: 保存的登录状态文件路径。如果提供且文件存在，
                          则使用临时上下文模式；否则使用持久化上下文模式
        """
        try:
            Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

            self._playwright = await async_playwright().start()

            use_storage = storage_state and Path(storage_state).exists()

            if use_storage:
                logger.info("使用已保存的登录状态启动浏览器: %s", storage_state)
                self._browser = await self._playwright.chromium.launch(
                    headless=headless,
                    args=_STEALTH_ARGS,
                )
                self._context = await self._browser.new_context(
                    storage_state=storage_state,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
            else:
                logger.info("使用持久化上下文启动浏览器: %s", self.user_data_dir)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=headless,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                    args=_STEALTH_ARGS,
                )

            self._page = (
                self._context.pages[0]
                if self._context.pages
                else await self._context.new_page()
            )
            logger.info("浏览器启动成功 (headless=%s, storage_state=%s)", headless, use_storage)

        except Exception as e:
            raise BrowserError(f"启动浏览器失败: {e}") from e

    async def close(self) -> None:
        """关闭浏览器并清理资源"""
        try:
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
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.exception("关闭浏览器时出现错误")

    async def __aenter__(self) -> "BrowserManager":
        """异步上下文管理器入口"""
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出"""
        await self.close()
