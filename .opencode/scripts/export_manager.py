#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正文导出管理器

支持将章节正文导出为多种格式：
- TXT: 纯文本
- Markdown: Markdown 格式
- EPUB: 电子书
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_CSS = """body {
    font-family: "SimSun", "Songti SC", serif;
    line-height: 1.8;
    text-indent: 2em;
    margin: 1em;
}
h1, h2, h3 {
    text-align: center;
    text-indent: 0;
}
p {
    margin: 0.5em 0;
}"""


def crop_cover_image(
    image_path: str, target_size: tuple = (1200, 1600)
) -> Optional[bytes]:
    """裁剪封面图片到目标尺寸（居中裁剪）

    Args:
        image_path: 原始图片路径
        target_size: 目标尺寸 (width, height)

    Returns:
        处理后的图片二进制数据，失败返回 None
    """
    try:
        from PIL import Image
    except ImportError:
        print("警告: 需要 Pillow 库进行封面裁剪")
        return None

    try:
        img = Image.open(image_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        src_width, src_height = img.size
        target_width, target_height = target_size

        # 计算缩放后的尺寸（保持比例）
        scale = max(target_width / src_width, target_height / src_height)
        new_width = int(src_width * scale)
        new_height = int(src_height * scale)

        # 缩放图片
        img = img.resize((new_width, new_height), Image.LANCZOS)

        # 计算裁剪区域（居中）
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        # 裁剪
        img = img.crop((left, top, right, bottom))

        # 输出为 JPEG
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()
    except Exception as e:
        print(f"警告: 封面裁剪失败: {e}")
        return None


class ExportManager:
    """正文导出管理器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.novel_dir = self.project_root / "正文"
        self.output_dir = self.project_root / "导出"

    def get_chapter_list(self) -> List[int]:
        """获取章节列表（递归查找子目录）"""
        chapters = []
        if not self.novel_dir.exists():
            return chapters

        # 递归查找所有 .md 文件
        for f in self.novel_dir.rglob("*.md"):
            if f.is_file():
                match = re.search(r"第(\d+)章", f.stem)
                if match:
                    chapters.append(int(match.group(1)))

        return sorted(set(chapters))

    def parse_chapter_range(self, range_str: str) -> List[int]:
        """解析章节范围

        支持格式：
        - "1-10" -> [1, 2, ..., 10]
        - "1,3,5" -> [1, 3, 5]
        - "1,3-5,10" -> [1, 3, 4, 5, 10]
        - "all" -> 全部章节
        """
        if range_str.lower() == "all":
            return self.get_chapter_list()

        chapters = []
        parts = range_str.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                chapters.extend(range(int(start), int(end) + 1))
            else:
                chapters.append(int(part))

        return sorted(set(chapters))

    def get_chapter_content(self, chapter: int) -> Tuple[str, str]:
        """获取章节内容（递归查找子目录）

        Returns:
            (title, content): 章节标题和正文内容
        """
        padded = f"{chapter:04d}"

        # 递归查找带标题的文件名
        for pattern in [f"**/第{padded}章-*.md", f"**/第{padded}章.md"]:
            matches = list(self.novel_dir.glob(pattern))
            if matches:
                file_path = matches[0]
                content = file_path.read_text(encoding="utf-8")
                # 从文件名提取标题
                title = file_path.stem.replace(f"第{padded}章-", "").replace(f"第{padded}章", "")
                return title or f"第{chapter}章", content

        return f"第{chapter}章", ""

    def export_to_txt(
        self,
        chapters: List[int],
        output_path: str,
        include_title: bool = True,
        add_separator: bool = True,
    ) -> int:
        """导出为 TXT 格式

        Args:
            chapters: 章节列表
            output_path: 输出文件路径
            include_title: 是否包含章节标题
            add_separator: 章节之间是否添加分隔符

        Returns:
            导出的章节数量
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        output_file = Path(output_path)
        if output_file.is_dir():
            output_file = self.output_dir / f"{self.project_root.name}.txt"

        with open(output_file, "w", encoding="utf-8") as f:
            for i, chapter in enumerate(chapters):
                title, content = self.get_chapter_content(chapter)

                if include_title:
                    f.write(f"\n{title}\n")
                    f.write("=" * len(title) + "\n\n")

                # 去除 frontmatter（--- 之间的内容）
                lines = content.split("\n")
                in_frontmatter = False
                frontmatter_count = 0

                for line in lines:
                    if line.strip() == "---":
                        frontmatter_count += 1
                        if frontmatter_count == 1:
                            in_frontmatter = True
                            continue
                        elif frontmatter_count == 2:
                            in_frontmatter = False
                            continue
                    if not in_frontmatter and line.strip():
                        f.write(line + "\n")

                if add_separator and i < len(chapters) - 1:
                    f.write("\n" + "=" * 40 + "\n\n")

        print(f"[OK] 已导出 TXT: {output_file} ({len(chapters)} 章)")
        return len(chapters)

    def export_to_markdown(
        self,
        chapters: List[int],
        output_path: str,
    ) -> int:
        """导出为 Markdown 格式

        Args:
            chapters: 章节列表
            output_path: 输出文件路径

        Returns:
            导出的章节数量
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        output_file = Path(output_path)
        if output_file.is_dir():
            output_file = self.output_dir / f"{self.project_root.name}.md"

        with open(output_file, "w", encoding="utf-8") as f:
            for i, chapter in enumerate(chapters):
                title, content = self.get_chapter_content(chapter)

                # 章节标题（Markdown 格式）
                f.write(f"\n## {title}\n\n")

                # 去除 frontmatter（--- 之间的内容）
                lines = content.split("\n")
                in_frontmatter = False
                frontmatter_count = 0

                for line in lines:
                    if line.strip() == "---":
                        frontmatter_count += 1
                        if frontmatter_count == 1:
                            in_frontmatter = True
                            continue
                        elif frontmatter_count == 2:
                            in_frontmatter = False
                            continue
                    if not in_frontmatter and line.strip():
                        f.write(line + "\n")

                if i < len(chapters) - 1:
                    f.write("\n---\n")

        print(f"[OK] 已导出 Markdown: {output_file} ({len(chapters)} 章)")
        return len(chapters)

    def export_to_epub(
        self,
        chapters: List[int],
        output_path: str,
        author: str = "未知作者",
        language: str = "zh-CN",
        cover_path: Optional[str] = None,
        style_path: Optional[str] = None,
        cover_size: tuple = (1200, 1600),
    ) -> int:
        """导出为 EPUB 格式

        Args:
            chapters: 章节列表
            output_path: 输出文件路径
            author: 作者名
            language: 语言代码
            cover_path: 封面图路径（默认检测项目根目录/cover.jpg）
            style_path: 自定义CSS路径（默认检测项目根目录/style.css）
            cover_size: 封面裁剪尺寸 (width, height)
        """
        try:
            import ebooklib
            from ebooklib import epub
        except ImportError:
            print("错误: 需要安装 ebooklib 库")
            print("运行: pip install ebooklib")
            return 0

        self.output_dir.mkdir(parents=True, exist_ok=True)

        output_file = Path(output_path)
        if output_file.is_dir():
            output_file = self.output_dir / f"{self.project_root.name}.epub"

        book = epub.EpubBook()

        book.set_identifier(f"novel-{self.project_root.name}")
        book.set_title(self.project_root.name)
        book.set_language(language)
        book.add_author(author)

        # 处理封面图
        if cover_path is None:
            default_cover = self.project_root / "cover.jpg"
            if default_cover.exists():
                cover_path = str(default_cover)

        if cover_path and Path(cover_path).exists():
            cover_data = crop_cover_image(cover_path, cover_size)
            if cover_data:
                book.set_cover("cover.jpg", cover_data)
                print(f"[INFO] 已添加封面: {cover_path}")
            else:
                print(f"[WARN] 封面处理失败，跳过封面")
        else:
            print(f"[INFO] 未找到封面图，跳过")

        # 处理 CSS 样式
        css_content = DEFAULT_CSS

        if style_path is None:
            default_style = self.project_root / "style.css"
            if default_style.exists():
                style_path = str(default_style)

        if style_path and Path(style_path).exists():
            try:
                css_content = Path(style_path).read_text(encoding="utf-8")
                print(f"[INFO] 已加载自定义样式: {style_path}")
            except Exception as e:
                print(f"[WARN] 加载自定义样式失败，使用默认样式: {e}")
        elif not style_path:
            print(f"[INFO] 未找到自定义样式，使用默认样式")

        # 创建样式文件
        style_item = epub.EpubItem(
            uid="style",
            file_name="style/style.css",
            media_type="text/css",
            content=css_content,
        )
        book.add_item(style_item)

        spine = ["nav"]
        toc = []

        for chapter in chapters:
            chapter_title, content = self.get_chapter_content(chapter)

            c = epub.EpubHtml(
                title=chapter_title,
                file_name=f"chapter_{chapter}.xhtml",
                lang=language,
            )

            html_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{chapter_title}</title>
    <link rel="stylesheet" type="text/css" href="style/style.css" />
</head>
<body>
<h1>{chapter_title}</h1>
"""

            lines = content.split("\n")
            in_frontmatter = False
            frontmatter_count = 0

            for line in lines:
                if line.strip() == "---":
                    frontmatter_count += 1
                    if frontmatter_count == 1:
                        in_frontmatter = True
                        continue
                    elif frontmatter_count == 2:
                        in_frontmatter = False
                        continue

                if not in_frontmatter and line.strip():
                    html_content += f"<p>{line}</p>\n"

            html_content += "</body>\n</html>"

            c.content = html_content
            book.add_item(c)

            spine.append(c)
            toc.append(epub.Link(f"chapter_{chapter}.xhtml", chapter_title, f"chapter_{chapter}"))

        book.toc = tuple(toc)
        book.spine = spine

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(str(output_file), book, {})
        print(f"[OK] 已导出 EPUB: {output_file} ({len(chapters)} 章)")
        return len(chapters)


def main():
    # 启用 Windows UTF-8 支持
    try:
        from runtime_compat import enable_windows_utf8_stdio
        enable_windows_utf8_stdio(skip_in_pytest=True)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="正文导出工具")
    parser.add_argument("--project-root", required=True, help="项目根目录")

    sub = parser.add_subparsers(dest="command", required=True)

    # list 命令
    p_list = sub.add_parser("list", help="列出可导出章节")
    p_list.set_defaults(func=cmd_list)

    # export 命令
    p_export = sub.add_parser("export", help="导出正文")
    p_export.add_argument(
        "--range",
        default="all",
        help="章节范围，如 1-10,15,20-30 或 all",
    )
    p_export.add_argument(
        "--format",
        choices=["txt", "markdown", "epub"],
        default="txt",
        help="导出格式",
    )
    p_export.add_argument(
        "--output",
        help="输出文件路径（默认自动生成）",
    )
    p_export.add_argument("--author", default="未知作者", help="作者名（仅 EPUB 需要）")
    p_export.add_argument(
        "--cover",
        help="封面图路径（默认: 项目根目录/cover.jpg）",
    )
    p_export.add_argument(
        "--style",
        help="自定义 CSS 路径（默认: 项目根目录/style.css）",
    )
    p_export.add_argument(
        "--cover-size",
        default="1200x1600",
        help="封面裁剪尺寸（格式: WIDTHxHEIGHT，默认: 1200x1600）",
    )
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()

    if args.command == "list":
        manager = ExportManager(args.project_root)
        chapters = manager.get_chapter_list()
        if chapters:
            print(f"可导出章节: {chapters}")
            print(f"共 {len(chapters)} 章")
        else:
            print("未找到章节文件")
        return

    if args.command == "export":
        manager = ExportManager(args.project_root)
        chapters = manager.parse_chapter_range(args.range)

        if not chapters:
            print("没有可导出的章节")
            return

        # 默认输出到导出目录，文件名取自 state.json 的 title
        if args.output:
            output_path = args.output
        else:
            # 从 state.json 读取 title
            title = "novel"
            state_path = Path(args.project_root) / ".webnovel" / "state.json"
            if state_path.exists():
                try:
                    import json
                    with open(state_path, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    title = state.get("project", {}).get("title", "novel")
                except Exception:
                    pass
            output_path = str(manager.output_dir / f"{title}.{args.format}")

        if args.format == "txt":
            manager.export_to_txt(chapters, output_path)
        elif args.format == "markdown":
            manager.export_to_markdown(chapters, output_path)
        elif args.format == "epub":
            # 解析封面尺寸
            cover_size = (1200, 1600)
            if args.cover_size:
                try:
                    w, h = args.cover_size.lower().split("x")
                    cover_size = (int(w), int(h))
                except ValueError:
                    print(f"[WARN] 无效的封面尺寸格式: {args.cover_size}，使用默认值 1200x1600")

            manager.export_to_epub(
                chapters,
                output_path,
                author=args.author,
                cover_path=args.cover,
                style_path=args.style,
                cover_size=cover_size,
            )


def cmd_list(args):
    pass


def cmd_export(args):
    pass


if __name__ == "__main__":
    main()
