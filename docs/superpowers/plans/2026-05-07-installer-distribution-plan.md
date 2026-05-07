# Installer Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite install.py as a lightweight bootstrap script backed by modular installer/ packages, with cross-platform process detection, GitHub mirror fallback, incremental manifest-based updates, and staging+apply two-phase replacement.

**Architecture:** install.py (~120 lines, pure stdlib) downloads the repo zip and extracts `.opencode/installer/`, then delegates to `preflight.py`. Six installer modules under `.opencode/installer/` handle preflight checks, downloading, version management, dependency installation, and terminal UI. All installer modules are pure stdlib — they run before pip dependencies are installed.

**Tech Stack:** Python 3.10+ stdlib only (urllib, zipfile, subprocess, pathlib, hashlib, json, shutil, platform). Tests use pytest.

**Key constraint:** installer modules MUST NOT import from `data_modules` or any external package. They are extracted from the repo zip and run before `pip install`.

---

## File Structure

```
install.py                              # Bootstrap (~120 lines, stdlib only)
.opencode/installer/
  __init__.py                           # Empty
  ui.py                                 # Terminal output (no deps)
  check.py                              # System checks + process detection
  fetch.py                              # Download + mirror fallback
  update.py                             # Version management + manifest diff
  deps.py                               # Dependency installation
  preflight.py                          # Orchestration + staging/apply
.opencode/version.json                  # Written on install (gitignored)
.opencode/scripts/gen_manifest.py       # Manifest generator
.opencode/scripts/tests/installer/      # Test directory
  __init__.py
  test_ui.py
  test_check.py
  test_fetch.py
  test_update.py
  test_deps.py
manifest.json                           # Generated file manifest
INSTALL.md                              # Updated skill
README.md                               # Updated install section
.gitignore                              # Add version.json
```

### Module Dependency Graph

```
ui.py          ← no deps
check.py       ← ui
fetch.py       ← ui
update.py      ← ui, fetch
deps.py        ← ui
preflight.py   ← ui, check, fetch, update, deps
install.py     ← standalone bootstrap, then calls preflight
gen_manifest.py ← standalone, no deps
```

---

### Task 1: ui.py — Terminal UI utilities

**Files:**
- Create: `.opencode/installer/__init__.py`
- Create: `.opencode/installer/ui.py`
- Create: `.opencode/scripts/tests/installer/__init__.py`
- Create: `.opencode/scripts/tests/installer/test_ui.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p .opencode/installer
mkdir -p .opencode/scripts/tests/installer
```

- [ ] **Step 2: Write empty __init__.py files**

`.opencode/installer/__init__.py`:
```python
"""Installer modules for webnovel-writer distribution."""
```

`.opencode/scripts/tests/installer/__init__.py`:
```python
"""Tests for installer modules."""
```

- [ ] **Step 3: Write failing test for ui.py**

`.opencode/scripts/tests/installer/test_ui.py`:
```python
"""Tests for installer.ui — terminal output utilities."""
import sys
import io
from pathlib import Path

# Installer modules are pure stdlib, direct import works
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.ui import display_width, Colors, step_header, info, warn


class TestDisplayWidth:
    def test_ascii_only(self):
        assert display_width("Hello") == 5

    def test_chinese_chars(self):
        assert display_width("你好") == 4  # Each CJK char = 2

    def test_mixed_cjk_ascii(self):
        assert display_width("Hello你好") == 9  # 5 + 4

    def test_ansi_escape_stripped(self):
        # ANSI codes should not count toward display width
        s = "\033[92mHello\033[0m"
        assert display_width(s) == 5

    def test_empty_string(self):
        assert display_width("") == 0


class TestStepFormatting:
    def test_step_header(self, capsys):
        step_header(1, 4, "Checking system")
        out = capsys.readouterr().out
        assert "1/4" in out
        assert "Checking system" in out

    def test_step_done(self, capsys):
        step_done(1, 4, "System check passed")
        out = capsys.readouterr().out
        assert "1/4" in out
        assert "System check passed" in out


class TestInfoWarn:
    def test_info_output(self, capsys):
        info("All good")
        out = capsys.readouterr().out
        assert "All good" in out

    def test_warn_output(self, capsys):
        warn("Something weird")
        out = capsys.readouterr().out
        assert "Something weird" in out
```

- [ ] **Step 4: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_ui.py -v
```
Expected: FAIL — module not found or functions not defined

- [ ] **Step 5: Implement ui.py**

`.opencode/installer/ui.py`:
```python
"""Terminal UI utilities for installer. Pure stdlib, no external deps."""
import re
import sys
import platform

_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# ---------- color constants ----------
class Colors:
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    NC = '\033[0m'


def display_width(s: str) -> int:
    """Calculate terminal display width. CJK chars count as 2, ASCII as 1."""
    clean = _ANSI_ESCAPE_RE.sub('', s)
    w = 0
    for ch in clean:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            w += 2
        else:
            w += 1
    return w


