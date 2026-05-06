#!/usr/bin/env python3
"""Export manager CLI — 章节收集 + 格式 dispatch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


# ── 章节收集 ─────────────────────────────────────────────

def collect_chapters(
    project_root: Path,
    range_spec: Optional[str] = None,
    volume: Optional[int] = None,
) -> list[tuple[int, str, Path]]:
    """
    收集 正文/ 下所有章节文件，返回 [(章号, 标题文本, 文件路径), ...]，
    按章号升序排列。支持 --range / --volume 过滤。

    章号从文件名提取，兼容:
      - 正文/第0001章-标题.md  (平铺布局)
      - 正文/第1卷/第001章-标题.md  (卷布局)
    """
    chapters_dir = project_root / "正文"
    if not chapters_dir.is_dir():
        return []

    # 兼容导入路径
    try:
        from chapter_paths import extract_chapter_num_from_filename
    except ImportError:
        from scripts.chapter_paths import extract_chapter_num_from_filename

    candidates: list[tuple[int, Path]] = []
    for f in sorted(chapters_dir.rglob("第*章*.md")):
        num = extract_chapter_num_from_filename(f.name)
        if num is not None:
            candidates.append((num, f))

    candidates.sort(key=lambda x: x[0])

    # 按卷过滤
    if volume is not None:
        try:
            from chapter_paths import volume_num_for_chapter
        except ImportError:
            from scripts.chapter_paths import volume_num_for_chapter
        candidates = [(n, f) for n, f in candidates if volume_num_for_chapter(n) == volume]

    # 按范围过滤
    if range_spec and range_spec != "all":
        allowed = _parse_range(range_spec, max_num=max(c[0] for c in candidates) if candidates else 0)
        candidates = [(n, f) for n, f in candidates if n in allowed]

    # 读取每章第一行作为标题
    result: list[tuple[int, str, Path]] = []
    for num, path in candidates:
        try:
            first_line = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
            # 去掉 markdown heading 符号
            title = first_line.lstrip("#").strip() if first_line.startswith("#") else first_line
        except Exception:
            title = f"第{num}章"
        result.append((num, title, path))

    return result


def _parse_range(spec: str, max_num: int = 0) -> set[int]:
    """解析范围字符串: '1-50', '1,3,5', 'all'"""
    allowed: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s.strip()), int(hi_s.strip())
            allowed.update(range(lo, hi + 1))
        else:
            allowed.add(int(part))
    if max_num > 0:
        allowed = {n for n in allowed if 1 <= n <= max_num}
    return allowed


# ── CLI ──────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> int:
    chapters = collect_chapters(args.project_root)
    if not chapters:
        print("无章节文件")
        return 1
    for num, title, path in chapters:
        print(f"第{num:04d}章  {title}  ({path})")
    print(f"\n共 {len(chapters)} 章")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    project_root = args.project_root
    chapters = collect_chapters(project_root, range_spec=args.range, volume=args.volume)

    if not chapters:
        print("错误：正文/ 目录不存在或无章节文件。请先使用 /webnovel-write 创建章节。")
        return 1

    fmt = args.format or "md"
    output = args.output
    if not output:
        title = args.title or project_root.name
        output = str(project_root / "导出" / f"{title}.{fmt}")

    # 确保输出目录存在
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    if fmt == "md":
        from .markdown import export_markdown
        title = args.title or project_root.name
        export_markdown(chapters, Path(output), title)
    elif fmt == "txt":
        from .txt import export_txt
        export_txt(chapters, Path(output))
    elif fmt == "epub":
        from .epub import export_epub
        export_epub(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            author=args.author,
            cover=args.cover,
            style=args.style,
            cover_size=args.cover_size,
        )
    else:
        print(f"不支持的格式: {fmt}，可选: md, txt, epub")
        return 1

    print(f"导出完成: {output}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="webnovel export manager")
    parser.add_argument("--project-root", type=Path, required=True, help="项目根目录")

    sub = parser.add_subparsers(dest="action")

    # export list
    sub.add_parser("list", help="列出可导出章节")

    # export (执行导出)
    p_export = sub.add_parser("export", help="执行导出")
    p_export.add_argument("--format", choices=["md", "txt", "epub"], default="md", help="输出格式")
    p_export.add_argument("--range", help="章节范围: 1-50 / 1,3,5 / all")
    p_export.add_argument("--volume", type=int, help="按卷导出")
    p_export.add_argument("--output", help="输出文件路径")
    p_export.add_argument("--title", help="书名")
    p_export.add_argument("--author", help="作者名 (EPUB)")
    p_export.add_argument("--cover", help="封面图路径 (EPUB)")
    p_export.add_argument("--style", help="自定义 CSS 路径 (EPUB)")
    p_export.add_argument("--cover-size", default="1200x1600", help="封面裁剪尺寸 (EPUB)")

    args = parser.parse_args()

    if args.action == "list":
        code = cmd_list(args)
    elif args.action == "export":
        code = cmd_export(args)
    else:
        parser.print_help()
        code = 1

    raise SystemExit(code)


if __name__ == "__main__":
    main()
