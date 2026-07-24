"""Shared fixtures: one small demo DB + wired services per session."""

from __future__ import annotations

from pathlib import Path

import pytest

from finsight.core.appdb import AppDB, SavedConnection
from finsight.core.config import AppConfig
from finsight.data.connections import ConnectionManager
from finsight.data.demo_data import generate_demo_db
from finsight.data.queries import LendingDataService
from finsight.modules.analytics import AnalyticsService
from finsight.modules.executive import ExecutiveService
from finsight.modules.nlq import NlqEngine


@pytest.fixture(scope="session", autouse=True)
def _isolated_home(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point FINSIGHT_HOME at a temp dir so tests never touch real data."""
    import os

    os.environ["FINSIGHT_HOME"] = str(tmp_path_factory.mktemp("home"))


@pytest.fixture(scope="session")
def config() -> AppConfig:
    cfg = AppConfig()
    cfg.demo.loans = 250
    cfg.demo.branches = 5
    cfg.demo.seed = 7
    return cfg


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory: pytest.TempPathFactory, config: AppConfig) -> Path:
    path = tmp_path_factory.mktemp("db") / "demo.db"
    generate_demo_db(config.demo, path=path, force=True)
    return path


@pytest.fixture(scope="session")
def appdb(tmp_path_factory: pytest.TempPathFactory) -> AppDB:
    return AppDB(tmp_path_factory.mktemp("appdb") / "app.db")


@pytest.fixture(scope="session")
def connections(appdb: AppDB, demo_db: Path) -> ConnectionManager:
    manager = ConnectionManager(appdb)
    manager.save(SavedConnection(name="test", kind="sqlite", params={"path": str(demo_db)}))
    return manager


@pytest.fixture(scope="session")
def data(connections: ConnectionManager) -> LendingDataService:
    return LendingDataService(connections, "test")


@pytest.fixture(scope="session")
def executive(data: LendingDataService, config: AppConfig) -> ExecutiveService:
    return ExecutiveService(data, config.executive)


@pytest.fixture(scope="session")
def analytics(data: LendingDataService) -> AnalyticsService:
    return AnalyticsService(data)


@pytest.fixture(scope="session")
def nlq(data: LendingDataService) -> NlqEngine:
    return NlqEngine(data)
