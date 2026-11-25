"""Team identity: display name, short label, colors and weapon."""
from __future__ import annotations

import colorsys
import hashlib
import unicodedata
from dataclasses import dataclass, replace

from ..config import load_team_overrides
from ..sim.weapons import WEAPON_ORDER

Color = tuple[int, int, int]


def normalize(name: str) -> str:
    """'Fenerbahçe SK' -> 'fenerbahce sk' (lowercase, no accents, single spaces)."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_ = ascii_.replace("ı", "i").replace("İ", "i")
    return " ".join(ascii_.lower().replace(".", " ").split())


def hex_to_rgb(value: str | None) -> Color | None:
    if not value:
        return None
    v = value.strip().lstrip("#")
    if len(v) != 6:
        return None
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        return None


def luminance(c: Color) -> float:
    r, g, b = (x / 255 for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def color_distance(a: Color, b: Color) -> float:
    # Weighted RGB distance, roughly perceptual, 0..~765
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return ((2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db) ** 0.5


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _hash_color(text: str, offset: float = 0.0) -> Color:
    h = ((_stable_hash(text) % 360) / 360 + offset) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.9)
    return (int(r * 255), int(g * 255), int(b * 255))


@dataclass(frozen=True)
class Team:
    name: str           # display name, international spelling
    short: str          # 2-4 letter label on the ball
    primary: Color
    secondary: Color
    weapon: str
    big: bool = False
    key: str = ""       # normalized lookup key

    @property
    def hashtag(self) -> str:
        return "".join(ch for ch in normalize(self.name) if ch.isalnum())


def _lookup(name: str) -> tuple[str, dict] | None:
    overrides = load_team_overrides()
    key = normalize(name)
    if key in overrides:
        return key, overrides[key]
    for k, v in overrides.items():
        if key in (normalize(a) for a in v.get("aliases", [])):
            return k, v
    # Loose match: ESPN sometimes adds suffixes like "FC" / "SK" / "JK"
    stripped = " ".join(w for w in key.split() if w not in {"fc", "sk", "jk", "afc", "cf", "ac", "as", "ssc"})
    for k, v in overrides.items():
        cands = [k] + [normalize(a) for a in v.get("aliases", [])]
        if stripped and stripped in cands:
            return k, v
    return None


def default_weapon(key: str) -> str:
    return WEAPON_ORDER[_stable_hash(key) % len(WEAPON_ORDER)]


def resolve_team(
    name: str,
    abbreviation: str | None = None,
    color: str | None = None,
    alt_color: str | None = None,
) -> Team:
    """Build a Team from our overrides, falling back to ESPN data, then to hashing."""
    found = _lookup(name)
    if found:
        key, o = found
        return Team(
            name=o.get("name", name),
            short=o.get("short") or (abbreviation or key[:3]).upper(),
            primary=hex_to_rgb(o.get("primary")) or hex_to_rgb(color) or _hash_color(key),
            secondary=hex_to_rgb(o.get("secondary")) or hex_to_rgb(alt_color) or (255, 255, 255),
            weapon=o.get("weapon") or default_weapon(key),
            big=bool(o.get("big", False)),
            key=key,
        )
    key = normalize(name)
    primary = hex_to_rgb(color) or _hash_color(key)
    secondary = hex_to_rgb(alt_color) or _hash_color(key, 0.5)
    if color_distance(primary, secondary) < 120:
        secondary = (255, 255, 255) if luminance(primary) < 0.6 else (20, 20, 20)
    short = (abbreviation or "".join(w[0] for w in key.split()[:3]) or key[:3]).upper()[:4]
    return Team(name=name, short=short, primary=primary, secondary=secondary,
                weapon=default_weapon(key), big=False, key=key)


def resolve_clash(home: Team, away: Team) -> tuple[Team, Team]:
    """Make sure the two balls are easy to tell apart.

    If the primaries are too close, the away side swaps to its secondary
    color. If that is still too close, it gets a hashed contrasting color.
    """
    if color_distance(home.primary, away.primary) >= 160:
        return home, away
    swapped = replace(away, primary=away.secondary, secondary=away.primary)
    if color_distance(home.primary, swapped.primary) >= 160:
        return home, swapped
    for i in range(1, 12):
        cand = _hash_color(away.key or away.name, i / 12)
        if color_distance(home.primary, cand) >= 200:
            return home, replace(away, primary=cand)
    return home, replace(away, primary=(255, 255, 255) if luminance(home.primary) < 0.5 else (30, 30, 30))


def readable_on_dark(c: Color, fallback: Color = (255, 255, 255)) -> Color:
    """Color suitable for text/bars on a near-black background."""
    if luminance(c) > 0.18:
        return c
    if max(c) - min(c) < 40:  # near-black / grey: no hue worth keeping
        return fallback
    # brighten saturated dark colors (e.g. dark red) instead of swapping them
    for k in range(1, 10):
        b = tuple(int(x + (255 - x) * k * 0.06) for x in c)
        b = tuple(min(255, int(x * (1 + k * 0.12))) for x in b)
        if luminance(b) > 0.18:
            return b
    return fallback
