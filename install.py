#!/usr/bin/env python3
"""
Webnovel Writer for OpenCode — one-click installer.
Downloads .opencode/ from GitHub and sets up the writing toolchain.

Usage:
  python install.py                    # Interactive menu (recommended)
  python install.py --update           # Check and apply updates
  python install.py --clean            # Wipe .opencode/ then fresh install
  python install.py --incremental      # Incremental update (manifest diff)
  python install.py --apply            # Apply staged update (after closing OpenCode)
  python install.py --uninstall        # Remove .opencode/ (keep project files)
  python install.py --uninstall --full # Full uninstall: .opencode/ + .venv/ + deps
  python install.py --venv             # Create and use .venv/
  python install.py --skip-playwright  # Skip browser install
  python install.py --mirror URL       # Use custom GitHub mirror
"""
import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"
MIRRORS = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
]

def build_urls(repo, branch, custom_mirror=None):
    mirrors = [custom_mirror] if custom_mirror else MIRRORS
    direct = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    urls = [direct]
    for m in mirrors:
        urls.append(f"{m.rstrip('/')}/{direct}")
    return urls


def download(urls, dest, timeout=30):
    for url in urls:
        try:
            print(f"  Downloading {url.rsplit('/', 1)[-1]} ...")
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                with open(dest, 'wb') as f:
                    shutil.copyfileobj(resp, f)
            return True
        except Exception as e:
            print(f"  Failed: {e}")
    return False


def extract_opencode(zip_path, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        prefix = ""
        for name in names:
            if '/' in name and not name.startswith('__'):
                prefix = name.split('/')[0] + '/'
                break

        op_prefix = prefix + ".opencode/"
        for name in names:
            if name.startswith(op_prefix):
                rel = name[len(op_prefix):]
                if not rel:
                    continue
                target = dest_dir / rel
                if name.endswith('/'):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)


def interactive_menu(args):
    installed = Path(".opencode").is_dir()
    staging = Path(".opencode_staging").is_dir()

    version = "未知"
    vf = Path(".opencode/version.json")
    if vf.is_file():
        import json
        try:
            version = json.loads(vf.read_text(encoding="utf-8")).get("version", "未知")
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("  Webnovel Writer for OpenCode — 安装管理")
    print("=" * 60)
    if installed:
        print(f"  状态: 已安装 ({version})")
    else:
        print(f"  状态: 未安装")
    if staging:
        print(f"  有暂存更新待应用")
    print("-" * 60)
    print()
    print("  请选择操作:")
    print()
    print("  [1] 安装 / 更新        下载最新版本并安装")
    print("  [2] 增量更新            仅更新变更文件 (快)")
    print("  [3] 清洁安装            擦除后全新安装")
    if staging:
        print("  [4] 应用暂存更新        关闭 IDE 后执行两阶段更新")
    print("  [5] 卸载                移除 .opencode/")
    print("  [6] 完全卸载            移除 .opencode/ + .venv/")
    print("  [0] 退出")
    print()

    try:
        choice = input("  输入数字选择 (默认=1): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消。")
        return

    if not choice:
        choice = "1"

    if choice == "1":
        if installed:
            args.update = True
    elif choice == "2":
        args.incremental = True
    elif choice == "3":
        args.clean = True
    elif choice == "4" and staging:
        args.apply = True
    elif choice == "5":
        args.uninstall = True
    elif choice == "6":
        args.uninstall = True
        args.full = True
        args.yes = True
    elif choice == "0":
        print("  已取消。")
        return
    else:
        print(f"  无效选择: {choice}")
        return

    run_selected_action(args)


def run_selected_action(args):
    """Execute the action selected from menu or CLI flags."""
    cwd = Path.cwd()
    opencode_dir = cwd / ".opencode"

    if getattr(args, 'uninstall', False):
        print("\n" + "=" * 60)
        print("  Webnovel Writer — 卸载")
        print("=" * 60 + "\n")
        sys.path.insert(0, str(opencode_dir))
        from installer.uninstall import cmd_uninstall
        cmd_uninstall(args)
        return

    if getattr(args, 'apply', False):
        print("\n--- Apply Staged Update ---\n")
        installer_dir = Path(".opencode/installer")
        if not installer_dir.is_dir():
            print("Downloading installer modules...")
            urls = build_urls(REPO, BRANCH, args.mirror)
            zip_path = Path(tempfile.gettempdir()) / "webnovel_installer.zip"
            if not download(urls, zip_path, getattr(args, 'timeout', 30)):
                print("[ERROR] Cannot download installer. Check network.")
                sys.exit(1)
            extract_opencode(zip_path, Path(".opencode"))
            zip_path.unlink(missing_ok=True)

        sys.path.insert(0, str(opencode_dir))
        from installer.preflight import apply_staging
        if apply_staging():
            print("\nUpdate applied. You can now reopen OpenCode.")
        else:
            sys.exit(1)
        return

    if getattr(args, 'clean', False):
        for d in [opencode_dir, Path(".opencode_staging"), Path(".opencode_backup")]:
            if d.is_dir():
                print(f"  Clean: removing {d}/")
                shutil.rmtree(str(d))

    print("\n" + "=" * 60)
    print("  Webnovel Writer for OpenCode — Installer")
    print("=" * 60 + "\n")

    print("[1/3] Downloading latest version...")
    urls = build_urls(REPO, BRANCH, getattr(args, 'mirror', None))
    zip_path = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"

    if not download(urls, zip_path, getattr(args, 'timeout', 30)):
        print("[ERROR] Download failed. Check network or use --mirror URL.")
        sys.exit(1)

    sys.path.insert(0, str(opencode_dir))
    print("[2/3] Extracting...")

    if getattr(args, 'incremental', False) and opencode_dir.is_dir():
        from installer.update import run_incremental_update
        extract_opencode(zip_path, Path(".opencode_staging"))
        run_incremental_update()
        Path(zip_path).unlink(missing_ok=True)
    else:
        extract_opencode(zip_path, opencode_dir)
        Path(zip_path).unlink(missing_ok=True)
        print("  Done.\n")

    from installer.preflight import run_install, run_update

    if getattr(args, 'update', False):
        run_update(args)
    else:
        run_install(args, skip_download=True)


def main():
    parser = argparse.ArgumentParser(description="Webnovel Writer for OpenCode Installer")
    parser.add_argument("--update", action="store_true", help="Check and apply updates")
    parser.add_argument("--apply", action="store_true", help="Apply staged update")
    parser.add_argument("--clean", action="store_true", help="Wipe .opencode/ before install or update")
    parser.add_argument("--incremental", action="store_true",
                        help="Incremental update: only download changed files via manifest diff")
    parser.add_argument("--uninstall", action="store_true", help="Remove .opencode/ (keep project files)")
    parser.add_argument("--full", action="store_true", help="With --uninstall: also remove .venv/")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--venv", action="store_true", help="Use/create .venv/")
    parser.add_argument("--skip-playwright", action="store_true", help="Skip playwright install")
    parser.add_argument("--mirror", type=str, help="Custom GitHub mirror URL")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Download timeout seconds")
    parser.add_argument("--no-menu", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # Detect if user passed any action flag
    action_flags = (
        getattr(args, 'update', False) or
        getattr(args, 'apply', False) or
        getattr(args, 'clean', False) or
        getattr(args, 'incremental', False) or
        getattr(args, 'uninstall', False)
    )

    if not action_flags and not args.no_menu:
        interactive_menu(args)
    else:
        run_selected_action(args)


if __name__ == "__main__":
    main()
