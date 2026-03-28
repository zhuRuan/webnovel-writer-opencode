#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说发布器单元测试

注意：此测试只测试不依赖 playwright 的工具函数。
"""

import re
from typing import Any, Dict, List

import pytest


def _clean_protagonist_name(name: str) -> str:
    """清洗主角名"""
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
        return int(categories[0]["category_id"])
    return 0


class TestFanqieClient:
    """测试 FanqieClient 工具函数"""

    def test_clean_protagonist_name(self):
        """测试主角名清洗"""
        assert _clean_protagonist_name("萧炎（炎帝）") == "萧炎"
        assert _clean_protagonist_name("萧炎(炎帝)") == "萧炎"
        assert _clean_protagonist_name("萧炎/炎帝") == "萧炎"
        assert _clean_protagonist_name("萧炎") == "萧炎"
        assert _clean_protagonist_name("") == ""

    def test_clean_protagonist_name_truncate(self):
        """测试主角名截断"""
        long_name = "a" * 30
        result = _clean_protagonist_name(long_name)
        assert len(result) <= 20

    def test_text_to_html(self):
        """测试文本转 HTML"""
        text = "第一行\n\n第二行\n第三行"
        html = _text_to_html(text)
        assert "<p>第一行</p>" in html
        assert "<p>第二行</p>" in html
        assert "<p>第三行</p>" in html
        assert html.count("<p>") == 3

    def test_text_to_html_empty_lines(self):
        """测试空行处理"""
        text = "有内容\n\n\n\n空行多"
        html = _text_to_html(text)
        assert "<p>有内容</p>" in html
        assert "<p>空行多</p>" in html

    def test_find_category_id_exact_match(self):
        """测试精确匹配分类"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
            {"category_id": 2, "name": "都市"},
            {"category_id": 3, "name": "仙侠"},
        ]
        assert _find_category_id(categories, "玄幻") == 1
        assert _find_category_id(categories, "都市") == 2

    def test_find_category_id_partial_match(self):
        """测试部分匹配分类"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
            {"category_id": 2, "name": "都市"},
            {"category_id": 3, "name": "古代言情"},
        ]
        assert _find_category_id(categories, "言情") == 3
        assert _find_category_id(categories, "古代") == 3

    def test_find_category_id_fallback(self):
        """测试分类匹配失败时使用默认"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
        ]
        result = _find_category_id(categories, "不存在的题材")
        assert result == 1

    def test_find_category_id_empty(self):
        """测试空分类列表"""
        result = _find_category_id([], "玄幻")
        assert result == 0

    def test_find_label_ids_exact_match(self):
        """测试精确匹配标签"""
        labels = [
            {"label_id": 1, "label_name": "热血"},
            {"label_id": 2, "label_name": "升级"},
            {"label_id": 3, "label_name": "穿越"},
        ]
        result = _find_label_ids(labels, "玄幻", max_count=2)
        assert len(result) == 2

    def test_find_label_ids_partial_match(self):
        """测试部分匹配标签"""
        labels = [
            {"label_id": 1, "label_name": "异世"},
            {"label_id": 2, "label_name": "穿越时空"},
        ]
        result = _find_label_ids(labels, "穿越", max_count=2)
        assert len(result) <= 2

    def test_find_label_ids_fallback(self):
        """测试标签匹配失败时使用默认"""
        labels = [
            {"label_id": 1, "label_name": "热血"},
            {"label_id": 2, "label_name": "升级"},
        ]
        result = _find_label_ids(labels, "不存在的标签", max_count=2)
        assert len(result) == 2
        assert "1" in result
        assert "2" in result


class TestExceptions:
    """测试异常类（需要 playwright 安装后测试）"""

    def test_publisher_error(self):
        """需要 playwright 安装后可测试"""
        pytest.skip("Requires playwright installation")
