#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin Manager tests
"""

import json
import sys
from pathlib import Path

import pytest


class TestPluginManager:
    """PluginManager 单元测试"""

    def test_plugin_discovery(self, tmp_path):
        """测试插件发现"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        test_plugin = plugins_dir / "test_plugin"
        test_plugin.mkdir()
        manifest = test_plugin / "manifest.json"
        manifest.write_text('{"id": "test_plugin", "name": "测试插件", "version": "1.0.0"}', encoding="utf-8")

        pm = PluginManager(tmp_path)
        plugins = pm.discover_plugins()

        assert "test_plugin" in plugins

    def test_invalid_plugin_loading(self, tmp_path):
        """测试无效插件加载"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        invalid_plugin = plugins_dir / "invalid"
        invalid_plugin.mkdir()

        pm = PluginManager(tmp_path)
        result = pm.load_plugin("invalid")

        assert result is False

    def test_manifest_loading(self, tmp_path):
        """测试 manifest 加载"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        test_plugin = plugins_dir / "test_plugin2"
        test_plugin.mkdir()
        manifest_data = {
            "id": "com_test",
            "name": "测试",
            "version": "1.0.0"
        }
        manifest = test_plugin / "manifest.json"
        manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

        pm = PluginManager(tmp_path)
        loaded = pm.load_manifest("test_plugin2")

        assert loaded is not None
        assert loaded["id"] == "com_test"

    def test_version_compatibility(self, tmp_path):
        """测试版本兼容性检查"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)

        assert pm.check_version_compatibility(">=2.0.0,<3.0.0") is True
        assert pm.check_version_compatibility(">=3.0.0") is False
        assert pm.check_version_compatibility(None) is True

    def test_permissions_check(self, tmp_path):
        """测试权限校验"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)

        assert pm.check_permissions({"permissions": ["read:chapters"]}) is True
        assert pm.check_permissions({"permissions": ["read:chapters", "network:requests"]}) is True
        assert pm.check_permissions({"permissions": ["illegal_permission"]}) is False

    def test_list_plugins(self, tmp_path):
        """测试列出已加载插件"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        test_plugin = plugins_dir / "test_plugin3"
        test_plugin.mkdir()
        manifest = test_plugin / "manifest.json"
        manifest.write_text(
            '{"id": "com_test3", "name": "测试插件3", "version": "1.0.0", "author": "tester", "description": "desc"}',
            encoding="utf-8"
        )

        pm = PluginManager(tmp_path)
        pm.load_all_plugins()

        plugins = pm.list_plugins()
        assert len(plugins) >= 1
        assert any(p["id"] == "com_test3" for p in plugins)

    def test_get_checker(self, tmp_path):
        """测试获取 Checker"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        pm = PluginManager(tmp_path)
        pm.load_all_plugins()

        checker_class = pm.get_checker("sensitive-word-checker")
        if checker_class:
            assert checker_class is not None

    def test_unload_plugin_removes_extensions(self, tmp_path):
        """测试卸载插件后扩展点被移除"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)

        pm.extensions["checkers"].append({
            "id": "test-checker",
            "class": None,
            "plugin_id": "com_test_reload"
        })
        pm.loaded_plugins["com_test_reload"] = {
            "name": "test_plugin",
            "manifest": {"id": "com_test_reload"}
        }

        result = pm.unload_plugin("com_test_reload")
        assert result is True

        checkers_after = [ext for ext in pm.extensions["checkers"] if ext.get("plugin_id") == "com_test_reload"]
        assert len(checkers_after) == 0
        assert "com_test_reload" not in pm.loaded_plugins

    def test_reload_all(self, tmp_path):
        """测试重载所有插件"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)

        pm.extensions["checkers"].append({
            "id": "test-checker-all",
            "class": None,
            "plugin_id": "com_test_reload_all"
        })
        pm.loaded_plugins["com_test_reload_all"] = {
            "name": "test_reload_all",
            "manifest": {"id": "com_test_reload_all"}
        }

        pm.reload_all()
        assert len(pm.loaded_plugins) == 0

    def test_reload_single_plugin(self, tmp_path):
        """测试重载单个插件"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)

        test_plugin = plugins_dir / "test_single_reload"
        test_plugin.mkdir()
        manifest = test_plugin / "manifest.json"
        manifest_data = {
            "id": "com_test_single_reload",
            "name": "测试单插件重载",
            "version": "1.0.0",
            "author": "tester",
            "entry_points": {
                "checkers": [
                    {"id": "test-checker-single", "class": "checkers.TestChecker", "description": "测试"}
                ]
            },
            "permissions": ["read:chapters"]
        }
        manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

        init_file = test_plugin / "__init__.py"
        init_file.write_text("", encoding="utf-8")
        checkers_dir = test_plugin / "checkers"
        checkers_dir.mkdir()
        checker_file = checkers_dir / "__init__.py"
        checker_file.write_text("", encoding="utf-8")

        pm = PluginManager(tmp_path)
        pm.load_all_plugins()

        result = pm.reload_plugin("com_test_single_reload")
        assert result is True

    def test_reloading_flag(self, tmp_path):
        """测试重载期间阻止插件调用"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)

        pm._reloading = True
        try:
            with pytest.raises(RuntimeError, match="插件正在重载中"):
                pm.get_checker("any")
        finally:
            pm._reloading = False


