#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说作家后台登录认证
"""

import asyncio
from logging import getLogger
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from .exceptions import AuthenticationError

logger = getLogger(__name__)

WRITER_URL = "https://fanqienovel.com/main/writer/?enter_from=author_zone"

_LOGIN_URL_KEYWORDS = ["login", "passport", "sso", "sign"]


def _is_writer_url(url: str) -> bool:
    """判断 URL 是否为作家后台页面（非登录页）"""
    url_lower = url.lower()
    if any(keyword in url_lower for keyword in _LOGIN_URL_KEYWORDS):
        return False
    return "fanqienovel.com" in url_lower and (
        "writer" in url_lower or "main" in url_lower or "author" in url_lower
    )


async def _save_auth_state(page: Page, save_path: Path) -> None:
    """保存浏览器认证状态（cookies + localStorage）到文件"""
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        await page.context.storage_state(path=str(save_path))
        logger.info("登录状态已保存到: %s", save_path)
    except Exception as e:
        logger.exception("保存登录状态失败")
        raise AuthenticationError(f"保存登录状态失败: {e}") from e


async def ensure_logged_in(
    page: Page,
    auth_state_path: Path,
    timeout_ms: int = 180000,
) -> bool:
    """导航到番茄作家后台并验证登录状态

    策略：导航到作家 URL 后检查是否被重定向到登录页。
    登录成功后保存浏览器状态供后续使用。

    Args:
        page: Playwright 页面实例
        auth_state_path: 登录状态保存路径
        timeout_ms: 手动登录超时时间（毫秒），默认 3 分钟

    Returns:
        True 表示已登录，False 表示超时
    """
    logger.info("正在导航到番茄作家后台: %s", WRITER_URL)

    try:
        await page.goto(WRITER_URL, wait_until="commit", timeout=60_000)
    except Exception as e:
        logger.exception("导航到作家后台失败")

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        await asyncio.sleep(5)

    if _is_writer_url(page.url):
        logger.info("已登录（URL: %s）", page.url)
        await _save_auth_state(page, auth_state_path)
        return True

    logger.info("需要登录（当前 URL: %s）", page.url)
    print("\n" + "=" * 50)
    print("  请在弹出的浏览器窗口中登录番茄小说作家后台")
    print("  （扫码登录或手机号登录均可）")
    print("=" * 50)
    print(f"等待登录中（最长 {timeout_ms // 1000} 秒）...\n")

    poll_interval_s = 2
    elapsed_ms = 0
    while elapsed_ms < timeout_ms:
        await asyncio.sleep(poll_interval_s)
        elapsed_ms += poll_interval_s * 1000

        current_url = page.url
        if _is_writer_url(current_url):
            logger.info("登录成功（URL: %s）", current_url)
            print("登录成功！\n")
            await asyncio.sleep(3)
            await _save_auth_state(page, auth_state_path)
            return True

    logger.error("登录超时，已等待 %d 秒", timeout_ms // 1000)
    print("登录超时，请重试。\n")
    return False


def check_auth_state(auth_state_path: Path) -> bool:
    """检查登录状态是否存在且有效

    Args:
        auth_state_path: 登录状态文件路径

    Returns:
        True 表示状态文件存在
    """
    return auth_state_path.exists() and auth_state_path.stat().st_size > 0


def get_default_auth_state_path() -> Path:
    """获取默认的登录状态文件路径"""
    return Path.home() / ".opencode" / "fanqie_auth_state.json"


def get_default_user_data_dir() -> Path:
    """获取默认的浏览器用户数据目录"""
    return Path.home() / ".opencode" / "browser_user_data"