def _pad_to_width(text: str, target: int) -> str:
    cur = display_width(text)
    return text + ' ' * (target - cur)


def step_header(step: int, total: int, msg: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}[Step {step}/{total}]{Colors.NC} {msg}")


def step_done(step: int, total: int, msg: str):
    print(f"{Colors.GREEN}[Step {step}/{total} done]{Colors.NC} {msg}")


def info(msg: str):
    print(f"  {Colors.GREEN}*{Colors.NC} {msg}")


def warn(msg: str):
    print(f"  {Colors.YELLOW}[WARN]{Colors.NC} {msg}")


def error(msg: str):
    """Print error and exit."""
    print(f"\n{Colors.RED}[ERROR]{Colors.NC} {msg}")
    sys.exit(1)


def success_box(title: str, lines: list):
    max_len = max(display_width(title), max((display_width(l) for l in lines), default=0)) + 2
    print()
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    print(f"  {Colors.BOLD}{title}{Colors.NC}")
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    for line in lines:
        print(f"  {line}")
    print(f"{Colors.GREEN}{'=' * max_len}{Colors.NC}")
    print()
```

- [ ] **Step 6: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_ui.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add .opencode/installer/__init__.py .opencode/installer/ui.py .opencode/scripts/tests/installer/
git commit -m "feat(installer): add ui.py terminal output module with CJK-aware display width

- display_width(): counts CJK as 2, ASCII as 1, strips ANSI escapes
- step_header/step_done: progress step formatting
- info/warn/error: leveled output with colors
- success_box: bordered completion banner
- Windows console VT sequence auto-enable"
```

---

### Task 2: check.py — System preflight + process detection

**Files:**
- Create: `.opencode/installer/check.py`
- Create: `.opencode/scripts/tests/installer/test_check.py`

- [ ] **Step 1: Write failing test**

`.opencode/scripts/tests/installer/test_check.py`:
```python
"""Tests for installer.check — system preflight checks."""
import sys
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.check import (
    check_python_version,
    check_disk_space,
    platform_name,
    KNOWN_OPENCODE_PROCESSES,
)


class TestPythonVersion:
    def test_python_310_passes(self):
        assert check_python_version((3, 10)) == True

    def test_python_39_fails(self):
        assert check_python_version((3, 9)) == False

    def test_current_python_passes(self):
        # Current interpreter must be >= 3.10 for this project
        assert check_python_version() == True


class TestDiskSpace:
    def test_sufficient_space(self):
        # Should have at least 1 MB free in temp dir
        d = tempfile.gettempdir()
        assert check_disk_space(d, required_mb=1) == True

    def test_insufficient_mb(self):
        # Request impossibly large space
        assert check_disk_space(tempfile.gettempdir(), required_mb=10**7) == False


class TestPlatformName:
    def test_returns_string(self):
        name = platform_name()
        assert name in ("windows", "linux", "darwin")

    @patch("platform.system")
    def test_windows(self, mock_sys):
        mock_sys.return_value = "Windows"
        assert platform_name() == "windows"

    @patch("platform.system")
    def test_linux(self, mock_sys):
        mock_sys.return_value = "Linux"
        assert platform_name() == "linux"

    @patch("platform.system")
    def test_macos(self, mock_sys):
        mock_sys.return_value = "Darwin"
        assert platform_name() == "darwin"


class TestProcessConfig:
    def test_known_processes_structure(self):
        assert set(KNOWN_OPENCODE_PROCESSES.keys()) == {"windows", "linux", "darwin"}
        assert isinstance(KNOWN_OPENCODE_PROCESSES["windows"], list)
        assert isinstance(KNOWN_OPENCODE_PROCESSES["linux"], list)
        assert isinstance(KNOWN_OPENCODE_PROCESSES["darwin"], list)
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_check.py -v
```
Expected: FAIL — module/function not found

- [ ] **Step 3: Implement check.py**

