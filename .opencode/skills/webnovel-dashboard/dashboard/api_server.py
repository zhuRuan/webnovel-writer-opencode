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
import re
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


def is_port_in_use(port: int) -> bool:
    """检查端口是否已被占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def get_port_process(pid: int) -> str:
    """获取占用端口的进程信息"""
    import psutil
    try:
        proc = psutil.Process(pid)
        return f"{proc.name()} (PID: {pid})"
    except:
        return f"PID: {pid}"


def kill_process_on_port(port: int) -> bool:
    """杀死占用指定端口的进程"""
    import psutil
    import signal
    
    for conn in psutil.net_connections():
        if conn.laddr.port == port and conn.status == 'LISTEN':
            try:
                proc = psutil.Process(conn.pid)
                print(f"正在终止占用端口 {port} 的进程: {proc.name()} (PID: {conn.pid})")
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=3)
                return True
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                print(f"无法终止进程: {e}")
                return False
    return False


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
            if path == '/api/files':
                self.handle_files_list(params)
            elif path == '/api/files/tree':
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
            elif path == '/api/characters':
                self.handle_characters()
            elif path == '/api/items':
                self.handle_items()
            elif path == '/api/checkers/config':
                self.handle_checker_config_get()
            elif path == '/api/foreshadowing/due':
                self.handle_foreshadowing_due()
            elif path == '/api/foreshadow':
                self.handle_foreshadow_get()
            else:
                self.send_error(404, 'Not Found')
        except Exception as e:
            logger.exception("API request failed: %s", e)
            self.send_json({'error': str(e)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            if path == '/api/checkers/config':
                self.handle_checker_config_post()
            elif path == '/api/files/write':
                self.handle_file_write()
            elif path == '/api/foreshadow':
                self.handle_foreshadow_post()
            else:
                self.send_error(404, 'Not Found')
        except Exception as e:
            logger.exception("API POST failed: %s", e)
            self.send_json({'error': str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def handle_files_list(self, params):
        path = params.get('path', [''])[0]
        if not path:
            self.send_json({'error': '缺少 path 参数'}, 400)
            return

        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            self.send_json({'error': '非法路径'}, 403)
            return

        if not full_path.is_dir():
            self.send_json({'error': '目录不存在'}, 404)
            return

        try:
            files = []
            for child in sorted(full_path.iterdir()):
                if child.is_file():
                    files.append({
                        'name': child.name,
                        'path': str(child.relative_to(PROJECT_ROOT)).replace('\\', '/'),
                        'size': child.stat().st_size
                    })
            self.send_json(files)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)

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

        allowed = ['正文', '大纲', '设定集', '审查报告']
        rel = full_path.relative_to(PROJECT_ROOT)
        if rel.parts[0] not in allowed:
            self.send_json({'error': '仅允许访问正文/大纲/设定集/审查报告'}, 403)
            return

        if not full_path.is_file():
            self.send_json({'error': '文件不存在'}, 404)
            return

        try:
            content = full_path.read_text(encoding='utf-8')
            self.send_json({'path': path, 'content': content})
        except UnicodeDecodeError:
            self.send_json({'error': '二进制文件，无法预览'}, 400)

    def handle_file_write(self):
        """处理文件写入请求"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_json({'error': '请求体为空'}, 400)
            return
            
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({'error': '无效的 JSON'}, 400)
            return
        
        path = data.get('path')
        content = data.get('content')
        
        if not path or content is None:
            self.send_json({'error': '缺少 path 或 content 参数'}, 400)
            return
        
        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            self.send_json({'error': '非法路径'}, 403)
            return
        
        allowed_dirs = ['正文', '大纲', '设定集', '审查报告']
        rel = full_path.relative_to(PROJECT_ROOT)
        if rel.parts[0] not in allowed_dirs:
            self.send_json({'error': f'仅允许写入 {"/".join(allowed_dirs)} 目录'}, 403)
            return
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            full_path.write_text(content, encoding='utf-8')
            self.send_json({'success': True, 'path': path})
        except Exception as e:
            logger.exception("Failed to write file")
            self.send_json({'error': str(e)}, 500)

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

    def handle_foreshadowing_due(self):
        """GET /api/foreshadowing/due - 返回到期和即将到期的伏笔"""
        try:
            state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
            if not state_file.exists():
                self.send_json({'error': '项目未初始化'}, 404)
                return

            data = json.loads(state_file.read_text(encoding='utf-8'))
            current_chapter = data.get('progress', {}).get('current_chapter', 0)
            foreshadowings = data.get('plot_threads', {}).get('foreshadowing', [])

            due = []          # 已过期
            upcoming = []     # 即将到期

            for f in foreshadowings:
                status = f.get('status', '')
                if status not in ['未回收', '']:
                    continue

                target = f.get('target_chapter')
                if target is None:
                    continue

                if current_chapter >= target:
                    due.append({
                        'content': f.get('content', ''),
                        'planted': f.get('planted_chapter', 0),
                        'target': target,
                        'overdue': current_chapter - target
                    })
                elif target - current_chapter <= 10:
                    upcoming.append({
                        'content': f.get('content', ''),
                        'planted': f.get('planted_chapter', 0),
                        'target': target,
                        'remaining': target - current_chapter
                    })

            self.send_json({
                'due': due,
                'upcoming': upcoming,
                'current_chapter': current_chapter
            })
        except Exception as e:
            logger.exception("Failed to get due foreshadowing")
            self.send_json({'error': str(e)}, 500)

    def handle_foreshadow_get(self):
        """GET /api/foreshadow - 获取所有伏笔列表"""
        try:
            state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
            if not state_file.exists():
                self.send_json([])
                return
            state = json.loads(state_file.read_text(encoding='utf-8'))
            foreshadowing = state.get('plot_threads', {}).get('foreshadowing', [])
            self.send_json(foreshadowing)
        except Exception as e:
            logger.exception("Failed to get foreshadowing")
            self.send_json({'error': str(e)}, 500)

    def handle_foreshadow_post(self):
        """POST /api/foreshadow - 处理伏笔的创建、更新、删除"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_json({'error': '请求体为空'}, 400)
            return
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({'error': '无效的 JSON'}, 400)
            return

        method = data.get('_method', 'POST').upper()
        
        state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
        if not state_file.exists():
            self.send_json({'error': '项目未初始化'}, 400)
            return
        
        try:
            state = json.loads(state_file.read_text(encoding='utf-8'))
            foreshadowing = state.setdefault('plot_threads', {}).setdefault('foreshadowing', [])
            
            if method == 'POST':
                new_foreshadow = {
                    'id': str(int(datetime.now().timestamp() * 1000)),
                    'content': data.get('content', ''),
                    'planted_chapter': data.get('planted_chapter', 0),
                    'target_chapter': data.get('target_chapter', 0),
                    'tier': data.get('tier', '支线'),
                    'status': data.get('status', '未回收'),
                    'added_at': datetime.now().strftime('%Y-%m-%d'),
                }
                foreshadowing.append(new_foreshadow)
                state['plot_threads']['foreshadowing'] = foreshadowing
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                self.send_json({'success': True, 'data': new_foreshadow})
                
            elif method == 'PUT':
                fid = data.get('id')
                if not fid:
                    self.send_json({'error': '缺少 id'}, 400)
                    return
                for i, f in enumerate(foreshadowing):
                    if f.get('id') == fid:
                        foreshadowing[i].update({
                            'content': data.get('content', f.get('content')),
                            'planted_chapter': data.get('planted_chapter', f.get('planted_chapter')),
                            'target_chapter': data.get('target_chapter', f.get('target_chapter')),
                            'tier': data.get('tier', f.get('tier')),
                            'status': data.get('status', f.get('status')),
                        })
                        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                        self.send_json({'success': True, 'data': foreshadowing[i]})
                        return
                self.send_json({'error': '伏笔不存在'}, 404)
                
            elif method == 'DELETE':
                fid = data.get('id')
                if not fid:
                    self.send_json({'error': '缺少 id'}, 400)
                    return
                original_len = len(foreshadowing)
                foreshadowing = [f for f in foreshadowing if f.get('id') != fid]
                if len(foreshadowing) == original_len:
                    self.send_json({'error': '伏笔不存在'}, 404)
                    return
                state['plot_threads']['foreshadowing'] = foreshadowing
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                self.send_json({'success': True})
            else:
                self.send_json({'error': '不支持的方法'}, 405)
                
        except Exception as e:
            logger.exception("Failed to handle foreshadow")
            self.send_json({'error': str(e)}, 500)

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

    def handle_characters(self):
        """处理角色库请求"""
        chars_dir = PROJECT_ROOT / '设定集' / '角色库'
        characters = []
        
        if chars_dir.is_dir():
            for category in ['主要角色', '次要角色', '反派角色']:
                cat_dir = chars_dir / category
                if cat_dir.is_dir():
                    for md_file in cat_dir.glob('*.md'):
                        try:
                            content = md_file.read_text(encoding='utf-8')
                            parsed = self._parse_character_file(content, category, md_file.stem)
                            if parsed:
                                characters.append(parsed)
                        except Exception as e:
                            logger.warning(f"Failed to parse character file {md_file}: {e}")
        
        self.send_json(characters)

    def _parse_character_file(self, content: str, category: str, filename: str) -> Dict[str, Any]:
        """解析角色卡文件"""
        result = {
            'name': filename,
            'category': category,
            'role': '',
            'age': '',
            'identity': '',
            'first_appearance': '',
            'keywords': '',
            'personality': '',
            'goal': '',
            'ability': '',
            'threat_level': ''
        }
        
        current_section = ''
        for line in content.split('\n'):
            line = line.strip()
            
            if line.startswith('## '):
                current_section = line[3:].strip()
                continue
            
            if line.startswith('- '):
                if '：' in line:
                    key, value = line[2:].split('：', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == '姓名':
                        result['name'] = value
                    elif key == '年龄':
                        result['age'] = value
                    elif key == '身份':
                        result['identity'] = value
                        result['role'] = value.split('→')[0].strip()
                    elif '首次出场' in key:
                        result['first_appearance'] = value
                    elif key == '觉醒等级' or key == '境界/等级':
                        result['ability'] = value
                    elif key == '当前威胁' or key == '威胁程度':
                        result['threat_level'] = value
                
                if current_section == '核心标签' and '关键词' in line:
                    result['keywords'] = line.split('：')[-1].strip()
                elif current_section == '性格与底色' and '核心性格' in line:
                    result['personality'] = line.split('：')[-1].strip()
                elif current_section == '动机与目标' and ('目标' in line or '渴望' in line):
                    result['goal'] = line.split('：')[-1].strip()
        
        return result

    def handle_items(self):
        """处理物品库请求"""
        items_dir = PROJECT_ROOT / '设定集' / '物品库'
        items = []
        
        if items_dir.is_dir():
            for md_file in items_dir.glob('**/*.md'):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    current_category = ''
                    current_item = None
                    
                    for line in content.split('\n'):
                        line = line.strip()
                        
                        if line.startswith('## '):
                            current_category = line[3:].strip()
                            continue
                        
                        if line.startswith('### '):
                            if current_item and current_item.get('name'):
                                items.append(current_item)
                            current_item = {
                                'name': line[4:].strip(),
                                'category': current_category,
                                'type': '',
                                'source': '',
                                'function': '',
                                'status': '',
                                'first_appearance': ''
                            }
                            continue
                        
                        if current_item and line.startswith('- ') and '：' in line:
                            key, value = line[2:].split('：', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            if key == '类型':
                                current_item['type'] = value
                            elif key == '来源':
                                current_item['source'] = value
                            elif key == '功能':
                                current_item['function'] = value
                            elif key == '状态':
                                current_item['status'] = value
                            elif '首次出场' in key:
                                current_item['first_appearance'] = value
                    
                    if current_item and current_item.get('name'):
                        items.append(current_item)
                        
                except Exception as e:
                    logger.warning(f"Failed to parse item file {md_file}: {e}")
        
        self.send_json(items)

    # ============================================================
    # 审查器配置 API
    # ============================================================

    # 参数校验规则
    CHECKER_PARAM_RULES = {
        'hook_config.strength_baseline': {'type': 'enum', 'values': ['strong', 'medium', 'weak']},
        'hook_config.transition_allowance': {'type': 'int', 'min': 1, 'max': 5},
        'coolpoint_config.density_per_chapter': {'type': 'enum', 'values': ['high', 'medium', 'low']},
        'coolpoint_config.combo_interval': {'type': 'int', 'min': 1, 'max': 20},
        'coolpoint_config.milestone_interval': {'type': 'int', 'min': 5, 'max': 30},
        'micropayoff_config.min_per_chapter': {'type': 'int', 'min': 0, 'max': 5},
        'micropayoff_config.transition_min': {'type': 'int', 'min': 0, 'max': 3},
        'pacing_config.stagnation_threshold': {'type': 'int', 'min': 1, 'max': 10},
        'pacing_config.strand_quest_max': {'type': 'int', 'min': 1, 'max': 20},
        'pacing_config.strand_fire_gap_max': {'type': 'int', 'min': 5, 'max': 30},
        'pacing_config.transition_max_consecutive': {'type': 'int', 'min': 1, 'max': 10},
        'override_config.debt_multiplier': {'type': 'float', 'min': 0.5, 'max': 2.0},
        'override_config.payback_window_default': {'type': 'int', 'min': 1, 'max': 20},
    }

    # shuangwen fallback 参数
    DEFAULT_PARAMS = {
        'hook_config': {
            'strength_baseline': 'medium',
            'transition_allowance': 2,
        },
        'coolpoint_config': {
            'density_per_chapter': 'high',
            'combo_interval': 5,
            'milestone_interval': 10,
        },
        'micropayoff_config': {
            'min_per_chapter': 2,
            'transition_min': 1,
        },
        'pacing_config': {
            'stagnation_threshold': 3,
            'strand_quest_max': 5,
            'strand_fire_gap_max': 15,
            'transition_max_consecutive': 2,
        },
        'override_config': {
            'debt_multiplier': 1.0,
            'payback_window_default': 3,
        },
    }

    def handle_checker_config_get(self):
        """GET /api/checkers/config - 返回当前生效的审查器参数"""
        # 读取 genre
        genre = '末世+异能'
        state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
                genre = state.get('project_info', {}).get('genre', genre)
            except Exception:
                pass

        # 尝试从 genre-profiles.md 解析对应 profile
        profile_source = 'shuangwen (默认)'
        profile_params = self._parse_genre_profile(genre)
        if profile_params:
            profile_source = genre
        else:
            profile_params = self.DEFAULT_PARAMS

        # 读取用户覆盖值
        overrides = {}
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
                overrides = state.get('genre_overrides', {})
            except Exception:
                pass

        # 合并：overrides 覆盖 profile
        merged_params = {}
        for section, defaults in profile_params.items():
            merged_params[section] = dict(defaults)
        for key, value in overrides.items():
            parts = key.split('.', 1)
            if len(parts) == 2:
                section, param = parts
                if section in merged_params:
                    merged_params[section][param] = value

        self.send_json({
            'genre': genre,
            'source': profile_source,
            'params': merged_params,
            'overrides': overrides,
        })

    def _parse_genre_profile(self, genre: str) -> Optional[Dict[str, Any]]:
        """从 genre-profiles.md 解析指定题材的参数配置"""
        profiles_file = PROJECT_ROOT / '.opencode' / 'references' / 'genre-profiles.md'
        if not profiles_file.exists():
            return None

        content = profiles_file.read_text(encoding='utf-8')

        # 映射中文题材名到 profile id
        genre_map = {
            '爽文': 'shuangwen', '系统流': 'shuangwen',
            '修仙': 'xianxia', '玄幻': 'xianxia',
            '都市': 'urban-power',
            '言情': 'romance',
            '悬疑': 'mystery',
            '历史': 'history-travel',
            '游戏': 'game-lit',
            '规则怪谈': 'rule-horror',
            '末世': 'post-apocalyptic',
        }

        profile_id = None
        for key, pid in genre_map.items():
            if key in genre:
                profile_id = pid
                break

        if not profile_id:
            return None

        # 查找 profile YAML block
        # 格式: ### 2.X 题材名 (profile_id)\n\n```yaml\n...\n```
        pattern = rf'id:\s*{re.escape(profile_id)}.*?```yaml\s*\n(.*?)```'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return None

        yaml_block = match.group(1)
        try:
            # 手动解析关键字段（避免依赖 yaml 库）
            params = dict(self.DEFAULT_PARAMS)
            current_section = None

            for line in yaml_block.split('\n'):
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('id:') or stripped.startswith('name:') or stripped.startswith('description:') or stripped.startswith('tags:'):
                    continue

                # 检测 section 头
                if stripped.endswith(':') and not stripped.startswith('-') and ':' not in stripped[1:-1]:
                    current_section = stripped[:-1].strip()
                    continue

                if current_section and ':' in stripped:
                    key, val = stripped.split(':', 1)
                    key = key.strip().lstrip('- ')
                    val = val.strip()

                    if current_section in params:
                        # 类型转换
                        if val in ('true', 'True'):
                            val = True
                        elif val in ('false', 'False'):
                            val = False
                        elif val.replace('.', '', 1).isdigit():
                            val = float(val) if '.' in val else int(val)
                        elif val in ('high', 'medium', 'low', 'strong', 'weak'):
                            pass  # 保持字符串
                        else:
                            continue  # 跳过非标量值

                        params[current_section][key] = val

            return params
        except Exception as e:
            logger.warning(f"Failed to parse genre profile for {genre}: {e}")
            return None

    def handle_checker_config_post(self):
        """POST /api/checkers/config - 保存用户调整的参数"""
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({'error': '无效的 JSON'}, 400)
            return

        overrides = data.get('overrides', {})
        if not isinstance(overrides, dict):
            self.send_json({'error': 'overrides 必须是对象'}, 400)
            return

        # 校验每个参数
        errors = []
        validated = {}
        for key, value in overrides.items():
            if key not in self.CHECKER_PARAM_RULES:
                errors.append(f'未知参数: {key}')
                continue

            rule = self.CHECKER_PARAM_RULES[key]
            if rule['type'] == 'enum':
                if value not in rule['values']:
                    errors.append(f'{key} 必须是 {rule["values"]} 之一，收到: {value}')
                    continue
            elif rule['type'] == 'int':
                if not isinstance(value, int):
                    errors.append(f'{key} 必须是整数')
                    continue
                if value < rule['min'] or value > rule['max']:
                    errors.append(f'{key} 范围: {rule["min"]}-{rule["max"]}，收到: {value}')
                    continue
            elif rule['type'] == 'float':
                if not isinstance(value, (int, float)):
                    errors.append(f'{key} 必须是数字')
                    continue
                if value < rule['min'] or value > rule['max']:
                    errors.append(f'{key} 范围: {rule["min"]}-{rule["max"]}，收到: {value}')
                    continue

            validated[key] = value

        if errors:
            self.send_json({'error': '; '.join(errors)}, 400)
            return

        # 写入 state.json
        state_file = PROJECT_ROOT / '.webnovel' / 'state.json'
        state = {}
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
            except Exception:
                pass

        state['genre_overrides'] = validated
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

        self.send_json({'success': True, 'overrides': validated})

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

    # 检查端口占用
    if is_port_in_use(PORT):
        print(f"[警告] 端口 {PORT} 已被占用!")
        print(f"尝试自动终止旧进程...")
        
        try:
            if kill_process_on_port(PORT):
                import time
                time.sleep(0.5)
                if is_port_in_use(PORT):
                    print(f"[错误] 无法释放端口 {PORT}，请手动关闭占用该端口的程序后重试")
                    return
                print(f"[成功] 端口 {PORT} 已释放")
            else:
                print(f"[错误] 无法自动释放端口 {PORT}")
                return
        except ImportError:
            print(f"[错误] 需要安装 psutil 库来自动管理进程: pip install psutil")
            print(f"[提示] 请手动关闭占用端口 {PORT} 的程序后重试")
            return

    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"API 服务器启动在: http://localhost:{PORT}")

    with socketserver.TCPServer(("", PORT), APIHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")


if __name__ == "__main__":
    main()
