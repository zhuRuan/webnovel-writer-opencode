# .opencode/scripts/publisher/adapters/fanqie.py
"""番茄小说平台适配器。"""
from __future__ import annotations

from publisher.base import BasePlatform, BookMeta, Chapter, UploadResult


class FanqieAdapter(BasePlatform):
    name = "fanqie"
    display_name = "番茄小说"
    login_url = "https://fanqienovel.com/main/writer/login?enter_from=author_zone"

    async def setup_auth(self, page) -> bool:
        await page.goto(self.login_url, wait_until="networkidle")
        try:
            await page.wait_for_url(
                "**/fanqienovel.com/writer/**",
                timeout=180_000,
            )
            return True
        except Exception:
            return False

    async def list_books(self, page) -> list[dict]:
        await page.goto(
            "https://fanqienovel.com/writer/book/list", wait_until="networkidle"
        )
        await page.wait_for_timeout(2000)
        books = await page.evaluate("""() => {
            const rows = document.querySelectorAll('.book-item, [class*="book"]');
            return Array.from(rows).map(row => {
                const titleEl = row.querySelector('.title, [class*="title"], h3, a');
                return {
                    title: titleEl?.textContent?.trim() || '',
                    url: titleEl?.href || '',
                };
            });
        }""")
        return books

    async def create_book(self, page, meta: BookMeta) -> str:
        await page.goto(
            "https://fanqienovel.com/writer/book/create", wait_until="networkidle"
        )
        await page.fill(
            'input[name="title"], input[placeholder*="书名"]', meta.title
        )
        await page.click(f"text={meta.genre}")
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

    async def upload_chapter(
        self, page, book_id: str, chapter: Chapter
    ) -> UploadResult:
        try:
            return await self._upload_via_api(page, book_id, chapter)
        except Exception:
            return await self._upload_via_browser(page, book_id, chapter)

    async def _upload_via_api(
        self, page, book_id: str, chapter: Chapter
    ) -> UploadResult:
        api_result = await page.evaluate(
            """async ([bookId, title, content]) => {
            try {
                const resp = await fetch('/api/writer/chapter/create', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        bookId: bookId,
                        title: title,
                        content: content,
                        status: 'draft'
                    })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    return {success: true, data: data};
                }
                return {success: false};
            } catch(e) {
                return {success: false, error: e.message};
            }
        }""",
            [book_id, chapter.title, chapter.content],
        )

        if api_result.get("success"):
            return UploadResult(
                success=True, chapter_index=chapter.index, message="API 直传"
            )
        raise RuntimeError(api_result.get("error", "API 返回失败"))

    async def _upload_via_browser(
        self, page, book_id: str, chapter: Chapter
    ) -> UploadResult:
        await page.goto(
            f"https://fanqienovel.com/writer/book/{book_id}/chapter/create",
            wait_until="networkidle",
        )

        await page.fill(
            'input[name="title"], [placeholder*="章节标题"]', chapter.title
        )

        content_editor = page.locator(
            'textarea[name="content"], [class*="editor"], .content-area'
        )
        await content_editor.click()
        await content_editor.fill(chapter.content)

        await page.wait_for_timeout(1000)
        await page.click(
            'button:has-text("保存草稿"), button:has-text("发布")'
        )
        await page.wait_for_timeout(2000)

        return UploadResult(
            success=True, chapter_index=chapter.index, message="浏览器模拟上传"
        )
