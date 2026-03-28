#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板 API 服务器 - 提供数据接口供前端调用
"""

import http.server
import socketserver
import json
import sqlite3
import urllib.parse
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORT = 8086
PROJECT_ROOT = None


@dataclass
class ProjectInfo:
    """项目基本信息"""
    title: str
    genre: str
    target_words: int
    target_chapters: int


@dataclass
class ProgressInfo:
    """进度信息"""
    current_chapter: int
    total_words: int
    avg_words_per_chapter: float
    percent: float


@dataclass
class HealthInfo:
    """健康度信息"""
    score: int
    issues: List[str]
    last_check: str


@dataclass
class ForeshadowingInfo:
    """伏笔统计"""
    total: int
    unresolved: int
    overdue: int
    recent: List[Dict[str, Any]]


@dataclass
class OverviewResponse:
    """概览响应"""
    project: ProjectInfo
    progress: ProgressInfo
    health: HealthInfo
    foreshadowing: ForeshadowingInfo
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": {
                "title": self.project.title,
                "genre": self.project.genre,
                "target_words": self.project.target_words,
                "target_chapters": self.project.target_chapters,
            },
            "progress": {
                "current_chapter": self.progress.current_chapter,
                "total_words": self.progress.total_words,
                "avg_words_per_chapter": self.progress.avg_words_per_chapter,
                "percent": self.progress.percent,
            },
            "health": {
                "score": self.health.score,
                "issues": self.health.issues,
                "last_check": self.health.last_check,
            },
            "foreshadowing": {
                "total": self.foreshadowing.total,
                "unresolved": self.foreshadowing.unresolved,
                "overdue": self.foreshadowing.overdue,
                "recent": self.foreshadowing.recent,
            },
            "updated_at": self.updated_at,
        }


class APIHandler(http.server.SimpleHTTPRequestHandler):
    """API 请求处理器"""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == '/api/files/tree':
                self.handle_file_tree()
            elif path == '/api/files/read':
                self.handle_file_read(params)
            elif path == '/api/entities':
                self.handle_entities(params)
            elif path == '/api/state-changes':
                self.handle_state_changes(params)
            elif path == '/api/reading-power':
                self.handle_reading_power(params)
            elif path == '/api/chapters':
                self.handle_chapters()
            elif path == '/api/scenes':
                self.handle_scenes(params)
            elif path == '/api/relationships':
                self.handle_relationships(params)
            elif path == '/api/review-metrics':
                self.handle_review_metrics(params)
            elif path == '/api/overview':
                self.handle_overview()
            else:
                self.send_error(404, 'Not Found')
        except Exception as e:
            logger.exception("API request failed: %s", e)
            self.send_json({'error': str(e)}, 500)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def handle_file_tree(self):
        result = {}
        for folder_name in ['正文', '大纲', '设定集']:
            folder = PROJECT_ROOT / folder_name
            if folder.is_dir():
                result[folder_name] = self._walk_tree(folder)
            else:
                result[folder_name] = []
        self.send_json(result)

    def _walk_tree(self, folder):
        items = []
        try:
            for child in sorted(folder.iterdir()):
                if child.name.startswith('.'):
                    continue
                if child.is_dir():
                    items.append({
                        'name': child.name,
                        'type': 'dir',
                        'path': str(child.relative_to(PROJECT_ROOT)).replace('\\', '/'),
                        'children': self._walk_tree(child)
                    })
                else:
                    items.append({
                        'name': child.name,
                        'type': 'file',
                        'path': str(child.relative_to(PROJECT_ROOT)).replace('\\', '/'),
                        'size': child.stat().st_size
                    })
        except Exception:
            pass
        return items

    def handle_file_read(self, params):
        path = params.get('path', [''])[0]
        if not path:
            self.send_json({'error': '缺少 path 参数'}, 400)
            return

        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            self.send_json({'error': '非法路径'}, 403)
            return

        allowed = ['正文', '大纲', '设定集']
        rel = full_path.relative_to(PROJECT_ROOT)
        if rel.parts[0] not in allowed:
            self.send_json({'error': '仅允许访问正文/大纲/设定集'}, 403)
            return

        if not full_path.is_file():
            self.send_json({'error': '文件不存在'}, 404)
            return

        try:
            content = full_path.read_text(encoding='utf-8')
            self.send_json({'path': path, 'content': content})
        except UnicodeDecodeError:
            self.send_json({'error': '二进制文件，无法预览'}, 400)

    def get_db(self):
        db_path = PROJECT_ROOT / '.webnovel' / 'index.db'
        if not db_path.is_file():
            return None
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def handle_entities(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        entity_type = params.get('type', [''])[0]
        try:
            if entity_type:
                rows = conn.execute(
                    'SELECT * FROM entities WHERE type = ? ORDER BY last_appearance DESC',
                    (entity_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM entities ORDER BY last_appearance DESC'
                ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_state_changes(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        entity = params.get('entity', [''])[0]
        limit = int(params.get('limit', ['100'])[0])
        try:
            if entity:
                rows = conn.execute(
                    'SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC LIMIT ?',
                    (entity, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?',
                    (limit,)
                ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_reading_power(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        limit = int(params.get('limit', ['50'])[0])
        try:
            rows = conn.execute(
                'SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?',
                (limit,)
            ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_chapters(self):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        try:
            rows = conn.execute(
                'SELECT * FROM chapters ORDER BY chapter ASC'
            ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_scenes(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        chapter = params.get('chapter', [''])[0]
        limit = int(params.get('limit', ['200'])[0])
        try:
            if chapter:
                rows = conn.execute(
                    'SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC',
                    (int(chapter),)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?',
                    (limit,)
                ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_relationships(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        limit = int(params.get('limit', ['300'])[0])
        try:
            rows = conn.execute(
                'SELECT * FROM relationships ORDER BY chapter DESC LIMIT ?',
                (limit,)
            ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_review_metrics(self, params):
        conn = self.get_db()
        if not conn:
            self.send_json([])
            return

        limit = int(params.get('limit', ['20'])[0])
        try:
            rows = conn.execute(
                'SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?',
                (limit,)
            ).fetchall()
            self.send_json([dict(r) for r in rows])
        except sqlite3.OperationalError:
            self.send_json([])
        finally:
            conn.close()

    def handle_overview(self) -> None:
        """
        处理 /api/overview 请求。

        返回项目概览数据，包含项目信息、进度、健康度和伏笔统计。
        """
        logger.info("Building overview for project: %s", PROJECT_ROOT)

        try:
            if not PROJECT_ROOT:
                logger.warning("Project root not configured")
                self.send_json({'error': '项目未初始化'}, 500)
                return

            state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
            if not state_file.exists():
                logger.warning("State file not found: %s", state_file)
                self.send_json({'error': '项目未初始化'}, 500)
                return

            state_data = json.loads(state_file.read_text(encoding='utf-8'))

            overview = self._build_overview(state_data)
            self.send_json(overview.to_dict())
            logger.info("Overview built successfully")

        except FileNotFoundError as e:
            logger.warning("Project file missing: %s", e)
            self.send_json({'error': '项目文件缺失'}, 500)
        except PermissionError as e:
            logger.error("Permission error: %s", e)
            self.send_json({'error': '权限不足'}, 403)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in state file: %s", e)
            self.send_json({'error': '项目配置文件格式错误'}, 500)
        except Exception as e:
            logger.exception("Overview API exception: %s", e)
            self.send_json({'error': '服务器错误'}, 500)

    def _build_overview(self, state_data: Dict[str, Any]) -> OverviewResponse:
        """构建概览响应数据"""
        progress = state_data.get("progress", {})
        project_info = state_data.get("project_info", {})

        current_chapter = progress.get("current_chapter", 0)
        total_words = progress.get("total_words", 0)
        target_words = project_info.get("target_words", 2000000)
        target_chapters = project_info.get("target_chapters", 1000)

        avg_words = total_words / current_chapter if current_chapter > 0 else 0
        percent = (total_words / target_words * 100) if target_words > 0 else 0

        project = ProjectInfo(
            title=project_info.get("title", "未命名项目"),
            genre=project_info.get("genre", "未知"),
            target_words=target_words,
            target_chapters=target_chapters,
        )

        progress_info = ProgressInfo(
            current_chapter=current_chapter,
            total_words=total_words,
            avg_words_per_chapter=round(avg_words, 1),
            percent=round(percent, 1),
        )

        health = self._calculate_health(state_data, current_chapter)

        foreshadowing = self._get_foreshadowing_info(state_data, current_chapter)

        return OverviewResponse(
            project=project,
            progress=progress_info,
            health=health,
            foreshadowing=foreshadowing,
            updated_at=datetime.now().isoformat(),
        )

    def _calculate_health(self, state_data: Dict[str, Any], current_chapter: int) -> HealthInfo:
        """计算健康度"""
        issues: List[str] = []

        plot_threads = state_data.get("plot_threads", {})
        if isinstance(plot_threads, dict):
            foreshadowing = plot_threads.get("foreshadowing", [])
            if isinstance(foreshadowing, list):
                unresolved = sum(
                    1 for f in foreshadowing
                    if not self._is_resolved(f.get("status"))
                )
                if unresolved > 5:
                    issues.append(f"存在 {unresolved} 条未回收伏笔")
                if unresolved > 10:
                    issues.append("伏笔过多，建议清理")

        character_issues = self._check_character_issues(state_data, current_chapter)
        issues.extend(character_issues)

        score = max(0, 100 - len(issues) * 10)

        return HealthInfo(
            score=score,
            issues=issues,
            last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _is_resolved(self, status: Optional[str]) -> bool:
        """判断伏笔是否已回收"""
        if not status:
            return False
        resolved_statuses = {"已回收", "已解决", "已完成", "resolved", "done"}
        return status in resolved_statuses

    def _check_character_issues(self, state_data: Dict[str, Any], current_chapter: int) -> List[str]:
        """检查角色问题"""
        issues: List[str] = []

        conn = self.get_db()
        if not conn:
            return issues

        try:
            rows = conn.execute(
                "SELECT id, canonical_name, last_appearance FROM entities WHERE type = '角色'"
            ).fetchall()

            for row in rows:
                last_app = row["last_appearance"] or 0
                absence = current_chapter - last_app
                if absence > 50:
                    issues.append(f"角色 {row['canonical_name']} 掉线 {absence} 章")

        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

        return issues

    def _get_foreshadowing_info(self, state_data: Dict[str, Any], current_chapter: int) -> ForeshadowingInfo:
        """获取伏笔统计信息"""
        plot_threads = state_data.get("plot_threads", {})
        foreshadowing_list: List[Dict[str, Any]] = []

        if isinstance(plot_threads, dict):
            foreshadowing_data = plot_threads.get("foreshadowing", [])
            if isinstance(foreshadowing_data, list):
                foreshadowing_list = foreshadowing_data

        total = len(foreshadowing_list)
        unresolved = sum(
            1 for f in foreshadowing_list
            if not self._is_resolved(f.get("status"))
        )

        overdue = 0
        recent: List[Dict[str, Any]] = []
        for f in foreshadowing_list:
            if not self._is_resolved(f.get("status")):
                planted = f.get("planted_chapter") or f.get("added_chapter") or 0
                elapsed = current_chapter - planted
                if elapsed > 20:
                    overdue += 1
                if len(recent) < 5:
                    recent.append({
                        "content": f.get("content", ""),
                        "planted_chapter": planted,
                        "status": f.get("status", "未回收"),
                    })

        return ForeshadowingInfo(
            total=total,
            unresolved=unresolved,
            overdue=overdue,
            recent=recent,
        )

    def log_message(self, format, *args):
        if '/api/' in str(args):
            print(f"[API] {args[0]}")


def main():
    global PROJECT_ROOT, PORT

    import sys
    args = sys.argv[1:]

    if '--help' in args or '-h' in args:
        print(f"用法: python {sys.argv[0]} [项目根目录] [--port PORT]")
        print(f"默认端口: {PORT}")
        return

    for i, arg in enumerate(args):
        if not arg.startswith('--') and arg != '--port':
            if i > 0 and args[i-1] == '--port':
                continue
            PROJECT_ROOT = Path(arg).resolve()
            break

    if not PROJECT_ROOT:
        PROJECT_ROOT = Path.cwd().resolve()

    if '--port' in args:
        idx = args.index('--port')
        if idx + 1 < len(args):
            PORT = int(args[idx + 1])

    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"API 服务器启动在: http://localhost:{PORT}")

    with socketserver.TCPServer(("", PORT), APIHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")


if __name__ == "__main__":
    main()
