"""Download management with mirror fallback. Pure stdlib."""
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path
from installer.ui import info, warn

REPO = "lujih/webnovel-writer-opencode"
BRANCH = "master"

MIRRORS = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
]


def build_urls(repo: str, branch: str, mirrors: list = None) -> list:
    """Build download URL list: direct GitHub first, then mirrors."""
    if mirrors is None:
        mirrors = MIRRORS
    direct = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    urls = [direct]
    for m in mirrors:
        urls.append(
            f"{m.rstrip('/')}/https://github.com/{repo}/archive/refs/heads/{branch}.zip"
        )
    return urls


def download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    """Download a file from URL to dest. Returns True on success."""
    try:
        info(f"Downloading {url.rsplit('/', 1)[-1]} ...")
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            with open(dest, 'wb') as f:
                shutil.copyfileobj(resp, f)
        return True
    except Exception as e:
        warn(f"Download failed: {e}")
        return False


def download_with_fallback(urls: list, dest: Path, timeout: int = 30) -> bool:
    """Try each URL in order until one succeeds."""
    for url in urls:
        if download_file(url, dest, timeout=timeout):
            return True
    return False


def extract_opencode_from_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract only .opencode/ from repo zip into dest_dir.

    The repo zip contains a top-level directory like 'webnovel-writer-master/'.
    We find it and extract .opencode/ from inside it, placing contents directly
    into dest_dir (no nested .opencode/ directory).
    """
    info("Extracting .opencode/ from archive...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        prefix = ""
        for name in names:
            if '/' in name and not name.startswith('__'):
                prefix = name.split('/')[0] + '/'
                break

        opencode_prefix = prefix + ".opencode/"

        for name in names:
            if name.startswith(opencode_prefix):
                rel = name[len(opencode_prefix):]
                if not rel:
                    continue
                target = dest_dir / rel
                if name.endswith('/'):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

        # Self-update: also extract install.py and manifest.json from repo root
        for root_file in ("install.py", "manifest.json"):
            zip_name = prefix + root_file
            if zip_name in names:
                try:
                    tmp = Path(root_file + ".new")
                    with zf.open(zip_name) as src, open(str(tmp), 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(str(tmp), str(Path(root_file)))
                except OSError:
                    pass
