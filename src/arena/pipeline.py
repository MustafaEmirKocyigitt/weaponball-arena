"""Daily pipeline: fixtures -> match of the day -> director -> render -> caption."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .caption import build_caption
from .config import OUTPUT, load_config
from .data import history
from .data.fixtures import fetch_day, http_get_json
from .data.select_match import choose, legends_clash
from .director import pick_battle
from .render.scenes import MatchCard


def local_today(cfg: dict) -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=cfg.get("timezone_offset_hours", 3))).date()


def run_daily(day: date | None = None, out_root: Path = OUTPUT, fetch=http_get_json, render: bool = True,
              log=print, history_path: Path = history.HISTORY_PATH) -> Path:
    cfg = load_config()
    day = day or local_today(cfg)
    day_seed = int(day.strftime("%Y%m%d"))
    out_dir = Path(out_root) / day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    hist = history.load(history_path)
    try:
        hist = history.resolve(hist, day, fetch, log)
    except Exception as e:
        log(f"[history] could not resolve past results: {e}")
    last, rec = history.last_call(hist, day), history.record(hist)

    try:
        matches = fetch_day(day, cfg["leagues"], cfg.get("timezone_offset_hours", 3), fetch, log)
        sel = choose(matches, day, cfg)
    except Exception as e:  # never miss a day because the data source is down
        log(f"[daily] fixture lookup failed ({e}); using legends clash")
        matches, sel = [], legends_clash(day, cfg)
    log(f"[daily] {day}: {len(matches)} matches -> {sel.home.name} vs {sel.away.name} "
        f"({sel.league}, {sel.tag}, strength {sel.strength[0]:.2f}/{sel.strength[1]:.2f})")

    pick = pick_battle(sel.home, sel.away, sel.strength, day_seed, cfg["director"])
    r = pick.result
    winner = (sel.home, sel.away)[r.winner]
    log(f"[daily] director: seed {r.seed}, {winner.name} wins, {r.duration:.1f}s, hp {r.hp}, score {pick.score:.2f}")

    card = MatchCard(
        league=sel.league, tag=sel.tag, home=sel.home, away=sel.away, form=sel.form,
        win_prob=None if sel.legends else pick.win_prob,
        cta="WHO WOULD WIN?" if sel.legends else ("WHO WINS TONIGHT?" if sel.tag == "TONIGHT" else "WHO WINS TODAY?"),
        sub_cta="COMMENT YOUR PICK" if sel.legends else "DROP YOUR SCORE IN THE COMMENTS",
        brand=cfg.get("brand", ""),
        record=rec if rec[1] >= 3 else None,
    )
    caption = build_caption(sel, r.winner, r.hp[r.winner], day_seed, cfg.get("hashtags_general", []),
                            win_prob=pick.win_prob, last=last, record=rec, brand=cfg.get("brand", ""))
    hist = history.add(hist, {
        "date": day.isoformat(), "league_code": sel.league_code, "event_id": sel.event_id,
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
        "date": day.isoformat(), "league": sel.league, "tag": sel.tag, "legends": sel.legends,
        "home": sel.home.name, "away": sel.away.name, "kickoff_utc": sel.kickoff.isoformat() if sel.kickoff else None,
        "strength": sel.strength, "win_prob": pick.win_prob, "seed": r.seed, "winner": winner.name,
        "fight_seconds": round(r.duration, 2), "hp": r.hp, "hits": r.hits, "parries": r.parries,
        "video": video.name if render else None,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[daily] wrote {out_dir}")
    return out_dir
