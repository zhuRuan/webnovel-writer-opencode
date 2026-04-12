#!/usr/bin/env python3
"""
跨平台安装脚本 - Webnovel Writer for OpenCode
自动检测依赖、安装配置、增量更新 .env
"""

import sys
import shutil
import subprocess
import platform
import zipfile
import urllib.request
import time
import re
from pathlib import Path

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"

# ---------- Windows 控制台初始化 ----------
if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # 启用虚拟终端序列 (ANSI 转义) 支持
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
    # 确保输出编码为 UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ---------- 颜色定义 ----------
class Colors:
    if platform.system() == "Windows":
        # Windows 下虚拟终端支持后也可使用 ANSI
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        NC = '\033[0m'
    else:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        NC = '\033[0m'

# ---------- 宽度计算（修复边框对齐） ----------
ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def display_width(s: str) -> int:
    """
    计算字符串在终端中的显示宽度（中文占2，英文占1），
    并自动忽略不可见的 ANSI 颜色转义序列。
    """
    clean = ANSI_ESCAPE_RE.sub('', s)
    width = 0
    for ch in clean:
        # 中文、全角符号等通常占2个英文字符宽度
        if ('\u4e00' <= ch <= '\u9fff' or
            '\u3000' <= ch <= '\u303f' or
            '\uff00' <= ch <= '\uffef'):
            width += 2
        else:
            width += 1
    return width

def pad_to_width(text: str, target_width: int) -> str:
    """在右侧填充空格以达到目标显示宽度（保留颜色代码）"""
    current = display_width(text)
    return text + ' ' * (target_width - current)

# ---------- 输出辅助函数 ----------
PROGRESS_BAR_WIDTH = 20

def print_progress_bar(current: int, total: int) -> str:
    filled = int((current / total) * PROGRESS_BAR_WIDTH)
    empty = PROGRESS_BAR_WIDTH - filled
    bar = f"{Colors.GREEN}{'█' * filled}{Colors.NC}{'░' * empty}"
    return f"[{bar}] {current}/{total}"

def log_info(msg: str, icon: str = "•"):
    print(f"  {Colors.GREEN}{icon}{Colors.NC} {msg}")

def log_warn(msg: str):
    print(f"  {Colors.YELLOW}⚠{Colors.NC} {msg}")

def log_error(msg: str):
    print(f"  {Colors.RED}✗{Colors.NC} {msg}")
    sys.exit(1)

def print_header(title: str):
    title_w = display_width(title)
    inner_width = title_w + 4
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}┏{'━' * inner_width}┓{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}┃{Colors.NC}  {Colors.BOLD}{title}{Colors.NC}  {Colors.BOLD}{Colors.CYAN}┃{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}┗{'━' * inner_width}┛{Colors.NC}")
    print()

def print_step(step: int, total: int, msg: str):
    bar = print_progress_bar(step, total)
    print(f"\n{Colors.BOLD}{Colors.BLUE}⏳ Step {step}/{total}{Colors.NC} {bar}")
    print(f"  {Colors.CYAN}→{Colors.NC} {msg}")

def print_step_done(step: int, total: int, msg: str):
    bar = print_progress_bar(step, total)
    print(f"\n{Colors.BOLD}{Colors.GREEN}✅ Step {step}/{total}{Colors.NC} {bar}")
    print(f"  {Colors.GREEN}✓{Colors.NC} {msg}")

def print_success_box(title: str, lines: list):
    max_len = max(display_width(title), max(display_width(l) for l in lines)) + 2
    print()
    print(f"{Colors.GREEN}┏{'━' * max_len}┓{Colors.NC}")
    print(f"{Colors.GREEN}┃{Colors.NC} {pad_to_width(Colors.BOLD + title + Colors.NC, max_len - 1)} {Colors.GREEN}┃{Colors.NC}")
    print(f"{Colors.GREEN}┣{'━' * max_len}┫{Colors.NC}")
    for line in lines:
        print(f"{Colors.GREEN}┃{Colors.NC} {pad_to_width(line, max_len - 1)} {Colors.GREEN}┃{Colors.NC}")
    print(f"{Colors.GREEN}┗{'━' * max_len}┛{Colors.NC}")
    print()

