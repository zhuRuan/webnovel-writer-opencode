"""Terminal UI utilities for installer. Pure stdlib, no external deps."""
import re
import sys
import platform

_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


# ---------- color constants ----------
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
    BOLD = '\033[1m'
    NC = '\033[0m'


def display_width(s: str) -> int:
    """Calculate terminal display width. CJK chars count as 2, ASCII as 1."""
    clean = _ANSI_ESCAPE_RE.sub('', s)
    w = 0
    for ch in clean:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            w += 2
        else:
            w += 1
    return w


def step_header(step: int, total: int, msg: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}[Step {step}/{total}]{Colors.NC} {msg}")


def step_done(step: int, total: int, msg: str):
    print(f"{Colors.GREEN}[Step {step}/{total} done]{Colors.NC} {msg}")


def info(msg: str):
    print(f"  {Colors.GREEN}*{Colors.NC} {msg}")


def warn(msg: str):
    print(f"  {Colors.YELLOW}[WARN]{Colors.NC} {msg}")


def error(msg: str):
    """Print error and exit."""
    print(f"\n{Colors.RED}[ERROR]{Colors.NC} {msg}")
    sys.exit(1)


def success_box(title: str, lines: list):
    max_len = max(display_width(title), max((display_width(l) for l in lines), default=0)) + 2
    print()
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    print(f"  {Colors.BOLD}{title}{Colors.NC}")
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    for line in lines:
        print(f"  {line}")
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    print()