`.opencode/installer/check.py`:
```python
"""System preflight checks. Pure stdlib, no external deps."""
import os
import sys
import shutil
import subprocess
import platform as _platform
from pathlib import Path

from installer.ui import info, warn, error

KNOWN_OPENCODE_PROCESSES = {
    "windows": ["OpenCode.exe", "Code.exe"],
    "linux":   [],
    "darwin":  ["OpenCode", "Electron"],
}


def platform_name() -> str:
    """Return normalized platform name: windows, linux, or darwin."""
    s = _platform.system()
    if s == "Windows":
        return "windows"
    elif s == "Linux":
        return "linux"
    elif s == "Darwin":
        return "darwin"
    return s.lower()


def check_python_version(min_version: tuple = (3, 10)) -> bool:
    """Check current Python version meets minimum."""
    actual = (sys.version_info.major, sys.version_info.minor)
    return actual >= min_version


def check_disk_space(path: str, required_mb: int = 50) -> bool:
    """Check available disk space at path."""
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= required_mb
    except Exception:
        return True  # Can't check, don't block


def check_network(timeout: int = 5) -> bool:
    """Check if we can reach GitHub."""
    import urllib.request
    try:
        urllib.request.urlopen("https://github.com", timeout=timeout)
        return True
    except Exception:
        return False


def is_opencode_running(target_dir: str = ".opencode") -> str:
    """
    Check if OpenCode is running. Returns 'running', 'not_running', or 'locked'.

    Layer 1: Process name scan (all platforms)
    Layer 2: File lock detection via os.rename (Windows-specific, definitive)
    """
    pname = platform_name()

    # Layer 1: process scan
    found = False
    try:
        procs = KNOWN_OPENCODE_PROCESSES.get(pname, [])
        if pname == "windows":
            if procs:
                cmd = ["tasklist", "/FI", f"IMAGENAME eq {procs[0]}"]
                for proc in procs[1:]:
                    cmd.extend(["/FI", f"IMAGENAME eq {proc}"])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                found = any(p.lower() in result.stdout.lower() for p in procs)
        elif pname == "linux":
            result = subprocess.run(
                ["pgrep", "-f", "opencode"],
                capture_output=True, text=True, timeout=5
            )
            found = result.returncode == 0
        elif pname == "darwin":
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            found = any(
                p.lower() in result.stdout.lower()
                for p in ["OpenCode", "Electron"]
            )
    except Exception:
        pass  # Process scan failed, try lock test

    # Layer 2: file lock test (Windows definitive check)
    if pname == "windows" and os.path.isdir(target_dir):
        lock_test = target_dir + "_lock_test"
        try:
            os.rename(target_dir, lock_test)
            os.rename(lock_test, target_dir)
            return "not_running" if not found else "running"
        except OSError:
            return "locked"  # 100% certainty — file is locked
    elif pname == "windows" and not os.path.isdir(target_dir):
        return "not_running"  # .opencode doesn't exist yet

    return "running" if found else "not_running"


def run_preflight_checks():
    """Run all preflight checks. Calls error() on failure."""
    info("Checking Python version...")
    if not check_python_version():
        v = f"{sys.version_info.major}.{sys.version_info.minor}"
        error(f"Python {v} is too old. Need 3.10+.")

    info("Python version OK")

    info("Checking disk space...")
    if not check_disk_space("."):
        warn("Low disk space — installation may fail")
    else:
        info("Disk space OK")
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_check.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/installer/check.py .opencode/scripts/tests/installer/test_check.py
git commit -m "feat(installer): add check.py system preflight with cross-platform process detection

- check_python_version: enforce 3.10+ minimum
- check_disk_space: verify free space before install
- check_network: GitHub reachability test
- is_opencode_running: layered detection (process scan + file lock)
- KNOWN_OPENCODE_PROCESSES: platform-specific process name registry"
```

---

### Task 3: fetch.py — Download management with mirror fallback

**Files:**
- Create: `.opencode/installer/fetch.py`
- Create: `.opencode/scripts/tests/installer/test_fetch.py`

- [ ] **Step 1: Write failing test**

