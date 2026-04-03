"""
Plugin Bridge — Dashboard 与 PluginManager 之间的桥接层。

Dashboard 是只读的 FastAPI 服务，不直接依赖 data_modules 模块。
此模块负责：
- 动态导入 PluginManager
- 提供面向 Dashboard API 的纯函数接口（无全局状态）
- 处理安装/卸载/启用/禁用/配置等操作
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# 确保 data_modules 的依赖可被导入（必须在模块顶层执行）
_opencode_root = Path(__file__).resolve().parent.parent  # .opencode 目录
_scripts_root = str(_opencode_root / "scripts")
_data_modules_root = str(_opencode_root / "scripts" / "data_modules")
for p in [_scripts_root, _data_modules_root]:
    if p not in sys.path:
        sys.path.insert(0, p)


def _get_plugin_manager(project_root: Path):
    """动态导入 PluginManager 并返回实例。"""
    from plugin_manager import PluginManager
    return PluginManager(project_root)


def list_plugins(project_root: Path) -> List[Dict]:
    """列出所有已安装插件（含启用状态）。"""
    pm = _get_plugin_manager(project_root)
    return pm.list_plugins()


def get_market_index(project_root: Path, force: bool = False) -> List[Dict]:
    """获取市场插件列表。"""
    pm = _get_plugin_manager(project_root)
    index = pm._get_market_index(force=force)
    return index.get("plugins", []) if index else []


def install_plugin(project_root: Path, source: str) -> str:
    """安装插件（支持市场名称、Git URL 或本地路径）。

    返回安装后的真实插件 ID。
    """
    pm = _get_plugin_manager(project_root)

    if source.startswith(("http", "git@")):
        pm._install_from_git(source)
    elif Path(source).exists():
        pm._install_from_local(Path(source))
    else:
        pm.install_from_market(source)

    # 从新安装的插件中读取真实 ID
    for item in pm.plugins_dir.iterdir():
        if item.is_dir() and (item / "manifest.json").exists():
            manifest = pm.load_manifest(item.name)
            if manifest:
                return manifest.get("id", item.name)

    return source


def uninstall_plugin(project_root: Path, plugin_id: str):
    """卸载插件（从内存卸载并删除目录）。"""
    pm = _get_plugin_manager(project_root)
    pm.uninstall_plugin(plugin_id)


def set_plugin_enabled(project_root: Path, plugin_id: str, enabled: bool):
    """启用/禁用插件。"""
    pm = _get_plugin_manager(project_root)
    pm.set_plugin_enabled(plugin_id, enabled)


def get_plugin_config(project_root: Path, plugin_id: str) -> Dict:
    """获取插件配置（config.json）。"""
    pm = _get_plugin_manager(project_root)
    for item in pm.plugins_dir.iterdir():
        if item.is_dir():
            m = pm.load_manifest(item.name)
            if m and m.get("id") == plugin_id:
                config_path = item / "config.json"
                if config_path.exists():
                    return json.loads(config_path.read_text(encoding="utf-8"))
                return {}
    raise ValueError(f"插件 {plugin_id} 未找到")


def save_plugin_config(project_root: Path, plugin_id: str, config: Dict):
    """保存插件配置（config.json）。"""
    pm = _get_plugin_manager(project_root)
    for item in pm.plugins_dir.iterdir():
        if item.is_dir():
            m = pm.load_manifest(item.name)
            if m and m.get("id") == plugin_id:
                config_path = item / "config.json"
                config_path.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                return
    raise ValueError(f"插件 {plugin_id} 未找到")
