"""
Dashboard 启动脚本

用法：
    python -m dashboard.server --project-root /path/to/novel-project
    python -m dashboard.server                   # 自动检测项目根目录
"""

import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def _resolve_project_root(cli_root: str | None) -> Path:
    """按优先级解析 PROJECT_ROOT：CLI > 环境变量 > .opencode 指针 > CWD。"""
    if cli_root:
        return Path(cli_root).resolve()

    env = os.environ.get("WEBNOVEL_PROJECT_ROOT")
    if env:
        return Path(env).resolve()

    # 尝试从 .opencode 指针读取
    cwd = Path.cwd()
    pointer = cwd / ".opencode" / ".webnovel-current-project"
    if pointer.is_file():
        target = pointer.read_text(encoding="utf-8").strip()
        if target:
            p = Path(target)
            if p.is_dir() and (p / ".webnovel" / "state.json").is_file():
                return p.resolve()

    # 最终兜底：当前目录
    if (cwd / ".webnovel" / "state.json").is_file():
        return cwd.resolve()

    print("ERROR: 无法定位 PROJECT_ROOT（需要包含 .webnovel/state.json 的目录）", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Webnovel Dashboard Server")
    parser.add_argument("--project-root", type=str, default=None, help="小说项目根目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--rebuild", action="store_true", help="强制重建前端")
    args = parser.parse_args()

    project_root = _resolve_project_root(args.project_root)
    print(f"项目路径: {project_root}")

    # 检查并自动构建前端
    frontend_dir = Path(__file__).parent / "frontend"
    dist_dir = frontend_dir / "dist"
    index_html = dist_dir / "index.html"

    if not index_html.exists() or args.rebuild:
        print("前端未构建，正在构建...")
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        try:
            subprocess.run([npm, "install"], cwd=frontend_dir, check=True, capture_output=True)
            subprocess.run([npm, "run", "build"], cwd=frontend_dir, check=True, capture_output=True)
            print("前端构建完成")
        except subprocess.CalledProcessError as e:
            print(f"前端构建失败: {e}", file=sys.stderr)
            sys.exit(1)

    # 延迟导入，以便先处理路径
    import uvicorn
    from .app import create_app

    app = create_app(project_root)

    url = f"http://{args.host}:{args.port}"
    print(f"Dashboard 启动: {url}")
    print(f"API 文档: {url}/docs")

    if not args.no_browser:
        webbrowser.open(url)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
