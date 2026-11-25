import json
from datetime import date, datetime, timezone
from pathlib import Path

from arena.caption import build_caption
from arena.config import load_config
from arena.data import history
from arena.data.fixtures import fetch_day
from arena.data.select_match import choose, choose_bonus, legends_clash
from arena.pipeline import run_daily

FIX = Path(__file__).parent / "fixtures"
DAY = date(2026, 11, 29)


def fake_fetch(url, params):
    if "eng.1/scoreboard" in url and params.get("dates") == "20261129":
        return json.loads((FIX / "eng1_scoreboard_20261129.json").read_text(encoding="utf-8"))
    if "eng.1/standings" in url:
        return json.loads((FIX / "eng1_standings.json").read_text(encoding="utf-8"))
    return {"events": []}


def _matches(cfg):
    return fetch_day(DAY, cfg["leagues"], 3, fake_fetch, log=lambda *_: None)


def test_bonus_picks_big_match_in_window_only():
    cfg = load_config()
    ms = _matches(cfg)
    big = next(m for m in ms if {"Arsenal", "Manchester City"} <= {m.home.name, m.away.name})
    before = big.kickoff.replace(hour=big.kickoff.hour - 2)
    sel = choose_bonus(ms, cfg, before)
    assert sel and sel.event_id == big.event_id
    # already posted today -> not picked again
    again = choose_bonus(ms, cfg, before, exclude={big.event_id})
    assert again is None or again.event_id != big.event_id
    # threshold respected
    strict = dict(cfg, schedule=dict(cfg.get("schedule", {}), bonus_min_score=999))
    assert choose_bonus(ms, strict, before) is None


def test_main_skips_started_and_posted_matches():
    cfg = load_config()
    ms = _matches(cfg)
    first = choose(ms, DAY, cfg)
    second = choose(ms, DAY, cfg, exclude={first.event_id})
    assert second.event_id != first.event_id
    late = datetime(2026, 11, 29, 23, 0, tzinfo=timezone.utc)
    assert choose(ms, DAY, cfg, now=late).legends  # everything already kicked off


def test_history_keeps_multiple_slots_per_day():
    e = []
    for slot in ("main", "early", "late"):
        e = history.add(e, {"date": "2026-11-29", "slot": slot, "event_id": slot})
    e = history.add(e, {"date": "2026-11-29", "slot": "main", "event_id": "main2"})
    assert [x["slot"] for x in e] == ["early", "main", "late"]
    assert [x["event_id"] for x in e if x["slot"] == "main"] == ["main2"]
    assert len(history.posted_on(e, DAY)) == 3


def test_bonus_slot_respects_daily_cap_and_skips_quietly(tmp_path):
    hp = tmp_path / "h.json"
    history.save([{"date": DAY.isoformat(), "slot": s, "event_id": s} for s in ("main", "early", "x")], hp)
    out = run_daily(DAY, tmp_path / "o", fake_fetch, render=False, log=lambda *_: None, history_path=hp,
                    slot="late", now=datetime(2026, 11, 29, 14, 0, tzinfo=timezone.utc))
    assert out is None


def test_bonus_then_main_never_duplicate(tmp_path):
    hp = tmp_path / "h.json"
    early = run_daily(DAY, tmp_path / "o", fake_fetch, render=False, log=lambda *_: None, history_path=hp,
                      slot="early", now=datetime(2026, 11, 29, 14, 0, tzinfo=timezone.utc))
    main = run_daily(DAY, tmp_path / "o", fake_fetch, render=False, log=lambda *_: None, history_path=hp,
                     slot="main")
    assert early is not None and main is not None and early != main
    ids = [e["event_id"] for e in history.load(hp)]
    assert len(ids) == len(set(ids)) == 2


def test_caption_has_few_targeted_hashtags():
    cfg = load_config()
    sel = legends_clash(DAY, cfg)
    cap = build_caption(sel, 0, 10, 1, cfg["hashtags_general"], max_tags=cfg["max_hashtags"])
    tags = [w for w in cap.split() if w.startswith("#")]
    assert 3 <= len(tags) <= 6
