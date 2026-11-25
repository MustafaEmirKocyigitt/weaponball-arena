"""Fetch fixtures and standings from ESPN's public (unofficial, keyless) JSON API."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import requests

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/{code}/standings"

Fetch = Callable[[str, dict], dict]


def http_get_json(url: str, params: dict | None = None, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            # ESPN rejects unknown bot User-Agents; requests' default one is accepted.
            r = requests.get(url, params=params or {}, timeout=20)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


@dataclass
class Side:
    espn_id: str
    name: str
    abbreviation: str | None = None
    color: str | None = None
    alt_color: str | None = None
    form: str = ""


@dataclass
class Match:
    league_code: str
    league_name: str
    tags: list[str]
    league_bonus: float
    kickoff: datetime          # UTC
    home: Side
    away: Side
    standings: dict = field(default_factory=dict)  # espn_id -> standing dict
    event_id: str = ""


def _parse_side(c: dict) -> Side:
    t = c.get("team", {})
    return Side(espn_id=str(t.get("id", "")), name=t.get("displayName") or t.get("name", "?"),
                abbreviation=t.get("abbreviation"), color=t.get("color"), alt_color=t.get("alternateColor"),
                form=(c.get("form") or "")[-5:])


def parse_scoreboard(data: dict, league: dict) -> list[Match]:
    out = []
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = comp.get("status", ev.get("status", {})).get("type", {}).get("name", "")
        if status not in ("STATUS_SCHEDULED", ""):
            continue
        sides = {c.get("homeAway"): _parse_side(c) for c in comp.get("competitors", [])}
        if "home" not in sides or "away" not in sides:
            continue
        ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
        out.append(Match(league["code"], league["name"], list(league.get("tags", [])),
                         float(league.get("bonus", 1.0)), ko, sides["home"], sides["away"],
                         event_id=str(ev.get("id", ""))))
    return out


def parse_standings(data: dict) -> dict[str, dict]:
    table: dict[str, dict] = {}
    groups = data.get("children") or [data]
    for g in groups:
        entries = g.get("standings", {}).get("entries", [])
        n = len(entries)
        for e in entries:
            stats = {s.get("name"): s.get("value") for s in e.get("stats", [])}
            tid = str(e.get("team", {}).get("id", ""))
            table[tid] = {
                "rank": stats.get("rank"),
                "gp": stats.get("gamesPlayed"),
                "pts": stats.get("points"),
                "gd": stats.get("pointDifferential"),
                "n": n,
            }
    return table


def fetch_day(day: date, leagues: list[dict], tz_offset_h: float, fetch: Fetch = http_get_json,
              log=print) -> list[Match]:
    """All scheduled matches whose local kickoff date is `day`."""
    tz = timezone(timedelta(hours=tz_offset_h))
    matches: list[Match] = []
    for lg in leagues:
        found: list[Match] = []
        seen = set()
        for d in (day, day + timedelta(days=1)):  # ESPN groups dates in US time
            try:
                data = fetch(SCOREBOARD.format(code=lg["code"]), {"dates": d.strftime("%Y%m%d")})
            except Exception as e:  # one league failing must not kill the day
                log(f"[fixtures] {lg['code']}: {e}")
                continue
            for m in parse_scoreboard(data, lg):
                key = (m.home.espn_id, m.away.espn_id, m.kickoff)
                if key not in seen and m.kickoff.astimezone(tz).date() == day:
                    seen.add(key)
                    found.append(m)
        if found:
            try:
                table = parse_standings(fetch(STANDINGS.format(code=lg["code"]), {}))
            except Exception as e:
                log(f"[standings] {lg['code']}: {e}")
                table = {}
            for m in found:
                m.standings = table
        matches.extend(found)
    return matches
