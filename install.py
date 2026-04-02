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
from pathlib import Path

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"


# ---------- 颜色输出（支持 Windows） ----------
class Colors:
    if platform.system() == "Windows":
        GREEN = ''
        RED = ''
        YELLOW = ''
        NC = ''
    else:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        NC = '\033[0m'

def log_info(msg: str):
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {msg}")

def log_warn(msg: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")

def log_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")
    sys.exit(1)


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
    log_info("依赖检测通过")


# ---------- 重试装饰器 ----------
def retry(func, max_attempts=3, delay=5):
    for attempt in range(1, max_attempts + 1):
        try:
            func()
            return True
        except Exception:
            if attempt < max_attempts:
                log_warn(f"失败，{delay}秒后重试 ({attempt}/{max_attempts})")
                import time
                time.sleep(delay)
            else:
                log_error(f"在 {max_attempts} 次尝试后仍失败")
    return False


# ---------- 远程下载 ----------
def download_file(url: str, dest: Path) -> bool:
    try:
        log_info(f"下载 {url} ...")
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        log_warn(f"下载失败: {e}")
        return False

def download_template():
    script_dir = Path(__file__).parent
    env_file = Path(".env")
    
    # 保存用户现有的 .env 配置
    user_env = {}
    if env_file.exists():
        log_info("保存用户现有的 .env 配置...")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _ = line.split('=', 1)
                    user_env[key] = line

    # 下载 .env 模板
    env_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/.env"
    env_template = script_dir / ".env.tmp"
    if not download_file(env_url, env_template):
        log_error("无法下载 .env 模板")

    # 下载 requirements.txt
    req_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/requirements.txt"
    req_file = script_dir / "requirements.txt"
    if not download_file(req_url, req_file):
        log_warn("无法下载 requirements.txt")

    # 合并用户配置（增量更新 .env）
    if user_env:
        log_info("合并用户配置...")
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
        log_info(".env 已更新（保留您的 API Key）")
        env_template.unlink()
    else:
        env_template.rename(env_file)


# ---------- 文件操作 ----------
def download_opencode():
    script_dir = Path(__file__).parent
    
    # 下载源码包
    zip_url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    zip_file = script_dir / "repo.zip"
    
    if not download_file(zip_url, zip_file):
        log_error("无法下载源码包")

    # 解压
    log_info("解压源码包...")
    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(script_dir)
    zip_file.unlink()

    # 找到解压目录并覆盖安装 .opencode
    dest = Path(".opencode")
    for item in script_dir.iterdir():
        if item.is_dir() and item.name.startswith("webnovel-writer"):
            opencode_src = item / ".opencode"
            if opencode_src.exists():
                log_info("覆盖安装 .opencode 配置...")
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(opencode_src, dest)
                shutil.rmtree(item)
                return
    
    log_error("解压后找不到 .opencode 目录")


# ---------- 依赖安装 ----------
def install_requirements():
    script_dir = Path(__file__).parent
    req_file = script_dir / "requirements.txt"
    if not req_file.exists():
        log_warn("未找到 requirements.txt，跳过")
        return
    log_info("安装 Python 依赖...")

    def install():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            check=True,
            cwd=script_dir
        )

    retry(install)

    if req_file.exists():
        req_file.unlink()
        log_info("已清理临时文件")


def maybe_install_playwright():
    try:
        answer = input("是否安装 playwright 浏览器（用于发布功能）？[y/N] ").strip().lower()
    except EOFError:
        log_info("非交互模式，跳过 playwright 安装")
        return

    if answer in ('y', 'yes'):
        log_info("安装 playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

        def install_chromium():
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

        retry(install_chromium)
        log_info("playwright 安装完成")
    else:
        log_info("跳过 playwright 安装")


# ---------- 主流程 ----------
def main():
    print("=" * 50)
    print("  Webnovel Writer for OpenCode 安装脚本")
    print("=" * 50)
    print()

    check_dependencies()

    download_template()
    download_opencode()
    install_requirements()
    maybe_install_playwright()

    print()
    print("=" * 50)
    print("  安装完成！")
    print("=" * 50)
    print()
    print("后续步骤:")
    print("  1. 编辑 .env 文件，填入您的 API Key")
    print("     - ModelScope: https://modelscope.cn/my/settings")
    print("     - Jina AI: https://jina.ai/")
    print("  2. 重启 OpenCode")
    print("  3. 运行 /webnovel-init 开始新项目")
    print()

    # 自删除安装脚本
    script_path = Path(__file__).resolve()
    try:
        script_path.unlink()
    except Exception:
        pass

if __name__ == "__main__":
    main()