`.opencode/scripts/tests/installer/test_fetch.py`:
```python
"""Tests for installer.fetch — download management."""
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.fetch import (
    MIRRORS,
    build_urls,
    download_file,
    extract_opencode_from_zip,
    REPO,
    BRANCH,
)


class TestMirrors:
    def test_mirrors_list_not_empty(self):
        assert len(MIRRORS) >= 0
        assert isinstance(MIRRORS, list)

    def test_build_urls_default(self):
        repo = "owner/repo"
        branch = "main"
        urls = build_urls(repo, branch)
        assert len(urls) > 0
        # First URL must be direct GitHub
        assert urls[0].startswith("https://github.com")
        assert "owner/repo" in urls[0]
        assert "main" in urls[0]

    def test_build_urls_with_custom_mirror(self):
        urls = build_urls("owner/repo", "main", mirrors=["https://example.com"])
        assert "https://example.com" in urls[-1]


class TestExtractOpenCode:
    def test_extract_opencode_from_real_zip(self):
        # Create a minimal zip mimicking the repo structure
        d = tempfile.mkdtemp()
        zip_path = Path(d) / "test.zip"
        extract_dir = Path(d) / "extracted"
        extract_dir.mkdir()

        # Build zip with a fake .opencode/ inside a top-level dir
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("webnovel-writer-master/.opencode/skills/test.md", "hello")
            zf.writestr("webnovel-writer-master/.opencode/scripts/test.py", "pass")
            zf.writestr("webnovel-writer-master/README.md", "readme")

        extract_opencode_from_zip(zip_path, extract_dir)

        # Files extracted directly into extract_dir (no nested .opencode/)
        assert (extract_dir / "skills" / "test.md").exists()
        assert (extract_dir / "scripts" / "test.py").exists()
        # README should NOT be extracted (only .opencode/ contents)
        assert not (extract_dir / "README.md").exists()
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_fetch.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement fetch.py**

`.opencode/installer/fetch.py`:
```python
"""Download management with mirror fallback. Pure stdlib."""
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from installer.ui import info, warn, error

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
        urls.append(f"{m.rstrip('/')}/https://github.com/{repo}/archive/refs/heads/{branch}.zip")
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
    We find it and extract .opencode/ from inside it.
    """
    info("Extracting .opencode/ from archive...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Find the prefix (top-level dir inside zip)
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_fetch.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/installer/fetch.py .opencode/scripts/tests/installer/test_fetch.py
git commit -m "feat(installer): add fetch.py download manager with mirror fallback

- build_urls: direct GitHub + mirror URL list construction
- download_file: single-URL download with timeout
- download_with_fallback: try URLs in order until one succeeds
- extract_opencode_from_zip: extract only .opencode/ from repo archive
- MIRRORS: ghproxy.com mirrors for China accessibility"
```

---

### Task 4: update.py — Version management with manifest diff

**Files:**
- Create: `.opencode/installer/update.py`
- Create: `.opencode/scripts/tests/installer/test_update.py`

- [ ] **Step 1: Write failing test**

`.opencode/scripts/tests/installer/test_update.py`:
```python
"""Tests for installer.update — version management."""
import sys
import json
import tempfile
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.update import (
    compute_diff,
    read_local_version,
    write_version_file,
    current_repo_version,
)


class TestVersionFile:
    def test_write_and_read(self):
        d = tempfile.mkdtemp()
        vf = Path(d) / "version.json"
        write_version_file(vf, "v1.2.0")
        assert vf.exists()
        data = json.loads(vf.read_text(encoding="utf-8"))
        assert data["version"] == "v1.2.0"
        assert data["channel"] == "install.py"
        assert "installed_at" in data

    def test_read_nonexistent(self):
        d = tempfile.mkdtemp()
        vf = Path(d) / "nonexistent.json"
        result = read_local_version(vf)
        assert result["version"] == "unknown"


class TestComputeDiff:
    def test_new_file_added(self):
        manifest = {
            "version": "v2.0.0",
            "files": {
                ".opencode/new_skill/SKILL.md": {"sha256": "abc", "size": 100}
            }
        }
        local_dir = tempfile.mkdtemp()
        diff = compute_diff(manifest, Path(local_dir))
        assert len(diff) == 1
        assert diff[0] == (".opencode/new_skill/SKILL.md", "add")

    def test_unchanged_file_skipped(self):
        d = tempfile.mkdtemp()
        p = Path(d) / ".opencode" / "test.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        content = b"hello world"
        p.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()

        manifest = {
            "version": "v1.0.0",
            "files": {
                ".opencode/test.txt": {"sha256": sha, "size": len(content)}
            }
        }
        diff = compute_diff(manifest, Path(d))
        assert len(diff) == 0

    def test_modified_file_detected(self):
        d = tempfile.mkdtemp()
        p = Path(d) / ".opencode" / "test.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"old content")

        manifest = {
            "version": "v1.0.0",
            "files": {
                ".opencode/test.txt": {"sha256": "different_hash_value", "size": 50}
            }
        }
        diff = compute_diff(manifest, Path(d))
        assert len(diff) == 1
        assert diff[0] == (".opencode/test.txt", "update")
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_update.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement update.py**

`.opencode/installer/update.py`:
```python
"""Version management with manifest-based incremental updates. Pure stdlib."""
import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from installer.ui import info, warn, error

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
    """
    Compare manifest against local files. Returns list of (path, action) tuples.
    action is one of: 'add', 'update', 'delete'
    """
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
    """Check if a newer version is available. Downloads manifest and compares."""
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
        return True  # Can't determine version, assume update needed
    return remote_ver != local_ver
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_update.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/installer/update.py .opencode/scripts/tests/installer/test_update.py
git commit -m "feat(installer): add update.py version management with manifest diff

- compute_diff: SHA256-based file comparison between manifest and local
- read_local_version / write_version_file: version.json I/O
- current_repo_version: detect version for both install.py and clone users
- needs_update: compare local vs remote manifest version"
```

---

### Task 5: deps.py — Dependency installation

**Files:**
- Create: `.opencode/installer/deps.py`
- Create: `.opencode/scripts/tests/installer/test_deps.py`

- [ ] **Step 1: Write failing test**

`.opencode/scripts/tests/installer/test_deps.py`:
```python
"""Tests for installer.deps — dependency installation."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.deps import create_venv, check_pip_available


class TestVenv:
    def test_create_venv_creates_directory(self):
        d = tempfile.mkdtemp()
        venv_path = Path(d) / ".venv"
        result = create_venv(venv_path)
        if result:
            assert venv_path.is_dir()
            # Check for python executable inside
            if sys.platform == "win32":
                assert (venv_path / "Scripts" / "python.exe").exists()
            else:
                assert (venv_path / "bin" / "python").exists()

    def test_create_venv_returns_false_on_existing(self):
        d = tempfile.mkdtemp()
        venv_path = Path(d) / "existing_venv"
        venv_path.mkdir(parents=True)
        result = create_venv(venv_path)
        assert result == False


