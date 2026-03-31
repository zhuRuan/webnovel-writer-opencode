#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件管理器

功能：
- 扫描并发现插件（discover_plugins）
- 加载插件及依赖（load_plugin, load_all_plugins）
- 注册插件提供的扩展点（Agent/Skill/Checker/Publisher）
- 版本兼容性检查
- 依赖拓扑排序
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from runtime_compat import normalize_windows_path

logger = logging.getLogger(__name__)

ALLOWED_PERMISSIONS: Set[str] = {
    "read:chapters",
    "write:chapters",
    "read:settings",
    "network:requests",
}


class PluginManager:
    """插件管理器核心类"""

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化插件管理器

        Args:
            project_root: 项目根目录，默认当前工作目录
        """
        if project_root is None:
            project_root = Path.cwd()
        self.project_root = normalize_windows_path(project_root)
        self.plugins_dir = self.project_root / ".opencode" / "plugins"
        self.loaded_plugins: Dict[str, Dict[str, Any]] = {}
        self.extensions: Dict[str, List[Dict[str, Any]]] = {
            "agents": [],
            "skills": [],
            "checkers": [],
            "publishers": [],
            "templates": [],
        }
        self._ensure_plugins_dir()
        self._loaded = False
        self._reloading = False

    def _ensure_plugins_dir(self) -> None:
        """确保插件目录存在"""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def discover_plugins(self) -> List[str]:
        """
        发现所有插件

        Returns:
            插件名称列表（目录名）
        """
        plugins = []
        if not self.plugins_dir.exists():
            return plugins

        for item in self.plugins_dir.iterdir():
            if item.is_dir() and (item / "manifest.json").exists():
                plugins.append(item.name)
        return plugins

    def load_manifest(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        加载插件 manifest.json

        Args:
            plugin_name: 插件目录名

        Returns:
            manifest 字典，失败返回 None
        """
        manifest_path = self.plugins_dir / plugin_name / "manifest.json"
        if not manifest_path.exists():
            logger.warning(f"插件 {plugin_name} 缺少 manifest.json")
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"插件 {plugin_name} manifest.json 格式错误: {e}")
            return None
        except Exception as e:
            logger.error(f"加载插件 {plugin_name} manifest 失败: {e}")
            return None

    def check_version_compatibility(self, version_spec: Optional[str]) -> bool:
        """
        检查核心版本兼容性

        Args:
            version_spec: 版本规范字符串（如 ">=2.0.0 <3.0.0"）

        Returns:
            是否兼容
        """
        if not version_spec:
            return True

        try:
            from packaging import version
            from packaging.specifiers import SpecifierSet

            core_version_str = "2.0.0"
            specifier = SpecifierSet(version_spec)
            return version.parse(core_version_str) in specifier
        except ImportError:
            logger.warning("packaging 库未安装，跳过版本检查")
            return True
        except Exception as e:
            logger.warning(f"版本检查失败: {e}，跳过")
            return True

    def check_permissions(self, manifest: Dict[str, Any]) -> bool:
        """
        校验权限声明

        Args:
            manifest: 插件 manifest

        Returns:
            权限是否合法
        """
        declared = set(manifest.get("permissions", []))
        return declared.issubset(ALLOWED_PERMISSIONS)

    def install_dependencies(self, plugin_name: str) -> bool:
        """
        安装插件 Python 依赖

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功
        """
        plugin_path = self.plugins_dir / plugin_name
        req_file = plugin_path / "requirements.txt"
        if not req_file.exists():
            return True

        try:
            import subprocess

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning(f"安装插件 {plugin_name} 依赖失败: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.warning(f"安装插件 {plugin_name} 依赖异常: {e}")
            return False

    def _get_class(self, module: Any, class_path: str):
        """
        根据点分路径获取类

        Args:
            module: 插件模块
            class_path: 类路径（如 "checkers.MyChecker"）

        Returns:
            类对象，失败返回 None
        """
        try:
            parts = class_path.split(".")
            class_name = parts[-1]
            module_path = ".".join(parts[:-1])

            if module_path:
                import sys
                plugin_path = str(self.plugins_dir / module.__name__.replace("_", "-"))
                if plugin_path not in sys.path:
                    sys.path.insert(0, plugin_path)
                try:
                    submodule = importlib.import_module(f"{module.__name__}.{module_path}")
                except ImportError:
                    submodule = importlib.import_module(module_path)
            else:
                submodule = module

            return getattr(submodule, class_name)
        except (ImportError, AttributeError) as e:
            logger.error(f"无法加载类 {class_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"加载类 {class_path} 异常: {e}")
            return None

    def _register_extensions(
        self, module: Any, manifest: Dict[str, Any], plugin_id: str
    ) -> None:
        """
        注册插件提供的扩展点

        Args:
            module: 插件模块
            manifest: 插件 manifest
            plugin_id: 插件 ID
        """
        entry_points = manifest.get("entry_points", {})

        for agent_def in entry_points.get("agents", []):
            agent_class = self._get_class(module, agent_def.get("class", ""))
            if agent_class:
                self.extensions["agents"].append(
                    {
                        "id": agent_def.get("id"),
                        "class": agent_class,
                        "description": agent_def.get("description", ""),
                        "plugin_id": plugin_id,
                    }
                )

        for skill_def in entry_points.get("skills", []):
            skill_class = self._get_class(module, skill_def.get("class", ""))
            if skill_class:
                self.extensions["skills"].append(
                    {
                        "command": skill_def.get("command"),
                        "class": skill_class,
                        "description": skill_def.get("description", ""),
                        "plugin_id": plugin_id,
                    }
                )

        for checker_def in entry_points.get("checkers", []):
            checker_class = self._get_class(module, checker_def.get("class", ""))
            if checker_class:
                self.extensions["checkers"].append(
                    {
                        "id": checker_def.get("id"),
                        "class": checker_class,
                        "category": checker_def.get("category", "custom"),
                        "description": checker_def.get("description", ""),
                        "plugin_id": plugin_id,
                    }
                )

        for pub_def in entry_points.get("publishers", []):
            pub_class = self._get_class(module, pub_def.get("class", ""))
            if pub_class:
                self.extensions["publishers"].append(
                    {
                        "id": pub_def.get("id"),
                        "name": pub_def.get("name"),
                        "class": pub_class,
                        "plugin_id": plugin_id,
                    }
                )

        for tmpl_def in entry_points.get("templates", []):
            self.extensions["templates"].append(
                {
                    "id": tmpl_def.get("id"),
                    "path": tmpl_def.get("path"),
                    "description": tmpl_def.get("description", ""),
                    "plugin_id": plugin_id,
                }
            )

    def load_plugin(self, plugin_name: str) -> bool:
        """
        加载单个插件

        Args:
            plugin_name: 插件目录名

        Returns:
            是否加载成功
        """
        manifest = self.load_manifest(plugin_name)
        if not manifest:
            return False

        plugin_id = manifest.get("id", plugin_name)

        if not self.check_version_compatibility(manifest.get("core_api_version")):
            logger.warning(f"插件 {plugin_id} 与核心版本不兼容，跳过")
            return False

        if not self.check_permissions(manifest):
            logger.warning(f"插件 {plugin_id} 权限声明不合法，跳过")
            return False

        self.install_dependencies(plugin_name)

        plugin_path = self.plugins_dir / plugin_name
        module_name = plugin_name.replace("-", "_")

        original_dir = plugin_path
        temp_link = self.plugins_dir / module_name

        try:
            if not temp_link.exists():
                import os

                try:
                    os.symlink(str(original_dir), str(temp_link))
                except OSError:
                    pass

            sys.path.insert(0, str(self.plugins_dir))
            plugin_module = importlib.import_module(module_name)
        except ImportError as e:
            logger.error(f"加载插件 {plugin_id} 模块失败: {e}")
            return False
        except Exception as e:
            logger.error(f"加载插件 {plugin_id} 异常: {e}")
            return False

        self._register_extensions(plugin_module, manifest, plugin_id)

        self.loaded_plugins[plugin_id] = {
            "manifest": manifest,
            "module": plugin_module,
            "path": plugin_path,
            "name": plugin_name,
        }

        logger.info(f"插件 {plugin_id} v{manifest.get('version')} 加载成功")
        return True

    def _resolve_deps(self, plugin_names: List[str]) -> List[str]:
        """
        解析插件依赖顺序（拓扑排序）

        Args:
            plugin_names: 插件名称列表

        Returns:
            排序后的插件名列表
        """
        plugins_data = []
        for name in plugin_names:
            manifest = self.load_manifest(name)
            if manifest:
                plugins_data.append(
                    {
                        "name": name,
                        "deps": manifest.get("dependencies", {})
                        .get("plugins", [])
                        .copy(),
                    }
                )

        resolved: List[str] = []
        seen: Set[str] = set()

        def visit(name: str, visiting: Set[str]) -> None:
            if name in seen:
                return
            if name in visiting:
                logger.warning(f"检测到循环依赖: {name}")
                return

            visiting.add(name)

            for p in plugins_data:
                if p["name"] == name:
                    for dep in p["deps"]:
                        dep_name = dep.split("@")[0].replace(".", "_")
                        if dep_name in plugin_names:
                            visit(dep_name, visiting)
                    break

            visiting.discard(name)
            seen.add(name)
            resolved.append(name)

        for p in plugins_data:
            visit(p["name"], set())

        return resolved

    def load_all_plugins(self) -> None:
        """
        加载所有插件
        """
        if self._loaded:
            return

        plugin_names = self.discover_plugins()
        sorted_names = self._resolve_deps(plugin_names)

        for name in sorted_names:
            self.load_plugin(name)

        self._loaded = True
        logger.info(f"已加载 {len(self.loaded_plugins)} 个插件")

    def reload_all(self) -> None:
        """
        重新加载所有插件
        """
        self._reloading = True
        try:
            plugin_ids = list(self.loaded_plugins.keys())
            for pid in plugin_ids:
                self.unload_plugin(pid)
            self._loaded = False
            self.load_all_plugins()
        finally:
            self._reloading = False

    def _check_reloading(self) -> None:
        """检查是否正在重载"""
        if self._reloading:
            raise RuntimeError("插件正在重载中，请稍后再试")

    def _remove_extensions(self, plugin_id: str) -> None:
        """
        从各扩展点列表中移除该插件注册的内容

        Args:
            plugin_id: 插件 ID
        """
        for ext_type in self.extensions:
            self.extensions[ext_type] = [
                ext for ext in self.extensions[ext_type]
                if ext.get("plugin_id") != plugin_id
            ]
        logger.info(f"已移除插件 {plugin_id} 注册的扩展点")

    def _clear_module_cache(self, plugin_name: str) -> None:
        """
        清除插件模块缓存

        Args:
            plugin_name: 插件目录名
        """
        prefix = plugin_name.replace("-", "_")
        to_remove = [m for m in sys.modules if m.startswith(prefix)]
        for name in to_remove:
            del sys.modules[name]
        if to_remove:
            logger.info(f"已清除 {len(to_remove)} 个模块缓存: {to_remove}")

    def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载指定插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        if plugin_id not in self.loaded_plugins:
            logger.warning(f"插件 {plugin_id} 未加载")
            return False

        plugin = self.loaded_plugins[plugin_id]
        plugin_name = plugin.get("name", plugin_id)

        self._remove_extensions(plugin_id)

        self._clear_module_cache(plugin_name)

        del self.loaded_plugins[plugin_id]
        logger.info(f"插件 {plugin_id} 已卸载")
        return True

    def reload_plugin(self, plugin_id: str) -> bool:
        """
        重载指定插件

        Args:
            plugin_id: 插件 ID 或名称

        Returns:
            是否成功
        """
        self._reloading = True
        try:
            was_loaded = plugin_id in self.loaded_plugins
            if was_loaded:
                plugin_name = self.loaded_plugins[plugin_id].get("name", plugin_id)
                self.unload_plugin(plugin_id)
            else:
                plugin_name = None
                for name, data in self.loaded_plugins.items():
                    if data["manifest"].get("name") == plugin_id:
                        plugin_name = data.get("name", plugin_id)
                        break
                if not plugin_name:
                    for item in self.plugins_dir.iterdir():
                        if item.is_dir():
                            manifest = self.load_manifest(item.name)
                            if manifest and (
                                manifest.get("id") == plugin_id
                                or manifest.get("name") == plugin_id
                            ):
                                plugin_name = item.name
                                break

            if not plugin_name:
                return False

            return self.load_plugin(plugin_name)
        finally:
            self._reloading = False

    def get_agent(self, agent_id: str):
        """
        获取指定 Agent 类

        Args:
            agent_id: Agent ID

        Returns:
            Agent 类，未找到返回 None
        """
        self._check_reloading()
        for agent in self.extensions["agents"]:
            if agent["id"] == agent_id:
                return agent["class"]
        return None

    def get_skill(self, command: str):
        """
        获取指定 Skill 类

        Args:
            command: 命令名称（如 /my-skill）

        Returns:
            Skill 类，未找到返回 None
        """
        self._check_reloading()
        for skill in self.extensions["skills"]:
            if skill["command"] == command:
                return skill["class"]
        return None

    def get_checker(self, checker_id: str):
        """
        获取指定 Checker 类

        Args:
            checker_id: Checker ID

        Returns:
            Checker 类，未找到返回 None
        """
        self._check_reloading()
        for checker in self.extensions["checkers"]:
            if checker["id"] == checker_id:
                return checker["class"]
        return None

    def get_publisher(self, publisher_id: str):
        """
        获取指定 Publisher 类

        Args:
            publisher_id: Publisher ID

        Returns:
            Publisher 类，未找到返回 None
        """
        self._check_reloading()
        for publisher in self.extensions["publishers"]:
            if publisher["id"] == publisher_id:
                return publisher["class"]
        return None

    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出已加载插件信息

        Returns:
            插件信息列表
        """
        result = []
        for plugin_id, data in self.loaded_plugins.items():
            manifest = data["manifest"]
            result.append(
                {
                    "id": plugin_id,
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "author": manifest.get("author"),
                    "description": manifest.get("description"),
                }
            )
        return result

    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取插件详情

        Args:
            plugin_id: 插件 ID

        Returns:
            插件信息，未找到返回 None
        """
        for name, data in self.loaded_plugins.items():
            if name == plugin_id or data["name"] == plugin_id:
                return data["manifest"]
        return None

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件（删除目录）

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        target = None
        for name, data in self.loaded_plugins.items():
            if name == plugin_id or data["name"] == plugin_id:
                target = data["path"]
                break

        if not target:
            for item in self.plugins_dir.iterdir():
                if item.is_dir():
                    manifest = self.load_manifest(item.name)
                    if manifest and (
                        manifest.get("id") == plugin_id
                        or manifest.get("name") == plugin_id
                    ):
                        target = item
                        break

        if not target or not target.exists():
            logger.warning(f"插件 {plugin_id} 未找到")
            return False

        try:
            import shutil

            shutil.rmtree(target)
            if plugin_id in self.loaded_plugins:
                del self.loaded_plugins[plugin_id]
            logger.info(f"插件 {plugin_id} 已卸载")
            return True
        except Exception as e:
            logger.error(f"卸载插件 {plugin_id} 失败: {e}")
            return False


def get_plugin_manager(project_root: Optional[Path] = None) -> PluginManager:
    """
    获取全局 PluginManager 实例

    Args:
        project_root: 项目根目录

    Returns:
        PluginManager 实例
    """
    global _plugin_manager

    if _plugin_manager is None:
        _plugin_manager = PluginManager(project_root)
        _plugin_manager.load_all_plugins()

    return _plugin_manager


_plugin_manager: Optional[PluginManager] = None


def main() -> None:
    """CLI 入口"""
    import argparse
    import shutil

    parser = argparse.ArgumentParser(description="插件管理工具")
    parser.add_argument("--project-root", help="项目根目录")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出已安装插件")
    p_list.set_defaults(func=cmd_list)

    p_info = sub.add_parser("info", help="查看插件详情")
    p_info.add_argument("plugin_id", help="插件 ID 或名称")
    p_info.set_defaults(func=cmd_info)

    p_install = sub.add_parser("install", help="安装插件（Git URL 或本地路径）")
    p_install.add_argument("source", help="Git URL 或本地路径")
    p_install.set_defaults(func=cmd_install)

    p_remove = sub.add_parser("remove", help="卸载插件")
    p_remove.add_argument("plugin_id", help="插件 ID 或名称")
    p_remove.set_defaults(func=cmd_remove)

    p_reload = sub.add_parser("reload", help="重新加载插件")
    p_reload.add_argument("plugin_id", nargs="?", help="插件 ID（可选，不指定则重载所有）")
    p_reload.set_defaults(func=cmd_reload)

    args = parser.parse_args()

    project_root = args.project_root
    if project_root:
        project_root = normalize_windows_path(project_root)
    else:
        project_root = Path.cwd()

    pm = PluginManager(project_root)
    pm.load_all_plugins()

    args.func(pm, args)


def cmd_list(pm: PluginManager, args: argparse.Namespace) -> None:
    """list 命令"""
    plugins = pm.list_plugins()
    if not plugins:
        print("没有安装任何插件")
        return

    print("已安装的插件:")
    print()
    for p in plugins:
        print(f"📦 {p['name']} (v{p['version']})")
        print(f"   ID: {p['id']}")
        print(f"   作者: {p['author']}")
        print(f"   描述: {p['description']}")
        print()


def cmd_info(pm: PluginManager, args: argparse.Namespace) -> None:
    """info 命令"""
    info = pm.get_plugin_info(args.plugin_id)
    if not info:
        print(f"插件 {args.plugin_id} 未找到")
        raise SystemExit(1)

    print(f"""
📦 插件信息

名称: {info.get('name', 'N/A')}
ID: {info.get('id', 'N/A')}
版本: {info.get('version', 'N/A')}
作者: {info.get('author', 'N/A')}
许可证: {info.get('license', 'N/A')}
描述: {info.get('description', '无')}
核心版本: {info.get('core_api_version', 'N/A')}

扩展点:
""")

    for ext_type in ["agents", "skills", "checkers", "publishers", "templates"]:
        entry_points = info.get("entry_points", {}).get(ext_type, [])
        if entry_points:
            print(f"  {ext_type}:")
            for ext in entry_points:
                ext_id = ext.get("id") or ext.get("command") or ext.get("name")
                print(f"    - {ext_id}: {ext.get('description', '无描述')}")
            print()


def cmd_install(pm: PluginManager, args: argparse.Namespace) -> None:
    """install 命令"""
    source = args.source
    plugins_dir = pm.plugins_dir

    if source.startswith("http") or source.startswith("git@"):
        try:
            import tempfile
            import git

            temp_dir = tempfile.mkdtemp()
            repo = git.Repo.clone_from(source, temp_dir)

            manifest_path = Path(temp_dir) / "manifest.json"
            if not manifest_path.exists():
                shutil.rmtree(temp_dir)
                print("错误: 无效的插件，缺少 manifest.json")
                raise SystemExit(1)

            with open(manifest_path) as f:
                manifest = json.load(f)

            plugin_id = manifest.get("id", "")
            plugin_name = plugin_id.replace(".", "_") if plugin_id else source.split("/")[-1].replace(".git", "")
            target_dir = plugins_dir / plugin_name

            if target_dir.exists():
                backup_dir = plugins_dir / f"{plugin_name}.backup"
                shutil.move(str(target_dir), str(backup_dir))

            shutil.move(temp_dir, str(target_dir))
            print(f"插件 {plugin_id or plugin_name} 安装成功！请重启 OpenCode 或重新加载插件。")

        except ImportError:
            print("错误: 需要 GitPython 才能从 Git 安装插件")
            print("请运行: pip install GitPython")
            raise SystemExit(1)
        except Exception as e:
            print(f"安装失败: {e}")
            raise SystemExit(1)

    else:
        source_path = normalize_windows_path(source)
        if not source_path.exists():
            print(f"错误: 路径不存在: {source}")
            raise SystemExit(1)

        manifest_path = source_path / "manifest.json"
        if not manifest_path.exists():
            print("错误: 无效的插件，缺少 manifest.json")
            raise SystemExit(1)

        with open(manifest_path) as f:
            manifest = json.load(f)

        plugin_id = manifest.get("id", source_path.name)
        plugin_name = plugin_id.replace(".", "_")
        target_dir = plugins_dir / plugin_name

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_path, target_dir)

        pm.install_dependencies(plugin_name)
        print(f"插件 {plugin_name} 安装成功！请重启 OpenCode 或重新加载插件。")


def cmd_remove(pm: PluginManager, args: argparse.Namespace) -> None:
    """remove 命令"""
    if pm.uninstall_plugin(args.plugin_id):
        print(f"插件 {args.plugin_id} 已卸载，请重启 OpenCode 生效。")
    else:
        print(f"插件 {args.plugin_id} 未找到")
        raise SystemExit(1)


def cmd_reload(pm: PluginManager, args: argparse.Namespace) -> None:
    """reload 命令"""
    if args.plugin_id:
        if pm.reload_plugin(args.plugin_id):
            print(f"插件 {args.plugin_id} 已重新加载")
        else:
            print(f"插件 {args.plugin_id} 未找到或加载失败")
            raise SystemExit(1)
    else:
        pm.reload_all()
        print(f"已重新加载 {len(pm.loaded_plugins)} 个插件")
