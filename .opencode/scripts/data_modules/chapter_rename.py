"""章节文件名编号统一工具。

将 `第060章-标题.md` 或 `第060章.md` 统一为 `第0060章-标题.md` / `第0060章.md`（四位数编号）。
也处理 `chapter_60.json` → `chapter_0060.json` 格式。

用法:
  python chapter_rename.py --project-root /path/to/project --dry-run
  python chapter_rename.py --project-root /path/to/project
"""
import argparse
import re
from pathlib import Path


# 匹配 "第060章-标题.md" 或 "第060章.md"（无标题）
_RE_CHINESE = re.compile(r"^第(\d{1,3})章(-.+)?(\.md)$")
# 匹配 "chapter_60.json" 或 "chapter_60.md" 格式
_RE_CHAPTER = re.compile(r"^chapter_(\d{1,3})\.(json|md)$")


def _pad_num(num_str: str, width: int = 4) -> str:
    """将数字字符串补齐到指定位数。"""
    return num_str.zfill(width)


def scan_chapters(story_dir: Path, recursive: bool = False) -> list[tuple[Path, Path]]:
    """扫描需要重命名的文件。返回 [(旧路径, 新路径), ...]"""
    renames = []

    if not story_dir.is_dir():
        return renames

    pattern = "**/*" if recursive else "*"
    for f in sorted(story_dir.glob(pattern)):
        if not f.is_file():
            continue

        m = _RE_CHINESE.match(f.name)
        if m:
            num, title_part, ext = m.groups()
            if len(num) < 4:
                new_name = f"第{_pad_num(num)}章{title_part or ''}{ext}"
                renames.append((f, f.parent / new_name))
            continue

        m = _RE_CHAPTER.match(f.name)
        if m:
            num, ext = m.groups()
            if len(num) < 4:
                new_name = f"chapter_{_pad_num(num)}.{ext}"
                renames.append((f, f.parent / new_name))

    return renames


def scan_story_system(ss_dir: Path) -> list[tuple[Path, Path]]:
    """扫描 .story-system/chapters/ 下需要重命名的文件。"""
    renames = []
    chapters_dir = ss_dir / "chapters"

    if not chapters_dir.is_dir():
        return renames

    for f in sorted(chapters_dir.iterdir()):
        if not f.is_file():
            continue

        m = _RE_CHAPTER.match(f.name)
        if m:
            num, ext = m.groups()
            if len(num) < 4:
                new_name = f"chapter_{_pad_num(num)}.{ext}"
                renames.append((f, f.parent / new_name))

    return renames


def apply_renames(renames: list[tuple[Path, Path]], dry_run: bool = True) -> int:
    """执行重命名。返回成功数。"""
    count = 0
    for old, new in renames:
        if dry_run:
            print(f"  [DRY-RUN] {old.name} → {new.name}")
        else:
            if new.exists():
                print(f"  [SKIP] 目标已存在: {new.name}")
                continue
            old.rename(new)
            print(f"  [OK] {old.name} → {new.name}")
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="章节文件名编号统一工具")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行")
    parser.add_argument("--recursive", action="store_true", help="递归扫描子目录（如按卷组织）")
    args = parser.parse_args()

    root = Path(args.project_root)
    story_dir = root / "story"
    ss_dir = root / ".story-system"

    print(f"项目: {root}")
    print(f"模式: {'预览' if args.dry_run else '执行'}\n")

    if not args.dry_run:
        print("⚠ 注意：重命名操作非原子性。中途失败会导致部分文件已重命名。")
        print("  建议先用 --dry-run 预览，确认无误后再执行。\n")

    all_renames = []

    # story/ 目录
    story_renames = scan_chapters(story_dir, recursive=args.recursive)
    if story_renames:
        print(f"story/ 目录 ({len(story_renames)} 个文件):")
        all_renames.extend(story_renames)
        apply_renames(story_renames, args.dry_run)
    else:
        print("story/ 目录: 无需重命名")

    print()

    # .story-system/chapters/ 目录
    ss_renames = scan_story_system(ss_dir)
    if ss_renames:
        print(f".story-system/chapters/ 目录 ({len(ss_renames)} 个文件):")
        all_renames.extend(ss_renames)
        apply_renames(ss_renames, args.dry_run)
    else:
        print(".story-system/chapters/ 目录: 无需重命名")

    print(f"\n{'将' if args.dry_run else '已'}处理 {len(all_renames)} 个文件")
    if args.dry_run and all_renames:
        print("去掉 --dry-run 参数执行实际重命名")


if __name__ == "__main__":
    main()
