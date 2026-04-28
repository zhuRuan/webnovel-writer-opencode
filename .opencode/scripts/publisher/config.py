#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publisher 配置集中管理

统一的超时时间、重试策略、stealth 参数和 URL 配置。
"""

# ── 浏览器配置 ──
DEFAULT_TIMEOUT = 30_000        # 默认操作超时（毫秒）
NAVIGATION_TIMEOUT = 60_000     # 页面导航超时（毫秒）
LOGIN_TIMEOUT = 180_000         # 手动登录等待超时（毫秒）
POLL_INTERVAL_MS = 2000         # 登录轮询间隔（毫秒）

# ── Stealth 参数 ──
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-extensions",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-sandbox",
    "--disable-setuid-sandbox",
]

# ── 网络配置 ──
BASE_URL = "https://fanqienovel.com"
WRITER_URL = "https://fanqienovel.com/main/writer/?enter_from=author_zone"
COMMON_PARAMS = "aid=2503&app_name=muye_novel"

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0       # 重试退避基础时间（秒）
RETRY_BACKOFF_MAX = 10.0       # 重试退避最大时间（秒）

# ── 视图配置 ──
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800
DEFAULT_LOCALE = "zh-CN"

# ── 认证配置 ──
AUTH_STATE_DIRNAME = ".opencode"
AUTH_STATE_FILENAME = "fanqie_auth_state.json"
BROWSER_USER_DATA_DIRNAME = "browser_user_data"

# ── 浏览器引擎 ──
SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")
DEFAULT_BROWSER = "chromium"

# ── 调试配置 ──
DEBUG_SCREENSHOT_DIR = ".webnovel/debug_screenshots"

# ── 性能优化 ──
BLOCKED_RESOURCES = [
    "image",
    "font",
    "media",
]
