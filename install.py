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
# Self-update: if install.py.new exists, swap it in.
# Two-step rename works around Windows file locking on running .py files.
import os as _os
from pathlib import Path as _P

_NEW = _P(__file__).with_suffix('.py.new') if '__file__' in dir() else _P('install.py.new')
if _NEW.is_file():
    _CUR = _P(__file__).resolve() if '__file__' in dir() else _P('install.py')
    _OLD = _CUR.with_suffix('.py.old')
    try:
        _os.replace(str(_CUR), str(_OLD))
        _os.replace(str(_NEW), str(_CUR))
        _OLD.unlink(missing_ok=True)
        print("install.py 已自动更新，请重新运行 python install.py")
        _os._exit(0)
    except OSError:
        pass

import argparse
import os
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

        # Self-update: extract install.py to .new (swapped on next startup)
        for root_file in ("install.py",):
            zip_name = prefix + root_file
            if zip_name in names:
                dest = Path(root_file)
                tmp = Path(str(dest) + ".new")
                with zf.open(zip_name) as src, open(str(tmp), 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                # Try in-place replace (works if not locked); .new persists otherwise
                try:
                    os.replace(str(tmp), str(dest))
                except OSError:
                    pass  # locked — startup check handles it next run


def _cjk_width(s: str) -> int:
    """Count display width: CJK=2, ASCII=1. Strips ANSI escapes first."""
    import re
    clean = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', s)
    w = 0
    for ch in clean:
        w += 2 if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯' else 1
    return w


def _pad(s: str, w: int) -> str:
    """Pad string to display width w."""
    return s + ' ' * (w - _cjk_width(s))


MANIFEST_URL = "https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/manifest.json"
BOX_W = 52
C = "\033[1m\033[96m"  # cyan bold
R = "\033[0m"       # reset
D = "\033[90m"       # dim
B = "\033[1m"        # bold
G = "\033[92m"       # green
Y = "\033[93m"       # yellow
X = "\033[90m"       # gray (inactive)

BAR = C + "─" * (BOX_W + 2) + R


def _row(text: str, color: str = "", right: str = "") -> None:
    """Print a box row: │ content │"""
    content = color + text + R + right
    print(f"{C}│{R} {_pad(content, BOX_W)} {C}│{R}")


def _check_update():
    """Compare local version with remote manifest. Returns (is_update, changelog, remote, local_tag, remote_tag)."""
    import json as _json
    import urllib.request

    local = {}
    local_vf = Path(".opencode/version.json")
    if local_vf.is_file():
        try:
            local = _json.loads(local_vf.read_text(encoding="utf-8"))
        except Exception:
            pass

    remote = {}
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            remote = _json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return (False, [], {}, "", "")

    local_tag = local.get("tag", "")
    remote_tag = remote.get("tag", "")
    local_ver = local.get("version", "unknown")
    remote_ver = remote.get("version", "")
    if local_ver == "unknown" or not remote_ver:
        return (True, [], remote, local_tag, remote_tag)
    if local_ver == remote_ver:
        return (False, [], remote, local_tag, remote_tag)

    return (True, remote.get("changelog", []), remote, local_tag, remote_tag)


def _show_changelog(changelog, remote_version, local_tag, remote_tag):
    """Display update changelog in CJK-aware box."""
    is_major = bool(local_tag and remote_tag and local_tag != remote_tag)
    tag_display = remote_tag or remote_version

    title = f"Webnovel Writer for OpenCode {tag_display}"
    subtitle = "大版本更新" if is_major else "小版本更新"

    print(f"\n{C}┌{BAR}┐{R}")
    print(f"{C}│{R}  {_pad(B + title + R, BOX_W)}  {C}│{R}")
    print(f"{C}│{R}  {_pad(subtitle, BOX_W)}  {C}│{R}")
    print(f"{C}├{BAR}┤{R}")
    if changelog:
        shown = 0
        for entry in changelog:
            if shown >= 15:
                print(f"{C}│{R}  {_pad(D + f'... 还有 {len(changelog) - 15} 条变更' + R, BOX_W)}  {C}│{R}")
                break
            msg = entry.get("message", "")[:48]
            print(f"{C}│{R}  {_pad(D + '- ' + R + msg, BOX_W)}  {C}│{R}")
            shown += 1
    else:
        print(f"{C}│{R}  {_pad(D + '(无详细日志)' + R, BOX_W)}  {C}│{R}")
    print(f"{C}└{BAR}┘{R}")
    print()


# 功能模块定义（与 installer.deps.FEATURE_GROUPS 保持一致）
_FEATURES = [
    ("dashboard", "Dashboard — 管理面板",        "fastapi/uvicorn ~15MB", True),
    ("export",    "导出 MD/EPUB/HTML/DOCX",       "mistune/docx ~8MB",    True),
    ("publish",   "发布 — 平台自动上传",          "playwright ~150MB",    False),
    ("dev",       "开发工具 — 测试套件",         "pytest ~10MB",         False),
]


def _select_features_interactive():
    """交互式选择要安装的功能模块。返回 {feature: bool}。"""
    selected = {k: default for k, _, _, default in _FEATURES}

    while True:
        print(f"\n{C}┌{BAR}┐{R}")
        print(f"{C}│{R}  {B}功能模块选择{R}  {C}│{R}")
        print(f"{C}├{BAR}┤{R}")
        _row(f"{G}●{R} 核心依赖 (必装): aiohttp + filelock + pydantic")
        print(f"{C}├{BAR}┤{R}")
        _row("可选模块:", color=D)
        _row("")
        for idx, (key, label, desc, _) in enumerate(_FEATURES):
            mark = f"{G}Y{R}" if selected[key] else f"{X}N{R}"
            _row(f" {B}[{idx + 1}]{R} [{mark}] {label}  {D}{desc}{R}")
        _row("")
        _row(f" {B}[A]{R} 全选    {B}[N]{R} 仅核心    {B}[0]{R} 确认", color=D)
        print(f"{C}└{BAR}┘{R}")
        print()

        try:
            choice = input(f"  {B}输入数字切换开关，0 确认{R}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return None

        if not choice or choice == "0":
            break
        if choice.upper() == "A":
            for key, _, _, _ in _FEATURES:
                selected[key] = True
            continue
        if choice.upper() == "N":
            for key, _, _, _ in _FEATURES:
                selected[key] = False
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(_FEATURES):
                key = _FEATURES[idx][0]
                selected[key] = not selected[key]
            else:
                print(f"  无效选择: {choice}")
        except ValueError:
            print(f"  无效选择: {choice}")

    return selected


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

    print(f"\n{C}┌{BAR}┐{R}")
    print(f"{C}│{R}  {B}Webnovel Writer for OpenCode — 安装管理{R}  {C}│{R}")
    print(f"{C}├{BAR}┤{R}")

    if installed:
        _row(f"{G}●{R} 已安装 ({B}{version}{R})")
    else:
        _row(f"{X}●{R} 未安装")
    if staging:
        _row(f"{Y}◐{R} 有暂存更新待应用")

    print(f"{C}├{BAR}┤{R}")
    _row("请选择操作:", color=D)
    _row("")
    _row(f" {B}[1]{R} 安装 / 更新      {D}下载最新版本{R}")
    _row(f" {B}[2]{R} 增量更新          {D}仅变更文件 (快){R}")
    _row(f" {B}[3]{R} 清洁安装          {D}擦除后全新安装{R}")
    if staging:
        _row(f" {B}[4]{R} {Y}应用暂存更新{R}      {D}关闭 IDE 后执行{R}")
    _row(f" {B}[5]{R} 卸载              {D}移除 .opencode/{R}")
    _row(f" {B}[6]{R} 完全卸载          {D}移除 .opencode/ + .venv/{R}")
    _row(f" {B}[0]{R} 退出")
    print(f"{C}└{BAR}┘{R}")
    print()

    try:
        choice = input(f"  {B}输入数字选择{R} {D}(默认=1){R}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消。")
        return

    if not choice:
        choice = "1"

    # 安装类操作：交互式选择功能模块
    if choice in ("1", "2", "3"):
        features = _select_features_interactive()
        if features is None:
            return
        args.with_features = [k for k, v in features.items() if v]
        for key, *_ in _FEATURES:
            if not features[key]:
                setattr(args, f'no_{key}', True)

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

    # Show update changelog
    is_update, changelog, remote, local_tag, remote_tag = _check_update()
    if is_update and changelog:
        _show_changelog(changelog, remote.get("version", ""), local_tag, remote_tag)

    print(f"\n{C}┌{BAR}┐{R}")
    print(f"{C}│{R}  {B}Webnovel Writer — Installer{R}  {C}│{R}")
    print(f"{C}└{BAR}┘{R}\n")

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
    parser.add_argument("--with", dest="with_features", action="append", default=[],
                        choices=["dashboard", "export", "publish", "dev"],
                        help="Enable optional feature (repeatable)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable dashboard module")
    parser.add_argument("--no-export", action="store_true", help="Disable export module")
    parser.add_argument("--no-publish", action="store_true", help="Disable publish module")
    parser.add_argument("--no-dev", action="store_true", help="Disable dev tools")
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
