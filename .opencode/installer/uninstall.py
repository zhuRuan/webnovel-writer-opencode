"""Uninstall: remove .opencode/ and optionally .venv/ and deps. Pure stdlib."""
import shutil
from pathlib import Path

from installer.ui import info, warn, success


def _safe_rmtree(path: Path) -> bool:
    """Remove directory tree safely. Returns True on success."""
    if not path.is_dir():
        return False
    try:
        shutil.rmtree(str(path))
        return True
    except OSError as e:
        warn(f"Cannot remove {path}: {e}")
        return False


def cmd_uninstall(args=None):
    """Remove .opencode/ and all installer artifacts.

    By default preserves .env and user data (only removes .opencode/).
    With --full also removes .venv/ and pip packages (requires --yes confirm).
    """
    full = getattr(args, 'full', False)
    yes = getattr(args, 'yes', False)

    dirs_to_remove = [".opencode", ".opencode_staging", ".opencode_backup"]

    if full:
        print()
        print("  完全卸载将删除:")
        for d in dirs_to_remove:
            print(f"    - {d}/")
        print("    - .venv/ (虚拟环境)")
        print()
        if not yes:
            info("使用 --yes 跳过确认，或重新运行 python install.py --uninstall --full --yes")
            try:
                resp = input("确认完全卸载？(yes/N): ").strip()
            except (EOFError, KeyboardInterrupt):
                resp = "n"
            if resp.lower() != "yes":
                info("已取消。")
                return
        dirs_to_remove.append(".venv")

    removed = []
    for d in dirs_to_remove:
        p = Path(d)
        if _safe_rmtree(p):
            removed.append(f"{d}/")
            info(f"已删除: {d}/")

    if not removed:
        info("没有需要清理的内容。")
        return

    print()
    success("卸载完成", [
        f"已删除: {', '.join(removed)}",
        "项目文件（正文、大纲、state.json 等）未被删除。",
    ])
