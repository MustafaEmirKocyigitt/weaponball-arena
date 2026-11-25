import json
from datetime import date
from pathlib import Path

import pytest

from arena.caption import build_caption
from arena.config import load_config
from arena.data.fixtures import fetch_day
from arena.data.select_match import choose, legends_clash
from arena.data.stats import form_score, strength
from arena.data.teams import color_distance, normalize, resolve_clash, resolve_team
from arena.director import drama_score, pick_battle, win_probability
from arena.render.timeline import build_timeline
from arena.sim.world import MAX_TIME, simulate

FIX = Path(__file__).parent / "fixtures"


def fake_fetch(url, params):
    if "eng.1/scoreboard" in url and params.get("dates") == "20261129":
        return json.loads((FIX / "eng1_scoreboard_20261129.json").read_text(encoding="utf-8"))
    if "eng.1/standings" in url:
        return json.loads((FIX / "eng1_standings.json").read_text(encoding="utf-8"))
    return {"events": []}


# ---------------------------------------------------------------- simulation
def test_simulation_is_deterministic():
    a = simulate(123, ("sword", "axe"))
    b = simulate(123, ("sword", "axe"))
    assert a.winner == b.winner
    assert a.duration == b.duration
    assert [(e.kind, e.t, e.value) for e in a.events] == [(e.kind, e.t, e.value) for e in b.events]
    assert a.states[-1] == b.states[-1]


def test_different_seeds_differ():
    a = simulate(1, ("spear", "hammer"), record=False)
    b = simulate(2, ("spear", "hammer"), record=False)
    assert (a.duration, a.hp) != (b.duration, b.hp)


def test_battles_end_with_ko():
    for s in range(15):
        r = simulate(s, ("daggers", "sword"), record=False)
        assert r.duration <= MAX_TIME
        if not r.timeout:
            assert min(r.hp) == 0
            assert any(e.kind == "ko" for e in r.events)


# ---------------------------------------------------------------- teams
def test_normalize_and_aliases():
    assert normalize("Fenerbahçe") == "fenerbahce"
    assert normalize("Beşiktaş JK") == "besiktas jk"
    assert resolve_team("Beşiktaş JK").short == "BJK"
    assert resolve_team("Bayern Munich").short == "FCB"
    unknown = resolve_team("Some Town FC", "STF", "123456", "ffffff")
    assert unknown.short == "STF" and unknown.primary == (0x12, 0x34, 0x56)


def test_color_clash_is_resolved():
    h, a = resolve_clash(resolve_team("Liverpool"), resolve_team("Arsenal"))  # both red
    assert color_distance(h.primary, a.primary) >= 160


# ---------------------------------------------------------------- data / selection
def test_form_and_strength():
    assert form_score("WWWWW") == pytest.approx(1.0)
    assert form_score("LLLLL") == 0.0
    assert form_score("") is None
    top = strength({"rank": 1, "gp": 12, "pts": 30, "gd": 20, "n": 20}, "WWWDW")
    bottom = strength({"rank": 20, "gp": 12, "pts": 5, "gd": -18, "n": 20}, "LLDLL")
    assert 0 <= bottom < 0.3 < 0.7 < top <= 1
    assert strength(None, "") == 0.5


def test_choose_match_from_real_fixture():
    cfg = load_config()
    matches = fetch_day(date(2026, 11, 29), cfg["leagues"], 3, fake_fetch, log=lambda *_: None)
    assert matches, "fixture should contain matches"
    sel = choose(matches, date(2026, 11, 29), cfg)
    assert not sel.legends
    assert sel.league == "PREMIER LEAGUE"
    assert 0 <= sel.strength[0] <= 1 and 0 <= sel.strength[1] <= 1
    assert sel.tag in ("TONIGHT", "TODAY")


def test_legends_fallback_when_no_matches():
    cfg = load_config()
    sel = choose([], date(2026, 12, 1), cfg)
    assert sel.legends and sel.tag == "LEGENDS CLASH"
    assert sel == legends_clash(date(2026, 12, 1), cfg)


# ---------------------------------------------------------------- director
def test_win_probability_direction():
    assert win_probability(0.9, 0.3) > 0.7
    assert win_probability(0.3, 0.9) < 0.3
    assert 0.45 < win_probability(0.5, 0.5) < 0.6


def test_director_picks_favourite_in_target_window():
    cfg = dict(load_config()["director"], seeds=60)
    home, away = resolve_team("Real Madrid"), resolve_team("Alaves")
    pick = pick_battle(home, away, (0.92, 0.45), 20261128, cfg, workers=1)
    assert pick.predicted == 0
    assert pick.result.winner == 0
    assert cfg["target_min_seconds"] - 3 <= pick.result.duration <= cfg["target_max_seconds"] + 3
    again = pick_battle(home, away, (0.92, 0.45), 20261128, cfg, workers=1)
    assert again.result.seed == pick.result.seed


def test_drama_score_rejects_wrong_winner():
    r = simulate(5, ("sword", "sword"), record=False)
    assert drama_score(r, 1 - r.winner, 20, 50) is None


# ---------------------------------------------------------------- timeline / caption
def test_timeline_maps_every_fight_event():
    r = simulate(7, ("sword", "spear"))
    tl = build_timeline(r, 60, 2.0, 1.0, 3.0)
    mapped = sum(len(v) for v in tl.events_at.values())
    assert mapped == len(r.events)
    assert tl.ko_frame > tl.fight_start
    assert tl.frames[-1].phase == "outro"
    assert tl.duration > r.duration


def test_caption_has_names_and_hashtags():
    cfg = load_config()
    sel = legends_clash(date(2026, 12, 1), cfg)
    cap = build_caption(sel, 0, 12.0, 20261201, cfg["hashtags_general"])
    assert sel.home.name in cap and sel.away.name in cap
    assert "#football" in cap
    assert cap == build_caption(sel, 0, 12.0, 20261201, cfg["hashtags_general"])
