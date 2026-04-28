#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器生命周期管理

支持持久化上下文（交互式登录）和临时上下文（已保存状态自动发布）两种模式。
集成了 stealth 反检测参数、崩溃重启和日志记录。
"""

from logger import get_logger
from pathlib import Path
from typing import Optional, List, Union

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from . import config
from .exceptions import BrowserError

logger = get_logger(__name__)


class BrowserManager:
    """Playwright 浏览器会话管理器

    两种模式：
    - 持久化上下文（setup-browser / 交互式登录）：使用浏览器 user-data 目录
    - 临时上下文（publish / 自动发布）：加载保存的 cookies + localStorage

    使用方式：
        # 方式 1：上下文管理器（推荐）
        async with BrowserManager(user_data_dir) as bm:
            page = await bm.launch()

        # 方式 2：手动管理
        bm = BrowserManager(user_data_dir)
        await bm.launch()
        try:
            ...
        finally:
            await bm.close()
    """

    def __init__(
        self,
        user_data_dir: str | Path,
        browser_type: str = config.DEFAULT_BROWSER,
    ):
        self.user_data_dir = str(user_data_dir)
        self.browser_type = browser_type
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = False
        self._extra_args: List[str] = []

    # ── 属性 ──

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

    def is_alive(self) -> bool:
        """检查浏览器是否存活"""
        if not self._browser:
            return False
        try:
            return self._browser.is_connected()
        except Exception:
            return False

    # ── 核心方法 ──

    async def launch(
        self,
        headless: bool = False,
        storage_state: Optional[str] = None,
        viewport_width: int = config.VIEWPORT_WIDTH,
        viewport_height: int = config.VIEWPORT_HEIGHT,
        locale: str = config.DEFAULT_LOCALE,
        extra_args: Optional[List[str]] = None,
    ) -> Page:
        """启动浏览器

        Args:
            headless: 是否无头模式运行
            storage_state: 保存的登录状态文件路径。如果提供且文件存在，
                           则使用临时上下文模式；否则使用持久化上下文模式
            viewport_width: 视口宽度
            viewport_height: 视口高度
            locale: 语言区域
            extra_args: 额外的浏览器启动参数

        Returns:
            Page 实例

        Raises:
            BrowserError: 浏览器启动失败时抛出
        """
        if self.is_alive():
            logger.warning("浏览器已在运行，先关闭旧实例")
            await self.close(suppress_exceptions=True)

        self._headless = headless
        self._extra_args = extra_args or []

        try:
            Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

            self._playwright = await async_playwright().start()

            use_storage = bool(storage_state and Path(storage_state).exists())
            all_args = config.STEALTH_ARGS + self._extra_args + [
                f"--window-size={viewport_width},{viewport_height + 85}",
            ]

            if use_storage:
                logger.info("使用已保存的登录状态启动浏览器: %s", storage_state)
                browser_launcher = getattr(self._playwright, self.browser_type)
                self._browser = await browser_launcher.launch(
                    headless=headless,
                    args=all_args,
                )
                self._context = await self._browser.new_context(
                    storage_state=storage_state,
                    viewport={"width": viewport_width, "height": viewport_height},
                    locale=locale,
                )
            else:
                logger.info("使用持久化上下文启动浏览器: %s", self.user_data_dir)
                browser_launcher = getattr(self._playwright, self.browser_type)
                self._context = await browser_launcher.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=headless,
                    viewport={"width": viewport_width, "height": viewport_height},
                    locale=locale,
                    args=all_args,
                )

            self._page = (
                self._context.pages[0]
                if self._context.pages
                else await self._context.new_page()
            )
            logger.info(
                "浏览器启动成功 (headless=%s, browser=%s, storage_state=%s)",
                headless,
                self.browser_type,
                use_storage,
            )
            return self._page

        except Exception as e:
            raise BrowserError(f"启动浏览器失败: {e}") from e

    async def restart(self) -> Page:
        """重启浏览器，保持之前的配置"""
        logger.info("正在重启浏览器...")
        await self.close(suppress_exceptions=True)
        return await self.launch(
            headless=self._headless,
        )

    async def ensure_alive(self) -> None:
        """确保浏览器存活，如果已崩溃则自动重启"""
        if not self.is_alive():
            logger.warning("检测到浏览器已崩溃，正在自动重启...")
            await self.restart()
            logger.info("浏览器已自动重启")

    async def close(self, suppress_exceptions: bool = False) -> None:
        """关闭浏览器并清理资源

        Args:
            suppress_exceptions: 如果为 True，异常会被记录但不会抛出。
                                用于清理场景（finally 块 / 析构）。
        """
        errors: List[Exception] = []

        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                errors.append(e)
                logger.warning("关闭页面时出错: %s", e)

        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                errors.append(e)
                logger.warning("关闭上下文时出错: %s", e)

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                errors.append(e)
                logger.warning("关闭浏览器时出错: %s", e)

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                errors.append(e)
                logger.warning("停止 Playwright 时出错: %s", e)

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

        if errors:
            logger.info("浏览器已关闭（有 %d 个非致命警告）", len(errors))
        else:
            logger.info("浏览器已正常关闭")

        if not suppress_exceptions and errors:
            raise BrowserError(
                f"关闭浏览器时出现 {len(errors)} 个错误",
                {"errors": [str(e) for e in errors]},
            )

    # ── 性能优化 ──

    async def block_unnecessary_resources(
        self,
        blocked_types: Optional[List[str]] = None,
    ) -> None:
        """拦截不必要的资源加载以提升性能

        Args:
            blocked_types: 要拦截的资源类型列表，默认使用 config.BLOCKED_RESOURCES
        """
        if blocked_types is None:
            blocked_types = config.BLOCKED_RESOURCES

        await self.page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in blocked_types
                else route.continue_()
            ),
        )
        logger.info("已拦截资源类型: %s", blocked_types)

    # ── 调试工具 ──

    def _debug_screenshot_dir(self) -> Path:
        """获取调试截图目录"""
        project_root = Path.cwd()
        return project_root / config.DEBUG_SCREENSHOT_DIR

    async def save_debug_screenshot(self, name: str) -> Optional[Path]:
        """保存调试截图

        Args:
            name: 截图文件名（不含扩展名）

        Returns:
            截图文件路径，如果浏览器未启动返回 None
        """
        if not self._page:
            logger.warning("无法保存调试截图：浏览器未启动")
            return None

        screenshot_dir = self._debug_screenshot_dir()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filepath = screenshot_dir / f"{name}.png"

        try:
            await self._page.screenshot(path=str(filepath), full_page=True)
            logger.info("调试截图已保存: %s", filepath)
            return filepath
        except Exception as e:
            logger.warning("保存调试截图失败: %s", e)
            return None

    async def start_trace(self) -> None:
        """启动浏览器追踪（用于调试）"""
        if not self._context:
            raise BrowserError("浏览器未启动，无法启动追踪")
        await self._context.tracing.start(screenshots=True, snapshots=True)
        logger.info("浏览器追踪已启动")

    async def stop_trace(self, path: str = "trace.zip") -> None:
        """停止浏览器追踪并保存

        Args:
            path: 追踪文件保存路径
        """
        if not self._context:
            logger.warning("无法停止追踪：浏览器未启动")
            return
        await self._context.tracing.stop(path=path)
        logger.info("浏览器追踪已保存: %s", path)

    # ── 上下文管理器 ──

    async def __aenter__(self) -> "BrowserManager":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close(suppress_exceptions=True)
