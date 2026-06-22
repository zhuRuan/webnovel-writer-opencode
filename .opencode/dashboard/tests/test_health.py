"""Dashboard 健康检查 —— 验证 app 工厂可以启动并响应基本请求。"""


def test_app_starts(test_app):
    """验证 test_app fixture 可启动，GET /api/project/info 返回 200。"""
    response = test_app.get("/api/project/info")
    assert response.status_code == 200
    data = response.json()
    assert "project_info" in data
    assert data["project_info"]["title"] == "test"
