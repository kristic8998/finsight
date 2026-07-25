"""AppContext — the composition root's dependency container.

Built once at startup and handed to every page: services are
constructed here (dependency injection by hand — explicit and
debuggable), so pages never build their own dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..core.appdb import AppDB
from ..core.config import AppConfig
from ..core.paths import user_plugins_dir
from ..core.registry import Registry
from ..core.tasks import TaskRunner
from ..data.connections import DEMO_CONNECTION, ConnectionManager
from ..data.queries import LendingDataService
from ..modules.analytics import AnalyticsService
from ..modules.automation import AutomationCenter
from ..modules.executive import ExecutiveService
from ..modules.mis import MisGenerator
from ..modules.mis_catalog import MisCatalog
from ..modules.nlq import NlqEngine
from ..modules.productivity import ProductivityService
from ..modules.sql_studio import SqlStudioService

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    config: AppConfig
    appdb: AppDB
    registry: Registry
    runner: TaskRunner
    connections: ConnectionManager
    data: LendingDataService
    executive: ExecutiveService
    analytics: AnalyticsService
    nlq: NlqEngine
    mis: MisGenerator
    mis_catalog: MisCatalog
    sql: SqlStudioService
    automation: AutomationCenter
    productivity: ProductivityService
    active_connection: str = DEMO_CONNECTION
    extras: dict = field(default_factory=dict)

    def use_connection(self, name: str) -> None:
        """Repoint every data-driven module at another connection."""
        self.active_connection = name
        self.data = LendingDataService(self.connections, name)
        self.executive = ExecutiveService(self.data, self.config.executive)
        self.analytics = AnalyticsService(self.data)
        self.nlq = NlqEngine(self.data)
        self.mis = MisGenerator(self.executive, self.config.branding.company_name)
        self.mis_catalog = MisCatalog(self.data, self.appdb, self.config.branding.company_name)


def _load_plugins(registry: Registry) -> None:
    """Discover drop-in plugins; never let a bad plugin break startup."""
    try:
        result = registry.load_plugins(user_dir=user_plugins_dir())
    except Exception as exc:  # noqa: BLE001 - discovery must never crash the app
        logger.warning("plugin discovery failed: %s", exc)
        return
    for source, message in result.errors:
        logger.warning("plugin skipped (%s): %s", source, message)
    if result.plugins:
        logger.info(
            "loaded %d plugin(s): %s", len(result.plugins), ", ".join(p.id for p in result.plugins)
        )


def build_context(config: AppConfig) -> AppContext:
    """Wire the whole application object graph."""
    appdb = AppDB()
    registry = Registry()
    _load_plugins(registry)
    runner = TaskRunner(max_workers=4)
    connections = ConnectionManager(appdb)
    data = LendingDataService(connections, DEMO_CONNECTION)
    executive = ExecutiveService(data, config.executive)
    analytics = AnalyticsService(data)
    nlq = NlqEngine(data)
    mis = MisGenerator(executive, config.branding.company_name)
    mis_catalog = MisCatalog(data, appdb, config.branding.company_name)
    sql = SqlStudioService(connections, appdb)
    automation = AutomationCenter(appdb, poll_seconds=config.automation.poll_seconds)
    productivity = ProductivityService(appdb)
    return AppContext(
        config=config,
        appdb=appdb,
        registry=registry,
        runner=runner,
        connections=connections,
        data=data,
        executive=executive,
        analytics=analytics,
        nlq=nlq,
        mis=mis,
        mis_catalog=mis_catalog,
        sql=sql,
        automation=automation,
        productivity=productivity,
    )
