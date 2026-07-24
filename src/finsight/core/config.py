"""Typed configuration (Pydantic + YAML) with safe defaults.

Anything a user may want to tune lives here; the Settings page edits a
subset and persists overrides to ``<app data>/config.yaml`` so upgrades
never clobber user preferences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from .paths import app_data_dir


class UiConfig(BaseModel):
    theme: Literal["dark", "light", "system"] = "dark"
    accent: str = "#2E7BE6"
    font_scale: float = Field(default=1.0, ge=0.75, le=1.75)
    start_page: str = "executive"


class ExecutiveConfig(BaseModel):
    par_alert_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    efficiency_alert_pct: float = Field(default=90.0, ge=0.0, le=100.0)
    concentration_alert_pct: float = Field(default=40.0, ge=0.0, le=100.0)


class ReconConfig(BaseModel):
    amount_tolerance: float = Field(default=1.0, ge=0.0)


class AutomationConfig(BaseModel):
    enabled: bool = False
    poll_seconds: int = Field(default=20, ge=5, le=600)


class EmailConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    use_tls: bool = True
    sender: str = ""
    # Password is stored via the credential vault, never in YAML.


class BrandingConfig(BaseModel):
    """Company identity stamped onto generated report packs."""

    company_name: str = ""


class DemoConfig(BaseModel):
    seed: int = 42
    branches: int = Field(default=8, ge=2, le=50)
    loans: int = Field(default=1200, ge=50, le=100_000)


class AppConfig(BaseModel):
    ui: UiConfig = Field(default_factory=UiConfig)
    executive: ExecutiveConfig = Field(default_factory=ExecutiveConfig)
    recon: ReconConfig = Field(default_factory=ReconConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    branding: BrandingConfig = Field(default_factory=BrandingConfig)
    demo: DemoConfig = Field(default_factory=DemoConfig)


class ConfigError(Exception):
    """Raised when a config file exists but cannot be used."""


def config_file() -> Path:
    return app_data_dir() / "config.yaml"


def load_config(path: Path | None = None) -> AppConfig:
    """Load config from YAML; missing file means pure defaults."""
    file_path = path if path is not None else config_file()
    if not file_path.is_file():
        return AppConfig()
    try:
        raw: Any = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"top level of {file_path} must be a mapping")
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration: {exc}") from exc


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Persist the full config as YAML (atomic write)."""
    file_path = path if path is not None else config_file()
    tmp = file_path.with_suffix(".tmp")
    tmp.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(file_path)
    return file_path
