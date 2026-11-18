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


def var_dir() -> Path:
    path = Path(os.environ.get("SETU_VAR", ROOT / "var"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.environ.get("SETU_DB", var_dir() / "setu.db"))


def mocks_db_path() -> Path:
    return Path(os.environ.get("SETU_MOCKS_DB", var_dir() / "tbo_mocks.db"))
