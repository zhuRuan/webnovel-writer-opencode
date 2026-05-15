# Tag + Date-Stamped Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Git tags become manual-only version anchors; CI auto-generates date-stamped sub-versions within each tag; install script shows changelog.

**Architecture:** Two CI jobs replace the current single auto-tag workflow. `gen_manifest.py` gains changelog support. `install.py` compares local/remote version and displays update log.

**Tech Stack:** Bash shell (CI), Python stdlib (installer)

---

### Task 1: gen_manifest.py — add changelog, tag, updated fields

**Files:**
- Modify: `.opencode/scripts/gen_manifest.py`

- [ ] **Step 1: Update build_manifest signature**

Change `build_manifest()` to accept optional `tag`, `updated`, `changelog` params:

```python
def build_manifest(opencode_dir: Path, version: str,
                   tag: str = "", updated: str = "",
                   changelog: list = None) -> dict:
    files = {}
    for root, dirs, filenames in os.walk(opencode_dir):
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

    result = {
        "version": version,
        "tag": tag,
        "updated": updated,
        "changelog": changelog or [],
        "files": files,
    }
    return result
```

- [ ] **Step 2: Add CLI arguments for new fields**

```python
def main():
    parser = argparse.ArgumentParser(description="Generate manifest.json for webnovel-writer")
    parser.add_argument("--version", default="0.0.0")
    parser.add_argument("--tag", default="")
    parser.add_argument("--updated", default="")
    parser.add_argument("--changelog-file", default="",
                        help="Path to JSON file with changelog array")
    parser.add_argument("--opencode-dir", default=".opencode")
    args = parser.parse_args()

    changelog = []
    if args.changelog_file and Path(args.changelog_file).is_file():
        changelog = json.loads(Path(args.changelog_file).read_text(encoding="utf-8"))

    opencode_dir = Path(args.opencode_dir).resolve()
    if not opencode_dir.is_dir():
        print(f"Error: {opencode_dir} not found", file=sys.stderr)
        sys.exit(1)

    manifest = build_manifest(opencode_dir, args.version,
                              tag=args.tag, updated=args.updated,
                              changelog=changelog)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
```

- [ ] **Step 3: Run tests to verify**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov
```

Expected: 40 PASS

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/gen_manifest.py
git commit -m "feat: add tag, updated, changelog fields to gen_manifest.py"
```

---

### Task 2: CI — rewrite manifest.yml for date-stamped versions + tag releases

**Files:**
- Modify: `.github/workflows/manifest.yml` (complete rewrite)

- [ ] **Step 1: Write the new workflow file**