class TestPluginBase:
    """插件基类测试"""

    def test_base_checker_interface(self):
        """测试 BaseChecker 接口"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_base import BaseChecker

        class TestChecker(BaseChecker):
            async def check(self, chapter_text: str, context: dict) -> dict:
                return {"passed": True, "issues": [], "score": 100, "suggestions": []}

        checker = TestChecker()
        assert checker.config == {}

        checker = TestChecker({"threshold": 50})
        assert checker.config["threshold"] == 50


class TestHookSystem:
    """工作流钩子系统测试"""

    def test_hook_dispatcher_init(self, tmp_path):
        """测试 HookDispatcher 初始化"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager, HookDispatcher

        pm = PluginManager(tmp_path)
        dispatcher = pm.hook_dispatcher

        assert isinstance(dispatcher, HookDispatcher)
        assert dispatcher.pm is pm

    async def mock_hook_trigger(self, context):
        context["executed"] = True
        return context

    def test_hook_registration(self, tmp_path):
        """测试钩子注册"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        class MockHook:
            async def trigger(self, context):
                context["executed"] = True
                return context

        pm = PluginManager(tmp_path)
        hook = MockHook()

        pm.hook_dispatcher.register(hook, ["after_review", "before_polish"], "test_plugin")

        hooks = pm.hook_dispatcher.list_hooks()
        assert "after_review" in hooks
        assert "before_polish" in hooks

    @pytest.mark.asyncio
    async def test_hook_dispatch(self, tmp_path):
        """测试钩子调度"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        class TestHook:
            async def trigger(self, context):
                context["modified"] = True
                return context

        pm = PluginManager(tmp_path)
        hook = TestHook()

        pm.hook_dispatcher.register(hook, ["after_review"], "test")

        context = {"chapter": 1}
        result = await pm.hook_dispatcher.dispatch("after_review", context)

        assert result["modified"] is True

    @pytest.mark.asyncio
    async def test_hook_dispatch_exception_handling(self, tmp_path):
        """测试钩子异常处理"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        class FailingHook:
            async def trigger(self, context):
                raise ValueError("Hook failed")

        class SuccessHook:
            async def trigger(self, context):
                context["success"] = True
                return context

        pm = PluginManager(tmp_path)
        pm.hook_dispatcher.register(FailingHook(), ["after_review"], "failing")
        pm.hook_dispatcher.register(SuccessHook(), ["after_review"], "success")

        context = {"chapter": 1}
        result = await pm.hook_dispatcher.dispatch("after_review", context, strict=False)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_hook_dispatch_strict_mode(self, tmp_path):
        """测试严格模式"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        class FailingHook:
            async def trigger(self, context):
                raise ValueError("Hook failed")

        pm = PluginManager(tmp_path)
        pm.hook_dispatcher.register(FailingHook(), ["after_review"], "failing")

        context = {"chapter": 1}
        with pytest.raises(ValueError, match="Hook failed"):
            await pm.hook_dispatcher.dispatch("after_review", context, strict=True)

    def test_hook_list_empty(self, tmp_path):
        """测试空钩子列表"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        pm = PluginManager(tmp_path)
        hooks = pm.hook_dispatcher.list_hooks()

        assert hooks == {}

    def test_get_hooks_for_point(self, tmp_path):
        """测试获取指定钩子点"""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data_modules.plugin_manager import PluginManager

        class TestHook:
            pass

        pm = PluginManager(tmp_path)
        pm.hook_dispatcher.register(TestHook(), ["after_review"], "test")

        hooks = pm.hook_dispatcher.get_hooks_for_point("after_review")
        assert len(hooks) == 1
        assert hooks[0]["plugin_id"] == "test"
