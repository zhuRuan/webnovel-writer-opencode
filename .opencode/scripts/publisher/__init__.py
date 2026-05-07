# .opencode/scripts/publisher/__init__.py
"""小说自动发布 — CLI 入口。

用法:
  python publisher/__init__.py --project-root <path> setup-auth --platform fanqie
  python publisher/__init__.py --project-root <path> list-books --platform fanqie
  python publisher/__init__.py --project-root <path> create-book --platform fanqie
  python publisher/__init__.py --project-root <path> upload --platform fanqie --book-id <id>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# subprocess 运行时 scripts/ 不在 Python path 中，确保绝对导入可用
_scripts_root = Path(__file__).resolve().parent.parent
if str(_scripts_root) not in sys.path:
    sys.path.insert(0, str(_scripts_root))

from publisher.adapters.fanqie import FanqieAdapter

REGISTRY: dict[str, type] = {
    "fanqie": FanqieAdapter,
}


def _get_adapter(platform: str):
    cls = REGISTRY.get(platform)
    if cls is None:
        print(f"未知平台: {platform}。可用: {', '.join(REGISTRY)}")
        sys.exit(1)
    return cls()


async def _cmd_setup_auth(args: argparse.Namespace):
    from publisher.browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(headless=False, platform=args.platform)
    page = await browser.start()
    try:
        ok = await adapter.setup_auth(page)
        if ok:
            print(f"[OK] {adapter.display_name} 登录成功，认证状态已自动保存")
        else:
            print(f"[FAIL] {adapter.display_name} 登录超时")
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_list_books(args: argparse.Namespace):
    from publisher.browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        books = await adapter.list_books(page)
        if not books:
            print("未找到书籍")
        else:
            for i, book in enumerate(books, 1):
                bid = book.get("book_id", "") or book.get("id", "")
                name = book.get("book_name", book.get("title", "未知"))
                print(f"  {i}. {name}  (book_id: {bid})")
    finally:
        await browser.close()


async def _cmd_create_book(args: argparse.Namespace):
    from publisher.browser import Browser
    from publisher.base import BookMeta
    adapter = _get_adapter(args.platform)
    project_root = Path(args.project_root).expanduser().resolve()
    meta = _read_book_meta(project_root)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        book_id = await adapter.create_book(page, meta)
        if book_id:
            print(f"[OK] 书籍创建成功！book_id: {book_id}")
        else:
            print("[FAIL] 创建失败，请手动检查")
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_upload(args: argparse.Namespace):
    from publisher.browser import Browser
    from publisher.base import Chapter
    from publisher.config import PublishConfig, load_upload_log, save_upload_log
    from publisher.formatter import format_for_platform

    adapter = _get_adapter(args.platform)
    cfg = PublishConfig(mode=args.mode)
    uploaded = load_upload_log(args.platform, args.book_id)

    project_root = Path(args.project_root).expanduser().resolve()
    chapter_indices = _parse_range(args.range, project_root)
    to_upload = [i for i in chapter_indices if i not in uploaded]
    if not to_upload:
        print("所有章节已上传。")
        return

    print(
        f"待上传: {len(to_upload)} 章 "
        f"(共 {len(chapter_indices)} 章, {len(uploaded)} 章已传)"
    )

    browser = Browser(headless=cfg.headless, platform=args.platform)
    page = await browser.start()
    success_count = 0
    fail_count = 0

    try:
        for idx in to_upload:
            chapter_file = _find_chapter_file(project_root, idx)
            if not chapter_file:
                print(f"  [WARN] 第{idx}章文件未找到，跳过")
                fail_count += 1
                continue

            raw_md = chapter_file.read_text(encoding="utf-8")
            title = _extract_title(raw_md) or f"第{idx}章"
            content = format_for_platform(raw_md, args.platform)
            chapter = Chapter(index=idx, title=title, content=content)

            result = await adapter.upload_chapter(page, args.book_id,
                                                   chapter)
            if result.success:
                uploaded.add(idx)
                save_upload_log(args.platform, args.book_id, uploaded)
                success_count += 1
                print(f"  [OK] 第{idx}章 {result.message}")
            else:
                fail_count += 1
                print(f"  [FAIL] 第{idx}章 {result.message}")

            await asyncio.sleep(cfg.chapter_gap)
    finally:
        await browser.close()

    print(f"\n上传完成: 成功 {success_count}, 失败 {fail_count}")


def _read_book_meta(project_root: Path):
    from publisher.base import BookMeta
    import json
    state_file = project_root / ".webnovel" / "state.json"
    meta = BookMeta(title="", genre="", synopsis="", protagonist="")
    if state_file.is_file():
        s = json.loads(state_file.read_text(encoding="utf-8"))
        proj_info = s.get("project_info", {}) if isinstance(s, dict) else {}
        meta.title = proj_info.get("title", "") or project_root.name
        meta.genre = proj_info.get("genre", "")
        protag = s.get("protagonist_state", {}) if isinstance(s, dict) else {}
        meta.protagonist = protag.get("name", "") if isinstance(
            protag, dict) else ""
        meta.synopsis = proj_info.get("synopsis", "")
    return meta


def _parse_range(spec: str, project_root: Path) -> list[int]:
    import re
    if spec.lower() == "all":
        text_dir = project_root / "正文"
        if text_dir.is_dir():
            nums = []
            for f in sorted(text_dir.rglob("第*章*.md")):
                m = re.match(r"第(\d+)章", f.name)
                if m:
                    nums.append(int(m.group(1)))
            return nums
        return []

    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        else:
            result.add(int(part))
    return sorted(result)


def _extract_title(md: str) -> str:
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _find_chapter_file(project_root: Path, index: int) -> Path | None:
    import re
    text_dir = project_root / "正文"
    if not text_dir.is_dir():
        return None
    for f in text_dir.rglob("*.md"):
        m = re.match(rf"第{index:04d}章|第{index}章", f.name)
        if m:
            return f
    return None


def main():
    parser = argparse.ArgumentParser(description="小说自动发布")
    parser.add_argument("--project-root", type=Path, default=Path("."),
                        help="书项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup-auth", help="引导登录指定平台")
    p_setup.add_argument("--platform", required=True,
                         help="平台名称 (fanqie)")

    p_list = sub.add_parser("list-books", help="列出已有书单")
    p_list.add_argument("--platform", required=True, help="平台名称")

    p_create = sub.add_parser("create-book", help="创建新书")
    p_create.add_argument("--platform", required=True, help="平台名称")

    p_upload = sub.add_parser("upload", help="上传章节")
    p_upload.add_argument("--platform", required=True, help="平台名称")
    p_upload.add_argument("--book-id", required=True, help="书籍 ID")
    p_upload.add_argument("--range", default="all", help="章节范围")
    p_upload.add_argument("--mode", default="draft",
                          help="发布模式 (draft|publish)")

    args = parser.parse_args()

    cmd_map = {
        "setup-auth": _cmd_setup_auth,
        "list-books": _cmd_list_books,
        "create-book": _cmd_create_book,
        "upload": _cmd_upload,
    }
    handler = cmd_map.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
