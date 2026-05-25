from __future__ import annotations

import os
from pathlib import Path


APP_DIR_ENV = "MAILWYRM_HOME"
DEFAULT_APP_DIR = Path.home() / ".mailwyrm"


def app_dir() -> Path:
    configured = os.environ.get(APP_DIR_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_APP_DIR


def token_path() -> Path:
    return app_dir() / "gmail-token.json"


def state_path() -> Path:
    return app_dir() / "state.json"

