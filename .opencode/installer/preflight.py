"""Install orchestration: main install flow, update flow, and staging/apply. Pure stdlib."""
import shutil
import tempfile
from pathlib import Path

from installer.ui import step_header, step_done, info, warn, error, success_box
from installer.check import run_preflight_checks, is_opencode_running
from installer.fetch import build_urls, download_with_fallback, extract_opencode_from_zip, REPO, BRANCH
from installer.update import write_version_file, needs_update, MANIFEST_URL
from installer.deps import install_core_deps


def _download_and_extract(target_dir_name: str):
    """Download repo zip and extract .opencode/ contents to target_dir_name."""
    urls = build_urls(REPO, BRANCH)
    zip_dest = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"

    if not download_with_fallback(urls, zip_dest):
        error("All download URLs failed. Check network or use --mirror.")

    dest = Path(target_dir_name)
    extract_opencode_from_zip(zip_dest, dest)
    zip_dest.unlink(missing_ok=True)


def run_install(args, skip_download=False):
    """Main install flow: fresh install or update."""
    total = 3 if skip_download else 4
    step = 1

    # Step 1: preflight checks
    step_header(step, total, "Running system checks")
    run_preflight_checks()
    step_done(step, total, "System checks passed")
    step += 1

    # Step 2: download (skip if caller already extracted .opencode/)
    if skip_download:
        info(".opencode/ up to date from bootstrap, skipping download")
    else:
        step_header(step, total, "Downloading latest version")
        existing = Path(".opencode").is_dir()
        is_running = is_opencode_running(".opencode") if existing else "not_running"

        if existing and is_running == "running":
            info("OpenCode detected — using staging mode")
            _download_and_extract(".opencode_staging")
            step_done(step, total, "Downloaded to .opencode_staging/")
            print()
            warn("OpenCode is running. New version saved to .opencode_staging/")
            print("  To apply the update:")
            print("  1. Close all OpenCode windows")
            print("  2. Run: python install.py --apply")
            return
        elif existing and is_running == "locked":
            error("Cannot check if OpenCode is running. Close OpenCode and try again.")
        elif existing:
            info("Replacing existing .opencode/")
            _download_and_extract(".opencode_staging")
            if not apply_staging():
                error("Failed to replace .opencode/. Check permissions.")
            step_done(step, total, "Downloaded and applied")
        else:
            _download_and_extract(".opencode")
            step_done(step, total, "Downloaded .opencode/")
        step += 1

    # Step 3: install dependencies
    step_header(step, total, "Installing dependencies")
    install_core_deps(
        venv_path=Path(args.venv) if getattr(args, 'venv', None) else None,
        skip_playwright=getattr(args, 'skip_playwright', False)
    )
    step_done(step, total, "Dependencies installed")
    step += 1

    # Step 4: verify
    step_header(step, total, "Verifying installation")
    if verify_installation():
        step_done(step, total, "Installation verified")
        _write_installed_version()
        success_box("Installation complete!", [
            "Next steps:",
            "  1. Edit .env and add your API keys",
            "  2. Restart OpenCode",
            "  3. Run /webnovel-init to start a new project",
        ])
    else:
        warn("Verification failed. Run: python .opencode/scripts/webnovel.py preflight")


def run_update(args):
    """Update flow: check for new version and update if needed."""
    if not needs_update():
        info("Already up to date.")
        return

    info("New version available. Updating...")
    run_install(args)


def apply_staging() -> bool:
    """Move .opencode_staging/ to .opencode/ with backup+rollback safety."""
    staging = Path(".opencode_staging")
    target = Path(".opencode")
    backup = Path(".opencode_backup")

    if not staging.is_dir():
        warn("No .opencode_staging/ directory found. Run install.py first.")
        return False

    # Check OpenCode again before applying
    if target.is_dir():
        status = is_opencode_running(str(target))
        if status in ("running", "locked"):
            error("OpenCode appears to be running. Close it before running --apply.")

    # Phase 1: backup existing
    if target.is_dir():
        try:
            shutil.move(str(target), str(backup))
        except OSError as e:
            error(f"Cannot move .opencode/ - it may be in use. Error: {e}")

    # Phase 2: move staging to target
    try:
        shutil.move(str(staging), str(target))
    except OSError as e:
        # Rollback: restore backup
        if backup.is_dir():
            shutil.move(str(backup), str(target))
        error(f"Failed to apply staging. Rolled back. Error: {e}")

    # Phase 3: clean up backup
    try:
        if backup.is_dir():
            shutil.rmtree(str(backup))
    except OSError:
        warn(f"Could not remove backup directory: {backup}")
        warn("You can safely delete it manually.")

    return True


def run_clean_install(args):
    """Wipe .opencode/ and perform fresh install."""
    import shutil as _shutil
    for d in [".opencode", ".opencode_staging", ".opencode_backup"]:
        p = Path(d)
        if p.is_dir():
            info(f"Clean: removing {d}/")
            _shutil.rmtree(str(p))
    run_install(args)


def verify_installation() -> bool:
    """Verify key scripts exist and core dependencies are importable."""
    scripts_dir = Path(".opencode/scripts")
    webnovel_py = scripts_dir / "webnovel.py"

    if not scripts_dir.is_dir():
        warn("Scripts directory not found: .opencode/scripts/")
        return False
    if not webnovel_py.exists():
        warn(f"Entry script not found: {webnovel_py}")
        return False

    checks = []
    # Verify core Python dependencies can be imported
    for mod in ("aiohttp", "pydantic", "filelock"):
        try:
            __import__(mod)
            checks.append(f"  OK {mod}")
        except ImportError:
            checks.append(f"  MISSING {mod}")

    ok_count = sum(1 for c in checks if c.startswith("  OK"))
    total = len(checks)
    print(f"  Dependencies: {ok_count}/{total} core packages OK")
    for c in checks:
        print(c)

    return ok_count == total


def _write_installed_version():
    """Write version.json after successful install."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            manifest = json.loads(text)
        version = manifest.get("version", "unknown")
    except Exception as e:
        warn(f"Could not determine version: {e}")
        version = "unknown"

    vf = Path(".opencode") / "version.json"
    write_version_file(vf, version)