```yaml
name: Version & Release

on:
  push:
    branches: [master]
    paths:
      - '.opencode/**'
      - '!manifest.json'
      - '!.github/**'
    tags:
      - 'v*'

jobs:
  update-manifest:
    if: github.ref_type == 'branch'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    env:
      FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Determine version
        run: |
          TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
          DATE_VER=$(date -u +'%Y%m%d.%H%M')
          VERSION="${TAG}-${DATE_VER}"
          UPDATED=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
          echo "tag=$TAG" >> $GITHUB_OUTPUT
          echo "version=$VERSION" >> $GITHUB_OUTPUT
          echo "updated=$UPDATED" >> $GITHUB_OUTPUT

      - name: Build changelog from previous commit
        run: |
          # Get timestamp of last CI run from manifest
          LAST_UPDATED=$(python3 -c "
      import json
      try:
          m = json.load(open('manifest.json', encoding='utf-8'))
          print(m.get('updated', ''))
      except: pass
      ")
          # Collect commits since last update, format as JSON array
          if [ -n "$LAST_UPDATED" ]; then
            SINCE="--since=$LAST_UPDATED"
          else
            SINCE="--since=$(git log --reverse --format='%aI' HEAD | head -1)"
          fi
          git log $SINCE --format='{"hash":"%h","type":"%s","message":"%s"}' --no-merges \
            | python3 -c "
      import sys, json
      entries = []
      for line in sys.stdin:
          line = line.strip()
          if not line: continue
          try:
              e = json.loads(line)
              msg = e.get('message','')
              e['type'] = msg.split(':')[0] if ':' in msg else 'chore'
              e['message'] = msg
              entries.append(e)
          except: pass
      print(json.dumps(entries[:50], ensure_ascii=True))
      " > /tmp/changelog.json

      - name: Regenerate manifest
        env:
          PYTHONUTF8: "1"
        run: |
          python3 .opencode/scripts/gen_manifest.py \
            --version "${{ steps.ver.outputs.version }}" \
            --tag "${{ steps.ver.outputs.tag }}" \
            --updated "${{ steps.ver.outputs.updated }}" \
            --changelog-file /tmp/changelog.json \
            --opencode-dir .opencode > manifest.json

      - name: Commit manifest
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if ! git diff --quiet manifest.json; then
            git add manifest.json
            git commit -m "chore: update manifest to ${{ steps.ver.outputs.version }} [skip ci]"
            git push origin master
          fi

  release:
    if: github.ref_type == 'tag'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    env:
      FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Get tag info
        run: |
          TAG=${GITHUB_REF#refs/tags/}
          PREV_TAG=$(git describe --tags --abbrev=0 --exclude="$TAG" 2>/dev/null || echo "")
          echo "tag=$TAG" >> $GITHUB_OUTPUT
          echo "prev_tag=$PREV_TAG" >> $GITHUB_OUTPUT

      - name: Build changelog
        run: |
          if [ -n "${{ steps.tags.outputs.prev_tag }}" ]; then
            RANGE="${{ steps.tags.outputs.prev_tag }}..${{ steps.tags.outputs.tag }}"
          else
            RANGE="${{ steps.tags.outputs.tag }}"
          fi
          git log "$RANGE" --format='{"hash":"%h","type":"%s","message":"%s"}' --no-merges \
            | python3 -c "
      import sys, json
      entries = []
      for line in sys.stdin:
          line = line.strip()
          if not line: continue
          try:
              e = json.loads(line)
              msg = e.get('message','')
              e['type'] = msg.split(':')[0] if ':' in msg else 'chore'
              e['message'] = msg
              entries.append(e)
          except: pass
      print(json.dumps(entries, ensure_ascii=True))
      " > /tmp/changelog.json

      - name: Update manifest for tag
        env:
          PYTHONUTF8: "1"
        run: |
          python3 .opencode/scripts/gen_manifest.py \
            --version "${{ steps.tags.outputs.tag }}" \
            --tag "${{ steps.tags.outputs.tag }}" \
            --updated "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
            --changelog-file /tmp/changelog.json \
            --opencode-dir .opencode > manifest.json
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add manifest.json
          git commit -m "chore: release ${{ steps.tags.outputs.tag }} [skip ci]" || true
          git push origin master

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.tags.outputs.tag }}
          name: Webnovel Writer for OpenCode ${{ steps.tags.outputs.tag }}
          body_path: /tmp/changelog.md
          generate_release_notes: false
```

- [ ] **Step 2: Manually verify the YAML syntax**

```bash
# Use a YAML validator if available, or just check git diff for structure
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/manifest.yml
git commit -m "ci: rewrite manifest workflow for date-stamped versions + manual tags"
```

---

### Task 3: update.py — write full version data to version.json

**Files:**
- Modify: `.opencode/installer/update.py`

- [ ] **Step 1: Update write_version_file**

Change `write_version_file` to store `tag` and `updated` alongside `version`:

```python
def write_version_file(path: Path, version: str, tag: str = "", updated: str = ""):
    data = {
        "version": version,
        "tag": tag or version.split("-")[0] if "-" in version else version,
        "updated": updated or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "channel": "install.py",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 2: Update read_local_version**

Return version dict with `tag` field:

Already returns full dict — no change needed. Just ensure callers handle the extra fields.

- [ ] **Step 3: Add fetch_remote_manifest function**

```python
def fetch_remote_manifest(manifest_url: str = None) -> dict:
    """Download remote manifest.json. Returns empty dict on failure."""
    import urllib.request
    if manifest_url is None:
        manifest_url = MANIFEST_URL
    try:
        with urllib.request.urlopen(manifest_url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}