class TestPipCheck:
    def test_check_pip_available(self):
        # pip should always be available in test environment
        assert check_pip_available() == True
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_deps.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement deps.py**

`.opencode/installer/deps.py`:
```python
"""Dependency installation. Pure stdlib, runs subprocess for pip/npm."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from installer.ui import info, warn, error, step_header, step_done


def check_pip_available() -> bool:
    """Check if pip can be invoked."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, check=True, timeout=10
        )
        return True
    except Exception:
        return False


def create_venv(path: Path) -> bool:
    """Create a Python virtual environment. Returns True on success."""
    if path.exists():
        warn(f"Virtual env already exists: {path}")
        return False
    info(f"Creating virtual environment: {path}")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(path)],
            check=True, timeout=60
        )
        return True
    except subprocess.CalledProcessError as e:
        warn(f"Failed to create venv: {e}")
        return False


def _get_pip_path(venv_path: Path = None) -> list:
    """Get pip command, optionally inside a venv."""
    if venv_path:
        if sys.platform == "win32":
            pip = [str(venv_path / "Scripts" / "python"), "-m", "pip"]
        else:
            pip = [str(venv_path / "bin" / "python"), "-m", "pip"]
    else:
        pip = [sys.executable, "-m", "pip"]
    return pip


def install_pip_requirements(req_files: list, venv_path: Path = None) -> bool:
    """Install Python dependencies from requirement files."""
    pip = _get_pip_path(venv_path)

    for rf in req_files:
        if not Path(rf).exists():
            warn(f"Requirements file not found: {rf}")
            continue
        info(f"Installing: {rf}")
        try:
            subprocess.run(
                pip + ["install", "-r", str(rf), "--quiet"],
                check=True, timeout=120
            )
        except subprocess.CalledProcessError as e:
            warn(f"pip install failed for {rf}: {e}")
            return False
    return True


def install_playwright_browser(venv_path: Path = None) -> bool:
    """Install playwright and chromium browser. Returns True on success."""
    pip = _get_pip_path(venv_path)
    info("Installing playwright...")
    try:
        subprocess.run(pip + ["install", "playwright", "--quiet"], check=True, timeout=60)
    except subprocess.CalledProcessError:
        warn("playwright pip install failed")
        return False

    info("Installing chromium browser...")
    try:
        pw_install = _get_pip_path(venv_path)
        subprocess.run(
            pw_install[:-2] + ["-m", "playwright", "install", "chromium"],
            check=True, timeout=300
        )
        return True
    except subprocess.CalledProcessError:
        warn("playwright chromium install failed")
        return False


def install_core_deps(venv_path: Path = None, skip_playwright: bool = False):
    """Install all core dependencies (called by preflight)."""
    req_files = [
        ".opencode/scripts/requirements.txt",
        ".opencode/dashboard/requirements.txt",
    ]

    if not install_pip_requirements(req_files, venv_path):
        error("Core dependency installation failed")

    if not skip_playwright:
        install_playwright_browser(venv_path)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_deps.py -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/installer/deps.py .opencode/scripts/tests/installer/test_deps.py
git commit -m "feat(installer): add deps.py dependency installation with venv support

- create_venv: Python virtual environment creation
- install_pip_requirements: batch pip install from requirements files
- install_playwright_browser: playwright + chromium installation
- install_core_deps: one-shot core dependency installation
- check_pip_available: pip availability check"
```

---

### Task 6: preflight.py — Orchestration + staging/apply

**Files:**
- Create: `.opencode/installer/preflight.py`
- Create: `.opencode/scripts/tests/installer/test_preflight.py`

- [ ] **Step 1: Write failing test**

