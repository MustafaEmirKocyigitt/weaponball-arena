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


def score_match(m: Match, cfg: dict, post_utc: datetime | None) -> float:
    """Global-popularity score. `post_utc=None` skips the 'kicks off after the post' bonus."""
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
    if post_utc is not None and m.kickoff >= post_utc:
        s += sel.get("after_post_time_bonus", 3.0)
    return s


def _selection(m: Match, score: float, tag: str) -> Selection:
    home, away = resolve_clash(_team(m.home), _team(m.away))
    st = (strength(m.standings.get(m.home.espn_id), m.home.form),
          strength(m.standings.get(m.away.espn_id), m.away.form))
    return Selection(home, away, m.league_name, m.tags, tag, st, (m.home.form, m.away.form), False,
                     m.kickoff, score, m.league_code, m.event_id)


def _evening_tag(m: Match, cfg: dict) -> str:
    local = m.kickoff + timedelta(hours=cfg.get("timezone_offset_hours", 3))
    return "TONIGHT" if local.hour >= 18 else "TODAY"


def choose(matches: list[Match], day: date, cfg: dict, exclude: set[str] = frozenset(),
           now: datetime | None = None) -> Selection:
    """Main post of the day. With `now`, matches about to start / already started are skipped."""
    post_utc = post_time_utc(day, cfg)
    pool = [m for m in matches if m.event_id not in exclude
            and (now is None or m.kickoff > now + timedelta(minutes=10))]
    if not pool:
        return legends_clash(day, cfg)
    scored = sorted(((score_match(m, cfg, post_utc), i, m) for i, m in enumerate(pool)),
                    key=lambda x: (-x[0], x[1]))
    best_score, _, m = scored[0]
    return _selection(m, best_score, "TONIGHT" if m.kickoff >= post_utc else "TODAY")


def choose_bonus(matches: list[Match], cfg: dict, now: datetime, exclude: set[str] = frozenset()) -> Selection | None:
    """A 'bonus battle': a high-profile match kicking off soon that hasn't been posted yet.

    Posted 1-4 hours before kickoff, when fans are scrolling for the game.
    Only matches above `schedule.bonus_min_score` qualify, so quiet days stay at one post.
    """
    sch = cfg.get("schedule", {})
    lo, hi = sch.get("bonus_window_minutes", [45, 250])
    min_score = sch.get("bonus_min_score", 9.0)
    cands = []
    for i, m in enumerate(matches):
        if m.event_id in exclude:
            continue
        if not (now + timedelta(minutes=lo) <= m.kickoff <= now + timedelta(minutes=hi)):
            continue
        s = score_match(m, cfg, None)
        if s >= min_score:
            cands.append((s, i, m))
    if not cands:
        return None
    s, _, m = sorted(cands, key=lambda x: (-x[0], x[1]))[0]
    return _selection(m, s, _evening_tag(m, cfg))


def legends_clash(day: date, cfg: dict) -> Selection:
    pairs = cfg.get("legends") or [["galatasaray", "fenerbahce"]]
    seed = int(day.strftime("%Y%m%d"))
    a, b = pairs[seed % len(pairs)]
    if (seed // len(pairs)) % 2:
        a, b = b, a
    home, away = resolve_clash(resolve_team(a), resolve_team(b))
    return Selection(home, away, "LEGENDS CLASH", ["footballlegends"], "LEGENDS CLASH", (0.5, 0.5), ("", ""),
                     True, None)
