"""Paths and config loading."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"
TEAMS_PATH = ROOT / "data" / "teams.yaml"
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_team_overrides() -> dict:
    with open(TEAMS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
