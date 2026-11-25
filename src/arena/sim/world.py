"""Deterministic 2D battle simulation.

Two balls bounce inside a circular arena at constant speed. Each carries a
rotating weapon. Weapon touching the enemy ball = damage; weapon touching
weapon = parry (sparks, both spins reverse, knock-back). After a while the
arena shrinks so every fight ends.

Pure Python + math with a seeded RNG: the same seed always produces the
same battle on the same machine.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .weapons import WEAPONS, WeaponSpec

SIM_HZ = 120
DT = 1.0 / SIM_HZ

BALL_R = 64.0
GAP = 6.0
ARENA_CX, ARENA_CY = 540.0, 975.0
ARENA_R0 = 440.0
ARENA_RMIN = 270.0
SHRINK_START = 13.0
SHRINK_DUR = 7.0
BASE_SPEED = 520.0
STEER = 1.2             # rad/s the balls turn toward each other
HIT_COOLDOWN = 0.42
PARRY_COOLDOWN = 0.20
KNOCKBACK = 0.95        # extra speed fraction after being hit
MAX_HP = 100.0
MAX_TIME = 50.0
DAMAGE_SCALE = 1.5     # tuned so fights last ~16-23 s (Reels sweet spot)


@dataclass
class Event:
    t: float
    kind: str           # hit | parry | wall | bump | levelup | ko | shrink
    x: float
    y: float
    a: int = -1         # actor (attacker / fighter)
    b: int = -1         # victim
    value: float = 0.0  # damage
    combo: int = 0
    level: int = 0


@dataclass
class BattleResult:
    seed: int
    winner: int
    duration: float
    timeout: bool
    events: list[Event]
    states: list[tuple]        # one per sim step, see Battle._snapshot
    hp: tuple[float, float]
    hits: tuple[int, int]
    parries: int
    lead_changes: int
    min_hp_winner: float       # lowest HP the winner dropped to
    max_deficit_winner: float  # largest HP deficit the winner came back from


def _seg_point_dist(ax, ay, bx, by, px, py):
    abx, aby = bx - ax, by - ay
    L2 = abx * abx + aby * aby
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / L2))
    cx, cy = ax + abx * t, ay + aby * t
    return math.hypot(px - cx, py - cy), cx, cy


def _seg_seg_dist(p1x, p1y, q1x, q1y, p2x, p2y, q2x, q2y):
    """Distance between two segments + midpoint of the closest points."""
    best = None
    for (d, cx, cy), (ox, oy) in (
        (_seg_point_dist(p2x, p2y, q2x, q2y, p1x, p1y), (p1x, p1y)),
        (_seg_point_dist(p2x, p2y, q2x, q2y, q1x, q1y), (q1x, q1y)),
        (_seg_point_dist(p1x, p1y, q1x, q1y, p2x, p2y), (p2x, p2y)),
        (_seg_point_dist(p1x, p1y, q1x, q1y, q2x, q2y), (q2x, q2y)),
    ):
        if best is None or d < best[0]:
            best = (d, (cx + ox) / 2, (cy + oy) / 2)
    # Proper intersection check
    d1x, d1y = q1x - p1x, q1y - p1y
    d2x, d2y = q2x - p2x, q2y - p2y
    den = d1x * d2y - d1y * d2x
    if den != 0:
        s = ((p2x - p1x) * d2y - (p2y - p1y) * d2x) / den
        u = ((p2x - p1x) * d1y - (p2y - p1y) * d1x) / den
        if 0 <= s <= 1 and 0 <= u <= 1:
            return 0.0, p1x + d1x * s, p1y + d1y * s
    return best


class Fighter:
    def __init__(self, idx: int, spec: WeaponSpec, power: float, x, y, heading, angle, spin_dir):
        self.idx = idx
        self.spec = spec
        self.power = power
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(heading) * BASE_SPEED, math.sin(heading) * BASE_SPEED
        self.angle = angle
        self.spin_dir = spin_dir
        self.length = spec.length
        self.spin = spec.spin
        self.damage = spec.damage
        self.hp = MAX_HP
        self.boost = 0.0
        self.hit_cd = 0.0
        self.parry_cd = 0.0
        self.level = 0
        self.hits = 0
        self.combo = 0
        self.roll = 0.0
        self.last_wall = -1.0

    def blades(self):
        r0 = BALL_R + GAP
        out = []
        for k in range(self.spec.blades):
            a = self.angle + k * math.pi
            ux, uy = math.cos(a), math.sin(a)
            out.append((self.x + ux * r0, self.y + uy * r0,
                        self.x + ux * (r0 + self.length), self.y + uy * (r0 + self.length)))
        return out

    def escalate(self):
        s = self.spec
        self.level += 1
        self.length = min(s.max_length, self.length + s.grow_length)
        self.spin = min(s.max_spin, self.spin + s.grow_spin)
        self.damage += s.grow_damage


class Battle:
    def __init__(self, seed: int, weapons: tuple[str, str], powers: tuple[float, float] = (1.0, 1.0),
                 record: bool = True):
        self.seed = seed
        self.rng = random.Random(seed)
        self.record = record
        rng = self.rng
        side = rng.choice([-1, 1])
        h0 = rng.uniform(-math.pi, math.pi)
        h1 = rng.uniform(-math.pi, math.pi)
        dx = 200.0 * side
        oy = rng.uniform(-80, 80)
        self.f = [
            Fighter(0, WEAPONS[weapons[0]], powers[0], ARENA_CX - dx, ARENA_CY + oy, h0,
                    rng.uniform(0, 2 * math.pi), rng.choice([-1, 1])),
            Fighter(1, WEAPONS[weapons[1]], powers[1], ARENA_CX + dx, ARENA_CY - oy, h1,
                    rng.uniform(0, 2 * math.pi), rng.choice([-1, 1])),
        ]
        self.t = 0.0
        self.R = ARENA_R0
        self.events: list[Event] = []
        self.states: list[tuple] = []
        self.parries = 0
        self.lead = 0
        self.lead_changes = 0
        self.min_hp = [MAX_HP, MAX_HP]
        self.max_deficit = [0.0, 0.0]
        self.shrink_announced = False

    # ---- one simulation step -------------------------------------------------
    def _snapshot(self):
        a, b = self.f
        self.states.append((self.R,
                            a.x, a.y, a.angle, a.length, a.hp, a.roll, a.level,
                            b.x, b.y, b.angle, b.length, b.hp, b.roll, b.level))

    def _move(self, f: Fighter, other: Fighter, dt: float):
        # Steer a little toward the opponent so fights stay engaged.
        desired = math.atan2(other.y - f.y, other.x - f.x)
        heading = math.atan2(f.vy, f.vx)
        diff = (desired - heading + math.pi) % (2 * math.pi) - math.pi
        heading += max(-STEER * dt, min(STEER * dt, diff))
        speed = BASE_SPEED * (1 + f.boost) * (1 + 0.15 * min(1.0, max(0.0, (self.t - SHRINK_START) / SHRINK_DUR)))
        f.vx, f.vy = math.cos(heading) * speed, math.sin(heading) * speed
        f.x += f.vx * dt
        f.y += f.vy * dt
        f.boost *= math.exp(-dt / 0.35)
        f.angle += f.spin * f.spin_dir * dt
        f.roll += speed * dt / BALL_R * 0.35 * (1 if f.idx == 0 else -1)
        f.hit_cd = max(0.0, f.hit_cd - dt)
        f.parry_cd = max(0.0, f.parry_cd - dt)

    def _walls(self, f: Fighter):
        dx, dy = f.x - ARENA_CX, f.y - ARENA_CY
        d = math.hypot(dx, dy)
        limit = self.R - BALL_R
        if d > limit and d > 0:
            nx, ny = dx / d, dy / d
            vn = f.vx * nx + f.vy * ny
            if vn > 0:
                f.vx -= 2 * vn * nx
                f.vy -= 2 * vn * ny
                # tiny random deflection avoids repeating orbits
                ang = self.rng.uniform(-0.18, 0.18)
                c, s = math.cos(ang), math.sin(ang)
                f.vx, f.vy = f.vx * c - f.vy * s, f.vx * s + f.vy * c
                if self.t - f.last_wall > 0.08:
                    self.events.append(Event(self.t, "wall", ARENA_CX + nx * self.R, ARENA_CY + ny * self.R, a=f.idx))
                    f.last_wall = self.t
            f.x, f.y = ARENA_CX + nx * limit, ARENA_CY + ny * limit

    def _bodies(self):
        a, b = self.f
        dx, dy = b.x - a.x, b.y - a.y
        d = math.hypot(dx, dy)
        if 0 < d < 2 * BALL_R:
            nx, ny = dx / d, dy / d
            van = a.vx * nx + a.vy * ny
            vbn = b.vx * nx + b.vy * ny
            if van - vbn > 0:
                a.vx += (vbn - van) * nx
                a.vy += (vbn - van) * ny
                b.vx += (van - vbn) * nx
                b.vy += (van - vbn) * ny
                self.events.append(Event(self.t, "bump", a.x + nx * BALL_R, a.y + ny * BALL_R))
            overlap = 2 * BALL_R - d
            a.x -= nx * overlap / 2
            a.y -= ny * overlap / 2
            b.x += nx * overlap / 2
            b.y += ny * overlap / 2

    def _parry(self) -> bool:
        a, b = self.f
        if a.parry_cd > 0 or b.parry_cd > 0:
            return False
        for sa in a.blades():
            for sb in b.blades():
                d, cx, cy = _seg_seg_dist(*sa, *sb)
                reach = a.spec.width + b.spec.width
                hit = d < reach
                # heads (hammer/axe) are bigger at the tip
                if not hit and a.spec.head:
                    dh, _, _ = _seg_point_dist(*sb, sa[2], sa[3])
                    if dh < a.spec.head + b.spec.width:
                        hit, cx, cy = True, sa[2], sa[3]
                if not hit and b.spec.head:
                    dh, _, _ = _seg_point_dist(*sa, sb[2], sb[3])
                    if dh < b.spec.head + a.spec.width:
                        hit, cx, cy = True, sb[2], sb[3]
                if hit:
                    a.spin_dir *= -1
                    b.spin_dir *= -1
                    # push apart
                    dx, dy = b.x - a.x, b.y - a.y
                    d2 = math.hypot(dx, dy) or 1.0
                    nx, ny = dx / d2, dy / d2
                    a.vx, a.vy = -nx * BASE_SPEED, -ny * BASE_SPEED
                    b.vx, b.vy = nx * BASE_SPEED, ny * BASE_SPEED
                    a.boost = max(a.boost, 0.45)
                    b.boost = max(b.boost, 0.45)
                    a.parry_cd = b.parry_cd = PARRY_COOLDOWN
                    # a parry also stops immediate follow-up hits
                    a.hit_cd = max(a.hit_cd, 0.12)
                    b.hit_cd = max(b.hit_cd, 0.12)
                    self.parries += 1
                    self.events.append(Event(self.t, "parry", cx, cy))
                    return True
        return False

    def _try_hit(self, att: Fighter, vic: Fighter):
        if att.hit_cd > 0:
            return
        for seg in att.blades():
            d, cx, cy = _seg_point_dist(*seg, vic.x, vic.y)
            touching = d < BALL_R + att.spec.width
            if not touching and att.spec.head:
                touching = math.hypot(seg[2] - vic.x, seg[3] - vic.y) < BALL_R + att.spec.head
                if touching:
                    cx, cy = seg[2], seg[3]
            if not touching:
                continue
            dmg = max(1, round(att.damage * att.power * DAMAGE_SCALE))
            vic.hp = max(0.0, vic.hp - dmg)
            att.hits += 1
            att.combo += 1
            vic.combo = 0
            att.hit_cd = HIT_COOLDOWN
            att.spin_dir *= -1
            # knock the victim away from the attacker
            dx, dy = vic.x - att.x, vic.y - att.y
            dd = math.hypot(dx, dy) or 1.0
            vic.vx, vic.vy = dx / dd * BASE_SPEED, dy / dd * BASE_SPEED
            vic.boost = KNOCKBACK
            # contact point on the victim's surface
            px, py = cx - vic.x, cy - vic.y
            pd = math.hypot(px, py) or 1.0
            hx, hy = vic.x + px / pd * BALL_R, vic.y + py / pd * BALL_R
            self.events.append(Event(self.t, "hit", hx, hy, a=att.idx, b=vic.idx, value=dmg,
                                     combo=att.combo, level=att.level))
            att.escalate()
            self.events.append(Event(self.t, "levelup", att.x, att.y, a=att.idx, level=att.level))
            return

    def _track_drama(self):
        a, b = self.f
        for i, f in enumerate(self.f):
            self.min_hp[i] = min(self.min_hp[i], f.hp)
        self.max_deficit[0] = max(self.max_deficit[0], b.hp - a.hp)
        self.max_deficit[1] = max(self.max_deficit[1], a.hp - b.hp)
        lead = 0 if a.hp == b.hp else (1 if a.hp > b.hp else -1)
        if lead != 0 and self.lead != 0 and lead != self.lead:
            self.lead_changes += 1
        if lead != 0:
            self.lead = lead

    def step(self):
        a, b = self.f
        dt = DT
        self.t += dt
        if self.t > SHRINK_START:
            if not self.shrink_announced:
                self.shrink_announced = True
                self.events.append(Event(self.t, "shrink", ARENA_CX, ARENA_CY))
            k = min(1.0, (self.t - SHRINK_START) / SHRINK_DUR)
            self.R = ARENA_R0 + (ARENA_RMIN - ARENA_R0) * (k * k * (3 - 2 * k))
        self._move(a, b, dt)
        self._move(b, a, dt)
        self._walls(a)
        self._walls(b)
        self._bodies()
        if not self._parry():
            self._try_hit(a, b)
            self._try_hit(b, a)
        self._track_drama()
        if self.record:
            self._snapshot()

    def run(self) -> BattleResult:
        if self.record:
            self._snapshot()
        a, b = self.f
        timeout = False
        while a.hp > 0 and b.hp > 0:
            self.step()
            if self.t >= MAX_TIME:
                timeout = True
                break
        if a.hp == b.hp:
            winner = 0 if a.hits >= b.hits else 1
        else:
            winner = 0 if a.hp > b.hp else 1
        loser = self.f[1 - winner]
        if not timeout:
            self.events.append(Event(self.t, "ko", loser.x, loser.y, a=winner, b=1 - winner))
        return BattleResult(
            seed=self.seed, winner=winner, duration=self.t, timeout=timeout,
            events=self.events, states=self.states, hp=(a.hp, b.hp), hits=(a.hits, b.hits),
            parries=self.parries, lead_changes=self.lead_changes,
            min_hp_winner=self.min_hp[winner], max_deficit_winner=self.max_deficit[winner],
        )


def simulate(seed: int, weapons: tuple[str, str], powers=(1.0, 1.0), record=True) -> BattleResult:
    return Battle(seed, weapons, powers, record).run()