def print_manual_box(title: str, lines: list):
    max_len = max(display_width(title), max(display_width(l) for l in lines)) + 2
    print()
    print(f"{Colors.YELLOW}┏{'━' * max_len}┓{Colors.NC}")
    print(f"{Colors.YELLOW}┃{Colors.NC} {pad_to_width(Colors.BOLD + Colors.YELLOW + title + Colors.NC, max_len - 1)} {Colors.YELLOW}┃{Colors.NC}")
    print(f"{Colors.YELLOW}┣{'━' * max_len}┫{Colors.NC}")
    for line in lines:
        print(f"{Colors.YELLOW}┃{Colors.NC} {pad_to_width(line, max_len - 1)} {Colors.YELLOW}┃{Colors.NC}")
    print(f"{Colors.YELLOW}┗{'━' * max_len}┛{Colors.NC}")
    print()

# ---------- 依赖检测 ----------
def check_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def check_python_version():
    if sys.version_info < (3, 9):
        log_error(f"Python 版本需 >= 3.9，当前为 {sys.version_info.major}.{sys.version_info.minor}")

def check_dependencies():
    missing = []
    if not check_command("python"):
        missing.append("python")
    if not check_command("pip"):
        missing.append("pip")
    if missing:
        log_error(f"缺少以下依赖: {', '.join(missing)}")
    check_python_version()
    log_info("Python 3.9+ ✓, pip ✓")

# ---------- 重试装饰器 ----------
def retry(func, max_attempts=3, delay=5):
    for attempt in range(1, max_attempts + 1):
        try:
            func()
            return True
        except Exception:
            if attempt < max_attempts:
                log_warn(f"失败，{delay}秒后重试 ({attempt}/{max_attempts})")
                time.sleep(delay)
            else:
                log_error(f"在 {max_attempts} 次尝试后仍失败")
    return False

# ---------- 远程下载 ----------
def download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    try:
        log_info(f"下载 {url.split('/')[-1]} ...", "↓")
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with open(dest, 'wb') as f:
                shutil.copyfileobj(response, f)
        return True
    except Exception as e:
        log_warn(f"下载失败: {e}")
        return False

def download_template(timeout: int = 30):
    script_dir = Path(__file__).parent
    env_file = Path(".env")
    
    user_env = {}
    if env_file.exists():
        log_info("保存现有 .env 配置...")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _ = line.split('=', 1)
                    user_env[key] = line

    env_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/.env"
    env_template = script_dir / ".env.tmp"
    if not download_file(env_url, env_template, timeout):
        log_error("无法下载 .env 模板")

    req_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/requirements.txt"
    req_file = script_dir / "requirements.txt"
    if not download_file(req_url, req_file, timeout):
        log_warn("无法下载 requirements.txt")

    if user_env:
        log_info("合并用户配置 (保留 API Key)...")
        with open(env_template, 'r', encoding='utf-8') as t:
            with open(env_file, 'w', encoding='utf-8') as f:
                for line in t:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _ = line.split('=', 1)
                        if key in user_env:
                            f.write(f"{user_env[key]}\n")
                        else:
                            f.write(f"{line}\n")
                    else:
                        f.write(f"{line}\n")
        log_info(".env 已更新 (保留原有配置)")
        env_template.unlink()
    else:
        env_template.rename(env_file)
        log_info(".env 模板已创建")

