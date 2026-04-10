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

CONSOLE_LEVEL_DEFAULT = "INFO"
FILE_LEVEL_DEFAULT = "DEBUG"

_module_levels: dict[str, str] = {}
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


def _load_env_config() -> tuple[str, str, str, str]:
    """从环境变量加载日志配置
    
    Returns:
        (log_level, log_file, console_level, file_level)
    """
    env_file = _get_project_root() / ".env"
    env_level = os.environ.get("LOG_LEVEL", LOG_LEVEL_DEFAULT)
    env_file_path = os.environ.get("LOG_FILE", LOG_FILE_DEFAULT)
    env_console_level = os.environ.get("LOG_CONSOLE_LEVEL", CONSOLE_LEVEL_DEFAULT)
    env_file_level = os.environ.get("LOG_FILE_LEVEL", FILE_LEVEL_DEFAULT)

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
                        elif key == "LOG_CONSOLE_LEVEL":
                            env_console_level = value
                        elif key == "LOG_FILE_LEVEL":
                            env_file_level = value
        except Exception:
            pass

    return env_level, env_file_path, env_console_level, env_file_level


def _parse_module_levels() -> dict[str, str]:
    """解析模块级日志配置 LOG_MODULE_LEVELS
    
    支持格式: "module1=DEBUG,module2=INFO"
    """
    global _module_levels
    if _module_levels:
        return _module_levels
    
    env = os.environ.get("LOG_MODULE_LEVELS", "")
    if not env:
        return _module_levels
    
    for item in env.split(","):
        item = item.strip()
        if "=" in item:
            module, level = item.split("=", 1)
            _module_levels[module.strip()] = level.strip()
    
    return _module_levels


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    project_root: Optional[Path] = None,
    console_level: Optional[str] = None,
    file_level: Optional[str] = None,
    force: bool = False
) -> None:
    """初始化日志系统（全局配置）
    
    Args:
        level: 全局日志级别
        log_file: 日志文件路径
        project_root: 项目根目录
        console_level: 控制台输出级别
        file_level: 文件记录级别
        force: 强制重新配置
    """
    global _configured
    if _configured and not force:
        return

    env_level, env_file, env_console_level, env_file_level = _load_env_config()

    log_level = level or env_level or LOG_LEVEL_DEFAULT
    log_file_path = log_file or env_file or LOG_FILE_DEFAULT
    console_lvl = console_level or env_console_level or CONSOLE_LEVEL_DEFAULT
    file_lvl = file_level or env_file_level or FILE_LEVEL_DEFAULT

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

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_lvl.upper(), logging.INFO))
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
            file_handler.setLevel(getattr(logging, file_lvl.upper(), logging.DEBUG))
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
    
    logger = logging.getLogger(name)
    
    # 应用模块级配置
    module_levels = _parse_module_levels()
    for module_prefix, level in module_levels.items():
        if name.startswith(module_prefix):
            logger.setLevel(getattr(logging, level.upper(), logging.INFO))
            break
    
    return logger


def get_log_file_path() -> Optional[Path]:
    """获取当前日志文件路径"""
    _, env_file, _, _ = _load_env_config()
    project_root = _get_project_root()
    log_path = project_root / (env_file or LOG_FILE_DEFAULT)
    return log_path if log_path.parent.exists() else None
