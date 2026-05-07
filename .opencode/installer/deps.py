"""Dependency installation. Pure stdlib, runs subprocess for pip."""
import subprocess
import sys
from pathlib import Path

from installer.ui import info, warn, error


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
    info("Installing playwright...")
    try:
        subprocess.run(pip + ["install", "playwright", "--quiet"], check=True, timeout=60)
    except subprocess.CalledProcessError:
        warn("playwright pip install failed")
        return False

    info("Installing chromium browser...")
    try:
        subprocess.run(
            [pip[0], "-m", "playwright", "install", "chromium"],
            check=True, timeout=300
        )
        return True
    except subprocess.CalledProcessError:
        warn("playwright chromium install failed")
        return False


def install_core_deps(venv_path: Path = None, skip_playwright: bool = False):
    """Install all core dependencies (called by preflight)."""
    req_files = [
        ".opencode/scripts/requirements.txt",
        ".opencode/dashboard/requirements.txt",
    ]

    if not install_pip_requirements(req_files, venv_path):
        error("Core dependency installation failed")

    if not skip_playwright:
        install_playwright_browser(venv_path)
