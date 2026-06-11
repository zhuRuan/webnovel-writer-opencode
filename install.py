#!/usr/bin/env python3
"""
Webnovel Writer for OpenCode — 一键安装脚本。
从 GitHub 下载 .opencode/ 并配置写作工具链。

用法:
  python install.py                    # 交互菜单（推荐）
  python install.py --update           # 检查并应用更新
  python install.py --clean            # 擦除后全新安装
  python install.py --incremental      # 增量更新（仅变更文件）
  python install.py --apply            # 应用暂存更新
  python install.py --uninstall        # 卸载（保留项目文件）
  python install.py --uninstall --full # 完全卸载（含 .venv/）
  python install.py --venv             # 创建并使用 .venv/
  python install.py --skip-playwright  # 跳过浏览器安装
  python install.py --mirror URL       # 使用自定义镜像
"""
# ── 自更新 ──────────────────────────────────────────────
# 启动时检查 install.py.new，存在则热替换。
# 两步 rename 绕过 Windows 文件锁定。
import os as _os
import sys as _sys
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

# 自更新区块用 _P，后续代码用 Path
Path = _P

# ── Windows 控制台 UTF-8 + ANSI ──────────────────────────
_ANSI_OK = True  # 假设 ANSI 可用，Win 下检测后可能关闭
if _os.name == "nt":
    try:
        for _s in ("stdout", "stderr", "stdin"):
            _obj = getattr(_sys, _s)
            if hasattr(_obj, "reconfigure"):
                _obj.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes
        _k32 = ctypes.windll.kernel32
        _STD_OUT = -11
        _ENABLE_VT = 0x0004
        _mode = ctypes.c_ulong()
        _k32.GetConsoleMode(_k32.GetStdHandle(_STD_OUT), ctypes.byref(_mode))
        _k32.SetConsoleMode(_k32.GetStdHandle(_STD_OUT), _mode.value | _ENABLE_VT)
    except Exception:
        _ANSI_OK = False

# ── 标准库导入 ──────────────────────────────────────────
import argparse
import json
import shutil
import tempfile
import urllib.request
import zipfile

# ── 内联 UI ─────────────────────────────────────────────
# install.py 必须在 .opencode/ 不存在时独立运行（自举），
# 因此 UI 函数直接内联，不依赖 .opencode/installer/ui.py。
# 安装后其他模块使用 .opencode/installer/ui.py（功能相同，多线程 spinner 等）。

import re
import threading
import time

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# 颜色常量（ANSI 不可用时自动降级为无颜色纯文本）
if _ANSI_OK:
    _G = '\033[92m'   # green
    _R = '\033[91m'   # red
    _Y = '\033[93m'   # yellow
    _C = '\033[96m'   # cyan
    _B = '\033[1m'    # bold
    _D = '\033[2m'    # dim
    _N = '\033[0m'    # reset
else:
    _G = _R = _Y = _C = _B = _D = _N = ""

BOX_W = 52


def _display_width(s: str) -> int:
    """计算显示宽度：CJK=2, ASCII=1，忽略 ANSI 转义。"""
    clean = _ANSI_RE.sub('', s)
    w = 0
    for ch in clean:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            w += 2
        else:
            w += 1
    return w


def _pad(s: str, w: int) -> str:
    """将字符串填充到指定显示宽度，过长则截断加 …。"""
    dw = _display_width(s)
    if dw > w:
        # 从右向左逐字截断，留 1 字符宽度给 …
        while _display_width(s) > w - 1 and s:
            s = s[:-1]
        return s + '…'
    return s + ' ' * (w - dw)


def box_open(width: int = BOX_W, color: str = ""):
    c = color or _C
    print(f"\n{c}┌{'─' * (width + 2)}┐{_N}")


def box_close(width: int = BOX_W, color: str = ""):
    c = color or _C
    print(f"{c}└{'─' * (width + 2)}┘{_N}")


def box_sep(width: int = BOX_W, color: str = ""):
    c = color or _C
    print(f"{c}├{'─' * (width + 2)}┤{_N}")


