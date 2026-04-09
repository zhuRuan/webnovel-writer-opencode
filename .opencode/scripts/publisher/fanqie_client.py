#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说作家后台 HTTP API 客户端

通过浏览器 JavaScript 上下文执行 fetch 请求，
确保请求携带真实的 cookies 和反爬虫指纹。

Base URL: https://fanqienovel.com
Auth: Cookie-based (managed by Playwright persistent browser context)
Encoding: application/x-www-form-urlencoded;charset=UTF-8
Params: aid=2503&app_name=muye_novel
"""

import json
import re
from logging import getLogger
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from .exceptions import (
    BookCreationError,
    ChapterPublishError,
    NetworkError,
    PublisherError,
)

logger = getLogger(__name__)

BASE_URL = "https://fanqienovel.com"
_COMMON_PARAMS = "aid=2503&app_name=muye_novel"

_FEMALE_GENRES = {"言情", "女频", "现代言情", "古代言情", "仙侠言情", "豪门", "穿越", "宫斗"}


def _clean_protagonist_name(name: str) -> str:
    """清洗主角名：去除全角括号和别名

    番茄 API 可能拒绝全角括号和斜杠。
    """
    name = re.sub(r"（[^）]*）", "", name)
    name = re.sub(r"\([^)]*\)", "", name)
    name = name.split("/")[0].strip()
    return name[:20]


def _text_to_html(text: str) -> str:
    """将纯文本每行用 <p> 标签包裹"""
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def _find_label_ids(labels: List[Dict], genre: str, max_count: int = 4) -> List[str]:
    """从标签列表中匹配与题材相关的标签 ID"""
    def get_name(label: Dict) -> str:
        return label.get("label_name") or label.get("name", "")

    def get_id(label: Dict) -> str:
        val = label.get("label_id") or label.get("id") or label.get("category_id")
        return str(val) if val else ""

    selected: List[str] = []
    genre_tokens = set(genre.replace(" ", ""))

    for label in labels:
        name = get_name(label)
        lid = get_id(label)
        if not name or not lid:
            continue
        if any(ch in name for ch in genre_tokens) or name in genre:
            selected.append(lid)
        if len(selected) >= max_count:
            break

    if not selected and labels:
        selected = [get_id(l) for l in labels[:2] if get_id(l)]

    return selected


def _find_category_id(categories: List[Dict], genre: str) -> int:
    """根据题材匹配分类 ID"""
    def get_name(cat: Dict) -> str:
        return cat.get("name") or cat.get("category_name", "")

    for cat in categories:
        if get_name(cat) == genre:
            return int(cat["category_id"])

    for cat in categories:
        name = get_name(cat)
        if genre in name or name in genre:
            return int(cat["category_id"])

    if categories:
        logger.warning("未匹配到分类 '%s'，使用默认: %s", genre, categories[0])
        return int(categories[0]["category_id"])
    return 0


class FanqieClient:
    """番茄小说作家后台 API 客户端

    通过 page.evaluate(fetch) 在浏览器 JS 上下文执行请求，
    确保 cookies 和浏览器指纹与真实用户一致。
    """

    def __init__(self, page: Page):
        self.page = page

    async def _fetch(
        self,
        method: str,
        path: str,
        form: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """在浏览器页面上下文中执行 fetch 请求

        Returns:
            API 响应的 data 字段
        Raises:
            PublisherError: 请求或 API 错误时抛出
        """
        url = f"{BASE_URL}{path}?{_COMMON_PARAMS}"
        if params:
            url += "&" + "&".join(f"{k}={v}" for k, v in params.items())

        form_json = json.dumps(form, ensure_ascii=False) if form else ""

        result = await self.page.evaluate(
            """async ([url, method, formJson]) => {
                try {
                    const opts = { method, credentials: 'include' };
                    if (formJson) {
                        const obj = JSON.parse(formJson);
                        opts.body = new URLSearchParams(obj).toString();
                        opts.headers = {
                            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
                        };
                    }
                    const resp = await fetch(url, opts);
                    const text = await resp.text();
                    return { ok: true, status: resp.status, body: text };
                } catch (e) {
                    return { ok: false, error: String(e) };
                }
            }""",
            [url, method, form_json],
        )

        if not result.get("ok"):
            raise NetworkError(f"fetch 错误: {result.get('error')}", {"path": path, "url": url})

        raw = result.get("body", "")
        status = result.get("status", 0)

        if "/article/" in path or "/publish" in path or "book/create" in path:
            logger.info("%s %s → HTTP %d  body=%s", method, path, status, raw[:500])
        else:
            logger.debug("%s %s → HTTP %d  body=%r", method, path, status, raw[:200])

        if not raw:
            raise NetworkError(f"API {path} 返回空响应 (HTTP {status})", {"path": path, "url": url})

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NetworkError(
                f"API {path} 返回非 JSON (HTTP {status}): {raw[:300]}",
                {"path": path},
            ) from exc

        if body.get("code") != 0:
            raise PublisherError(
                f"API {path} 失败: {body.get('message', 'unknown error')}",
                {"path": path, "code": body.get("code"), "form": form},
            )

        data = body.get("data")
        return data if data is not None else {}

    async def _post(self, path: str, form: Dict[str, Any]) -> Any:
        """POST 请求"""
        return await self._fetch("POST", path, form=form)

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET 请求"""
        return await self._fetch("GET", path, params=params)

    async def get_category_list(self, gender: int = 1) -> List[Dict[str, Any]]:
        """获取书籍分类列表

        Args:
            gender: 0=女频, 1=男频
        """
        data = await self._get("/api/author/book/category_list/v0/", {"gender": str(gender)})
        if isinstance(data, list):
            return data
        return data.get("category_list", [])

    async def get_label_list(self, gender: int = 1) -> List[Dict[str, Any]]:
        """获取书籍标签列表"""
        data = await self._get(
            "/api/author/book/group_category_list/v0/", {"gender": str(gender)}
        )

        labels: List[Dict[str, Any]] = []
        if isinstance(data, list):
            labels = data
        elif isinstance(data, dict):
            for group in data.get("group_list", data.get("label_list", [])):
                if isinstance(group, dict):
                    labels.extend(group.get("label_list", group.get("labels", [])))
        return labels

    async def get_book_list(self) -> List[Dict[str, Any]]:
        """获取已创建的书单"""
        data = await self._get(
            "/api/author/homepage/book_list/v0/",
            {"page_count": "50", "page_index": "0"},
        )
        if isinstance(data, dict):
            books = data.get("book_list", [])
            if isinstance(books, list):
                return books
        if isinstance(data, list):
            return data
        return []

    async def create_book(
        self,
        title: str,
        genre: str,
        synopsis: str,
        protagonist_name_1: str = "",
        protagonist_name_2: str = "",
    ) -> str:
        """创建新书并返回 book_id

        Args:
            title: 小说标题
            genre: 题材（如"玄幻"、"都市"）
            synopsis: 简介
            protagonist_name_1: 主角1
            protagonist_name_2: 主角2

        Returns:
            书籍 ID 字符串
        """
        gender = 0 if any(g in genre for g in _FEMALE_GENRES) and not any(
            m in genre for m in ("仙侠", "玄幻", "武侠", "男频", "都市", "科幻")
        ) else 1

        categories = await self.get_category_list(gender)
        category_id = _find_category_id(categories, genre)

        labels = await self.get_label_list(gender)
        label_ids = _find_label_ids(labels, genre)

        logger.info("创建书籍: genre=%r gender=%d category_id=%d label_ids=%s", genre, gender, category_id, label_ids)

        abstract = " ".join(line.strip() for line in synopsis.splitlines() if line.strip())
        if len(abstract) < 50:
            abstract = abstract + "。" * (50 - len(abstract))

        p1 = _clean_protagonist_name(protagonist_name_1)[:5]
        p2 = _clean_protagonist_name(protagonist_name_2)[:5]

        try:
            data = await self._post("/api/author/book/create/v0/", {
                "aid": "2503",
                "app_name": "muye_novel",
                "book_name": title,
                "gender": str(gender),
                "abstract": abstract,
                "category_id": str(category_id),
                "original_type": "1",
                "label_id_list": ",".join(label_ids),
                "protagonist_name_1": p1,
                "protagonist_name_2": p2,
            })
        except PublisherError as e:
            raise BookCreationError(
                f"创建书籍失败（注意：番茄平台每天限创建1本新书）: {e}",
                {"original_error": str(e)},
            ) from e

        if isinstance(data, dict):
            book_id = str(data.get("book_id", ""))
        else:
            book_id = ""

        if not book_id:
            raise BookCreationError("创建书籍响应中无 book_id", {"data": data})

        logger.info("书籍创建成功: id=%s, title=%s", book_id, title)
        return book_id

    async def get_volume_list(self, book_id: str) -> List[Dict[str, Any]]:
        """获取卷列表"""
        data = await self._get("/api/author/volume/volume_list/v1/", {"book_id": book_id})
        if isinstance(data, list):
            return data
        return data.get("volume_list", [])

    async def _get_first_volume(self, book_id: str) -> tuple[str, str]:
        """获取第一卷的 volume_id 和 volume_name"""
        volumes = await self.get_volume_list(book_id)
        if not volumes:
            raise BookCreationError(f"书籍 {book_id} 没有卷", {})
        vol = volumes[0]
        return str(vol["volume_id"]), vol.get("volume_name", "第一卷：默认")

    async def get_draft_list(self, book_id: str) -> List[Dict[str, Any]]:
        """获取草稿章节列表"""
        data = await self._get("/api/author/chapter/draft_list/v1/", {
            "book_id": book_id,
            "page_index": "0",
            "page_count": "200",
        })
        if isinstance(data, list):
            return data
        return data.get("draft_list") or data.get("item_list", [])

    async def save_draft(
        self,
        book_id: str,
        volume_id: str,
        volume_name: str,
        title: str,
        content: str,
        item_id: str = "",
    ) -> str:
        """保存章节为草稿并返回 item_id

        Args:
            title: 章节标题，如"第 1 章 替嫁之局"（5-30字符）
        """
        html_content = _text_to_html(content)

        if not item_id:
            create_form = {
                "book_id": book_id,
                "title": title,
                "content": html_content,
                "volume_id": volume_id,
                "volume_name": volume_name,
            }
            data = await self._post("/api/author/article/new_article/v0/", create_form)
            if isinstance(data, dict):
                item_id = str(data.get("item_id", ""))
            if not item_id:
                logger.warning("new_article 未返回 item_id: '%s'", title)
                return ""
            logger.info("已创建草稿槽: item_id=%s", item_id)

        save_form = {
            "book_id": book_id,
            "item_id": item_id,
            "title": title,
            "content": html_content,
            "volume_id": volume_id,
            "volume_name": volume_name,
        }
        data = await self._post("/api/author/article/cover_article/v0/", save_form)
        returned_id = item_id
        if isinstance(data, dict) and data.get("item_id"):
            returned_id = str(data["item_id"])

        logger.info("草稿已保存: item_id=%s, title=%s", returned_id, title)
        return returned_id

    async def publish_article(
        self,
        book_id: str,
        volume_id: str,
        volume_name: str,
        title: str,
        content: str,
    ) -> str:
        """直接发布章节"""
        item_id = await self.save_draft(
            book_id=book_id,
            volume_id=volume_id,
            volume_name=volume_name,
            title=title,
            content=content,
        )

        form: Dict[str, Any] = {
            "book_id": book_id,
            "item_id": item_id,
            "title": title,
            "content": _text_to_html(content),
            "volume_id": volume_id,
            "volume_name": volume_name,
        }

        await self._post("/api/author/publish_article/v0/", form)

        logger.info("章节已发布: item_id=%s, title=%s", item_id, title)
        return item_id

    async def get_chapter_list(
        self,
        book_id: str,
        volume_id: str = "",
        page_index: int = 0,
        page_count: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取章节列表（已发布+草稿）"""
        params: Dict[str, Any] = {
            "book_id": book_id,
            "page_index": str(page_index),
            "page_count": str(page_count),
            "status": "0",
            "must_have_correction_feedback": "0",
            "need_correction_feedback_num": "1",
            "sort": "",
        }
        if volume_id:
            params["volume_id"] = volume_id

        data = await self._get("/api/author/chapter/chapter_list/v1", params)
        if isinstance(data, dict):
            return data.get("item_list") or data.get("chapter_list", [])
        if isinstance(data, list):
            return data
        return []

    async def get_chapter_content(self, book_id: str, item_id: str) -> Dict[str, Any]:
        """获取章节内容用于编辑"""
        data = await self._get("/api/author/edit_article/v0/", {
            "book_id": book_id,
            "item_id": item_id,
            "from_source": "0",
        })
        if isinstance(data, dict):
            return data
        return {}

    async def modify_chapter(
        self,
        book_id: str,
        item_id: str,
        content: str,
        title: str = "",
    ) -> bool:
        """修改已发布的章节"""
        html_content = _text_to_html(content)

        form: Dict[str, Any] = {
            "book_id": book_id,
            "item_id": item_id,
            "content": html_content,
        }
        if title:
            form["title"] = title

        await self._post("/api/author/publish_article/v0/", form)
        logger.info("章节已修改: item_id=%s, title=%s", item_id, title or "(不变)")
        return True

    async def publish_chapters(
        self,
        book_id: str,
        chapters: List[Dict[str, Any]],
        publish_mode: str = "draft",
    ) -> List[Dict[str, Any]]:
        """批量上传章节

        Args:
            book_id: 书籍 ID
            chapters: 章节列表，每项需包含 chapter_number, title, content
            publish_mode: "draft" 或 "publish"

        Returns:
            每章节的结果列表
        """
        volume_id, volume_name = await self._get_first_volume(book_id)
        logger.info("开始上传 %d 章到书籍 %s", len(chapters), book_id)

        results: List[Dict[str, Any]] = []
        for ch in chapters:
            ch_number = ch.get("chapter_number", 0)
            raw_title = ch["title"]
            full_title = f"第 {ch_number} 章 {raw_title}" if ch_number > 0 else raw_title
            if len(full_title) > 30:
                full_title = full_title[:30]

            ch_content = ch["content"]
            try:
                if publish_mode == "draft":
                    item_id = await self.save_draft(
                        book_id=book_id,
                        volume_id=volume_id,
                        volume_name=volume_name,
                        title=full_title,
                        content=ch_content,
                    )
                    results.append({
                        "success": True,
                        "message": f"草稿已保存：{full_title}",
                        "item_id": item_id,
                    })
                else:
                    item_id = await self.publish_article(
                        book_id=book_id,
                        volume_id=volume_id,
                        volume_name=volume_name,
                        title=full_title,
                        content=ch_content,
                    )
                    results.append({
                        "success": True,
                        "message": f"已发布：{full_title}",
                        "item_id": item_id,
                    })

            except Exception as e:
                logger.error("上传章节失败 '%s': %s", full_title, e)
                results.append({
                    "success": False,
                    "message": str(e),
                    "item_id": "",
                })

        return results
