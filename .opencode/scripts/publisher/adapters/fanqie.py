# .opencode/scripts/publisher/adapters/fanqie.py
"""番茄小说平台适配器。

番茄没有公开的 Writer API，所有操作（登录、创建书、上传章节）均通过
浏览器自动化完成。CSS 选择器和页面 URL 需在能访问番茄后台时实地验证。
"""
from __future__ import annotations

from publisher.base import BasePlatform, BookMeta, Chapter, UploadResult


class FanqieAdapter(BasePlatform):
    name = "fanqie"
    display_name = "番茄小说"
    login_url = "https://fanqienovel.com/main/writer/login?enter_from=author_zone"

    # ── 认证 ─────────────────────────────────────────────

    async def setup_auth(self, page) -> bool:
        """打开登录页，等待用户扫码。超时 3 分钟。"""
        await page.goto(self.login_url, wait_until="networkidle")
        try:
            await page.wait_for_url(
                "**/fanqienovel.com/writer/**",
                timeout=180_000,
            )
            return True
        except Exception:
            return False

    # ── 书单 ─────────────────────────────────────────────

    async def list_books(self, page) -> list[dict]:
        """打开作家后台书单页，抓取已有书籍列表。"""
        await page.goto(
            "https://fanqienovel.com/writer/book/list",
            wait_until="networkidle",
        )
        await page.wait_for_timeout(2000)
        books = await page.evaluate("""() => {
            const rows = document.querySelectorAll(
                '.book-item, [class*="book"], tr[class*="row"]'
            );
            return Array.from(rows).map(row => {
                const titleEl = row.querySelector(
                    '.title, [class*="title"], h3, a'
                );
                return {
                    title: titleEl?.textContent?.trim() || '',
                    url: titleEl?.href || '',
                };
            });
        }""")
        return books

    # ── 创建书籍 ─────────────────────────────────────────

    async def create_book(self, page, meta: BookMeta) -> str:
        """创建新书并返回 book_id。"""
        await page.goto(
            "https://fanqienovel.com/writer/book/create",
            wait_until="networkidle",
        )
        await page.fill(
            'input[name="title"], input[placeholder*="书名"]', meta.title
        )
        # 题材选择
        try:
            await page.click(f"text={meta.genre}")
        except Exception:
            pass
        await page.fill(
            'textarea[name="synopsis"], textarea[placeholder*="简介"]',
            meta.synopsis,
        )
        await page.click(
            'button:has-text("创建"), button:has-text("提交")'
        )
        await page.wait_for_timeout(3000)

        import re
        m = re.search(r"book/(\d+)", page.url)
        return m.group(1) if m else ""

    # ── 上传章节 ─────────────────────────────────────────

    async def upload_chapter(
        self, page, book_id: str, chapter: Chapter
    ) -> UploadResult:
        """浏览器模拟上传单章。"""
        await page.goto(
            f"https://fanqienovel.com/writer/book/{book_id}/chapter/create",
            wait_until="networkidle",
        )

        # 填写标题
        await page.fill(
            'input[name="title"], [placeholder*="章节标题"]',
            chapter.title,
        )

        # 填写正文
        content_editor = page.locator(
            'textarea[name="content"], [class*="editor"], .content-area, '
            '[contenteditable="true"]'
        )
        await content_editor.click()
        await content_editor.fill(chapter.content)

        await page.wait_for_timeout(1000)

        # 提交（先找"保存草稿"，再找"发布"）
        try:
            await page.click(
                'button:has-text("保存草稿")'
            )
        except Exception:
            await page.click(
                'button:has-text("发布"), button[type="submit"]'
            )

        await page.wait_for_timeout(2000)

        return UploadResult(
            success=True,
            chapter_index=chapter.index,
            message="浏览器模拟上传",
        )
