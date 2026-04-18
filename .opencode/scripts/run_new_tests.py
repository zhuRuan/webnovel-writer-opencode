#!/usr/bin/env python3
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))
sys.path.insert(0, str(scripts_dir.parent))

import pytest
sys.exit(pytest.main([
    str(scripts_dir / "data_modules/tests/test_exceptions.py"),
    str(scripts_dir / "data_modules/tests/test_rag_backend.py"),
    "-v", "--no-header"
]))