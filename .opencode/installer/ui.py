"""Terminal UI utilities for installer. Pure stdlib, no external deps.

注意：install.py 有独立的内联 UI 实现（自举需要），此文件供安装后模块使用。
两者的函数签名和视觉效果保持一致。
"""
import re
import sys
import platform
import threading
import time
from contextlib import contextmanager

_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class Colors:
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    NC = '\033[0m'


# Box-drawing characters
BOX_H = "─"
BOX_V = "│"
BOX_TL = "┌"
BOX_TR = "┐"
BOX_BL = "└"
BOX_BR = "┘"
BOX_LT = "├"
BOX_RT = "┤"

# Default box width
BOX_W = 52


def display_width(s: str) -> int:
    """Calculate display width of string (CJK=2, ASCII=1), ignoring ANSI escapes."""
    clean = _ANSI_ESCAPE_RE.sub('', s)
    w = 0
    for ch in clean:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            w += 2
        else:
            w += 1
    return w


def _pad_to(s: str, w: int) -> str:
    """Pad string to display width w with spaces."""
    dw = display_width(s)
    return s + ' ' * (w - dw) if dw < w else s


# ---------------------------------------------------------------------------
# Simple box (single call)
# ---------------------------------------------------------------------------

def box(content: list[str], title: str = "", color: str = Colors.CYAN):
    """Print a Unicode box with optional title."""
    max_w = max((display_width(line) for line in content), default=0)
    if title:
        max_w = max(max_w, display_width(title) + 4)
    max_w = max(max_w, 40)

    top = f"{color}{BOX_TL}{BOX_H * (max_w + 2)}{BOX_TR}{Colors.NC}"
    bottom = f"{color}{BOX_BL}{BOX_H * (max_w + 2)}{BOX_BR}{Colors.NC}"

    print()
    print(top)
    if title:
        title_pad = display_width(title)
        left = (max_w + 2 - title_pad) // 2
        print(f"{color}{BOX_V}{Colors.NC} {' ' * left}{Colors.BOLD}{title}{Colors.NC}"
              f"{' ' * (max_w + 2 - title_pad - left)} {color}{BOX_V}{Colors.NC}")
        print(f"{color}{BOX_LT}{BOX_H * (max_w + 2)}{BOX_RT}{Colors.NC}")
    for line in content:
        print(f"{color}{BOX_V}{Colors.NC} {_pad_to(line, max_w)} {color}{BOX_V}{Colors.NC}")
    print(bottom)
    print()


# ---------------------------------------------------------------------------
# Incremental box (row-by-row, used by install.py interactive menus)
# ---------------------------------------------------------------------------

def box_open(width: int = BOX_W, color: str = Colors.CYAN):
    """Print the top border of a box."""
    print(f"\n{color}{BOX_TL}{BOX_H * (width + 2)}{BOX_TR}{Colors.NC}")


def box_close(width: int = BOX_W, color: str = Colors.CYAN):
    """Print the bottom border of a box."""
    print(f"{color}{BOX_BL}{BOX_H * (width + 2)}{BOX_BR}{Colors.NC}")


def box_sep(width: int = BOX_W, color: str = Colors.CYAN):
    """Print a horizontal separator inside a box."""
    print(f"{color}{BOX_LT}{BOX_H * (width + 2)}{BOX_RT}{Colors.NC}")


def box_row(text: str, width: int = BOX_W, color: str = "",
            right: str = "", box_color: str = Colors.CYAN):
    """Print a row inside a box: │ content │"""
    content = color + text + Colors.NC + right if color else text + right
    print(f"{box_color}{BOX_V}{Colors.NC} {_pad_to(content, width)} {box_color}{BOX_V}{Colors.NC}")


# ---------------------------------------------------------------------------
# Headers, steps, info
# ---------------------------------------------------------------------------

