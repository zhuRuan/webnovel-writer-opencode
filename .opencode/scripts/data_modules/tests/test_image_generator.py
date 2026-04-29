#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ImageGenerator utility function tests.
"""

from ..image_generator import ImageGenerator, SUPPORTED_SIZES, DEFAULT_STYLES, ImageGenStats
from ..config import DataModulesConfig


def _make_config(tmp_path):
    cfg = DataModulesConfig(project_root=tmp_path)
    cfg.image_api_key = "test-key"
    cfg.image_base_url = "https://api-inference.modelscope.cn/v1"
    cfg.image_model = "test-model"
    cfg.image_size = "1:1"
    cfg.world_preset = "xianxia"
    cfg.api_max_retries = 2
    cfg.normal_timeout = 10
    return cfg


def test_supported_sizes_format():
    """SUPPORTED_SIZES maps ratio strings to pixel strings."""
    assert "1:1" in SUPPORTED_SIZES
    assert "3:4" in SUPPORTED_SIZES
    assert "x" in SUPPORTED_SIZES["1:1"]


def test_default_styles():
    """DEFAULT_STYLES covers major genres."""
    assert "xianxia" in DEFAULT_STYLES
    assert "urban" in DEFAULT_STYLES
    assert len(DEFAULT_STYLES) >= 4


def test_validate_size_known(tmp_path):
    config = _make_config(tmp_path)
    gen = ImageGenerator(config)

    assert gen._validate_size("1:1") == SUPPORTED_SIZES["1:1"]
    assert gen._validate_size("3:4") == SUPPORTED_SIZES["3:4"]


def test_validate_size_pixel_format(tmp_path):
    config = _make_config(tmp_path)
    gen = ImageGenerator(config)

    assert gen._validate_size("1328x1328") == "1328x1328"


def test_validate_size_unknown_fallback(tmp_path):
    config = _make_config(tmp_path)
    gen = ImageGenerator(config)

    result = gen._validate_size("unknown")
    assert result == "1:1"


def test_build_url(tmp_path):
    config = _make_config(tmp_path)
    gen = ImageGenerator(config)

    url = gen._build_url()
    assert "/v1/images/generations" in url


def test_build_headers(tmp_path):
    config = _make_config(tmp_path)
    gen = ImageGenerator(config)

    headers = gen._build_headers()
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["X-ModelScope-Async-Mode"] == "true"


def test_image_gen_stats():
    stats = ImageGenStats()
    assert stats.total == 0
    assert stats.success == 0
    assert stats.errors == 0

    stats.total = 5
    stats.success = 3
    stats.errors = 2
    assert stats.total == stats.success + stats.errors
