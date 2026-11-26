import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from arena.config import load_config
from arena.data import history
from arena.report import build_report, refresh_insights
from arena.variants import resolve, variant_for

FIX = Path(__file__).parent / "fixtures"


def test_rotation_cycles_all_drafts_and_slots_differ():
    cfg = load_config()
    rot = cfg["variants"]["rotation"]
    d0 = date(2026, 12, 1)
    seen = {variant_for(d0 + timedelta(days=i), "main", cfg) for i in range(len(rot))}
    assert seen == set(rot)
    assert len({variant_for(d0, s, cfg) for s in ("main", "early", "late")}) == 3


def test_variant_merges_over_base_config():
    cfg = load_config()
    v = resolve("neon", cfg)
    assert v.video["intro_seconds"] == 0 and v.video["width"] == cfg["video"]["width"]
    assert v.audio["bpm"] == 140 and v.audio["sample_rate"] == cfg["audio"]["sample_rate"]
    assert v.tuning["damage_scale"] > 1.5
    assert resolve("classic", cfg).video["intro_seconds"] == cfg["video"]["intro_seconds"]


def test_cold_open_draft_is_short_with_early_clash():
    from arena.data.teams import resolve_team
    from arena.director import pick_battle
    cfg = load_config()
    v = resolve("coldopen", cfg)
    pick = pick_battle(resolve_team("Galatasaray"), resolve_team("Fenerbahce"), (0.7, 0.6), 20261126,
                       dict(v.director, seeds=80), workers=1, tuning=v.tuning)
    r = pick.result
    assert r.duration <= v.director["target_max_seconds"] + 4
    first = min(e.t for e in r.events if e.kind in ("hit", "parry"))
    assert first < 3.0


class FakeIG:
    def __init__(self):
        self.calls = []

    def insights(self, mid, metrics):
        self.calls.append(mid)
        return {"views": 1000 if mid == "m1" else 400, "likes": 50, "comments": 5, "shares": 3, "saved": 2,
                "ig_reels_avg_watch_time": 9000 if mid == "m1" else 5000}


def test_report_compares_drafts():
    cfg = load_config()
    now = datetime(2026, 12, 10, tzinfo=timezone.utc)
    hist = []
    for i, (v, mid) in enumerate([("classic", "m2"), ("coldopen", "m1"), ("classic", "m3")]):
        hist.append({"date": f"2026-12-0{i + 1}", "slot": "main", "variant": v, "media_id": mid,
                     "home": "A", "away": "B", "outcome": "hit", "posted_at": f"2026-12-0{i + 1}T16:00:00+00:00"})
    ig = FakeIG()
    ins = refresh_insights(ig, hist, {}, now, log=lambda *_: None)
    assert set(ig.calls) == {"m1", "m2", "m3"}
    md = build_report(hist, ins, cfg, now)
    assert "B · Cold open" in md and "A · Classic" in md
    assert "9.0 s" in md  # cold open average watch time
    # posts older than 8 days are not re-fetched once stored
    ig2 = FakeIG()
    refresh_insights(ig2, hist, ins, now + timedelta(days=30), log=lambda *_: None)
    assert ig2.calls == []


def test_plan_lists_every_slot(monkeypatch, tmp_path):
    from arena import pipeline, plan

    def fetch_day(day, leagues, tz, fetch=None, log=None):
        from arena.data.fixtures import fetch_day as real
        def fake(url, params):
            if "eng.1/scoreboard" in url and params.get("dates") == "20261129":
                return json.loads((FIX / "eng1_scoreboard_20261129.json").read_text(encoding="utf-8"))
            if "eng.1/standings" in url:
                return json.loads((FIX / "eng1_standings.json").read_text(encoding="utf-8"))
            return {"events": []}
        return real(day, leagues, tz, fake, lambda *_: None)

    monkeypatch.setattr(pipeline, "fetch_day", fetch_day)
    monkeypatch.setattr(history, "HISTORY_PATH", tmp_path / "none.json")
    cfg = load_config()
    monkeypatch.setattr(pipeline, "load_config", lambda: dict(cfg, director=dict(cfg["director"], seeds=20),
                        variants=dict(cfg["variants"], rotation=["classic"])))
    md = plan.build_plan(date(2026, 11, 29))
    assert "| early |" in md and "| main |" in md and "| late |" in md
    assert "Arsenal vs Man City" in md
