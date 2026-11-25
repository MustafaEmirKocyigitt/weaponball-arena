import json
from datetime import date
from pathlib import Path

from arena.caption import MATCH_TEMPLATES, build_caption, record_line
from arena.config import load_config
from arena.data import history
from arena.data.select_match import legends_clash
from arena.pipeline import run_daily

FIX = Path(__file__).parent / "fixtures"


def _scoreboard(event_id, home, away, completed=True, state="STATUS_FULL_TIME"):
    return {"events": [{"id": event_id, "competitions": [{
        "status": {"type": {"completed": completed, "name": state}},
        "competitors": [{"homeAway": "home", "score": str(home)}, {"homeAway": "away", "score": str(away)}],
    }]}]}


def _entry(day, side=0, event="E1"):
    return {"date": day, "league_code": "eng.1", "event_id": event, "home": "Arsenal", "away": "Man City",
            "home_short": "ARS", "away_short": "MCI", "predicted": "Arsenal" if side == 0 else "Man City",
            "predicted_side": side, "legends": False, "outcome": None}


def test_resolve_hit_miss_draw():
    for (h, a, side), want in {(2, 1, 0): "hit", (2, 1, 1): "miss", (1, 1, 0): "draw"}.items():
        entries = [_entry("2026-11-29", side)]
        history.resolve(entries, date(2026, 11, 30), lambda u, p: _scoreboard("E1", h, a), log=lambda *_: None)
        assert entries[0]["outcome"] == want
        assert entries[0]["score"] == f"{h}-{a}"


def test_unfinished_match_stays_open_then_voids():
    entries = [_entry("2026-11-29")]
    sb = lambda u, p: _scoreboard("E1", 0, 0, completed=False, state="STATUS_IN_PROGRESS")
    history.resolve(entries, date(2026, 11, 30), sb, log=lambda *_: None)
    assert entries[0]["outcome"] is None
    history.resolve(entries, date(2026, 12, 6), sb, log=lambda *_: None)
    assert entries[0]["outcome"] == "void"


def test_record_and_last_call():
    e = [dict(_entry("2026-11-27"), outcome="hit", score="2-0"),
         dict(_entry("2026-11-28"), outcome="miss", score="0-1"),
         dict(_entry("2026-11-29"), outcome="hit", score="3-1")]
    assert history.record(e) == (2, 3)
    assert history.last_call(e, date(2026, 11, 30))["date"] == "2026-11-29"
    assert history.last_call(e, date(2026, 12, 9)) is None
    line = record_line(history.last_call(e, date(2026, 11, 30)), history.record(e))
    assert "✅" in line and "ARS 3-1 MCI" in line and "2/3" in line


def test_caption_variety_and_brand():
    cfg = load_config()
    sel = legends_clash(date(2026, 12, 1), cfg)
    sel.legends = False
    caps = {build_caption(sel, 0, 10, 20261200 + d, cfg["hashtags_general"]).split("\n")[0] for d in range(1, 15)}
    assert len(caps) >= 8, "consecutive days should rarely repeat"
    cap = build_caption(sel, 0, 10, 20261201, [], brand="@weaponball.fc")
    assert "@weaponball.fc" in cap
    assert len(MATCH_TEMPLATES) >= 20


def test_daily_pipeline_records_prediction(tmp_path):
    def fetch(url, params):
        if "eng.1/scoreboard" in url and params.get("dates") == "20261129":
            return json.loads((FIX / "eng1_scoreboard_20261129.json").read_text(encoding="utf-8"))
        if "eng.1/standings" in url:
            return json.loads((FIX / "eng1_standings.json").read_text(encoding="utf-8"))
        return {"events": []}

    hp = tmp_path / "history.json"
    out = run_daily(date(2026, 11, 29), tmp_path / "out", fetch, render=False, log=lambda *_: None, history_path=hp)
    entries = history.load(hp)
    assert len(entries) == 1 and entries[0]["event_id"] and entries[0]["league_code"] == "eng.1"
    assert (out / "caption.txt").read_text(encoding="utf-8")
