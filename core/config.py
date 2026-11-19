"""Filesystem locations. Everything a TBO developer edits lives outside ``core/``."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

POLICIES_DIR = ROOT / "policies"
WORKFLOWS_DIR = ROOT / "workflows"
SKILLS_DIR = ROOT / "skills"
CONNECTORS_DIR = ROOT / "connectors"
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into the environment (existing variables win).
    Tiny on purpose: no dependency, no interpolation."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def var_dir() -> Path:
    path = Path(os.environ.get("SETU_VAR", ROOT / "var"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.environ.get("SETU_DB", var_dir() / "setu.db"))


def mocks_db_path() -> Path:
    return Path(os.environ.get("SETU_MOCKS_DB", var_dir() / "tbo_mocks.db"))