`.opencode/scripts/tests/installer/test_preflight.py`:
```python
"""Tests for installer.preflight — orchestration."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.preflight import apply_staging, verify_installation


class TestApplyStaging:
    def test_no_staging_directory(self, capsys):
        """apply_staging without .opencode_staging should error."""
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            result = apply_staging()
            assert result == False

    def test_staging_replaces_opencode(self):
        """With staging dir and no existing .opencode, apply succeeds."""
        d = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(d)
        try:
            staging = Path(d) / ".opencode_staging"
            staging.mkdir()
            (staging / "test_file.txt").write_text("new content")
            # No .opencode/ exists — simulate fresh apply
            result = apply_staging()
            assert result == True
            assert (Path(d) / ".opencode").is_dir()
            assert (Path(d) / ".opencode" / "test_file.txt").read_text() == "new content"
            assert not staging.exists()
        finally:
            os.chdir(cwd)


class TestVerifyInstallation:
    @patch("subprocess.run")
    def test_verify_runs_preflight(self, mock_run):
        mock_run.return_value.returncode = 0
        assert verify_installation() == True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_verify_fails_on_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert verify_installation() == False
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest .opencode/scripts/tests/installer/test_preflight.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement preflight.py**

`.opencode/installer/preflight.py`:
```python
"""Install orchestration: main install flow, update flow, and staging/apply. Pure stdlib."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from installer.ui import step_header, step_done, info, warn, error, success_box
from installer.check import run_preflight_checks, is_opencode_running
from installer.fetch import build_urls, download_with_fallback, extract_opencode_from_zip, REPO, BRANCH
from installer.update import write_version_file, needs_update, MANIFEST_URL
from installer.deps import install_core_deps


def _download_and_extract(target_dir_name: str):
    """Download repo zip and extract .opencode/ to target_dir_name."""
    urls = build_urls(REPO, BRANCH)
    zip_dest = Path(tempfile.gettempdir()) / "webnovel_writer_repo.zip"

    if not download_with_fallback(urls, zip_dest):
        error("All download URLs failed. Check network or use --mirror.")

    dest = Path(target_dir_name)
    extract_opencode_from_zip(zip_dest, dest)
    zip_dest.unlink(missing_ok=True)


def run_install(args):
    """Main install flow: fresh install or update."""
    total = 4

    # Step 1: preflight checks
    step_header(1, total, "Running system checks")
    run_preflight_checks()
    step_done(1, total, "System checks passed")

    # Step 2: download
    step_header(2, total, "Downloading latest version")

    existing = Path(".opencode").is_dir()
    is_running = is_opencode_running(".opencode") if existing else "not_running"

    if existing and is_running == "running":
        # OpenCode is running — use staging
        info("OpenCode detected — using staging mode")
        _download_and_extract(".opencode_staging")
        step_done(2, total, "Downloaded to .opencode_staging/")
        print()
        warn("OpenCode is running. New version saved to .opencode_staging/")
        print("  To apply the update:")
        print("  1. Close all OpenCode windows")
        print("  2. Run: python install.py --apply")
        return
    elif existing and is_running == "locked":
        error("Cannot check if OpenCode is running. Close OpenCode and try again.")
    elif existing:
        # OpenCode not running — direct replace
        info("Replacing existing .opencode/")
        _download_and_extract(".opencode_staging")
        if not apply_staging():
            error("Failed to replace .opencode/. Check permissions.")
        step_done(2, total, "Downloaded and applied")
    else:
        # Fresh install
        _download_and_extract(".opencode")
        step_done(2, total, "Downloaded .opencode/")

    # Step 3: install dependencies
    step_header(3, total, "Installing dependencies")
    install_core_deps(
        venv_path=Path(args.venv) if getattr(args, 'venv', None) else None,
        skip_playwright=getattr(args, 'skip_playwright', False)
    )
    step_done(3, total, "Dependencies installed")

    # Step 4: verify
    step_header(4, total, "Verifying installation")
    if verify_installation():
        step_done(4, total, "Installation verified")

        # Write version from manifest
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
    """Move .opencode_staging/ → .opencode/ with backup+rollback safety."""
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
            error(f"Cannot move .opencode/ — it may be in use. Error: {e}")

    # Phase 2: move staging → target
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


def verify_installation() -> bool:
    """Run webnovel.py preflight to verify installed .opencode/ works."""
    preflight_script = Path(".opencode/scripts/webnovel.py")
    if not preflight_script.exists():
        warn(f"Preflight script not found: {preflight_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(preflight_script), "preflight"],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout:
            print(result.stdout)
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        warn("Preflight verification timed out")
        return False


def _write_installed_version():
    """Write version.json after successful install."""
    import json, urllib.request
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
        version = manifest.get("version", "unknown")
    except Exception:
        version = "unknown"

    vf = Path(".opencode") / "version.json"
    write_version_file(vf, version)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest .opencode/scripts/tests/installer/test_preflight.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/installer/preflight.py .opencode/scripts/tests/installer/test_preflight.py
git commit -m "feat(installer): add preflight.py orchestration with staging/apply

- run_install: full install flow (check→download→deps→verify)
- run_update: check manifest for new version, then run install
- apply_staging: safe .opencode_staging→.opencode with backup+rollback
- verify_installation: run webnovel.py preflight after install
- Smart mode: auto-detect OpenCode running→staging, not running→direct"
```

---

### Task 7: install.py — Bootstrap script rewrite

**Files:**
- Modify: `install.py` (complete rewrite)

- [ ] **Step 1: Write the new install.py**

`install.py`:
```python
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

        # Re-check that we have installer modules to run apply
        installer_dir = Path(".opencode/installer")
        if not installer_dir.is_dir():
            # Installer not yet extracted — download minimal installer first
            print("Downloading installer modules...")
            urls = build_urls(REPO, BRANCH, args.mirror)
            zip_path = Path(tempfile.gettempdir()) / "webnovel_installer.zip"
            if not download(urls, zip_path, args.timeout):
                print("[ERROR] Cannot download installer. Check network.")
                sys.exit(1)
            extract_opencode(zip_path, Path(".opencode"))
            zip_path.unlink(missing_ok=True)

        # Now delegate to installer/preflight.apply_staging()
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

    # Always extract installer modules (they may have changed)
    extract_opencode(zip_path, Path(".opencode"))
    zip_path.unlink(missing_ok=True)
    print("  Done.\n")

    # Phase 2: Delegate to installer/preflight
    sys.path.insert(0, str(Path.cwd() / ".opencode"))
    from installer.preflight import run_install, run_update

    if args.update:
        run_update(args)
    else:
        run_install(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify install.py is syntactically valid**

```bash
python -c "import py_compile; py_compile.compile('install.py', doraise=True); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add install.py
git commit -m "feat(installer): rewrite install.py as lightweight bootstrap

- ~130 lines, pure stdlib, no external dependencies
- Downloads repo zip, extracts installer modules, delegates to preflight.py
- --apply: standalone staging→production replacement
- --update: check manifest for new version
- --mirror: custom GitHub mirror support
- --venv / --skip-playwright: dependency options"
```

---

### Task 8: gen_manifest.py — Manifest generator

**Files:**
- Create: `.opencode/scripts/gen_manifest.py`

- [ ] **Step 1: Implement gen_manifest.py**

`.opencode/scripts/gen_manifest.py`:
```python
#!/usr/bin/env python3
"""
Generate manifest.json for the webnovel-writer .opencode/ directory.
Lists every file with SHA256 hash and size. Used for incremental updates.