def header(title: str):
    """Print a centered bold header line."""
    w = display_width(title)
    bar = "═" * (w + 4)
    print(f"\n{Colors.BOLD}{Colors.CYAN}{bar}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{bar}{Colors.NC}\n")


def step(step_num: int, total: int, msg: str):
    """Print a step indicator."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}  [{step_num}/{total}]{Colors.NC} {msg}")
    print(f"  {Colors.DIM}{'─' * 50}{Colors.NC}")


def step_ok(step_num: int, total: int, msg: str):
    """Print a completed step."""
    print(f"{Colors.GREEN}  [{step_num}/{total}] ✓{Colors.NC} {msg}")


def step_warn(msg: str):
    """Print a step warning."""
    print(f"  {Colors.YELLOW}⚠{Colors.NC}  {msg}")


def info(msg: str):
    print(f"  {Colors.DIM}▸{Colors.NC} {msg}")


def warn(msg: str):
    print(f"  {Colors.YELLOW}⚠  {msg}{Colors.NC}")


def error(msg: str):
    print(f"\n{Colors.RED}{Colors.BOLD}  ✗ 错误{Colors.NC} {msg}")
    sys.exit(1)


def success(title: str, lines: list[str] = None):
    """Print a success box."""
    if lines is None:
        lines = []
    content = [title]
    if lines:
        content.append("")
        content.extend(lines)
    box(content, title="", color=Colors.GREEN)


# ---------------------------------------------------------------------------
# Download progress bar
# ---------------------------------------------------------------------------

def download_progress(resp, dest_path, label: str = "下载中"):
    """Download from urllib response with a progress bar."""
    total = int(resp.headers.get("Content-Length", 0) or 0)
    downloaded = 0
    last_pct = -1

    with open(dest_path, 'wb') as f:
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)

            if total:
                pct = downloaded * 100 // total
                if pct != last_pct:
                    bar_len = 30
                    filled = pct * bar_len // 100
                    bar = "█" * filled + "░" * (bar_len - filled)
                    size_mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    sys.stdout.write(
                        f"\r  {Colors.CYAN}{label}{Colors.NC} "
                        f"[{bar}] {pct}%  "
                        f"{Colors.DIM}{size_mb:.1f}/{total_mb:.1f} MB{Colors.NC}"
                    )
                    sys.stdout.flush()
                    last_pct = pct

    if total:
        print()
    else:
        size_mb = downloaded / (1024 * 1024)
        print(f"  {Colors.GREEN}✓{Colors.NC} {label}  "
              f"{Colors.DIM}{size_mb:.1f} MB{Colors.NC}")


# ---------------------------------------------------------------------------
# Spinner with state
# ---------------------------------------------------------------------------

def _spinner_thread(msg: str, stop_event: threading.Event):
    """Run a spinner animation. Set stop_event to terminate."""
    frames = ["◐", "◓", "◑", "◒"]
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r  {Colors.CYAN}{frames[i]}{Colors.NC} {msg}")
        sys.stdout.flush()
        i = (i + 1) % len(frames)
        time.sleep(0.15)
    sys.stdout.write(f"\r{' ' * (display_width(msg) + 10)}\r")
    sys.stdout.flush()


@contextmanager
def spinner(msg: str):
    """Context manager for spinner animation.

    Prints ✓ on success, ✗ on exception.

    Usage:
        with spinner("安装中..."):
            run_slow_operation()
    """
    stop = threading.Event()
    thread = threading.Thread(target=_spinner_thread, args=(msg, stop), daemon=True)
    thread.start()
    try:
        yield
        stop.set()
        thread.join(timeout=0.5)
        sys.stdout.write(f"\r  {Colors.GREEN}✓{Colors.NC} {msg}\n")
        sys.stdout.flush()
    except Exception:
        stop.set()
        thread.join(timeout=0.5)
        sys.stdout.write(f"\r  {Colors.RED}✗{Colors.NC} {msg}\n")
        sys.stdout.flush()
        raise
