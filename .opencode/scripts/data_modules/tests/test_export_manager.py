import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from export_manager import ExportManager


def test_parse_chapter_range(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章-起始.md").write_text("# 第1章", encoding="utf-8")
    (tmp_path / "正文" / "第0002章-发展.md").write_text("# 第2章", encoding="utf-8")
    (tmp_path / "正文" / "第0003章-高潮.md").write_text("# 第3章", encoding="utf-8")
    (tmp_path / "正文" / "第0005章-结局.md").write_text("# 第5章", encoding="utf-8")

    manager = ExportManager(str(tmp_path))
    assert manager.parse_chapter_range("1-3") == [1, 2, 3]
    assert manager.parse_chapter_range("1,3,5") == [1, 3, 5]
    assert manager.parse_chapter_range("1,3-5") == [1, 3, 4, 5]
    assert manager.parse_chapter_range("all") == [1, 2, 3, 5]


def test_get_chapter_list(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章.md").write_text("内容", encoding="utf-8")
    (tmp_path / "正文" / "第0003章.md").write_text("内容", encoding="utf-8")
    (tmp_path / "正文" / "notes.md").write_text("不是章节", encoding="utf-8")

    manager = ExportManager(str(tmp_path))
    assert manager.get_chapter_list() == [1, 3]


def test_get_chapter_content(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章-觉醒.md").write_text("正文内容", encoding="utf-8")

    manager = ExportManager(str(tmp_path))
    title, content = manager.get_chapter_content(1)
    assert "觉醒" in title or title == "第1章"
    assert "正文内容" in content

    title2, content2 = manager.get_chapter_content(99)
    assert content2 == ""


def test_export_to_txt(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章-起始.md").write_text("第一章内容", encoding="utf-8")
    (tmp_path / "正文" / "第0002章-发展.md").write_text("第二章内容", encoding="utf-8")

    manager = ExportManager(str(tmp_path))
    output = tmp_path / "output.txt"

    count = manager.export_to_txt([1, 2], str(output))
    assert count == 2
    assert output.exists()

    text = output.read_text(encoding="utf-8")
    assert "第一章内容" in text
    assert "第二章内容" in text


def test_export_to_markdown(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章-起始.md").write_text("第一章内容", encoding="utf-8")
    (tmp_path / "正文" / "第0002章-发展.md").write_text("第二章内容", encoding="utf-8")

    manager = ExportManager(str(tmp_path))
    output = tmp_path / "output.md"

    count = manager.export_to_markdown([1, 2], str(output))
    assert count == 2
    assert output.exists()

    md = output.read_text(encoding="utf-8")
    assert "第一章内容" in md
    assert "第二章内容" in md
    assert "## " in md


def test_empty_chapters(tmp_path):
    (tmp_path / "正文").mkdir()
    manager = ExportManager(str(tmp_path))
    assert manager.get_chapter_list() == []
    assert manager.parse_chapter_range("all") == []
