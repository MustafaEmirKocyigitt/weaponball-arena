"""Prediction history: was yesterday's arena call right?

Stored in data/history.json, which the GitHub workflow commits back to the
repo after each successful post, so the record survives between runs.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from ..config import ROOT
from .fixtures import SCOREBOARD, Fetch, http_get_json

HISTORY_PATH = ROOT / "data" / "history.json"
MAX_ENTRIES = 400


def load(path: Path = HISTORY_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("predictions", [])
    except (ValueError, OSError):
        return []


def save(entries: list[dict], path: Path = HISTORY_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"predictions": entries[-MAX_ENTRIES:]}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def add(entries: list[dict], entry: dict) -> list[dict]:
    out = [e for e in entries if e.get("date") != entry["date"]]
    out.append(entry)
    out.sort(key=lambda e: e["date"])
    return out


def _find_result(code: str, day: date, event_id: str, fetch: Fetch) -> dict | None:
    for d in (day, day + timedelta(days=1), day - timedelta(days=1)):
        try:
            data = fetch(SCOREBOARD.format(code=code), {"dates": d.strftime("%Y%m%d")})
        except Exception:
            continue
        for ev in data.get("events", []):
            if str(ev.get("id")) != str(event_id):
                continue
            comp = (ev.get("competitions") or [{}])[0]
            st = comp.get("status", ev.get("status", {})).get("type", {})
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            return {
                "completed": bool(st.get("completed")),
                "state": st.get("name", ""),
                "home": sides.get("home", {}).get("score"),
                "away": sides.get("away", {}).get("score"),
            }
    return None


def resolve(entries: list[dict], today: date, fetch: Fetch = http_get_json, log=print) -> list[dict]:
    """Fill in outcomes of past predictions whose matches have finished."""
    for e in entries:
        if e.get("outcome") or e.get("legends") or not e.get("event_id"):
            continue
        day = date.fromisoformat(e["date"])
        if day >= today:
            continue
        res = _find_result(e["league_code"], day, e["event_id"], fetch)
        if res and res["completed"]:
            try:
                hs, as_ = int(res["home"]), int(res["away"])
            except (TypeError, ValueError):
                continue
            e["score"] = f"{hs}-{as_}"
            if hs == as_:
                e["outcome"] = "draw"
            else:
                e["outcome"] = "hit" if (hs > as_) == (e["predicted_side"] == 0) else "miss"
            log(f"[history] {e['date']} {e['home']} {e['score']} {e['away']}: {e['outcome']}")
        elif (res and res["state"] in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_ABANDONED")) or \
                (today - day).days > 4:
            e["outcome"] = "void"
    return entries


def record(entries: list[dict]) -> tuple[int, int]:
    done = [e for e in entries if e.get("outcome") in ("hit", "miss", "draw")]
    return sum(e["outcome"] == "hit" for e in done), len(done)


def last_call(entries: list[dict], today: date, max_age_days: int = 3) -> dict | None:
    for e in reversed(entries):
        if e.get("outcome") in ("hit", "miss", "draw"):
            if (today - date.fromisoformat(e["date"])).days <= max_age_days:
                return e
            return None
    return None
