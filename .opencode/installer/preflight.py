"""Install orchestration: main install flow, update flow, and staging/apply. Pure stdlib."""
import shutil
import tempfile
from pathlib import Path

from installer.ui import step, step_ok, step_warn, info, warn, error, success, spinner
from installer.check import run_preflight_checks, is_opencode_running
from installer.fetch import build_urls, download_with_fallback, extract_opencode_from_zip, REPO, BRANCH
from installer.update import write_version_file, needs_update, MANIFEST_URL
from installer.deps import install_core_deps


def _download_and_extract(target_dir_name: str):
    urls = build_urls(REPO, BRANCH)
    zip_dest = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"
    if not download_with_fallback(urls, zip_dest):
        error("All download URLs failed. Check network or use --mirror.")
    dest = Path(target_dir_name)
    extract_opencode_from_zip(zip_dest, dest)
    zip_dest.unlink(missing_ok=True)


def run_install(args, skip_download=False):
    total = 3 if skip_download else 4
    n = 1

    step(n, total, "系统预检")
    run_preflight_checks()
    step_ok(n, total, "系统预检通过")
    n += 1

    if skip_download:
        info(".opencode/ 已就绪，跳过下载")
    else:
        step(n, total, "下载最新版本")
        existing = Path(".opencode").is_dir()
        is_running = is_opencode_running(".opencode") if existing else "not_running"

        if existing and is_running == "running":
            info("检测到 OpenCode 运行中 — 使用暂存模式")
            _download_and_extract(".opencode_staging")
            step_ok(n, total, "已下载到 .opencode_staging/")
            warn("OpenCode 正在运行，新版本已保存到 .opencode_staging/")
            print("    关闭 OpenCode 后运行: python install.py --apply")
            return
        elif existing and is_running == "locked":
            error("无法检测 OpenCode 状态。关闭 OpenCode 后重试。")
        elif existing:
            info("替换现有 .opencode/")
            _download_and_extract(".opencode_staging")
            if not apply_staging():
                error("替换失败，请检查文件权限。")
            step_ok(n, total, "下载并应用完成")
        else:
            _download_and_extract(".opencode")
            step_ok(n, total, "下载完成")
        n += 1

    step(n, total, "安装依赖")
    install_core_deps(
        venv_path=Path(args.venv) if getattr(args, 'venv', None) else None,
        skip_playwright=getattr(args, 'skip_playwright', False)
    )
    step_ok(n, total, "依赖安装完成")
    n += 1

    step(n, total, "验证安装")
    if verify_installation():
        step_ok(n, total, "安装验证通过")
        _write_installed_version()
        success("安装完成!", [
            "  1. 编辑 .env 添加 API Key",
            "  2. 重启 OpenCode",
            "  3. 运行 /webnovel-init 初始化项目",
        ])
    else:
        step_warn("验证未通过。运行: python .opencode/scripts/webnovel.py preflight")


def run_update(args):
    if not needs_update():
        info("已是最新版本。")
        return
    info("发现新版本，开始更新...")
    run_install(args)


def apply_staging() -> bool:
    staging = Path(".opencode_staging")
    target = Path(".opencode")
    backup = Path(".opencode_backup")

    if not staging.is_dir():
        warn("未找到 .opencode_staging/ 目录。先运行 install.py 下载。")
        return False

    if target.is_dir():
        status = is_opencode_running(str(target))
        if status in ("running", "locked"):
            error("OpenCode 仍在运行。请先关闭。")

    if target.is_dir():
        try:
            shutil.move(str(target), str(backup))
        except OSError as e:
            error(f"无法移动 .opencode/ — 文件可能被占用。{e}")

    try:
        shutil.move(str(staging), str(target))
    except OSError as e:
        if backup.is_dir():
            shutil.move(str(backup), str(target))
        error(f"应用暂存失败，已回滚。{e}")

    try:
        if backup.is_dir():
            shutil.rmtree(str(backup))
    except OSError:
        warn(f"无法删除备份目录: {backup}")
        warn("你可以手动删除它。")

    return True


def run_clean_install(args):
    for d in [".opencode", ".opencode_staging", ".opencode_backup"]:
        p = Path(d)
        if p.is_dir():
            info(f"清理: {d}/")
            shutil.rmtree(str(p))
    run_install(args)


def verify_installation() -> bool:
    scripts_dir = Path(".opencode/scripts")
    webnovel_py = scripts_dir / "webnovel.py"
    if not scripts_dir.is_dir():
        warn(".opencode/scripts/ 目录不存在")
        return False
    if not webnovel_py.exists():
        warn(f"入口脚本不存在: {webnovel_py}")
        return False

    checks = []
    for mod in ("aiohttp", "pydantic", "filelock"):
        try:
            __import__(mod)
            checks.append(f"  ✓  {mod}")
        except ImportError:
            checks.append(f"  ✗  {mod} (缺失)")

    ok_count = sum(1 for c in checks if c.startswith("  ✓"))
    total = len(checks)
    print(f"  核心依赖: {ok_count}/{total}")
    for c in checks:
        print(c)
    return ok_count == total


def _write_installed_version():
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            manifest = json.loads(text)
        version = manifest.get("version", "unknown")
    except Exception as e:
        warn(f"无法确定版本: {e}")
        version = "unknown"
    vf = Path(".opencode") / "version.json"
    write_version_file(vf, version)