def box_row(text: str, width: int = BOX_W, color: str = "",
            right: str = "", box_color: str = ""):
    c = box_color or _C
    content = color + text + _N + right if color else text + right
    print(f"{c}│{_N} {_pad(content, width)} {c}│{_N}")


def header(title: str):
    w = _display_width(title)
    bar = "═" * (w + 4)
    print(f"\n{_B}{_C}{bar}{_N}")
    print(f"{_B}{_C}  {title}{_N}")
    print(f"{_B}{_C}{bar}{_N}\n")


def step(step_num: int, total: int, msg: str):
    print(f"\n{_B}{_C}  [{step_num}/{total}]{_N} {msg}")
    print(f"  {_D}{'─' * 50}{_N}")


def info(msg: str):
    print(f"  {_D}▸{_N} {msg}")


def warn(msg: str):
    print(f"  {_Y}⚠  {msg}{_N}")


def error(msg: str):
    print(f"\n{_R}{_B}  ✗ 错误{_N} {msg}")
    _sys.exit(1)


def success(title: str, lines: list = None):
    if lines is None:
        lines = []
    content = [title]
    if lines:
        content.append("")
        content.extend(lines)
    box_open(color=_G)
    for line in content:
        box_row(f"{_G}{line}{_N}", box_color=_G)
    box_close(color=_G)


def download_progress(resp, dest_path, label: str = "下载中"):
    """带进度条的下载。"""
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
                    _sys.stdout.write(
                        f"\r  {_C}{label}{_N} [{bar}] {pct}%  "
                        f"{_D}{size_mb:.1f}/{total_mb:.1f} MB{_N}"
                    )
                    _sys.stdout.flush()
                    last_pct = pct

    if total:
        print()
    else:
        size_mb = downloaded / (1024 * 1024)
        print(f"  {_G}✓{_N} {label}  {_D}{size_mb:.1f} MB{_N}")


class _Spinner:
    """带状态的 spinner（✓/✗）。"""

    def __init__(self, msg: str):
        self._msg = msg
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, *_):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if exc_type:
            _sys.stdout.write(f"\r  {_R}✗{_N} {self._msg}\n")
        else:
            _sys.stdout.write(f"\r  {_G}✓{_N} {self._msg}\n")
        _sys.stdout.flush()

    def _run(self):
        frames = ["◐", "◓", "◑", "◒"]
        i = 0
        while not self._stop.is_set():
            _sys.stdout.write(f"\r  {_C}{frames[i]}{_N} {self._msg}")
            _sys.stdout.flush()
            i = (i + 1) % len(frames)
            time.sleep(0.15)
        _sys.stdout.write(f"\r{' ' * (_display_width(self._msg) + 10)}\r")
        _sys.stdout.flush()


def spinner(msg: str):
    return _Spinner(msg)


# ── 安装逻辑 ────────────────────────────────────────────
# 以下 build_urls/download/extract_opencode 与 installer/fetch.py 功能重复，
# 这是有意为之：install.py 必须在 .opencode/ 下载之前独立运行（启动自举）。
# 一旦 .opencode/ 就位，后续流程使用 installer/ 模块。

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"
_DEFAULT_MIRRORS = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
]
MANIFEST_URL = "https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/manifest.json"


def build_urls(repo, branch, custom_mirror=None, remote=None):
    mirrors = [custom_mirror] if custom_mirror else _get_mirrors(remote)
    direct = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    urls = [direct]
    for m in mirrors:
        urls.append(f"{m.rstrip('/')}/{direct}")
    return urls


def _get_mirrors(remote: dict = None) -> list:
    """获取镜像列表：优先从远程 manifest 读取，fallback 到硬编码。

    Args:
        remote: 已缓存的 manifest dict（避免重复网络请求）。
    """
    if remote:
        mirrors = remote.get("mirrors", [])
        if mirrors:
            return mirrors
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            mirrors = data.get("mirrors", [])
            if mirrors:
                return mirrors
    except Exception:
        pass
    return list(_DEFAULT_MIRRORS)


