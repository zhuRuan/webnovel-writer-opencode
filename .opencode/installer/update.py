"""Version management with manifest-based incremental updates. Pure stdlib."""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from installer.ui import info, warn

MANIFEST_URL = "https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/manifest.json"


def read_local_version(version_file: Path = None) -> dict:
    """Read local version.json. Returns {'version': 'unknown'} if absent."""
    if version_file is None:
        version_file = Path(".opencode") / "version.json"
    try:
        if version_file.exists():
            return json.loads(version_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"version": "unknown"}


def write_version_file(path: Path, version: str):
    """Write version.json after successful install."""
    data = {
        "version": version,
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "channel": "install.py",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def current_repo_version(project_root: Path = None) -> str:
    """Get current version: from version.json (install.py users) or git describe (clone users)."""
    if project_root is None:
        project_root = Path.cwd()

    vf = project_root / ".opencode" / "version.json"
    if vf.exists():
        data = read_local_version(vf)
        return data.get("version", "unknown")

    # clone user: try git describe
    import subprocess
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, cwd=project_root, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def compute_diff(manifest: dict, local_dir: Path) -> list:
    """Compare manifest against local files. Returns list of (path, action) tuples.
    action is one of: 'add', 'update'"""
    changes = []
    files = manifest.get("files", {})

    for rel_path, info in files.items():
        local_file = local_dir / rel_path
        if not local_file.exists():
            changes.append((rel_path, "add"))
        else:
            try:
                content = local_file.read_bytes()
                local_sha = hashlib.sha256(content).hexdigest()
                if local_sha != info["sha256"]:
                    changes.append((rel_path, "update"))
            except Exception:
                changes.append((rel_path, "update"))

    return changes


def needs_update(manifest_url: str = None) -> bool:
    """Check if a newer version is available."""
    import urllib.request
    if manifest_url is None:
        manifest_url = MANIFEST_URL

    try:
        with urllib.request.urlopen(manifest_url, timeout=10) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        warn(f"Cannot check for updates: {e}")
        return False

    local_ver = current_repo_version()
    remote_ver = manifest.get("version", "")

    if local_ver == "unknown":
        return True
    return remote_ver != local_ver
