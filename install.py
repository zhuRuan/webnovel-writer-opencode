#!/usr/bin/env python3
"""
跨平台安装脚本 - Webnovel Writer for OpenCode
自动检测依赖、安装配置、增量更新 .env
"""

import os
import sys
import shutil
import subprocess
import platform
import urllib.request
from pathlib import Path
from typing import List, Optional

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"


# ---------- 自更新 ----------
def self_update():
    """从 GitHub 下载最新版本的安装脚本并替换"""
    script_path = Path(__file__).resolve()
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/install.py"
    
    try:
        log_info("检查更新...")
        tmp_file = script_path.parent / "install_new.py"
        urllib.request.urlretrieve(url, tmp_file)
        
        # 替换脚本
        tmp_file.replace(script_path)
        log_info("已更新到最新版本，重新运行...")
        
        # 重新执行新脚本
        subprocess.run([sys.executable, str(script_path)])
        sys.exit(0)
    except Exception as e:
        # 更新失败，继续使用当前版本
        log_warn(f"自更新失败，使用当前版本: {e}")


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
    """检查系统命令是否存在"""
    return shutil.which(cmd) is not None

def check_python_version():
    """检查 Python >= 3.9"""
    if sys.version_info < (3, 9):
        log_error(f"Python 版本需 >= 3.9，当前为 {sys.version_info.major}.{sys.version_info.minor}")

def check_dependencies():
    """检测 python3, pip"""
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
    """带重试的函数执行"""
    for attempt in range(1, max_attempts + 1):
        try:
            func()
            return True
        except Exception as e:
            if attempt < max_attempts:
                log_warn(f"失败，{delay}秒后重试 ({attempt}/{max_attempts}): {e}")
                import time
                time.sleep(delay)
            else:
                log_error(f"在 {max_attempts} 次尝试后仍失败: {e}")
    return False


# ---------- 远程下载 ----------
def download_file(url: str, dest: Path) -> bool:
    """从远程下载文件"""
    try:
        log_info(f"下载 {url} ...")
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        log_warn(f"下载失败: {e}")
        return False

def download_template():
    """从 GitHub 下载模板文件"""
    script_dir = Path(__file__).parent
    env_file = Path(".env")
    
    # 先保存用户现有的 .env（如果存在）
    user_env = {}
    if env_file.exists():
        log_info("保存用户现有的 .env 配置...")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _ = line.split('=', 1)
                    user_env[key] = line

    # 下载 .env 模板（存为 .env.tmp）
    env_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/.env"
    env_template = script_dir / ".env.tmp"
    if not download_file(env_url, env_template):
        log_error("无法下载 .env 模板")

    # 下载 requirements.txt
    req_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/requirements.txt"
    req_file = script_dir / "requirements.txt"
    if not download_file(req_url, req_file):
        log_warn("无法下载 requirements.txt")

    # 用用户配置合并模板
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
        # 删除临时模板
        env_template.unlink()
    else:
        # 没有用户配置，直接重命名
        env_template.rename(env_file)


# ---------- 文件操作 ----------
def remove_opencode():
    """删除旧的 .opencode 目录"""
    opencode_dir = Path(".opencode")
    if opencode_dir.exists():
        log_info("移除旧的 .opencode 目录...")
        shutil.rmtree(opencode_dir)

def download_opencode():
    """从 GitHub 下载并解压 .opencode 目录"""
    script_dir = Path(__file__).parent
    
    # 下载源码包
    zip_url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    zip_file = script_dir / "repo.zip"
    
    if not download_file(zip_url, zip_file):
        log_error("无法下载源码包")

    # 解压
    log_info("解压源码包...")
    import zipfile
    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(script_dir)
    zip_file.unlink()

    # 找到解压目录并复制 .opencode 到正确位置
    for item in script_dir.iterdir():
        if item.is_dir() and item.name.startswith("webnovel-writer"):
            opencode_src = item / ".opencode"
            if opencode_src.exists():
                log_info("安装 .opencode 配置...")
                # 先删除旧的 .opencode，再复制新的
                dest = Path(".opencode")
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(opencode_src, dest)
                # 删除解压目录
                shutil.rmtree(item)
                return
    
    log_error("解压后找不到 .opencode 目录")

def incremental_update_env():
    """增量更新 .env：已在 download_template 中处理"""
    # 此功能已集成到 download_template 中
    pass


# ---------- 依赖安装 ----------
def install_requirements():
    """安装 requirements.txt 中的依赖（带重试）"""
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

    # 清理临时下载的 requirements.txt
    if req_file.exists():
        req_file.unlink()
        log_info("已清理临时文件")


def maybe_install_playwright():
    """询问是否安装 playwright 浏览器（非交互模式下自动跳过）"""
    try:
        answer = input("是否安装 playwright 浏览器（用于发布功能）？[y/N] ").strip().lower()
    except EOFError:
        log_info("非交互模式，跳过 playwright 安装（如需安装，后续可运行: pip install playwright && playwright install chromium）")
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

    # 先自更新
    self_update()

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

if __name__ == "__main__":
    main()
