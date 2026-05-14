"""Terminal UI utilities for installer. Pure stdlib, no external deps."""
import re
import sys
import platform
import threading
import time

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
BOX_T = "┬"
BOX_B = "┴"
BOX_LT = "├"
BOX_RT = "┤"
BOX_VC = "┆"


def display_width(s: str) -> int:
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
        print(f"{color}{BOX_V}{Colors.NC} {' ' * left}{Colors.BOLD}{title}{Colors.NC}{' ' * (max_w + 2 - title_pad - left)} {color}{BOX_V}{Colors.NC}")
        print(f"{color}{BOX_LT}{BOX_H * (max_w + 2)}{BOX_RT}{Colors.NC}")
    for line in content:
        print(f"{color}{BOX_V}{Colors.NC} {_pad_to(line, max_w)} {color}{BOX_V}{Colors.NC}")
    print(bottom)
    print()


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
    print(f"\n{Colors.RED}{Colors.BOLD}  ✗ ERROR{Colors.NC} {msg}")
    sys.exit(1)


def success(title: str, lines: list[str] = []):
    """Print a success box."""
    content = [title]
    if lines:
        content.append("")
        content.extend(lines)
    box(content, title="", color=Colors.GREEN)


def spinner_thread(msg: str, stop_event: threading.Event):
    """Run a spinner animation. Set stop_event to terminate."""
    frames = ["◐", "◓", "◑", "◒"]
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r  {Colors.CYAN}{frames[i]}{Colors.NC} {msg}")
        sys.stdout.flush()
        i = (i + 1) % len(frames)
        time.sleep(0.15)
    sys.stdout.write(f"\r  {Colors.GREEN}✓{Colors.NC} {msg}    \n")
    sys.stdout.flush()


def spinner(msg: str):
    """Context manager for spinner animation.
    Usage:
        with spinner("Installing..."):
            run_slow_operation()
    """
    class SpinnerCtx:
        def __init__(self, msg):
            self._stop = threading.Event()
            self._thread = threading.Thread(target=spinner_thread, args=(msg, self._stop))
        def __enter__(self):
            self._thread.start()
            return self
        def __exit__(self, *args):
            self._stop.set()
            self._thread.join(timeout=0.5)

    return SpinnerCtx(msg)
