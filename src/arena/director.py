"""The director: simulate many seeds without rendering, keep the most dramatic.

- Team strength (0..1, from standings + form) becomes a win probability and
  a small damage bonus for the favourite.
- The predicted winner is the favourite, unless the two sides are nearly
  equal, in which case a deterministic coin flip (seeded by the day) decides.
- Among battles where the predicted winner wins, we prefer fights of the
  target length with a close finish, comebacks and lead changes.
"""
from __future__ import annotations

import math
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from .data.teams import Team
from .sim.world import BattleResult, simulate


@dataclass
class Pick:
    result: BattleResult
    win_prob: tuple[float, float]
    predicted: int
    powers: tuple[float, float]
    score: float
    candidates: int


def win_probability(s_home: float, s_away: float, home_adv: float = 0.04) -> float:
    """Probability that home wins, from strengths in 0..1."""
    x = (s_home - s_away) * 4.5 + home_adv * 4.5
    p = 1 / (1 + math.exp(-x))
    return min(0.85, max(0.15, p))


def powers_for(p_home: float, spread: float) -> tuple[float, float]:
    edge = abs(p_home - 0.5) * 2  # 0..1
    bonus = 1 + spread * edge
    return (bonus, 1.0) if p_home >= 0.5 else (1.0, bonus)


def drama_score(r: BattleResult, want: int, tmin: float, tmax: float) -> float | None:
    if r.timeout or r.winner != want:
        return None
    s = 0.0
    if tmin <= r.duration <= tmax:
        s += 4
    else:
        s -= abs(r.duration - (tmin if r.duration < tmin else tmax)) * 0.6
    hp_w = r.hp[r.winner]
    s += 3 * (1 - hp_w / 100)              # close finish
    if 4 <= hp_w <= 35:
        s += 1.5
    s += min(r.max_deficit_winner, 45) / 15  # comeback
    s += 0.6 * min(r.lead_changes, 4)
    s += 0.04 * min(r.parries, 25)
    if min(r.hits) < 3:                     # one-sided beatdowns are boring
        s -= 3
    return s


def _sim_job(args):
    seed, weapons, powers, tuning = args
    r = simulate(seed, weapons, powers, record=False, **tuning)
    return seed, r


def pick_battle(home: Team, away: Team, strength: tuple[float, float], day_seed: int,
                director_cfg: dict, workers: int | None = None, tuning: dict | None = None) -> Pick:
    """`tuning` passes sim overrides (damage_scale, shrink_start, shrink_dur) for mini battles."""
    tuning = tuning or {}
    n = int(director_cfg.get("seeds", 300))
    tmin = float(director_cfg.get("target_min_seconds", 26))
    tmax = float(director_cfg.get("target_max_seconds", 44))
    threshold = float(director_cfg.get("coin_flip_threshold", 0.06))
    spread = float(director_cfg.get("power_spread", 0.10))

    p_home = win_probability(*strength)
    rng = random.Random(day_seed)
    if abs(p_home - 0.5) < threshold:
        predicted = rng.choice([0, 1])
    else:
        predicted = 0 if p_home > 0.5 else 1
    powers = powers_for(p_home, spread)
    weapons = (home.weapon, away.weapon)

    base = (day_seed % 100000) * 1000
    jobs = [(base + i, weapons, powers, tuning) for i in range(n)]
    if workers == 1:
        results = [_sim_job(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_sim_job, jobs, chunksize=max(1, n // 32)))

    best_seed, best_score = None, -1e9
    for seed, r in results:
        sc = drama_score(r, predicted, tmin, tmax)
        if sc is not None and sc > best_score:
            best_seed, best_score = seed, sc
    if best_seed is None:  # extremely unlikely: fall back to any non-timeout fight
        for seed, r in results:
            if not r.timeout:
                best_seed, best_score, predicted = seed, 0.0, r.winner
                break
        else:
            best_seed = results[0][0]
            predicted = results[0][1].winner
    final = simulate(best_seed, weapons, powers, record=True, **tuning)
    return Pick(result=final, win_prob=(p_home, 1 - p_home), predicted=predicted, powers=powers,
                score=best_score, candidates=n)
