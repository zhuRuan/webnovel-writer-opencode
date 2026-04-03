#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel 统一入口脚本（无须 `cd`）

用法示例：
  python "<SCRIPTS_DIR>/webnovel.py" preflight
  python "<SCRIPTS_DIR>/webnovel.py" where
  python "<SCRIPTS_DIR>/webnovel.py" index stats
  python "<SCRIPTS_DIR>/webnovel.py" dashboard

说明：
- 该脚本仅负责把 `.opencode/scripts` 和 `.opencode` 加入 sys.path，然后转发到 `data_modules.webnovel`。
- 适配 skills/agents 在项目级或用户级（~/.opencode）安装时的调用方式。
"""

from __future__ import annotations

import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def _opencode_dir() -> Path:
    return _scripts_dir().parent


def main() -> None:
    scripts_dir = _scripts_dir()
    sys.path.insert(0, str(scripts_dir))
    sys.path.insert(0, str(_opencode_dir()))

    # 延迟导入，避免 sys.path 未就绪
    from data_modules.webnovel import main as _main

    _main()


if __name__ == "__main__":
    enable_windows_utf8_stdio(skip_in_pytest=True)
    main()
