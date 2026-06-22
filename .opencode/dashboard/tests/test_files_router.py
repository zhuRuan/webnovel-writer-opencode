"""routers/files.py 端点测试 —— 包含路径穿越防护验证。"""

from pathlib import Path


class TestFileTree:
    """GET /api/files/tree —— 目录树。"""

    def test_empty_dirs_returns_empty(self, test_app) -> None:
        response = test_app.get("/api/files/tree")
        assert response.status_code == 200
        data = response.json()
        assert data == {"正文": [], "大纲": [], "设定集": []}

    def test_with_files(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("# 第一章", encoding="utf-8")
        (project_root / "大纲").mkdir(exist_ok=True)
        (project_root / "大纲" / "outline.md").write_text("# 大纲", encoding="utf-8")

        response = test_app.get("/api/files/tree")
        assert response.status_code == 200
        data = response.json()
        assert len(data["正文"]) == 1
        assert data["正文"][0]["name"] == "ch01.md"
        assert data["正文"][0]["type"] == "file"
        assert len(data["大纲"]) == 1
        assert len(data["设定集"]) == 0

    def test_bak_files_excluded(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("hello", encoding="utf-8")
        (project_root / "正文" / "ch01.md.bak").write_text("backup", encoding="utf-8")

        response = test_app.get("/api/files/tree")
        assert response.status_code == 200
        data = response.json()
        assert len(data["正文"]) == 1
        assert data["正文"][0]["name"] == "ch01.md"

    def test_subdirs_nested(self, test_app, project_root: Path) -> None:
        (project_root / "设定集").mkdir(exist_ok=True)
        sub = project_root / "设定集" / "sub"
        sub.mkdir(exist_ok=True)
        (sub / "nested.md").write_text("deep", encoding="utf-8")

        response = test_app.get("/api/files/tree")
        assert response.status_code == 200
        data = response.json()
        children = data["设定集"][0]["children"]
        assert len(children) == 1
        assert children[0]["name"] == "nested.md"


class TestFileRead:
    """GET /api/files/read —— 文件读取与安全。"""

    def test_read_existing(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("# 第一章内容", encoding="utf-8")

        response = test_app.get("/api/files/read", params={"path": "正文/ch01.md"})
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "正文/ch01.md"
        assert data["content"] == "# 第一章内容"

    def test_path_traversal_dotdot_returns_403(self, test_app) -> None:
        response = test_app.get("/api/files/read", params={"path": "../../etc/passwd"})
        assert response.status_code == 403

    def test_path_traversal_absolute_returns_403(self, test_app) -> None:
        response = test_app.get("/api/files/read", params={"path": "/etc/passwd"})
        assert response.status_code == 403

    def test_outside_allowed_dirs_returns_403(self, test_app, project_root: Path) -> None:
        (project_root / ".webnovel" / "secret.txt").write_text("secret", encoding="utf-8")

        response = test_app.get("/api/files/read", params={"path": ".webnovel/secret.txt"})
        assert response.status_code == 403

    def test_missing_file_returns_404(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)

        response = test_app.get("/api/files/read", params={"path": "正文/nonexistent.md"})
        assert response.status_code == 404

    def test_binary_file_placeholder(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        response = test_app.get("/api/files/read", params={"path": "正文/image.png"})
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "[二进制文件，无法预览]"


class TestFileWrite:
    """PUT /api/files/write —— 写入与 SSE 推送。"""

    def test_write_existing(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("旧内容", encoding="utf-8")

        response = test_app.put("/api/files/write", json={
            "path": "正文/ch01.md",
            "content": "新内容",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["path"] == "正文/ch01.md"
        assert data["size"] == 3

        assert (project_root / "正文" / "ch01.md").read_text(encoding="utf-8") == "新内容"

    def test_write_path_traversal_returns_403(self, test_app) -> None:
        response = test_app.put("/api/files/write", json={
            "path": "../../etc/passwd",
            "content": "evil",
        })
        assert response.status_code == 403

    def test_write_missing_file_returns_404(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)

        response = test_app.put("/api/files/write", json={
            "path": "正文/nonexistent.md",
            "content": "内容",
        })
        assert response.status_code == 404


class TestFileNormalize:
    """POST /api/files/normalize —— 内容同步。"""

    def test_normalize_non_md_skipped(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "notes.txt").write_text("hello", encoding="utf-8")

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/notes.txt",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["warning"] == "非 Markdown 文件，跳过处理"

    def test_normalize_no_backup(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("# 新内容", encoding="utf-8")

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/ch01.md",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["warning"] == "no backup found"

    def test_normalize_unchanged(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        content = "# 相同内容\n一些文字。"
        (project_root / "正文" / "ch01.md").write_text(content, encoding="utf-8")
        (project_root / "正文" / "ch01.md.bak").write_text(content, encoding="utf-8")

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/ch01.md",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["warning"] == "文件内容未变化"

    def test_normalize_path_traversal_returns_403(self, test_app) -> None:
        response = test_app.post("/api/files/normalize", json={
            "path": "../../etc/passwd",
        })
        assert response.status_code == 403

    def test_normalize_missing_file_returns_404(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/nonexistent.md",
        })
        assert response.status_code == 404

    def test_normalize_binary_content(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "binary.md").write_bytes(b"\x80\x81\x82")
        (project_root / "正文" / "binary.md.bak").write_text("backup", encoding="utf-8")

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/binary.md",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["warning"] == "文件编码不是 UTF-8"

    def test_normalize_with_diff_no_entities(self, test_app, project_root: Path) -> None:
        (project_root / "正文").mkdir(exist_ok=True)
        (project_root / "正文" / "ch01.md").write_text("新内容不同", encoding="utf-8")
        (project_root / "正文" / "ch01.md.bak").write_text("旧内容", encoding="utf-8")

        response = test_app.post("/api/files/normalize", json={
            "path": "正文/ch01.md",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        backup = project_root / "正文" / "ch01.md.bak"
        assert not backup.exists()
