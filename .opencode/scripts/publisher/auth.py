#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说作家后台登录认证

负责导航到作家后台、检测登录状态、保存/加载认证状态。
集成了超时处理、自动重试和状态验证功能。
"""

import asyncio
from logger import get_logger
from pathlib import Path
from typing import Optional, Tuple

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from . import config
from .exceptions import AuthenticationError

logger = get_logger(__name__)

_LOGIN_URL_KEYWORDS = ["login", "passport", "sso", "sign"]


def _is_writer_url(url: str) -> bool:
    """判断 URL 是否为作家后台页面（非登录页）

    Args:
        url: 当前页面 URL

    Returns:
        如果 URL 指向作家后台（非登录页）返回 True
    """
    url_lower = url.lower()
    if any(keyword in url_lower for keyword in _LOGIN_URL_KEYWORDS):
        return False
    return "fanqienovel.com" in url_lower and (
        "writer" in url_lower or "main" in url_lower or "author" in url_lower
    )


async def _save_auth_state(page: Page, save_path: Path) -> None:
    """保存浏览器认证状态（cookies + localStorage）到文件

    Args:
        page: Playwright 页面实例
        save_path: 保存路径

    Raises:
        AuthenticationError: 保存失败时抛出
    """
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        await page.context.storage_state(path=str(save_path))
        logger.info("登录状态已保存到: %s (%.1f KB)", save_path, save_path.stat().st_size / 1024)
    except Exception as e:
        logger.exception("保存登录状态失败")
        raise AuthenticationError(f"保存登录状态失败: {e}") from e


async def _navigate_to_writer(page: Page, timeout_ms: int) -> None:
    """导航到番茄作家后台

    Args:
        page: Playwright 页面实例
        timeout_ms: 导航超时时间

    Raises:
        AuthenticationError: 导航失败时抛出
    """
    logger.info("正在导航到番茄作家后台: %s", config.WRITER_URL)

    try:
        await page.goto(config.WRITER_URL, wait_until="commit", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.warning("导航到作家后台超时，尝试继续检查状态...")
    except Exception as e:
        logger.warning("导航到作家后台时出错: %s", e)

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        logger.warning("页面加载未在 15 秒内完成，继续...")
    except Exception:
        await asyncio.sleep(3)


async def _wait_for_login_manual(
    page: Page,
    timeout_ms: int,
    poll_interval_ms: int,
) -> Tuple[bool, str]:
    """等待用户手动登录（交互式）

    Args:
        page: Playwright 页面实例
        timeout_ms: 总等待时间
        poll_interval_ms: 轮询间隔

    Returns:
        (是否成功, 当前URL)
    """
    print("\n" + "=" * 50)
    print("  请在弹出的浏览器窗口中登录番茄小说作家后台")
    print("  （扫码登录或手机号登录均可）")
    print("=" * 50)
    print(f"等待登录中（最长 {timeout_ms // 1000} 秒）...\n")

    elapsed_ms = 0
    while elapsed_ms < timeout_ms:
        await asyncio.sleep(poll_interval_ms / 1000)
        elapsed_ms += poll_interval_ms

        current_url = page.url
        if _is_writer_url(current_url):
            logger.info("登录成功（URL: %s）", current_url)
            print("登录成功！\n")
            await asyncio.sleep(2)
            return True, current_url

    return False, page.url


def check_auth_state(auth_state_path: Path) -> bool:
    """检查登录状态文件是否存在且非空

    Args:
        auth_state_path: 登录状态文件路径

    Returns:
        True 如果状态文件存在且非空
    """
    if not auth_state_path.exists():
        logger.debug("认证状态文件不存在: %s", auth_state_path)
        return False
    if auth_state_path.stat().st_size == 0:
        logger.warning("认证状态文件为空: %s", auth_state_path)
        return False
    return True


async def ensure_logged_in(
    page: Page,
    auth_state_path: Path,
    timeout_ms: int = config.LOGIN_TIMEOUT,
    poll_interval_ms: int = config.POLL_INTERVAL_MS,
) -> bool:
    """导航到番茄作家后台并验证登录状态

    策略：
    1. 导航到作家 URL
    2. 检查是否被重定向到登录页
    3. 如果未登录，等待用户手动登录
    4. 登录成功后保存浏览器状态供后续使用

    Args:
        page: Playwright 页面实例
        auth_state_path: 登录状态保存路径
        timeout_ms: 手动登录超时时间（毫秒），默认 3 分钟
        poll_interval_ms: 轮询间隔（毫秒），默认 2 秒

    Returns:
        True 表示已登录，False 表示超时
    """
    await _navigate_to_writer(page, timeout_ms)

    if _is_writer_url(page.url):
        logger.info("已登录（URL: %s）", page.url)
        await _save_auth_state(page, auth_state_path)
        return True

    logger.info("需要登录（当前 URL: %s）", page.url)

    success, _ = await _wait_for_login_manual(
        page, timeout_ms, poll_interval_ms
    )

    if not success:
        logger.error("登录超时，已等待 %.1f 分钟", timeout_ms / 60000)
        print("登录超时，请重试。\n")
        raise AuthenticationError(
            f"登录超时：在 {timeout_ms / 60000:.0f} 分钟内未完成登录"
        )

    await _save_auth_state(page, auth_state_path)
    return True


def get_default_auth_state_path() -> Path:
    """获取默认的登录状态文件路径"""
    return Path.home() / config.AUTH_STATE_DIRNAME / config.AUTH_STATE_FILENAME


def get_default_user_data_dir() -> Path:
    """获取默认的浏览器用户数据目录"""
    return Path.home() / config.AUTH_STATE_DIRNAME / config.BROWSER_USER_DATA_DIRNAME
