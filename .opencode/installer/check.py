"""System preflight checks. Pure stdlib, no external deps."""
import os
import sys
import shutil
import subprocess
import platform as _platform
from pathlib import Path

from installer.ui import info, warn, error

KNOWN_OPENCODE_PROCESSES = {
    "windows": ["OpenCode.exe", "Code.exe"],
    "linux":   [],
    "darwin":  ["OpenCode", "Electron"],
}


def platform_name() -> str:
    """Return normalized platform name: windows, linux, or darwin."""
    s = _platform.system()
    if s == "Windows":
        return "windows"
    elif s == "Linux":
        return "linux"
    elif s == "Darwin":
        return "darwin"
    return s.lower()


def check_python_version(version: tuple = None) -> bool:
    """Check that a Python version meets the project minimum (3.10).
    Defaults to checking the current interpreter.
    """
    if version is None:
        version = (sys.version_info.major, sys.version_info.minor)
    return version >= (3, 10)


def check_disk_space(path: str, required_mb: int = 50) -> bool:
    """Check available disk space at path."""
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= required_mb
    except Exception:
        return True  # Can't check, don't block


def check_network(timeout: int = 5) -> bool:
    """Check if we can reach GitHub."""
    import urllib.request
    try:
        urllib.request.urlopen("https://github.com", timeout=timeout)
        return True
    except Exception:
        return False


def is_opencode_running(target_dir: str = ".opencode") -> str:
    """
    Check if OpenCode is running. Returns 'running', 'not_running', or 'locked'.

    Layer 1: Process name scan (all platforms)
    Layer 2: File lock detection via os.rename (Windows-specific, definitive)
    """
    pname = platform_name()

    # Layer 1: process scan
    found = False
    try:
        procs = KNOWN_OPENCODE_PROCESSES.get(pname, [])
        if pname == "windows":
            if procs:
                cmd = ["tasklist", "/FI", f"IMAGENAME eq {procs[0]}"]
                for proc in procs[1:]:
                    cmd.extend(["/FI", f"IMAGENAME eq {proc}"])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                found = any(p.lower() in result.stdout.lower() for p in procs)
        elif pname == "linux":
            result = subprocess.run(
                ["pgrep", "-f", "opencode"],
                capture_output=True, text=True, timeout=5
            )
            found = result.returncode == 0
        elif pname == "darwin":
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            found = any(
                p.lower() in result.stdout.lower()
                for p in ["OpenCode", "Electron"]
            )
    except Exception:
        pass  # Process scan failed, try lock test

    # Layer 2: file lock test (Windows definitive check)
    if pname == "windows" and os.path.isdir(target_dir):
        lock_test = target_dir + "_lock_test"
        try:
            os.rename(target_dir, lock_test)
            os.rename(lock_test, target_dir)
            return "not_running" if not found else "running"
        except OSError:
            return "locked"  # 100% certainty — file is locked
    elif pname == "windows" and not os.path.isdir(target_dir):
        return "not_running"  # .opencode doesn't exist yet

    return "running" if found else "not_running"


def run_preflight_checks():
    """Run all preflight checks. Calls error() on failure."""
    info("Checking Python version...")
    if not check_python_version():
        v = f"{sys.version_info.major}.{sys.version_info.minor}"
        error(f"Python {v} is too old. Need 3.10+.")

    info("Python version OK")

    info("Checking disk space...")
    if not check_disk_space("."):
        warn("Low disk space — installation may fail")
    else:
        info("Disk space OK")

    info("Checking network...")
    if not check_network():
        warn("Cannot reach GitHub — download may fail. Use --mirror if needed.")
    else:
        info("Network OK")
