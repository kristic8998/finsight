"""Core platform tests: config, appdb, registry, tasks, backup."""

from __future__ import annotations

import time

import pytest

from finsight.core.appdb import AppDB, SavedConnection
from finsight.core.backup import create_backup, list_backups
from finsight.core.config import AppConfig, ConfigError, load_config, save_config
from finsight.core.registry import Action, Module, Registry
from finsight.core.tasks import TaskRunner, retry


class TestConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.ui.theme == "dark"
        assert config.executive.par_alert_pct == 5.0

    def test_roundtrip(self, tmp_path):
        config = AppConfig()
        config.ui.theme = "light"
        config.recon.amount_tolerance = 2.5
        path = save_config(config, tmp_path / "c.yaml")
        loaded = load_config(path)
        assert loaded.ui.theme == "light"
        assert loaded.recon.amount_tolerance == 2.5

    def test_missing_file_gives_defaults(self, tmp_path):
        assert load_config(tmp_path / "nope.yaml").ui.theme == "dark"

    def test_invalid_yaml_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("ui: [not a mapping", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(bad)

    def test_invalid_values_raise(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("ui:\n  font_scale: 99\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(bad)


class TestAppDB:
    def test_kv_roundtrip(self, tmp_path):
        db = AppDB(tmp_path / "a.db")
        db.set_value("layout", {"page": "executive"})
        assert db.get_value("layout") == {"page": "executive"}
        assert db.get_value("missing", 42) == 42

    def test_history_and_saved_queries(self, tmp_path):
        db = AppDB(tmp_path / "b.db")
        db.add_history("demo", "SELECT 1", 1, 3.2)
        assert db.history()[0]["sql"] == "SELECT 1"
        db.save_query("mine", "SELECT 2")
        db.save_query("mine", "SELECT 3")  # upsert
        assert db.saved_queries()[0]["sql"] == "SELECT 3"
        db.delete_saved_query("mine")
        assert db.saved_queries() == []

    def test_notes_tasks_favorites(self, tmp_path):
        db = AppDB(tmp_path / "c.db")
        note_id = db.upsert_note("hello", "body")
        db.upsert_note("hello2", "body2", note_id)
        assert db.notes()[0]["title"] == "hello2"
        task_id = db.add_task("do it")
        db.set_task_status(task_id, "done")
        assert db.tasks()[0]["status"] == "done"
        with pytest.raises(ValueError):
            db.set_task_status(task_id, "bogus")
        db.add_favorite("query", "q1", "My query")
        db.add_favorite("query", "q1", "My query")  # idempotent
        assert len(db.favorites("query")) == 1

    def test_job_runs_and_connections(self, tmp_path):
        db = AppDB(tmp_path / "d.db")
        run_id = db.job_started("mis")
        db.job_finished(run_id, "success", "done")
        assert db.job_runs()[0]["status"] == "success"
        db.save_connection(SavedConnection(name="x", kind="sqlite", params={"path": "p"}))
        assert db.connections()[0].params == {"path": "p"}


class TestRegistry:
    def _registry(self) -> Registry:
        registry = Registry()
        registry.register_module(Module(id="sql", title="SQL Studio", icon="▤", order=1))
        registry.register_module(Module(id="mis", title="MIS", icon="▣", order=2))
        registry.register_action(
            Action(
                id="a",
                title="Open SQL Studio",
                category="sql",
                run=lambda: None,
                keywords=("query",),
            )
        )
        registry.register_action(
            Action(id="b", title="Generate MIS", category="mis", run=lambda: None)
        )
        return registry

    def test_search_prefix_beats_substring(self):
        registry = self._registry()
        results = registry.search("open")
        assert results[0].id == "a"

    def test_keyword_match(self):
        registry = self._registry()
        assert any(a.id == "a" for a in registry.search("query"))

    def test_disabled_module_hidden(self):
        registry = self._registry()
        registry.set_module_enabled("sql", False)
        assert all(a.category != "sql" for a in registry.search("open"))
        assert [m.id for m in registry.enabled_modules()] == ["mis"]


class TestTasks:
    def test_runner_success_and_error(self):
        runner = TaskRunner(max_workers=2)
        done: list = []
        errors: list = []
        runner.submit(lambda: 21 * 2, on_done=done.append)
        runner.submit(lambda: 1 / 0, on_error=errors.append)
        deadline = time.time() + 5
        while (not done or not errors) and time.time() < deadline:
            time.sleep(0.02)
        runner.shutdown()
        assert done == [42]
        assert isinstance(errors[0], ZeroDivisionError)

    def test_retry_recovers(self):
        calls = {"n": 0}

        @retry((RuntimeError,), attempts=3, delay=0.001)
        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return "ok"

        assert flaky() == "ok"

    def test_retry_gives_up(self):
        @retry((RuntimeError,), attempts=2, delay=0.001)
        def bad() -> None:
            raise RuntimeError("always")

        with pytest.raises(RuntimeError):
            bad()


class TestBackup:
    def test_backup_creates_and_prunes(self):
        first = create_backup(keep=2)
        second = create_backup(keep=2)
        third = create_backup(keep=2)
        remaining = list_backups()
        assert third in remaining
        assert second in remaining
        assert first not in remaining  # pruned
        assert all(p.suffix == ".zip" for p in remaining)
