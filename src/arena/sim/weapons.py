"""Weapon definitions.

Every weapon is a rotating capsule (a segment with thickness) attached to
the ball, optionally with a round "head" at the tip (hammer / axe).
Each successful hit escalates the weapon so fights get faster and end on
their own.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeaponSpec:
    kind: str
    length: float        # blade length (px) starting just outside the ball
    width: float         # collision half-thickness of the blade
    head: float          # collision radius of a head at the tip (0 = none)
    damage: float
    spin: float          # rad/s
    blades: int          # 1, or 2 for twin blades on opposite sides
    grow_length: float   # per hit
    grow_spin: float     # per hit
    grow_damage: float   # per hit
    max_length: float
    max_spin: float


WEAPONS: dict[str, WeaponSpec] = {
    "sword":   WeaponSpec("sword",   112, 9, 0,  11.5, 3.1, 1, 9,  0.14, 0.40, 230, 6.8),
    "spear":   WeaponSpec("spear",   172, 7, 0,  12.5, 2.7, 1, 11, 0.13, 0.40, 290, 6.2),
    "hammer":  WeaponSpec("hammer",   86, 6, 22, 13.0, 2.4, 1, 6,  0.22, 0.45, 170, 6.6),
    "daggers": WeaponSpec("daggers",  62, 7, 0,  3.6, 2.8, 2, 4,  0.12, 0.15, 140, 7.0),
    "axe":     WeaponSpec("axe",     100, 7, 18, 12.5, 2.7, 1, 7,  0.18, 0.40, 190, 6.6),
}

WEAPON_ORDER = ["sword", "spear", "hammer", "daggers", "axe"]
