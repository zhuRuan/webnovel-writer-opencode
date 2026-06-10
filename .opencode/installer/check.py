"""系统预检模块。纯标准库，无外部依赖。"""
import os
import sys
import shutil
import subprocess
import platform as _platform

from installer.ui import info, warn, error, success, Colors

KNOWN_OPENCODE_PROCESSES = {
    "windows": ["OpenCode.exe"],
    "linux":   [],
    "darwin":  ["OpenCode"],
}


def platform_name() -> str:
    """返回标准化平台名: windows, linux, darwin。"""
    s = _platform.system()
    if s == "Windows":
        return "windows"
    elif s == "Linux":
        return "linux"
    elif s == "Darwin":
        return "darwin"
    return s.lower()


def check_python_version(version: tuple = None) -> bool:
    """检查 Python 版本是否满足最低要求 (3.10)。"""
    if version is None:
        version = (sys.version_info.major, sys.version_info.minor)
    return version >= (3, 10)


def check_disk_space(path: str, required_mb: int = 50) -> bool:
    """检查磁盘可用空间。"""
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= required_mb
    except Exception:
        return True  # 无法检查时不阻断


def check_network(timeout: int = 5) -> bool:
    """检查是否能访问 GitHub。"""
    import urllib.request
    try:
        urllib.request.urlopen("https://github.com", timeout=timeout)
        return True
    except Exception:
        return False


def is_opencode_running(target_dir: str = ".opencode") -> str:
    """检查 OpenCode 是否正在运行。返回 'running', 'not_running', 'locked'。

    层级 1: 进程名扫描 (全平台)
    层级 2: 文件锁检测 (Windows: os.rename, macOS/Linux: lsof/fuser)
    """
    pname = platform_name()

    # 层级 1: 进程扫描
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
            result = subprocess.run(
                ["pgrep", "-i", "OpenCode"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            found = result.returncode == 0
    except Exception:
        pass  # 进程扫描失败，尝试锁检测

    # 层级 2: 文件锁检测
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
        if os.path.isdir(target_dir):
            locked = _check_open_files_non_windows(target_dir)
            if locked:
                return "locked"
            return "not_running" if not found else "running"
        else:
            return "not_running"


def _check_open_files_non_windows(target_dir: str) -> bool:
    """检查是否有进程持有 target_dir 下的文件 (macOS/Linux)。"""
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
    """运行全部预检项目，输出汇总结果。"""
    results = []

    info("检查 Python 版本...")
    ok = check_python_version()
    if not ok:
        v = f"{sys.version_info.major}.{sys.version_info.minor}"
        error(f"Python {v} 版本过低，需要 3.10+。请升级 Python 后重试。")
    results.append(("Python 版本", ok))

    info("检查磁盘空间...")
    ok = check_disk_space(".")
    if not ok:
        warn("磁盘空间不足，安装可能失败")
    results.append(("磁盘空间", ok))

    info("检查网络连接...")
    ok = check_network()
    if not ok:
        warn("无法访问 GitHub，下载可能失败。可使用 --mirror 指定镜像。")
    results.append(("网络连接", ok))

    # 汇总
    print()
    all_ok = True
    for name, passed in results:
        icon = f"{Colors.GREEN}✓{Colors.NC}" if passed else f"{Colors.RED}✗{Colors.NC}"
        info(f"{icon} {name}")
        if not passed:
            all_ok = False

    if all_ok:
        success("预检全部通过")
    else:
        warn("部分检查未通过，安装可能遇到问题")