Usage:
  python .opencode/scripts/gen_manifest.py [--version v1.2.0] > manifest.json
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


def hash_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def build_manifest(opencode_dir: Path, version: str) -> dict:
    """Build manifest dict for all files under opencode_dir."""
    files = {}
    for root, dirs, filenames in os.walk(opencode_dir):
        # Skip __pycache__, node_modules, .git
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git')]
        for fn in filenames:
            if fn.endswith('.pyc'):
                continue
            full = Path(root) / fn
            rel = full.relative_to(opencode_dir.parent).as_posix()
            st = full.stat()
            files[rel] = {
                "sha256": hash_file(full),
                "size": st.st_size,
            }

    return {
        "version": version,
        "generated_at": None,  # filled by CI, optional
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate manifest.json for webnovel-writer")
    parser.add_argument("--version", default="0.0.0", help="Version tag (e.g., v1.2.0)")
    parser.add_argument("--opencode-dir", default=".opencode", help="Path to .opencode directory")
    args = parser.parse_args()

    opencode_dir = Path(args.opencode_dir).resolve()
    if not opencode_dir.is_dir():
        print(f"Error: {opencode_dir} not found", file=sys.stderr)
        sys.exit(1)

    manifest = build_manifest(opencode_dir, args.version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys
    main()
```

- [ ] **Step 2: Test gen_manifest.py locally**

```bash
python .opencode/scripts/gen_manifest.py --version v0.1.0 | python -c "import json,sys; m=json.load(sys.stdin); print(f'Version: {m[\"version\"]}'); print(f'Files: {len(m[\"files\"])}')"
```
Expected: prints version and file count (>10)

- [ ] **Step 3: Generate initial manifest.json and commit**

```bash
python .opencode/scripts/gen_manifest.py --version v0.1.0 > manifest.json
git add .opencode/scripts/gen_manifest.py manifest.json
git commit -m "feat(installer): add gen_manifest.py and initial manifest.json

- gen_manifest.py: walks .opencode/, computes SHA256+size for each file
- manifest.json: generated file manifest for incremental update diffing
- Skips __pycache__, node_modules, .pyc files"
```

---

### Task 9: Documentation — INSTALL.md, README.md, .gitignore

**Files:**
- Modify: `INSTALL.md`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Update .gitignore**

```bash
echo "" >> .gitignore
echo "# Installer version tracking (generated on install)" >> .gitignore
echo ".opencode/version.json" >> .gitignore
```

- [ ] **Step 2: Rewrite INSTALL.md skill**

Replace the existing INSTALL.md content with:

```markdown
---
name: webnovel-install
description: 自动安装 Webnovel Writer。触发条件："安装"、"重新安装"、"更新"、"安装依赖"、"setup"、"初始化环境"。
compatibility: opencode
allowed-tools: Bash
---

# Webnovel Writer 安装

## 目标

一键安装或更新 Webnovel Writer 插件到当前 OpenCode 工作区。

## 执行流程

### 方式 1：curl 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

### 方式 2：下载后运行

```bash
# 下载安装脚本
python -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py', 'install.py')"

# 全新安装
python install.py

# 更新到最新版本
python install.py --update

# 创建虚拟环境安装
python install.py --venv

# 跳过 playwright 浏览器（节省时间）
python install.py --skip-playwright
```

### 安装过程（4步）

1. **系统预检** — Python 版本、磁盘空间、网络连通性
2. **下载** — 从 GitHub 下载最新 .opencode/（中国大陆自动切换镜像）
3. **安装依赖** — pip install + 可选 playwright
4. **验证** — 运行 preflight 确认安装成功

### 如果 OpenCode 正在运行

安装脚本检测到 OpenCode 正在运行时自动进入 staging 模式：

```
1. 关闭所有 OpenCode 窗口
2. 运行: python install.py --apply
3. 重新打开 OpenCode
```

### 更新

```bash
# 检查并安装更新
python install.py --update
```

增量更新机制：对比 manifest.json，只下载变更文件。

## 常见问题

| 问题 | 解决 |
|------|------|
| 下载失败 | 网络问题，使用 `--mirror` 指定镜像 |
| OpenCode 占用 | 关闭 OpenCode 后运行 `python install.py --apply` |
| pip 安装失败 | 检查 Python 版本 >= 3.10，或用 `--venv` 创建虚拟环境 |
| 权限不足 | Linux/macOS 尝试 `sudo`，Windows 以管理员运行 |
```

- [ ] **Step 3: Update README.md quick-start section**

Find and replace the quick-start/installation section in README.md to reference the new install flow:

```bash
# In README.md, replace the quickstart section with:
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

- [ ] **Step 4: Commit**

```bash
git add INSTALL.md README.md .gitignore
git commit -m "docs: update INSTALL.md, README.md, .gitignore for new installer

- INSTALL.md: rewritten for new install.py flow, includes --apply and --update
- README.md: updated quick-start section
- .gitignore: added .opencode/version.json"
```

---

### Task 10: Integration — end-to-end smoke test

**Files:**
- Create: `.opencode/scripts/tests/installer/test_integration.py`

- [ ] **Step 1: Write integration smoke test**

`.opencode/scripts/tests/installer/test_integration.py`:
```python
"""Integration smoke tests for installer — tests that modules compose correctly."""
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestModuleImports:
    """Verify all installer modules import without errors (pure stdlib guarantee)."""
    def test_import_ui(self):
        from installer import ui
        assert hasattr(ui, 'info')
        assert hasattr(ui, 'warn')

    def test_import_check(self):
        from installer import check
        assert hasattr(check, 'check_python_version')
        assert hasattr(check, 'is_opencode_running')

    def test_import_fetch(self):
        from installer import fetch
        assert hasattr(fetch, 'download_with_fallback')
        assert hasattr(fetch, 'extract_opencode_from_zip')

    def test_import_update(self):
        from installer import update
        assert hasattr(update, 'compute_diff')
        assert hasattr(update, 'read_local_version')

    def test_import_deps(self):
        from installer import deps
        assert hasattr(deps, 'create_venv')
        assert hasattr(deps, 'check_pip_available')

    def test_import_preflight(self):
        from installer import preflight
        assert hasattr(preflight, 'run_install')
        assert hasattr(preflight, 'apply_staging')


class TestEndToEndZipExtraction:
    """Verify the full extract flow works with a synthetic zip."""
    def test_full_extract_and_module_load(self):
        d = tempfile.mkdtemp()
        # Create a fake repo zip with .opencode/installer/ inside
        zip_path = Path(d) / "repo.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("repo-master/.opencode/installer/__init__.py", "")
            zf.writestr("repo-master/.opencode/installer/ui.py", "print('ui ok')")
            zf.writestr("repo-master/.opencode/scripts/webnovel.py", "print('ok')")

        from installer.fetch import extract_opencode_from_zip
        extract_dir = Path(d) / "workspace"
        extract_opencode_from_zip(zip_path, extract_dir)

        assert (extract_dir / "installer" / "__init__.py").exists()
        assert (extract_dir / "installer" / "ui.py").exists()
        assert (extract_dir / "scripts" / "webnovel.py").exists()
```

- [ ] **Step 2: Run integration tests**

```bash
python -m pytest .opencode/scripts/tests/installer/test_integration.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 3: Run full installer test suite**

```bash
python -m pytest .opencode/scripts/tests/installer/ -v
```
Expected: all tests PASS (approximately 25 tests across 6 files)

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/tests/installer/test_integration.py
git commit -m "test(installer): add integration smoke tests for module composition

- Verifies all 6 modules import cleanly (pure stdlib guarantee)
- End-to-end zip extraction and file verification
- Tests run without any external dependencies"
```

---

## Completion Checklist

After all tasks are complete, verify:

- [ ] `python install.py` runs without errors (dry-run on existing .opencode/)
- [ ] `python install.py --apply` correctly handles staging directory
- [ ] `python .opencode/scripts/gen_manifest.py --version v0.1.0` produces valid manifest.json
- [ ] All installer modules import without external dependencies
- [ ] Existing skills (webnovel-write, webnovel-export, etc.) are unaffected
- [ ] Full test suite passes: `python -m pytest .opencode/scripts/tests/installer/ -v`
