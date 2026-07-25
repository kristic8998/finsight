"""Page factories — the shell looks pages up here by module id."""

from __future__ import annotations

from .analytics_page import AnalyticsPage
from .api_page import ApiPage
from .ask_page import AskPage
from .automation_page import AutomationPage
from .dq_page import DqPage
from .excel_page import ExcelPage
from .executive_page import ExecutivePage
from .mis_page import MisPage
from .mis_studio_page import MisStudioPage
from .productivity_page import ProductivityPage
from .recon_page import ReconPage
from .settings_page import SettingsPage
from .sql_page import SqlPage

PAGE_FACTORIES = {
    "executive": ExecutivePage,
    "ask": AskPage,
    "sql": SqlPage,
    "excel": ExcelPage,
    "dq": DqPage,
    "recon": ReconPage,
    "mis": MisPage,
    "studio": MisStudioPage,
    "analytics": AnalyticsPage,
    "automation": AutomationPage,
    "api": ApiPage,
    "productivity": ProductivityPage,
    "settings": SettingsPage,
}

__all__ = ["PAGE_FACTORIES"]
