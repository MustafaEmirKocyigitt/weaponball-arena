"""Daily pipeline: fixtures -> match pick -> director -> render -> caption.

Slots:
  main   the daily anchor post (16:00 UTC, always posts; legends clash if no match)
  early  bonus battle before big early kick-offs (only if a high-profile match is coming up)
  late   bonus battle before big evening kick-offs (same rule)
A day never gets more than `schedule.max_posts_per_day` posts, and the same
match is never posted twice.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .caption import build_caption
from .config import OUTPUT, load_config
from .data import history
from .data.fixtures import fetch_day, http_get_json
from .data.select_match import choose, choose_bonus, legends_clash
from .director import pick_battle
from .render.scenes import MatchCard

SLOTS = {"main": 0, "early": 1, "late": 2}


def local_today(cfg: dict) -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=cfg.get("timezone_offset_hours", 3))).date()


def run_daily(day: date | None = None, out_root: Path = OUTPUT, fetch=http_get_json, render: bool = True,
              log=print, history_path: Path = history.HISTORY_PATH, slot: str = "main",
              now: datetime | None = None) -> Path | None:
    """Produce one post. Returns its folder, or None when a bonus slot has nothing worth posting.

    `now` (UTC) enables live filtering: skip matches that already kicked off and
    pick bonus matches by their kickoff window. Tests / back-fills leave it None.
    """
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot!r}")
    cfg = load_config()
    day = day or local_today(cfg)
    sch = cfg.get("schedule", {})

    hist = history.load(history_path)
    try:
        hist = history.resolve(hist, day, fetch, log)
    except Exception as e:
        log(f"[history] could not resolve past results: {e}")
    last, rec = history.last_call(hist, day), history.record(hist)
    today_posts = history.posted_on(hist, day)
    done_ids = {e.get("event_id") for e in today_posts if e.get("slot", "main") != slot and e.get("event_id")}

    if slot != "main":
        if len([e for e in today_posts if e.get("slot", "main") != slot]) >= sch.get("max_posts_per_day", 3):
            log(f"[{slot}] daily cap reached, nothing to do")
            history.save(hist, history_path)
            return None
        try:
            matches = fetch_day(day, cfg["leagues"], cfg.get("timezone_offset_hours", 3), fetch, log)
        except Exception as e:
            log(f"[{slot}] fixture lookup failed ({e}); skipping bonus slot")
            return None
        sel = choose_bonus(matches, cfg, now or datetime.now(timezone.utc), done_ids)
        if sel is None:
            log(f"[{slot}] no high-profile match kicking off soon; skipping")
            history.save(hist, history_path)
            return None
    else:
        try:
            matches = fetch_day(day, cfg["leagues"], cfg.get("timezone_offset_hours", 3), fetch, log)
            sel = choose(matches, day, cfg, exclude=done_ids, now=now)
        except Exception as e:  # never miss the anchor post because the data source is down
            log(f"[daily] fixture lookup failed ({e}); using legends clash")
            matches, sel = [], legends_clash(day, cfg)

    log(f"[{slot}] {day}: {len(matches)} matches -> {sel.home.name} vs {sel.away.name} "
        f"({sel.league}, {sel.tag}, strength {sel.strength[0]:.2f}/{sel.strength[1]:.2f})")

    day_seed = int(day.strftime("%Y%m%d"))
    seed = day_seed if slot == "main" else day_seed * 10 + SLOTS[slot]
    out_dir = Path(out_root) / (day.isoformat() if slot == "main" else f"{day.isoformat()}-{slot}")
    out_dir.mkdir(parents=True, exist_ok=True)

    pick = pick_battle(sel.home, sel.away, sel.strength, seed, cfg["director"])
    r = pick.result
    winner = (sel.home, sel.away)[r.winner]
    log(f"[{slot}] director: seed {r.seed}, {winner.name} wins, {r.duration:.1f}s, hp {r.hp}, score {pick.score:.2f}")

    card = MatchCard(
        league=sel.league, tag=sel.tag, home=sel.home, away=sel.away, form=sel.form,
        win_prob=None if sel.legends else pick.win_prob,
        cta="WHO WOULD WIN?" if sel.legends else ("WHO WINS TONIGHT?" if sel.tag == "TONIGHT" else "WHO WINS TODAY?"),
        sub_cta="COMMENT YOUR PICK" if sel.legends else "DROP YOUR SCORE IN THE COMMENTS",
        brand=cfg.get("brand", ""),
        record=rec if rec[1] >= 3 else None,
    )
    caption = build_caption(sel, r.winner, r.hp[r.winner], seed, cfg.get("hashtags_general", []),
                            win_prob=pick.win_prob, last=last if slot == "main" else None, record=rec,
                            brand=cfg.get("brand", ""), max_tags=cfg.get("max_hashtags", 6))
    hist = history.add(hist, {
        "date": day.isoformat(), "slot": slot, "league_code": sel.league_code, "event_id": sel.event_id,
        "home": sel.home.name, "away": sel.away.name, "home_short": sel.home.short, "away_short": sel.away.short,
        "predicted": winner.name, "predicted_side": r.winner, "legends": sel.legends, "outcome": None,
    })
    history.save(hist, history_path)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")

    video = out_dir / "video.mp4"
    if render:
        from .render.renderer import render_video
        render_video(card, r, video, cfg["video"], cfg["audio"])
    meta = {
        "date": day.isoformat(), "slot": slot, "league": sel.league, "tag": sel.tag, "legends": sel.legends,
        "home": sel.home.name, "away": sel.away.name, "kickoff_utc": sel.kickoff.isoformat() if sel.kickoff else None,
        "strength": sel.strength, "win_prob": pick.win_prob, "seed": r.seed, "winner": winner.name,
        "fight_seconds": round(r.duration, 2), "hp": r.hp, "hits": r.hits, "parries": r.parries,
        "video": video.name if render else None,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[{slot}] wrote {out_dir}")
    return out_dir