# ---------- 文件操作 ----------
def download_opencode(timeout: int = 30):
    script_dir = Path(__file__).parent
    
    temp_dest = Path(".opencode_new")
    if temp_dest.exists():
        shutil.rmtree(temp_dest)
    
    zip_url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    zip_file = script_dir / "repo.zip"
    
    if not download_file(zip_url, zip_file, timeout):
        log_error("无法下载源码包")

    log_info("解压源码包...")
    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(script_dir)
    zip_file.unlink()

    dest = Path(".opencode")
    for item in script_dir.iterdir():
        if item.is_dir() and item.name.startswith("webnovel-writer"):
            opencode_src = item / ".opencode"
            if opencode_src.exists():
                log_info("准备安装 .opencode 目录...")
                
                if temp_dest.exists():
                    shutil.rmtree(temp_dest)
                shutil.copytree(opencode_src, temp_dest)
                shutil.rmtree(item)
                
                try:
                    if dest.exists():
                        shutil.rmtree(dest)
                    temp_dest.rename(dest)
                    log_info(".opencode 安装成功")
                except PermissionError:
                    print_manual_box("需要手动操作", [
                        "OpenCode 正在运行，无法直接更新",
                        "",
                        "请执行以下步骤：",
                        "1. 关闭 OpenCode",
                        "2. 删除 .opencode 目录",
                        "3. 将 .opencode_new 重命名为 .opencode"
                    ])
                except OSError as e:
                    log_warn(f"删除旧目录时出错: {e}")
                    print_manual_box("需要手动操作", [
                        f"删除旧目录失败: {e}",
                        "",
                        "请执行以下步骤：",
                        "1. 删除 .opencode 目录",
                        "2. 将 .opencode_new 重命名为 .opencode"
                    ])
                return
    
    log_error("解压后找不到 .opencode 目录")

# ---------- 依赖安装 ----------
def install_requirements():
    script_dir = Path(__file__).parent
    req_file = script_dir / "requirements.txt"
    if not req_file.exists():
        log_warn("未找到 requirements.txt，跳过")
        return
    log_info("后台安装 Python 依赖 (pip install -r requirements.txt)...")
    
    import threading
    
    def install_in_background():
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                check=True,
                cwd=script_dir,
                capture_output=True
            )
            if req_file.exists():
                req_file.unlink()
        except Exception:
            pass
    
    thread = threading.Thread(target=install_in_background, daemon=True)
    thread.start()
    time.sleep(0.5)

def maybe_install_playwright():
    if not sys.stdin.isatty():
        log_info("非交互模式，跳过 playwright 安装")
        return
    try:
        answer = input(f"  {Colors.CYAN}?{Colors.NC} 是否安装 playwright 浏览器（用于发布功能）？[y/N] ").strip().lower()
    except EOFError:
        log_info("非交互模式，跳过 playwright 安装")
        return

    if answer in ('y', 'yes'):
        log_info("安装 playwright 及 chromium...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

        def install_chromium():
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

        retry(install_chromium)
        log_info("playwright 安装完成")
    else:
        log_info("跳过 playwright 安装")

# ---------- 主流程 ----------
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Webnovel Writer for OpenCode 安装脚本')
    parser.add_argument('--yes', '-y', action='store_true', help='自动确认所有交互')
    parser.add_argument('--skip-playwright', action='store_true', help='跳过 playwright 安装')
    parser.add_argument('--timeout', '-t', type=int, default=30, help='网络下载超时秒数（默认30）')
    args = parser.parse_args()

    print_header("Webnovel Writer for OpenCode")

    total_steps = 4
    step = 1
    print_step(step, total_steps, "检查系统依赖")
    check_dependencies()
    print_step_done(step, total_steps, "系统依赖检查通过")

    step = 2
    print_step(step, total_steps, "下载配置文件 (.env, requirements.txt)")
    download_template(args.timeout)
    print_step_done(step, total_steps, "配置文件就绪")

    step = 3
    print_step(step, total_steps, "安装 .opencode 核心文件")
    download_opencode(args.timeout)
    print_step_done(step, total_steps, ".opencode 安装完成")

    step = 4
    print_step(step, total_steps, "安装 Python 依赖")
    install_requirements()
    print_step_done(step, total_steps, "Python 依赖后台安装中")

    if args.skip_playwright or args.yes:
        log_info("跳过 playwright 安装（--yes 或 --skip-playwright 模式）")
    else:
        maybe_install_playwright()

    print_success_box("✓ 安装完成！", [
        "后续步骤:",
        "  1. 编辑 .env 文件，填入您的 API Key",
        "     - ModelScope: https://modelscope.cn/my/settings",
        "     - Jina AI: https://jina.ai/",
        "  2. 重启 OpenCode",
        "  3. 运行 /webnovel-init 开始新项目",
        "",
        f"{Colors.GREEN}提示:{Colors.NC} 安装脚本已运行完成，您可以手动删除 install.py"
    ])

if __name__ == "__main__":
    main()