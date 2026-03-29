#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说看板 - 本地服务器启动脚本
"""

import http.server
import socketserver
import webbrowser
import os
import sys
import subprocess
import json
import re

PORT = 8085

# 全局变量
PROJECT_ROOT = None
DASHBOARD_DIR = None


def scan_character_library(project_root):
    """扫描角色库目录，提取角色信息"""
    chars = []
    char_lib_path = os.path.join(project_root, '设定集', '角色库')
    
    if not os.path.exists(char_lib_path):
        return chars
    
    # 扫描所有子目录
    for category in ['主要角色', '次要角色', '反派角色']:
        category_path = os.path.join(char_lib_path, category)
        if not os.path.exists(category_path):
            continue
        
        for filename in os.listdir(category_path):
            if not filename.endswith('.md'):
                continue
            
            filepath = os.path.join(category_path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                char_info = {
                    'name': filename.replace('.md', ''),
                    'category': category,
                    'role': '',
                    'firstAppearance': '',
                    'realm': None
                }
                
                # 提取姓名
                name_match = re.search(r'#+\s*(?:姓名|名称)[：:]\s*(.+)', content)
                if name_match:
                    char_info['name'] = name_match.group(1).strip()
                
                # 提取身份
                role_match = re.search(r'身份[：:]\s*(.+)', content)
                if role_match:
                    char_info['role'] = role_match.group(1).strip()
                
                # 提取首次出场
                appear_match = re.search(r'首次出场[：:]\s*(.+)', content)
                if appear_match:
                    char_info['firstAppearance'] = appear_match.group(1).strip()
                
                # 提取境界（如果有）
                realm_match = re.search(r'境界[：:]\s*(.+)', content)
                if realm_match:
                    char_info['realm'] = realm_match.group(1).strip()
                
                chars.append(char_info)
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
    
    return chars


class DualHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.lstrip('/')
        
        # 优先从 dashboard 目录查找
        dashboard_path = os.path.join(DASHBOARD_DIR, path)
        if os.path.isfile(dashboard_path):
            return dashboard_path
        
        # 从项目根目录查找数据文件
        if path.startswith('.webnovel/') or path.startswith('大纲/') or path.startswith('正文/'):
            project_path = os.path.join(PROJECT_ROOT, path)
            if os.path.isfile(project_path):
                return project_path
        
        # 尝试向上查找项目根目录
        if '.webnovel/' in path or '大纲/' in path or '正文/' in path:
            for parent_dir in [DASHBOARD_DIR] + self._get_parent_dirs(DASHBOARD_DIR):
                potential_root = os.path.dirname(parent_dir)
                for _ in range(5):
                    if os.path.exists(os.path.join(potential_root, '.webnovel')):
                        project_path = os.path.join(potential_root, path)
                        if os.path.isfile(project_path):
                            return project_path
                    potential_root = os.path.dirname(potential_root)
        
        return os.path.join(DASHBOARD_DIR, path)
    
    def _get_parent_dirs(self, path):
        parents = []
        current = path
        for _ in range(10):
            parent = os.path.dirname(current)
            if parent == current:
                break
            parents.append(parent)
            current = parent
        return parents
    
    def log_message(self, format, *args):
        pass


def main():
    global PROJECT_ROOT, DASHBOARD_DIR
    
    # 处理命令行参数
    if "--detach" in sys.argv:
        # 后台启动自己
        script = os.path.abspath(__file__)
        args = [a for a in sys.argv[1:] if a != "--detach"]
        if sys.platform == "win32":
            subprocess.Popen(
                [sys.executable, script] + args,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True
            )
            print(f"Dashboard started in background. Open http://localhost:{PORT}")
        else:
            subprocess.Popen(
                [sys.executable, script] + args,
                start_new_session=True,
                close_fds=True
            )
            print(f"Dashboard started in background. Open http://localhost:{PORT}")
        return
    
    # dashboard 目录
    DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 项目根目录
    PROJECT_ROOT = os.path.dirname(DASHBOARD_DIR)
    
    # 查找实际项目根目录
    markers = ['.webnovel', 'novel.txt', '大纲', '正文']
    for m in markers:
        if os.path.exists(os.path.join(PROJECT_ROOT, m)):
            break
    else:
        # 向上查找
        current = PROJECT_ROOT
        while current:
            if any(os.path.exists(os.path.join(current, m)) for m in markers):
                PROJECT_ROOT = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    
    # state.json 相对路径
    state_rel_path = '.webnovel/state.json'
    
    print("=" * 50)
    print("  Novel Dashboard - Local Server")
    print("=" * 50)
    print()
    print(f"Project: {PROJECT_ROOT}")
    print(f"Dashboard: {DASHBOARD_DIR}")
    print(f"Data: {state_rel_path}")
    print()
    print(f"Server running at: http://localhost:{PORT}")
    print("Press Ctrl+C to stop server")
    print()
    
    # 写入配置文件
    config_path = os.path.join(DASHBOARD_DIR, 'config.js')
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(f"window.DASHBOARD_CONFIG = {{\n")
        f.write(f"    projectRoot: '{PROJECT_ROOT.replace(chr(92), '/')}',\n")
        f.write(f"    stateJsonPath: '{state_rel_path}'\n")
        f.write(f"}};\n")
    
    # 扫描角色库并生成 characters.json
    characters = scan_character_library(PROJECT_ROOT)
    chars_path = os.path.join(DASHBOARD_DIR, 'characters.json')
    with open(chars_path, 'w', encoding='utf-8') as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)
    print(f"Found {len(characters)} characters from library")
    
    # 切换到 dashboard 目录
    os.chdir(DASHBOARD_DIR)
    
    # 自动打开浏览器
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except:
        pass
    
    with socketserver.TCPServer(("", PORT), DualHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            if os.path.exists(config_path):
                os.remove(config_path)


if __name__ == "__main__":
    main()
