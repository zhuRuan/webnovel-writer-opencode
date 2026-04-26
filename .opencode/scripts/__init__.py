"""
webnovel-writer scripts package

This package contains all Python scripts for the webnovel-writer plugin.
"""

__version__ = "5.5.4"
__author__ = "lcy"

# Expose main modules (best-effort, allow test runners without full path)
try:
    from . import security_utils  # noqa: F401
except ImportError:
    pass
try:
    from . import project_locator  # noqa: F401
except ImportError:
    pass
try:
    from . import chapter_paths  # noqa: F401
except ImportError:
    pass

__all__ = [
    "security_utils",
    "project_locator",
    "chapter_paths",
]
