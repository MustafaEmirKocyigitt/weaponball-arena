"""Turn standings + recent form into a 0..1 strength score."""
from __future__ import annotations

FORM_POINTS = {"W": 1.0, "D": 0.4, "L": 0.0}


def form_score(form: str) -> float | None:
    pts = [FORM_POINTS[c] for c in form.upper() if c in FORM_POINTS]
    if not pts:
        return None
    # recent games weigh a bit more (ESPN lists oldest -> newest)
    weights = [1 + 0.15 * i for i in range(len(pts))]
    return sum(p * w for p, w in zip(pts, weights)) / sum(weights)


def strength(standing: dict | None, form: str) -> float:
    parts: list[tuple[float, float]] = []  # (weight, value)
    s = standing or {}
    gp = s.get("gp") or 0
    if gp:
        if s.get("pts") is not None:
            parts.append((0.35, min(1.0, s["pts"] / gp / 3)))
        if s.get("gd") is not None:
            parts.append((0.20, max(0.0, min(1.0, s["gd"] / gp / 4 + 0.5))))
    if s.get("rank") and s.get("n", 0) > 1:
        parts.append((0.20, 1 - (s["rank"] - 1) / (s["n"] - 1)))
    f = form_score(form)
    if f is not None:
        parts.append((0.25, f))
    if not parts:
        return 0.5
    total = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / total


def rank_score(standing: dict | None) -> float:
    s = standing or {}
    if s.get("rank") and s.get("n", 0) > 1:
        return 1 - (s["rank"] - 1) / (s["n"] - 1)
    return 0.4
