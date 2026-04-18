#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 exceptions.py

验证异常基类和子类定义。
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestExceptions:
    def test_webnovel_error_basic(self):
        from data_modules.exceptions import WebnovelError

        err = WebnovelError("test message")
        assert err.message == "test message"
        assert err.details == {}
        assert str(err) == "test message"

    def test_webnovel_error_with_details(self):
        from data_modules.exceptions import WebnovelError

        err = WebnovelError("test message", {"key": "value"})
        assert err.message == "test message"
        assert err.details == {"key": "value"}

    def test_state_manager_error_inherits(self):
        from data_modules.exceptions import WebnovelError, StateManagerError

        err = StateManagerError("state error", {"chapter": 10})
        assert isinstance(err, WebnovelError)
        assert err.message == "state error"
        assert err.details == {"chapter": 10}

    def test_index_manager_error_inherits(self):
        from data_modules.exceptions import WebnovelError, IndexManagerError

        err = IndexManagerError("index error")
        assert isinstance(err, WebnovelError)
        assert err.message == "index error"

    def test_api_client_error_inherits(self):
        from data_modules.exceptions import WebnovelError, APIClientError

        err = APIClientError("api error", {"status": 500})
        assert isinstance(err, WebnovelError)
        assert err.details == {"status": 500}

    def test_config_error_inherits(self):
        from data_modules.exceptions import WebnovelError, ConfigError

        err = ConfigError("config error")
        assert isinstance(err, WebnovelError)
        assert err.message == "config error"

    def test_all_exceptions_inherit_from_base(self):
        from data_modules.exceptions import (
            WebnovelError,
            StateManagerError,
            IndexManagerError,
            APIClientError,
            ConfigError,
        )

        for exc_class in [StateManagerError, IndexManagerError, APIClientError, ConfigError]:
            assert issubclass(exc_class, WebnovelError)

    def test_exception_message_accessible(self):
        from data_modules.exceptions import StateManagerError

        err = StateManagerError(" chapters mismatch")
        assert err.args[0] == " chapters mismatch"
        assert err.message == " chapters mismatch"