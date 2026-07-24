"""AppContext — the composition root's dependency container.

Built once at startup and handed to every page: services are
constructed here (dependency injection by hand — explicit and
debuggable), so pages never build their own dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.appdb import AppDB
from ..core.config import AppConfig
from ..core.registry import Registry
from ..core.tasks import TaskRunner
from ..data.connections import DEMO_CONNECTION, ConnectionManager
from ..data.queries import LendingDataService
from ..modules.analytics import AnalyticsService
from ..modules.automation import AutomationCenter
from ..modules.executive import ExecutiveService
from ..modules.mis import MisGenerator
from ..modules.nlq import NlqEngine
from ..modules.productivity import ProductivityService
from ..modules.sql_studio import SqlStudioService


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
        self.mis = MisGenerator(self.executive)


def build_context(config: AppConfig) -> AppContext:
    """Wire the whole application object graph."""
    appdb = AppDB()
    registry = Registry()
    runner = TaskRunner(max_workers=4)
    connections = ConnectionManager(appdb)
    data = LendingDataService(connections, DEMO_CONNECTION)
    executive = ExecutiveService(data, config.executive)
    analytics = AnalyticsService(data)
    nlq = NlqEngine(data)
    mis = MisGenerator(executive)
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
        sql=sql,
        automation=automation,
        productivity=productivity,
    )
