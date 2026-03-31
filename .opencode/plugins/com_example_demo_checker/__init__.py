#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_checker 插件入口
"""

from .checkers.sensitive_checker import SensitiveWordChecker

__all__ = ["SensitiveWordChecker"]
