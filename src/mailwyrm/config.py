from __future__ import annotations

import os
from pathlib import Path


APP_DIR_ENV = "MAILWYRM_HOME"
CLIENT_SECRET_ENV = "MAILWYRM_CLIENT_SECRET"
SHOW_METRICS_ENV = "MAILWYRM_SHOW_METRICS"
DEFAULT_APP_DIR = Path.home() / ".mailwyrm"


def app_dir() -> Path:
    configured = os.environ.get(APP_DIR_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_APP_DIR


def token_path() -> Path:
    return app_dir() / "gmail-token.json"


def state_path() -> Path:
    return app_dir() / "state.json"


def client_secret_path() -> Path | None:
    configured = os.environ.get(CLIENT_SECRET_ENV)
    return Path(configured).expanduser() if configured else None


def show_metrics_enabled() -> bool:
    configured = os.environ.get(SHOW_METRICS_ENV, "")
    return configured.strip().lower() in {"1", "true", "yes", "on"}
