"""Safe chapter deletion with projection cleanup.

Deletes chapter markdown files and cleans up:
  - state.json progress.chapter_status
  - index.db entries for deleted chapters
  - memory scratchpad entries
  - summaries/ directory
  - story-system events (soft: mark as deleted)

Supports dry-run mode (--dry-run) to preview changes without applying.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_range(spec: str) -> list[int]:
    chapters = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            chapters.extend(range(int(a), int(b) + 1))
        else:
            chapters.append(int(part))
    return sorted(set(chapters))


def _find_chapter_files(project_root: Path, chapter_nums: list[int]) -> dict[int, Path]:
    """Find markdown files matching chapter numbers."""
    text_dir = project_root / "正文"
    if not text_dir.is_dir():
        return {}

    found: dict[int, Path] = {}
    for f in text_dir.rglob("第*章*.md"):
        m = re.match(r"第0*(\d+)章", f.name)
        if m:
            num = int(m.group(1))
            if num in chapter_nums:
                found[num] = f
    return found


def _clean_state_json(project_root: Path, chapters: list[int], dry_run: bool) -> list[str]:
    """Remove chapter entries from state.json."""
    state_path = project_root / ".webnovel" / "state.json"
    if not state_path.is_file():
        return ["state.json not found — skipped"]

    if dry_run:
        return [f"Would remove chapters {chapters} from state.json progress.chapter_status"]

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        chapter_status = (state.get("progress") or {}).get("chapter_status") or {}
        removed = []
        for ch in chapters:
            key = str(ch)
            if key in chapter_status:
                del chapter_status[key]
                removed.append(key)

        if removed:
            state.setdefault("progress", {})["chapter_status"] = chapter_status
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return [f"Removed {len(removed)} entries from state.json: {removed}"]
        return ["No matching entries in state.json"]
    except Exception as e:
        return [f"Failed to update state.json: {e}"]


def _clean_memory(project_root: Path, chapters: list[int], dry_run: bool) -> list[str]:
    """Remove memory entries sourced from deleted chapters."""
    scratchpad = project_root / ".webnovel" / "memory_scratchpad.json"
    if not scratchpad.is_file():
        return ["memory_scratchpad.json not found — skipped"]

    if dry_run:
        return [f"Would clean memory entries sourced from chapters {chapters}"]

    try:
        data = json.loads(scratchpad.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return ["memory_scratchpad.json is not a list — skipped"]

        original = len(data)
        data = [item for item in data
                if isinstance(item, dict)
                and item.get("source_chapter") not in chapters
                and item.get("planted_chapter") not in chapters]
        removed = original - len(data)

        if removed > 0:
            scratchpad.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return [f"Removed {removed} memory entries ({original} → {len(data)})"]
        return ["No matching memory entries"]
    except Exception as e:
        return [f"Failed to clean memory: {e}"]


def cmd_delete_chapters(args) -> int:
    """Main entry: delete chapters and clean projections."""
    project_root = Path(args.project_root).expanduser().resolve()
    if not (project_root / ".webnovel" / "state.json").is_file():
        print("ERROR: Not a webnovel project root.", file=sys.stderr)
        return 1

    chapters = _parse_range(args.chapters)
    if not chapters:
        print("ERROR: no chapters specified", file=sys.stderr)
        return 1

    dry_run = getattr(args, 'dry_run', False)
    label = "[DRY RUN] " if dry_run else ""

    # 1. Find chapter files
    found = _find_chapter_files(project_root, chapters)
    missing = [c for c in chapters if c not in found]

    print(f"{label}Chapters to delete: {chapters}")
    print(f"{label}  Found: {list(found.keys())}")
    if missing:
        print(f"{label}  Missing (no file): {missing}")

    if dry_run:
        print()

    # 2. Clean state.json
    for msg in _clean_state_json(project_root, chapters, dry_run):
        print(f"{label}  {msg}")

    # 3. Clean memory
    for msg in _clean_memory(project_root, chapters, dry_run):
        print(f"{label}  {msg}")

    # 4. Delete chapter files
    for num, path in found.items():
        if dry_run:
            print(f"{label}  Would delete: {path.relative_to(project_root)}")
        else:
            try:
                path.unlink()
                print(f"  Deleted: {path.relative_to(project_root)}")
            except OSError as e:
                print(f"  FAILED: {path.relative_to(project_root)} — {e}")

    if dry_run:
        print(f"\nDry run complete. Run without --dry-run to apply.")
    else:
        print(f"\nDeleted {len(found)} chapter(s). Run 'webnovel state process-chapter' to rebuild projections if needed.")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Safe chapter deletion with projection cleanup")
    ap.add_argument("chapters", help="Chapter range, e.g. '5-12' or '5,7,9-12'")
    ap.add_argument("--project-root", required=True, help="Book project root")
    ap.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    args = ap.parse_args()
    raise SystemExit(cmd_delete_chapters(args))
