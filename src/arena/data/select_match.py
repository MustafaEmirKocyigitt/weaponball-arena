"""Pick the match of the day, or a 'legends clash' when there is none."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .fixtures import Match
from .stats import rank_score, strength
from .teams import Team, normalize, resolve_clash, resolve_team


@dataclass
class Selection:
    home: Team
    away: Team
    league: str
    tags: list[str]
    tag: str                    # TONIGHT | TODAY | LEGENDS CLASH
    strength: tuple[float, float]
    form: tuple[str, str]
    legends: bool
    kickoff: datetime | None
    score: float = 0.0
    league_code: str = ""
    event_id: str = ""


def post_time_utc(day: date, cfg: dict) -> datetime:
    hh, mm = (int(x) for x in cfg.get("post_time_local", "19:00").split(":"))
    tz = timezone(timedelta(hours=cfg.get("timezone_offset_hours", 3)))
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz).astimezone(timezone.utc)


def _team(side) -> Team:
    return resolve_team(side.name, side.abbreviation, side.color, side.alt_color)


def _is_derby(a: Team, b: Team, derbies: list) -> bool:
    pair = {a.key, b.key}
    return any({normalize(x), normalize(y)} == pair for x, y in derbies)


def score_match(m: Match, cfg: dict, post_utc: datetime) -> float:
    sel = cfg.get("selection", {})
    h, a = _team(m.home), _team(m.away)
    s = m.league_bonus
    big = int(h.big) + int(a.big)
    s += sel.get("big_club_bonus", 4.0) * big
    if big == 2:
        s += sel.get("both_big_bonus", 3.0)
    rs = (rank_score(m.standings.get(m.home.espn_id)) + rank_score(m.standings.get(m.away.espn_id))) / 2
    s += sel.get("rank_weight", 3.0) * rs
    if _is_derby(h, a, cfg.get("derbies", [])):
        s += sel.get("derby_bonus", 6.0)
    if m.kickoff >= post_utc:
        s += sel.get("after_post_time_bonus", 3.0)
    return s


def choose(matches: list[Match], day: date, cfg: dict) -> Selection:
    post_utc = post_time_utc(day, cfg)
    if not matches:
        return legends_clash(day, cfg)
    scored = sorted(((score_match(m, cfg, post_utc), i, m) for i, m in enumerate(matches)),
                    key=lambda x: (-x[0], x[1]))
    best_score, _, m = scored[0]
    home, away = resolve_clash(_team(m.home), _team(m.away))
    st = (strength(m.standings.get(m.home.espn_id), m.home.form),
          strength(m.standings.get(m.away.espn_id), m.away.form))
    tag = "TONIGHT" if m.kickoff >= post_utc else "TODAY"
    return Selection(home, away, m.league_name, m.tags, tag, st, (m.home.form, m.away.form), False,
                     m.kickoff, best_score, m.league_code, m.event_id)


def legends_clash(day: date, cfg: dict) -> Selection:
    pairs = cfg.get("legends") or [["galatasaray", "fenerbahce"]]
    seed = int(day.strftime("%Y%m%d"))
    a, b = pairs[seed % len(pairs)]
    if (seed // len(pairs)) % 2:
        a, b = b, a
    home, away = resolve_clash(resolve_team(a), resolve_team(b))
    return Selection(home, away, "LEGENDS CLASH", ["footballlegends"], "LEGENDS CLASH", (0.5, 0.5), ("", ""),
                     True, None)
