#!/usr/bin/env python3
"""
Webnovel Writer for OpenCode — one-click installer.
Downloads .opencode/ from GitHub and sets up the writing toolchain.

Usage:
  python install.py               # Fresh install or update
  python install.py --update      # Check and apply updates
  python install.py --apply       # Apply staged update (after closing OpenCode)
  python install.py --venv        # Create and use .venv/
  python install.py --skip-playwright  # Skip browser install
  python install.py --mirror URL  # Use custom GitHub mirror
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


def main():
    parser = argparse.ArgumentParser(description="Webnovel Writer for OpenCode Installer")
    parser.add_argument("--update", action="store_true", help="Check and apply updates")
    parser.add_argument("--apply", action="store_true", help="Apply staged update")
    parser.add_argument("--venv", action="store_true", help="Use/create .venv/")
    parser.add_argument("--skip-playwright", action="store_true", help="Skip playwright install")
    parser.add_argument("--mirror", type=str, help="Custom GitHub mirror URL")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Download timeout seconds")
    args = parser.parse_args()

    # Phase 0: --apply mode (separate entry point)
    if args.apply:
        print("\n--- Apply Staged Update ---\n")

        installer_dir = Path(".opencode/installer")
        if not installer_dir.is_dir():
            print("Downloading installer modules...")
            urls = build_urls(REPO, BRANCH, args.mirror)
            zip_path = Path(tempfile.gettempdir()) / "webnovel_installer.zip"
            if not download(urls, zip_path, args.timeout):
                print("[ERROR] Cannot download installer. Check network.")
                sys.exit(1)
            extract_opencode(zip_path, Path(".opencode"))
            zip_path.unlink(missing_ok=True)

        sys.path.insert(0, str(Path.cwd() / ".opencode"))
        from installer.preflight import apply_staging
        if apply_staging():
            print("\nUpdate applied. You can now reopen OpenCode.")
        else:
            sys.exit(1)
        return

    # Phase 1: Download repo zip and extract installer modules
    print("\n" + "=" * 60)
    print("  Webnovel Writer for OpenCode — Installer")
    print("=" * 60 + "\n")

    print("[Step 1/3] Downloading latest version...")
    urls = build_urls(REPO, BRANCH, args.mirror)
    zip_path = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"

    if not download(urls, zip_path, args.timeout):
        print("[ERROR] Download failed. Check network or use --mirror URL.")
        sys.exit(1)

    extract_opencode(zip_path, Path(".opencode"))
    zip_path.unlink(missing_ok=True)
    print("  Done.\n")

    # Phase 2: Delegate to installer/preflight
    sys.path.insert(0, str(Path.cwd() / ".opencode"))
    from installer.preflight import run_install, run_update

    if args.update:
        run_update(args)
    else:
        run_install(args, skip_download=True)


if __name__ == "__main__":
    main()
