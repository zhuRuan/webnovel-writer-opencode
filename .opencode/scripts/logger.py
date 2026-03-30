#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志模块

提供标准化的日志输出配置，支持：
- 控制台和文件双输出
- 日志级别配置（通过环境变量 LOG_LEVEL）
- 日志文件配置（通过环境变量 LOG_FILE）
- 按日期自动轮转
- 统一的日志格式
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_LEVEL_DEFAULT = "INFO"
LOG_FILE_DEFAULT = "logs/webnovel.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_loggers: dict = {}
_configured: bool = False


def _get_project_root() -> Path:
    """获取项目根目录"""
    if getattr(sys, '_MEIPASS', None):
        return Path(sys._MEIPASS).parent
    current = Path(__file__).parent
    for _ in range(10):
        if (current / ".webnovel").exists() or (current / ".env").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path.cwd()


def _load_env_config() -> tuple[str, str]:
    """从环境变量加载日志配置"""
    env_file = _get_project_root() / ".env"
    env_level = os.environ.get("LOG_LEVEL", LOG_LEVEL_DEFAULT)
    env_file_path = os.environ.get("LOG_FILE", LOG_FILE_DEFAULT)

    if env_file.exists():
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "LOG_LEVEL":
                            env_level = value
                        elif key == "LOG_FILE":
                            env_file_path = value
        except Exception:
            pass

    return env_level, env_file_path


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    project_root: Optional[Path] = None,
    force: bool = False
) -> None:
    """初始化日志系统（全局配置）"""
    global _configured
    if _configured and not force:
        return

    env_level, env_file = _load_env_config()

    log_level = level or env_level or LOG_LEVEL_DEFAULT
    log_file_path = log_file or env_file or LOG_FILE_DEFAULT

    if project_root is None:
        project_root = _get_project_root()

    log_file_abs = project_root / log_file_path
    log_dir = log_file_abs.parent

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Warning: Cannot create log directory {log_dir}: {e}", file=sys.stderr)
        log_file_abs = None

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    if log_file_abs:
        try:
            file_handler = TimedRotatingFileHandler(
                log_file_abs,
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Cannot create file handler {log_file_abs}: {e}", file=sys.stderr)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取配置好的 logger

    Args:
        name: logger 名称，通常使用 __name__

    Returns:
        配置好的 logger 实例
    """
    if not _configured:
        setup_logging()
    return logging.getLogger(name)


def get_log_file_path() -> Optional[Path]:
    """获取当前日志文件路径"""
    _, env_file = _load_env_config()
    project_root = _get_project_root()
    log_path = project_root / (env_file or LOG_FILE_DEFAULT)
    return log_path if log_path.parent.exists() else None