```

- [ ] **Step 4: Update needs_update to use version/tag comparison**

```python
def needs_update(manifest_url: str = None) -> bool:
    import urllib.request
    if manifest_url is None:
        manifest_url = MANIFEST_URL

    try:
        remote = fetch_remote_manifest(manifest_url)
    except Exception as e:
        warn(f"Cannot check for updates: {e}")
        return False

    local = read_local_version()

    local_ver = local.get("version", "unknown")
    remote_ver = remote.get("version", "")
    if local_ver == "unknown":
        return True
    return remote_ver != local_ver
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest .opencode/scripts/tests/installer/ -q --no-cov
```

Expected: existing tests pass (39+)

- [ ] **Step 6: Commit**

```bash
git add .opencode/installer/update.py
git commit -m "feat: add tag/updated fields to version.json, add fetch_remote_manifest"
```

---

### Task 4: install.py — show changelog on update

**Files:**
- Modify: `install.py` (updates to `run_selected_action` flow)

- [ ] **Step 1: Add helper to fetch and compare versions**

```python
def _check_update():
    """Compare local version with remote manifest. Returns (is_update, changelog, remote)."""
    local_vf = Path(".opencode/version.json")
    local = {}
    if local_vf.is_file():
        import json
        try:
            local = json.loads(local_vf.read_text(encoding="utf-8"))
        except Exception:
            pass

    remote = {}
    try:
        import urllib.request
        import json as _json
        with urllib.request.urlopen(
            "https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/manifest.json",
            timeout=10
        ) as resp:
            remote = _json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return (False, [], {})

    local_ver = local.get("version", "unknown")
    remote_ver = remote.get("version", "")
    if local_ver == "unknown" or not remote_ver:
        return (True, [], remote)
    if local_ver == remote_ver:
        return (False, [], remote)

    local_tag = local.get("tag", "")
    remote_tag = remote.get("tag", "")
    changelog = remote.get("changelog", [])
    return (True, changelog, remote, local_tag, remote_tag)
```

- [ ] **Step 2: Add _show_changelog function**

```python
def _show_changelog(changelog, remote_version, local_tag, remote_tag):
    """Display update changelog in a box."""
    is_major = (local_tag != remote_tag)
    tag_display = remote_tag or remote_version

    title = f"Webnovel Writer for OpenCode {tag_display}"
    subtitle = "大版本更新" if is_major else "小版本更新"

    print(f"\n{C}┌{BAR}┐{R}")
    print(f"{C}│{R}  {B}{title}{R}  {C}│{R}")
    print(f"{C}│{R}  {subtitle}  {C}│{R}")
    print(f"{C}├{BAR}┤{R}")
    if changelog:
        shown = 0
        for entry in changelog:
            if shown >= 15:
                print(f"{C}│{R}  ... 还有 {len(changelog) - 15} 条变更  {C}│{R}")
                break
            msg = entry.get("message", "")[:46]
            print(f"{C}│{R}  {D}-{R} {msg}  {C}│{R}")
            shown += 1
    else:
        print(f"{C}│{R}  (无详细日志)  {C}│{R}")
    print(f"{C}└{BAR}┘{R}")
    print()
```

- [ ] **Step 3: Integrate into install flow**

In `run_selected_action()`, right before the download step, add:

```python
    is_update, changelog, remote = _check_update()
    if is_update and changelog:
        local_tag = ...  # from _check_update return
        remote_tag = ... # from _check_update return
        _show_changelog(changelog, remote.get("version", ""), local_tag, remote_tag)
```

And in preflight.py's `_write_installed_version`, update to write full data:

```python
def _write_installed_version():
    import json
    import urllib.request
    from installer.update import write_version_file, MANIFEST_URL

    tag = ""; updated = ""
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=10) as resp:
            manifest = json.loads(resp.read().decode("utf-8", errors="replace"))
        version = manifest.get("version", "unknown")
        tag = manifest.get("tag", "")
        updated = manifest.get("updated", "")
    except Exception as e:
        warn(f"无法确定版本: {e}")
        version = "unknown"

    vf = Path(".opencode") / "version.json"
    write_version_file(vf, version, tag=tag, updated=updated)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov
python -m pytest .opencode/scripts/tests/installer/test_ui.py -q --no-cov
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add install.py .opencode/installer/preflight.py
git commit -m "feat: show update changelog in install script, compare tag/dates"
```

---

### Task 5: End-to-end verification

**Files:**
- No code changes. Verify the full pipeline.

- [ ] **Step 1: Verify gen_manifest.py locally**

```bash
python .opencode/scripts/gen_manifest.py \
  --version v2.8.0-20260515.1430 \
  --tag v2.8.0 \
  --updated "2026-05-15T14:30:00Z" \
  --changelog-file /dev/null \
  --opencode-dir .opencode | python -m json.tool > /dev/null && echo "OK"
```

- [ ] **Step 2: Verify install.py syntax**

```bash
python -c "import ast; ast.parse(open('install.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: Verify installer tests**

```bash
cd .opencode/scripts && python -m pytest tests/installer/ -q --no-cov
```

- [ ] **Step 4: Commit any final adjustments**

```bash
git add -A && git commit -m "chore: final verification of tag versioning pipeline"
```

---

### Test Summary

After all tasks complete:

| Test Suite | Expected |
|-----------|----------|
| `tests/installer/` | 39+ PASS |
| `tests/test_export_manager.py` | 40 PASS |
| `install.py` syntax check | OK |
| `manifest.yml` structure | Valid YAML |
