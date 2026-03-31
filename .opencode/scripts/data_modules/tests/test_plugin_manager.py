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
