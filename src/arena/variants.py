"""Video drafts for A/B testing (config.yaml -> variants)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SLOT_OFFSET = {"main": 0, "early": 1, "late": 2}


@dataclass
class Variant:
    name: str
    label: str
    video: dict
    audio: dict
    director: dict
    tuning: dict = field(default_factory=dict)


def variant_for(day: date, slot: str, cfg: dict) -> str:
    """Rotate drafts day by day; bonus slots are offset so one day shows different drafts."""
    rot = cfg.get("variants", {}).get("rotation") or ["classic"]
    return rot[(day.toordinal() + SLOT_OFFSET.get(slot, 0)) % len(rot)]


def resolve(name: str, cfg: dict) -> Variant:
    defs = cfg.get("variants", {}).get("defs", {})
    d = defs.get(name)
    if d is None:
        raise ValueError(f"unknown variant {name!r}; known: {', '.join(defs) or 'none'}")
    return Variant(
        name=name,
        label=d.get("label", name),
        video={**cfg["video"], **d.get("video", {})},
        audio={**cfg["audio"], **d.get("audio", {})},
        director={**cfg["director"], **d.get("director", {})},
        tuning=dict(d.get("tuning", {})),
    )
