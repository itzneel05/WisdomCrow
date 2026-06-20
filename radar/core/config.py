import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _resolve_env_var(value: Any) -> Any:
    if isinstance(value, str):

        def _replace(m: re.Match) -> str:
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise ValueError(f"Environment variable {var} is not set")
            return val

        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_var(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_var(v) for v in value]
    return value


class Config:
    def __init__(self, settings_path: str | Path, sources_path: str | Path) -> None:
        self.settings_path = Path(settings_path)
        self.sources_path = Path(sources_path)
        self._settings: dict[str, Any] = {}
        self._sources: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {self.settings_path}")
        if not self.sources_path.exists():
            raise FileNotFoundError(f"Sources file not found: {self.sources_path}")

        with open(self.settings_path) as f:
            raw_settings = yaml.safe_load(f)
        with open(self.sources_path) as f:
            raw_sources = yaml.safe_load(f)

        self._settings = _resolve_env_var(raw_settings)
        self._sources = _resolve_env_var(raw_sources)
        self._validate()

    def _validate(self) -> None:
        if "app" not in self._settings:
            raise ValueError("settings.yaml missing 'app' section")
        if "database" not in self._settings:
            raise ValueError("settings.yaml missing 'database' section")
        if "url" not in self._settings.get("database", {}):
            raise ValueError("settings.yaml database missing 'url'")
        if "discord" not in self._settings:
            raise ValueError("settings.yaml missing 'discord' section")
        if "webhooks" not in self._settings.get("discord", {}):
            raise ValueError("settings.yaml discord missing 'webhooks'")
        if "sources" not in self._sources:
            raise ValueError("sources.yaml missing 'sources' list")
        if not isinstance(self._sources["sources"], list):
            raise ValueError("sources.yaml 'sources' must be a list")

    @property
    def app_name(self) -> str:
        return self._settings["app"]["name"]

    @property
    def app_version(self) -> str:
        return self._settings["app"]["version"]

    @property
    def data_dir(self) -> str:
        return self._settings["app"]["data_dir"]

    @property
    def database_url(self) -> str:
        return self._settings["database"]["url"]

    @property
    def healthcheck_url(self) -> str:
        return self._settings.get("healthcheck", {}).get("url", "")

    def get_webhook_for_channel(self, channel: str) -> str:
        return self._settings["discord"]["webhooks"].get(channel, "")

    @property
    def fast_cadence_minutes(self) -> int:
        return self._settings["scan"]["fast_cadence_minutes"]

    @property
    def full_cadence_hours(self) -> int:
        return self._settings["scan"]["full_cadence_hours"]

    @property
    def fuzzy_threshold(self) -> int:
        return self._settings["dedup"]["fuzzy_threshold"]

    @property
    def dedup_window_days(self) -> int:
        return self._settings["dedup"]["window_days"]

    @property
    def max_alerts_per_run(self) -> int:
        return self._settings["alerts"]["max_per_run"]

    @property
    def max_alerts_per_category(self) -> int:
        return self._settings["alerts"]["max_per_category"]

    @property
    def auto_disable_after_errors(self) -> int:
        return self._settings["source"]["auto_disable_after_errors"]

    @property
    def raw_hit_retention_days(self) -> int:
        return self._settings["source"]["raw_hit_retention_days"]

    def get_sources(self) -> list[dict[str, Any]]:
        return self._sources["sources"]

    def get_sources_by_cadence(self, cadence: str) -> list[dict[str, Any]]:
        return [
            s
            for s in self._sources["sources"]
            if s.get("cadence") == cadence and s.get("enabled", True)
        ]

    def get_sources_by_type(self, source_type: str) -> list[dict[str, Any]]:
        return [
            s
            for s in self._sources["sources"]
            if s.get("type") == source_type and s.get("enabled", True)
        ]
