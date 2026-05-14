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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=project_root, timeout=5
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
            manifest = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        warn(f"Cannot check for updates: {e}")
        return False

    local_ver = current_repo_version()
    remote_ver = manifest.get("version", "")

    if local_ver == "unknown":
        return True
    return remote_ver != local_ver


def run_incremental_update(manifest_url: str = None):
    """Apply incremental update from .opencode_staging/ → .opencode/.

    Compares manifest.json against local files and only copies changed files.
    Falls back to full staging-apply if manifest is unavailable.
    """
    import urllib.request
    import shutil
    from pathlib import Path

    if manifest_url is None:
        manifest_url = MANIFEST_URL

    staging = Path(".opencode_staging")
    target = Path(".opencode")
    if not staging.is_dir():
        warn("No .opencode_staging/ directory for incremental update.")
        return

    # Fetch manifest
    try:
        with urllib.request.urlopen(manifest_url, timeout=10) as resp:
            manifest = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        warn(f"Cannot fetch manifest for incremental update: {e}")
        warn("Falling back to full staging apply.")
        from installer.preflight import apply_staging
        apply_staging()
        return

    files = manifest.get("files", {})
    if not files:
        warn("Manifest empty — falling back to full staging apply.")
        from installer.preflight import apply_staging
        apply_staging()
        return

    # Build diff
    changes = compute_diff(manifest, target)
    if not changes:
        info("All files up to date — nothing to do.")
        shutil.rmtree(str(staging))
        return

    added = sum(1 for _, a in changes if a == "add")
    updated = sum(1 for _, a in changes if a == "update")
    info(f"Incremental update: {added} new, {updated} changed ({len(changes)} total)")

    # Apply changes
    applied = 0
    for rel_path, _action in changes:
        src = staging / rel_path
        dst = target / rel_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            applied += 1
        elif _action == "update":
            # File removed upstream — delete local copy
            if dst.exists():
                dst.unlink()

    info(f"Applied {applied}/{len(changes)} incremental changes.")

    # Clean staging
    shutil.rmtree(str(staging))

    # Update version file
    version = manifest.get("version", "unknown")
    vf = target / "version.json"
    write_version_file(vf, version)
    print(f"  Updated to {version}")
