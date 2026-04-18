#!/usr/bin/env python3
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))
sys.path.insert(0, str(scripts_dir.parent))

import pytest

# 只运行失败的测试
sys.exit(pytest.main([
    str(scripts_dir / "data_modules/tests/test_webnovel_unified_cli.py::test_preflight_succeeds_for_valid_project_root"),
    str(scripts_dir / "data_modules/tests/test_webnovel_unified_cli.py::test_preflight_fails_when_required_scripts_are_missing"),
    "-v", "--no-header"
]))