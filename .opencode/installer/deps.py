"""Dependency installation. Pure stdlib, runs subprocess for pip."""
import subprocess
import sys
from pathlib import Path

from installer.ui import info, warn, error, spinner

FEATURE_GROUPS = {
    "dashboard": {
        "label": "Dashboard — Web 管理面板",
        "desc": "fastapi/uvicorn (~15MB)",
        "req": ".opencode/dashboard/requirements.txt",
        "default": True,
    },
    "export": {
        "label": "导出 — MD/TXT/EPUB/HTML/DOCX/PDF",
        "desc": "mistune/python-docx/ebooklib (~8MB)",
        "req": ".opencode/scripts/requirements-export.txt",
        "default": True,
    },
    "publish": {
        "label": "发布 — 小说平台自动发布",
        "desc": "playwright + Chromium (~150MB)",
        "req": None,
        "default": False,
    },
    "dev": {
        "label": "开发工具 — 测试套件",
        "desc": "pytest/pytest-cov (~10MB)",
        "req": ".opencode/scripts/requirements-dev.txt",
        "default": False,
    },
}

CORE_REQ = ".opencode/scripts/requirements.txt"


def check_pip_available() -> bool:
    """Check if pip can be invoked."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, check=True, timeout=10
        )
        return True
    except Exception:
        return False


def create_venv(path: Path) -> bool:
    """Create a Python virtual environment. Returns True on success."""
    if path.exists():
        warn(f"Virtual env already exists: {path}")
        return False
    info(f"Creating virtual environment: {path}")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(path)],
            check=True, timeout=60
        )
        return True
    except subprocess.CalledProcessError as e:
        warn(f"Failed to create venv: {e}")
        return False


def _get_pip_path(venv_path: Path = None) -> list:
    """Get pip command, optionally inside a venv."""
    if venv_path:
        if sys.platform == "win32":
            pip = [str(venv_path / "Scripts" / "python"), "-m", "pip"]
        else:
            pip = [str(venv_path / "bin" / "python"), "-m", "pip"]
    else:
        pip = [sys.executable, "-m", "pip"]
    return pip


def install_pip_requirements(req_files: list, venv_path: Path = None) -> bool:
    """Install Python dependencies from requirement files."""
    pip = _get_pip_path(venv_path)

    for rf in req_files:
        if not Path(rf).exists():
            warn(f"Requirements file not found: {rf}")
            continue
        info(f"Installing: {rf}")
        try:
            subprocess.run(
                pip + ["install", "-r", str(rf), "--quiet"],
                check=True, timeout=120
            )
        except subprocess.CalledProcessError as e:
            warn(f"pip install failed for {rf}: {e}")
            return False
    return True


def install_playwright_browser(venv_path: Path = None) -> bool:
    """Install playwright and chromium browser."""
    pip = _get_pip_path(venv_path)
    try:
        subprocess.run(pip + ["install", "playwright", "--quiet"], check=True, timeout=60)
    except subprocess.CalledProcessError:
        warn("playwright pip install failed")
        return False

    with spinner("安装 Chromium 浏览器 (可能需要几分钟)..."):
        try:
            subprocess.run(
                [pip[0], "-m", "playwright", "install", "chromium"],
                check=True, timeout=300, capture_output=True
            )
            return True
        except subprocess.CalledProcessError:
            warn("playwright chromium install failed")
            return False


def _resolve_features(args, *, skip_playwright: bool = False) -> dict:
    """Resolve which optional features to install from args or defaults."""
    features = {}
    with_any = getattr(args, 'with_features', None) or []
    for key in FEATURE_GROUPS:
        if key == "publish" and skip_playwright:
            features[key] = False
        elif key in with_any:
            features[key] = True
        elif hasattr(args, f'no_{key}') and getattr(args, f'no_{key}'):
            features[key] = False
        else:
            features[key] = FEATURE_GROUPS[key]["default"]
    return features


def install_core_deps(venv_path: Path = None, skip_playwright: bool = False,
                      features: dict = None):
    """Install core + selected optional dependencies."""
    # Core is always installed
    req_files = [CORE_REQ]

    # Resolve optional features
    if features is None:
        features = {k: v["default"] for k, v in FEATURE_GROUPS.items()}
        if skip_playwright:
            features["publish"] = False

    # Collect optional requirement files
    for key, cfg in FEATURE_GROUPS.items():
        if features.get(key) and cfg["req"]:
            req_files.append(cfg["req"])

    # Show what will be installed
    labels = ["core"]
    for key, cfg in FEATURE_GROUPS.items():
        labels.append(f"{key}={'Y' if features.get(key) else 'N'}")
    info(f"模块选择: {', '.join(labels)}")

    if not install_pip_requirements(req_files, venv_path):
        error("Core dependency installation failed")

    # Playwright is special — separate pip + browser install
    if features.get("publish") and not skip_playwright:
        install_playwright_browser(venv_path)
