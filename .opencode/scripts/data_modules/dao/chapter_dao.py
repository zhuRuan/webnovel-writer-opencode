from .base import BaseDAO


class ChapterDAO(BaseDAO):
    def search_chapters(self, query: str, exclude_chapter: int = 0, limit: int = 5) -> list[dict]:
        return self._fetch(
            """SELECT chapter, title, SUBSTR(content, 1, 500) as snippet
               FROM chapters
               WHERE content LIKE ? AND chapter < ?
               ORDER BY chapter DESC LIMIT ?""",
            (f'%{query}%', exclude_chapter, limit),
        )

    def get_chapter_content(self, chapter: int) -> str:
        rows = self._fetch("SELECT content FROM chapters WHERE chapter = ?", (chapter,))
        return rows[0]['content'] if rows else ''

    def upsert_chapter_content(self, chapter: int, title: str, content: str):
        word_count = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
        self._execute(
            """INSERT OR REPLACE INTO chapters (chapter, title, content, word_count)
               VALUES (?, ?, ?, ?)""",
            (chapter, title, content, word_count),
        )

    def batch_import_existing(self, project_root: str) -> dict:
        """导入已有章节文件到数据库"""
        from pathlib import Path
        import re

        text_dir = Path(project_root) / '正文'
        if not text_dir.exists():
            return {"imported": 0}

        imported = 0
        for f in sorted(text_dir.glob("第*章*.md")):
            m = re.match(r'第(\d+)章[_-](.+)\.md', f.name)
            if not m:
                continue
            chapter = int(m.group(1))
            title = m.group(2)
            content = f.read_text(encoding='utf-8')
            self.upsert_chapter_content(chapter, title, content)
            imported += 1

        return {"imported": imported}