def download(urls, dest, timeout=30):
    for url in urls:
        try:
            short_name = url.rsplit('/', 1)[-1][:40]
            info(f"尝试下载: {short_name}")
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                download_progress(resp, dest, label="下载中")
            return True
        except (OSError, urllib.error.URLError, ValueError) as e:
            warn(f"下载失败: {e}")
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

        # 自更新：提取 install.py 到 .new（下次启动时替换）
        for root_file in ("install.py",):
            zip_name = prefix + root_file
            if zip_name in names:
                dest = Path(root_file)
                tmp = Path(str(dest) + ".new")
                with zf.open(zip_name) as src, open(str(tmp), 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                try:
                    _os.replace(str(tmp), str(dest))
                except OSError:
                    pass


def _check_update():
    """对比本地与远程版本。返回 (状态, changelog, remote, local_tag, remote_tag)。
    状态: None=检查失败, False=无更新, True=有更新。
    """
    local = {}
    local_vf = Path(".opencode/version.json")
    if local_vf.is_file():
        try:
            local = json.loads(local_vf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    remote = {}
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            remote = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return (None, [], {}, "", "")

    local_tag = local.get("tag", "")
    remote_tag = remote.get("tag", "")
    local_ver = local.get("version", "unknown")
    remote_ver = remote.get("version", "")

    if not remote_ver:
        return (None, [], {}, "", "")
    if local_ver == "unknown":
        return (True, [], remote, local_tag, remote_tag)
    if local_ver == remote_ver:
        return (False, [], remote, local_tag, remote_tag)

    return (True, remote.get("changelog", []), remote, local_tag, remote_tag)


def _show_changelog(changelog, remote_version, local_tag, remote_tag):
    """在 box 中显示更新日志。"""
    is_major = bool(local_tag and remote_tag and local_tag != remote_tag)
    tag_display = remote_tag or remote_version

    title = f"Webnovel Writer for OpenCode {tag_display}"
    subtitle = "大版本更新" if is_major else "小版本更新"

    box_open()
    box_row(f"{_B}{title}{_N}")
    box_row(subtitle, color=_D)
    box_sep()
    if changelog:
        shown = 0
        for entry in changelog:
            if shown >= 15:
                box_row(_D + f"... 还有 {len(changelog) - 15} 条变更" + _N)
                break
            msg = entry.get("message", "")[:48]
            box_row(_D + "- " + _N + msg)
            shown += 1
    else:
        box_row(_D + "(无详细日志)" + _N)
    box_close()
    print()


# _FEATURES 与 installer/deps.py 的 FEATURE_GROUPS 功能重复。
# 启动自举需要：install.py 独立运行时可无 .opencode/ 依赖。
_FEATURES = [
    ("dashboard", "Dashboard — Web 管理面板",       "fastapi/uvicorn (~15MB)", True),
    ("export",    "导出 — MD/TXT/EPUB/HTML/DOCX/PDF", "mistune/python-docx/ebooklib (~8MB)", True),
    ("publish",   "发布 — 小说平台自动发布",        "playwright + Chromium (~150MB)", False),
    ("dev",       "开发工具 — 测试套件",           "pytest/pytest-cov (~10MB)", False),
]


def _select_features_interactive():
    """交互式选择要安装的功能模块。返回 {feature: bool}。"""
    selected = {k: default for k, _, _, default in _FEATURES}
    first_show = True

    while True:
        if not first_show:
            print()
        first_show = False

        box_open()
        box_row(f"{_B}功能模块选择{_N}")
        box_sep()
        box_row(f"{_G}●{_N} 核心依赖 (必装): aiohttp + filelock + pydantic")
        box_sep()
        for idx, (key, label, desc, _) in enumerate(_FEATURES):
            mark = f"{_G}Y{_N}" if selected[key] else f"{_D}N{_N}"
            box_row(f" {_B}[{idx + 1}]{_N} [{mark}] {label}")
        box_sep()
        # 显示预计大小
        selected_keys = {k for k, v in selected.items() if v}
        if selected_keys:
            labels = ", ".join(k for k, _, _, _ in _FEATURES if k in selected_keys)
            box_row(f"{_G}已选:{_N} {labels}", color=_D)
        box_row("")
        box_row(f" 回车确认  [1-4]切换  [A]全选  [N]仅核心", color=_D)
        box_close()

        try:
            choice = input(f"  {_B}选择{_N} {_D}(回车=确认){_N}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return None

        if not choice:
            break
        if choice.upper() == "A":
            for key, _, _, _ in _FEATURES:
                selected[key] = True
            continue
        if choice.upper() == "N":
            for key, _, _, _ in _FEATURES:
                selected[key] = False
            continue

        # 支持逗号分隔多选: 1,2,3
        for part in choice.replace(" ", "").split(","):
            try:
                idx = int(part) - 1
                if 0 <= idx < len(_FEATURES):
                    key = _FEATURES[idx][0]
                    selected[key] = not selected[key]
                else:
                    print(f"  无效选择: {part}")
            except ValueError:
                print(f"  无效选择: {part}")

    return selected


def _show_post_install_guidance(installed_before: bool):
    """安装/更新完成后显示下一步操作指引。"""
    if installed_before:
        success("更新完成！", [
            "已更新到最新版本。",
            "",
            "下一步:",
            "  python .opencode/scripts/webnovel.py status  # 查看项目状态",
        ])
    else:
        success("安装完成！", [
            "Webnovel Writer 已就绪。",
            "",
            "下一步:",
            "  1. python .opencode/scripts/webnovel.py init    # 初始化小说项目",
            "  2. 编辑 .env 添加 API Key",
            "  3. python install.py --with dashboard           # 启动管理面板",
        ])


def interactive_menu(args):
    installed = Path(".opencode").is_dir()
    staging = Path(".opencode_staging").is_dir()

    version = "未知"
    vf = Path(".opencode/version.json")
    if vf.is_file():
        try:
            version = json.loads(vf.read_text(encoding="utf-8")).get("version", "未知")
        except (OSError, ValueError):
            pass

    box_open()
    box_row(f"{_B}Webnovel Writer for OpenCode — 安装管理{_N}")
    box_sep()

    if installed:
        box_row(f"{_G}●{_N} 已安装 ({_B}{version}{_N})")
    else:
        box_row(f"{_D}●{_N} 未安装")
    if staging:
        box_row(f"{_Y}◐{_N} 有暂存更新待应用")

    box_sep()
    box_row("请选择操作:", color=_D)
    box_row("")
    box_row(f" {_B}[1]{_N} 安装 / 更新      {_D}下载最新版本{_N}")
    box_row(f" {_B}[2]{_N} 增量更新          {_D}仅变更文件 (快){_N}")
    box_row(f" {_B}[3]{_N} 清洁安装          {_D}擦除后全新安装{_N}")
    if staging:
        box_row(f" {_B}[4]{_N} {_Y}应用暂存更新{_N}      {_D}关闭 IDE 后执行{_N}")
    box_row(f" {_B}[5]{_N} 卸载              {_D}移除 .opencode/{_N}")
    box_row(f" {_B}[6]{_N} 完全卸载          {_D}移除 .opencode/ + .venv/{_N}")
    box_row(f" {_B}[0]{_N} 退出")
    box_close()

    try:
        choice = input(f"  {_B}输入数字选择{_N} {_D}(默认=1){_N}: ").strip()
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
    """执行从菜单或 CLI 标志选择的操作。"""
    cwd = Path.cwd()
    opencode_dir = cwd / ".opencode"

    if getattr(args, 'uninstall', False):
        header("Webnovel Writer — 卸载")
        if not opencode_dir.is_dir():
            warn(".opencode/ 不存在，无需卸载。")
            return
        _sys.path.insert(0, str(opencode_dir))
        from installer.uninstall import cmd_uninstall
        cmd_uninstall(args)
        return

    if getattr(args, 'apply', False):
        header("应用暂存更新")
        installer_dir = Path(".opencode/installer")
        if not installer_dir.is_dir():
            info("下载安装器模块...")
            urls = build_urls(REPO, BRANCH, args.mirror)
            zip_path = Path(tempfile.gettempdir()) / "webnovel_installer.zip"
            if not download(urls, zip_path, getattr(args, 'timeout', 30)):
                error("无法下载安装器，请检查网络。")
            with spinner("解压安装器..."):
                extract_opencode(zip_path, opencode_dir)
            zip_path.unlink(missing_ok=True)

        _sys.path.insert(0, str(opencode_dir))
        from installer.preflight import apply_staging
        if apply_staging():
            success("暂存更新已应用", ["现在可以重新打开 OpenCode。"])
        else:
            _sys.exit(1)
        return

    if getattr(args, 'clean', False):
        for d in [opencode_dir, Path(".opencode_staging"), Path(".opencode_backup")]:
            if d.is_dir():
                info(f"清洁安装: 删除 {d}/")
                shutil.rmtree(str(d))

    # 显示更新日志
    is_update, changelog, remote, local_tag, remote_tag = _check_update()
    if is_update is None:
        warn("无法检查更新（网络问题），将执行全量安装")
    elif is_update and changelog:
        _show_changelog(changelog, remote.get("version", ""), local_tag, remote_tag)

    installed_before = opencode_dir.is_dir()

    header("Webnovel Writer — 安装")

    step(1, 3, "下载最新版本...")
    urls = build_urls(REPO, BRANCH, getattr(args, 'mirror', None), remote=remote)
    zip_path = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"

    if not download(urls, zip_path, getattr(args, 'timeout', 30)):
        error("下载失败，请检查网络或使用 --mirror URL 指定镜像。")

    _sys.path.insert(0, str(opencode_dir))
    step(2, 3, "解压文件...")

    if getattr(args, 'incremental', False) and opencode_dir.is_dir():
        from installer.update import run_incremental_update
        with spinner("解压到暂存目录..."):
            extract_opencode(zip_path, Path(".opencode_staging"))
        with spinner("应用增量更新..."):
            run_incremental_update()
        Path(zip_path).unlink(missing_ok=True)
    else:
        with spinner("解压中..."):
            extract_opencode(zip_path, opencode_dir)
        Path(zip_path).unlink(missing_ok=True)

    from installer.preflight import run_install, run_update

    step(3, 3, "安装依赖...")
    if getattr(args, 'update', False):
        run_update(args)
    else:
        run_install(args, skip_download=True)

    _show_post_install_guidance(installed_before)


def main():
    parser = argparse.ArgumentParser(description="Webnovel Writer for OpenCode 安装器")
    parser.add_argument("--update", action="store_true", help="检查并应用更新")
    parser.add_argument("--apply", action="store_true", help="应用暂存更新")
    parser.add_argument("--clean", action="store_true", help="安装/更新前擦除 .opencode/")
    parser.add_argument("--incremental", action="store_true",
                        help="增量更新：通过 manifest diff 仅下载变更文件")
    parser.add_argument("--uninstall", action="store_true", help="移除 .opencode/（保留项目文件）")
    parser.add_argument("--full", action="store_true", help="配合 --uninstall：同时移除 .venv/")
    parser.add_argument("--yes", action="store_true", help="跳过确认提示")
    parser.add_argument("--venv", action="store_true", help="创建并使用 .venv/")
    parser.add_argument("--skip-playwright", action="store_true", help="跳过 playwright 安装")
    parser.add_argument("--with", dest="with_features", action="append", default=[],
                        choices=["dashboard", "export", "publish", "dev"],
                        help="启用可选功能模块（可重复）")
    parser.add_argument("--no-dashboard", action="store_true", help="禁用 dashboard 模块")
    parser.add_argument("--no-export", action="store_true", help="禁用 export 模块")
    parser.add_argument("--no-publish", action="store_true", help="禁用 publish 模块")
    parser.add_argument("--no-dev", action="store_true", help="禁用 dev 工具")
    parser.add_argument("--mirror", type=str, help="自定义 GitHub 镜像 URL")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="下载超时秒数")
    parser.add_argument("--no-menu", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # 检测是否传入了操作标志
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
