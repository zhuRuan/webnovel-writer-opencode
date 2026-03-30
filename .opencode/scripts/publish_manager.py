#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说发布器 CLI 入口

用法:
    python publish_manager.py setup-browser
    python publish_manager.py list-books --project-root <path>
    python publish_manager.py create-book --title "xxx" --genre "玄幻" --synopsis "..."
    python publish_manager.py upload --book-id xxx --range 1-10 --mode draft --project-root <path>
    python publish_manager.py upload-all --book-id xxx --mode draft --project-root <path>
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from publisher import (
    BrowserManager,
    FanqieClient,
    PublisherError,
    check_auth_state,
    ensure_logged_in,
    get_default_auth_state_path,
    get_default_user_data_dir,
)

from logger import get_logger, setup_logging


class PublisherManager:
    """番茄小说发布管理器"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root
        self.auth_state_path = get_default_auth_state_path()
        self.user_data_dir = get_default_user_data_dir()
        self._browser_mgr: Optional[BrowserManager] = None
        self._client: Optional[FanqieClient] = None

    async def _ensure_client(self) -> FanqieClient:
        """确保客户端已初始化"""
        if self._client is None:
            if self._browser_mgr is None:
                self._browser_mgr = BrowserManager(self.user_data_dir)
                await self._browser_mgr.launch(
                    headless=False,
                    storage_state=str(self.auth_state_path) if check_auth_state(self.auth_state_path) else None,
                )
                if not await ensure_logged_in(self._browser_mgr.page, self.auth_state_path):
                    raise PublisherError("登录失败")
            self._client = FanqieClient(self._browser_mgr.page)
        return self._client

    async def close(self) -> None:
        """关闭浏览器"""
        if self._browser_mgr:
            await self._browser_mgr.close()
            self._browser_mgr = None
            self._client = None

    async def list_books(self) -> List[Dict[str, Any]]:
        """获取书单"""
        client = await self._ensure_client()
        books = await client.get_book_list()
        return books

    async def create_book(
        self,
        title: str,
        genre: str,
        synopsis: str,
        protagonist1: str = "",
        protagonist2: str = "",
    ) -> str:
        """创建新书"""
        client = await self._ensure_client()
        book_id = await client.create_book(
            title=title,
            genre=genre,
            synopsis=synopsis,
            protagonist_name_1=protagonist1,
            protagonist_name_2=protagonist2,
        )
        return book_id

    def load_chapters(self, range_spec: str) -> List[Dict[str, Any]]:
        """从项目加载章节

        Args:
            range_spec: 章节范围，如 "1-10" 或 "1,3,5" 或 "all"

        Returns:
            章节列表，每项包含 chapter_number, title, content
        """
        if not self.project_root:
            raise PublisherError("未指定项目根目录")

        chapters_dir = self.project_root / "正文"
        if not chapters_dir.is_dir():
            raise PublisherError(f"正文目录不存在: {chapters_dir}")

        # 递归搜索所有 .md 和 .txt 文件
        chapter_files = sorted(chapters_dir.rglob("*.md")) + sorted(chapters_dir.rglob("*.txt"))
        if not chapter_files:
            raise PublisherError(f"未找到章节文件: {chapters_dir}")

        def extract_chapter_num(path: Path) -> int:
            name = path.stem
            nums = "".join(c for c in name if c.isdigit())
            return int(nums) if nums else 0

        chapter_files.sort(key=extract_chapter_num)

        if range_spec.lower() == "all":
            selected = chapter_files
        elif "-" in range_spec:
            start, end = range_spec.split("-")
            start_num, end_num = int(start), int(end)
            selected = [f for f in chapter_files if start_num <= extract_chapter_num(f) <= end_num]
        elif "," in range_spec:
            nums = [int(n) for n in range_spec.split(",")]
            selected = [f for f in chapter_files if extract_chapter_num(f) in nums]
        else:
            num = int(range_spec)
            selected = [f for f in chapter_files if extract_chapter_num(f) == num]

        chapters: List[Dict[str, Any]] = []
        for path in selected:
            content = path.read_text(encoding="utf-8")
            content = self._clean_chapter_content(content)
            title = self._extract_chapter_title(path)
            chapter_num = extract_chapter_num(path)
            chapters.append({
                "chapter_number": chapter_num,
                "title": title,
                "content": content,
            })

        return chapters

    def _extract_chapter_title(self, path: Path) -> str:
        """从文件名提取章节标题

        "第0044章-遗迹深处" → "遗迹深处"
        "第0001章-地摊买书" → "地摊买书"
        """
        stem = path.stem
        if "-" in stem:
            parts = stem.split("-", 1)
            if len(parts) > 1:
                return parts[1].strip()
        return stem

    def _clean_chapter_content(self, content: str) -> str:
        """清理章节内容"""
        lines = content.splitlines()
        cleaned_lines: List[str] = []
        in_frontmatter = False

        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    async def upload_chapters(
        self,
        book_id: str,
        range_spec: str,
        publish_mode: str = "draft",
    ) -> List[Dict[str, Any]]:
        """上传章节"""
        chapters = self.load_chapters(range_spec)
        if not chapters:
            raise PublisherError("没有可上传的章节")

        client = await self._ensure_client()
        results = await client.publish_chapters(
            book_id=book_id,
            chapters=chapters,
            publish_mode=publish_mode,
        )
        return results


async def cmd_setup_browser() -> int:
    """首次配置：启动浏览器让用户登录"""
    print("=" * 60)
    print("  番茄小说发布器 - 首次配置")
    print("=" * 60)
    print()

    auth_state_path = get_default_auth_state_path()
    user_data_dir = get_default_user_data_dir()

    print(f"登录状态保存路径: {auth_state_path}")
    print(f"浏览器用户数据目录: {user_data_dir}")
    print()

    browser_mgr = BrowserManager(user_data_dir)
    try:
        await browser_mgr.launch(headless=False)
        success = await ensure_logged_in(browser_mgr.page, auth_state_path)
        if success:
            print()
            print("=" * 60)
            print("  配置完成！登录状态已保存。")
            print("=" * 60)
            return 0
        else:
            print()
            print("登录超时，请重试。")
            return 1
    except Exception as e:
        logger.exception("配置失败: %s", e)
        print(f"错误: {e}")
        return 1
    finally:
        await browser_mgr.close()


async def cmd_list_books(project_root: Optional[Path]) -> int:
    """列出已创建的书单"""
    manager = PublisherManager(project_root)
    try:
        books = await manager.list_books()
        if not books:
            print("未找到已创建的书籍。请先在番茄作家后台创建书籍。")
            return 0

        print(f"\n找到 {len(books)} 本书:\n")
        for i, book in enumerate(books, 1):
            print(f"{i}. {book.get('book_name', '未命名')}")
            print(f"   ID: {book.get('book_id', 'N/A')}")
            print(f"   状态: {book.get('status', 'N/A')}")
            print()
        return 0
    except Exception as e:
        logger.exception("获取书单失败: %s", e)
        print(f"错误: {e}")
        return 1
    finally:
        await manager.close()


async def cmd_create_book(
    project_root: Optional[Path],
    title: str,
    genre: str,
    synopsis: str,
    protagonist1: str,
    protagonist2: str,
) -> int:
    """创建新书"""
    manager = PublisherManager(project_root)
    try:
        print(f"正在创建书籍: {title}")
        book_id = await manager.create_book(title, genre, synopsis, protagonist1, protagonist2)
        print(f"\n书籍创建成功！")
        print(f"书籍 ID: {book_id}")
        print(f"\n请记下此 ID，后续上传章节时需要使用。")
        return 0
    except Exception as e:
        logger.exception("创建书籍失败: %s", e)
        print(f"错误: {e}")
        return 1
    finally:
        await manager.close()


def _cleanup_txt_files(project_root: Path, range_spec: str) -> int:
    """清理上传后残留的 .txt 文件（仅删除有对应 .md 的 .txt）"""
    chapters_dir = project_root / "正文"
    if not chapters_dir.is_dir():
        return 0

    txt_files = list(chapters_dir.glob("*.txt"))
    if not txt_files:
        return 0

    def extract_chapter_num(path: Path) -> int:
        nums = "".join(c for c in path.stem if c.isdigit())
        return int(nums) if nums else 0

    if range_spec.lower() == "all":
        selected = txt_files
    elif "-" in range_spec:
        start, end = range_spec.split("-")
        selected = [f for f in txt_files if int(start) <= extract_chapter_num(f) <= int(end)]
    elif "," in range_spec:
        nums = [int(n) for n in range_spec.split(",")]
        selected = [f for f in txt_files if extract_chapter_num(f) in nums]
    else:
        selected = [f for f in txt_files if extract_chapter_num(f) == int(range_spec)]

    cleaned = 0
    for txt_path in selected:
        md_path = txt_path.with_suffix(".md")
        if md_path.exists():
            deleted = True
        else:
            # 检查第1卷目录（章节可能在正文/或正文/第1卷/）
            md_in_subdir = (project_root / "正文" / "第1卷" / txt_path.name).with_suffix(".md")
            if md_in_subdir.exists():
                md_path = md_in_subdir
                deleted = True
            else:
                deleted = False
        if deleted:
            try:
                txt_path.unlink()
                cleaned += 1
            except OSError:
                pass
    return cleaned


async def cmd_upload(
    project_root: Optional[Path],
    book_id: str,
    range_spec: str,
    publish_mode: str,
) -> int:
    """上传章节"""
    manager = PublisherManager(project_root)
    try:
        print(f"正在加载章节: {range_spec}")
        results = await manager.upload_chapters(book_id, range_spec, publish_mode)

        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count

        print(f"\n上传完成: 成功 {success_count}, 失败 {fail_count}\n")
        for r in results:
            status = "OK" if r.get("success") else "FAIL"
            print(f"  [{status}] {r.get('message', '')}")

        if success_count > 0 and project_root:
            cleaned = _cleanup_txt_files(project_root, range_spec)
            if cleaned:
                print(f"\n已清理 {cleaned} 个临时 .txt 文件")

        return 0 if fail_count == 0 else 1
    except Exception as e:
        logger.exception("上传章节失败: %s", e)
        print(f"错误: {e}")
        return 1
    finally:
        await manager.close()


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)

    parser = argparse.ArgumentParser(description="番茄小说发布器")
    parser.add_argument("--project-root", help="项目根目录")

    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup-browser", help="首次配置：登录番茄作家后台")
    p_setup.set_defaults(func=lambda _: cmd_setup_browser())

    p_list = sub.add_parser("list-books", help="列出已创建的书籍")
    p_list.set_defaults(func=lambda args: cmd_list_books(Path(args.project_root) if args.project_root else None))

    p_create = sub.add_parser("create-book", help="创建新书")
    p_create.add_argument("--title", required=True, help="小说标题")
    p_create.add_argument("--genre", required=True, help="题材（如玄幻、都市）")
    p_create.add_argument("--synopsis", required=True, help="小说简介（至少50字）")
    p_create.add_argument("--protagonist1", default="", help="主角1")
    p_create.add_argument("--protagonist2", default="", help="主角2")
    p_create.set_defaults(func=lambda args: cmd_create_book(
        Path(args.project_root) if args.project_root else None,
        args.title,
        args.genre,
        args.synopsis,
        args.protagonist1,
        args.protagonist2,
    ))

    p_upload = sub.add_parser("upload", help="上传章节")
    p_upload.add_argument("--book-id", required=True, help="番茄书籍 ID")
    p_upload.add_argument("--range", default="all", help="章节范围（如 1-10 或 1,3,5 或 all）")
    p_upload.add_argument("--mode", default="draft", choices=["draft", "publish"], help="发布模式")
    p_upload.set_defaults(func=lambda args: cmd_upload(
        Path(args.project_root) if args.project_root else None,
        args.book_id,
        args.range,
        args.mode,
    ))

    p_upload_all = sub.add_parser("upload-all", help="上传全部已审稿章节")
    p_upload_all.add_argument("--book-id", required=True, help="番茄书籍 ID")
    p_upload_all.add_argument("--mode", default="draft", choices=["draft", "publish"], help="发布模式")
    p_upload_all.set_defaults(func=lambda args: cmd_upload(
        Path(args.project_root) if args.project_root else None,
        args.book_id,
        "all",
        args.mode,
    ))

    args = parser.parse_args()

    import inspect
    coro = args.func(args)
    if asyncio.iscoroutine(coro):
        code = asyncio.run(coro)
        raise SystemExit(code)


if __name__ == "__main__":
    main()
