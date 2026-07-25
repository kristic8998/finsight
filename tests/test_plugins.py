"""Tests for the drop-in plugin discovery + registry integration.

These stay UI-free: temp plugin files import only ``finsight.core.plugins``
(never customtkinter), and the built-in scan is pointed at an empty temp
dir so the shipped CTk example is not imported here.
"""

from __future__ import annotations

import pytest

from finsight.core.plugins import FinSightPlugin, discover_plugins
from finsight.core.registry import Registry

_VALID = """
from finsight.core.plugins import FinSightPlugin

class DummyPlugin(FinSightPlugin):
    id = "dummy"
    title = "Dummy Tool"
    icon = "★"
    order = 500

    def create_page(self, parent, app):
        return ("page", parent, app)
"""

_BROKEN = "import a_module_that_does_not_exist_xyz\n"

_NO_PLUGIN = "x = 1\n"

_BAD_ID = """
from finsight.core.plugins import FinSightPlugin

class BadId(FinSightPlugin):
    id = "not an identifier"
    title = "Nope"

    def create_page(self, parent, app):
        return None
"""


def _write(directory, name, content):
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def _empty(tmp_path):
    d = tmp_path / "builtin_empty"
    d.mkdir()
    return d


class TestDiscovery:
    def test_loads_valid_plugin(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "dummy_plugin.py", _VALID)
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert [p.id for p in result.plugins] == ["dummy"]
        assert result.plugins[0].title == "Dummy Tool"
        # the factory works without any UI dependency
        assert result.plugins[0].create_page("P", "A") == ("page", "P", "A")

    def test_broken_plugin_is_skipped_with_error(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "broken_plugin.py", _BROKEN)
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert result.plugins == []
        assert len(result.errors) == 1

    def test_file_without_plugin_is_ignored(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "just_code.py", _NO_PLUGIN)
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert result.plugins == []
        assert result.errors == []

    def test_bad_metadata_is_rejected(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "bad_id_plugin.py", _BAD_ID)
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert result.plugins == []
        assert any("identifier" in msg for _src, msg in result.errors)

    def test_underscored_files_are_skipped(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "_private.py", _VALID)
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert result.plugins == []

    def test_missing_user_dir_is_fine(self, tmp_path):
        result = discover_plugins(builtin_dir=_empty(tmp_path), user_dir=tmp_path / "nope")
        assert result.plugins == []
        assert result.errors == []


class TestValidate:
    def test_rejects_empty_id(self):
        class P(FinSightPlugin):
            id = ""
            title = "x"

            def create_page(self, parent, app):
                return None

        with pytest.raises(ValueError):
            P().validate()

    def test_rejects_empty_title(self):
        class P(FinSightPlugin):
            id = "ok"
            title = ""

            def create_page(self, parent, app):
                return None

        with pytest.raises(ValueError):
            P().validate()


class TestRegistryIntegration:
    def test_load_plugins_registers_module_and_plugin(self, tmp_path):
        users = tmp_path / "users"
        users.mkdir()
        _write(users, "dummy_plugin.py", _VALID)
        registry = Registry()
        result = registry.load_plugins(builtin_dir=_empty(tmp_path), user_dir=users)
        assert "dummy" in registry.plugins
        assert "dummy" in registry.modules
        assert registry.modules["dummy"].title == "Dummy Tool"
        assert [p.id for p in result.plugins] == ["dummy"]
