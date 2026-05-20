"""System preflight checks. Pure stdlib, no external deps."""
import os
import sys
import shutil
import subprocess
import platform as _platform

from installer.ui import info, warn, error

KNOWN_OPENCODE_PROCESSES = {
    "windows": ["OpenCode.exe"],
    "linux":   [],
    "darwin":  ["OpenCode"],
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
    Layer 2: File lock detection (Windows: os.rename, macOS/Linux: lsof/fuser)
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
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=5)
                found = any(p.lower() in result.stdout.lower() for p in procs)
        elif pname == "linux":
            result = subprocess.run(
                ["pgrep", "-f", "opencode"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            found = result.returncode == 0
        elif pname == "darwin":
            # ps aux | grep OpenCode (not Electron — too many false matches)
            result = subprocess.run(
                ["pgrep", "-i", "OpenCode"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            found = result.returncode == 0
    except Exception:
        pass  # Process scan failed, try lock test

    # Layer 2: file lock test
    if pname == "windows":
        if os.path.isdir(target_dir):
            lock_test = target_dir + "_lock_test"
            try:
                os.rename(target_dir, lock_test)
                os.rename(lock_test, target_dir)
                return "not_running" if not found else "running"
            except OSError:
                return "locked"
        else:
            return "not_running"
    else:
        # macOS / Linux: use lsof to see if any process holds files in .opencode/
        if os.path.isdir(target_dir):
            locked = _check_open_files_non_windows(target_dir)
            if locked:
                return "locked"
            return "not_running" if not found else "running"
        else:
            return "not_running"


def _check_open_files_non_windows(target_dir: str) -> bool:
    """Check if any process has files open under target_dir (macOS/Linux)."""
    # Try lsof first (available on macOS, often on Linux)
    if shutil.which("lsof"):
        try:
            result = subprocess.run(
                ["lsof", "+D", os.path.abspath(target_dir)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass

    # Fallback: fuser (Linux)
    if shutil.which("fuser"):
        try:
            result = subprocess.run(
                ["fuser", target_dir],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass

    return False


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
