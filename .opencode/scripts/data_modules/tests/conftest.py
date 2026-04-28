import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))


@pytest.fixture(autouse=True)
def _reset_jieba_state():
    try:
        from data_modules.rag_adapter import RAGAdapter
        RAGAdapter._jieba_initialized = False
        RAGAdapter._jieba_loaded = False
    except ImportError:
        pass
    yield
