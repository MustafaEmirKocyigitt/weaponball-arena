"""Procedural sound effects (numpy). No samples, no licensing issues.

Every function returns a mono float32 array in [-1, 1].
"""
from __future__ import annotations

import numpy as np

SR = 48000


def _t(dur: float, sr: int = SR) -> np.ndarray:
    return np.arange(int(dur * sr)) / sr


def _env(dur: float, tau: float, attack: float = 0.002, sr: int = SR) -> np.ndarray:
    t = _t(dur, sr)
    env = np.exp(-t / tau)
    a = max(1, int(attack * sr))
    env[:a] *= np.linspace(0, 1, a)
    return env


def _sweep(f0: float, f1: float, dur: float, curve: float = 6.0, sr: int = SR) -> np.ndarray:
    t = _t(dur, sr)
    f = f1 + (f0 - f1) * np.exp(-t * curve)
    return np.sin(2 * np.pi * np.cumsum(f) / sr)


def _lowpass(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return x
    return np.convolve(x, np.ones(k) / k, mode="same")


def _bandnoise(n: int, lo: float, hi: float, rng: np.random.Generator, sr: int = SR) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec[(freqs < lo) | (freqs > hi)] = 0
    out = np.fft.irfft(spec, n)
    m = np.max(np.abs(out)) or 1.0
    return out / m


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


def hit(pitch: float, rng: np.random.Generator, heavy: float = 0.0) -> np.ndarray:
    """Meaty impact: pitched thump + crack + crunchy body."""
    dur = 0.45 + 0.25 * heavy
    n = int(dur * SR)
    thump = _sweep(190 * pitch, 48, dur, curve=18) * _env(dur, 0.09 + 0.05 * heavy)
    crack = _bandnoise(n, 1800, 9000, rng) * _env(dur, 0.012)
    body = _bandnoise(n, 150, 1800, rng) * _env(dur, 0.05 + 0.04 * heavy)
    ring = np.sin(2 * np.pi * 520 * pitch * _t(dur)) * _env(dur, 0.06) * 0.25
    return _norm(1.0 * thump + 0.55 * crack + 0.6 * body + ring)


def clang(pitch: float, rng: np.random.Generator) -> np.ndarray:
    """Metallic parry: inharmonic partials + bright transient."""
    dur = 0.9
    t = _t(dur)
    base = 760 * pitch
    out = np.zeros_like(t)
    for ratio, amp, tau in ((1.0, 1.0, 0.35), (2.41, 0.6, 0.22), (3.87, 0.45, 0.16),
                            (5.53, 0.3, 0.1), (7.2, 0.2, 0.07)):
        det = 1 + rng.uniform(-0.004, 0.004)
        out += amp * np.sin(2 * np.pi * base * ratio * det * t) * np.exp(-t / tau)
    out += _bandnoise(len(t), 3000, 12000, rng) * _env(dur, 0.006) * 0.8
    return _norm(out)


def tick(pitch: float, rng: np.random.Generator) -> np.ndarray:
    """Soft wall bounce: woody 'tok'."""
    dur = 0.12
    s = np.sin(2 * np.pi * 330 * pitch * _t(dur)) * _env(dur, 0.025)
    s += _bandnoise(int(dur * SR), 800, 4000, rng) * _env(dur, 0.004) * 0.4
    return _norm(s)


def bump(rng: np.random.Generator) -> np.ndarray:
    dur = 0.3
    s = _sweep(140, 55, dur, curve=14) * _env(dur, 0.07)
    s += _bandnoise(int(dur * SR), 100, 1200, rng) * _env(dur, 0.03) * 0.5
    return _norm(s)


def blip(notes: list[float], step: float = 0.055) -> np.ndarray:
    """Short rising arpeggio (level-up)."""
    parts = []
    for f in notes:
        t = _t(step * 1.6)
        tone = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
        parts.append(tone * _env(step * 1.6, step * 0.5))
    n = int(step * SR)
    out = np.zeros(n * (len(notes) - 1) + len(parts[-1]))
    for i, p in enumerate(parts):
        out[i * n:i * n + len(p)] += p
    return _norm(out)


def ko(rng: np.random.Generator) -> np.ndarray:
    """Huge knock-out boom with a long tail."""
    dur = 2.6
    n = int(dur * SR)
    sub = _sweep(130, 30, dur, curve=2.5) * _env(dur, 0.7)
    crash = _bandnoise(n, 200, 9000, rng) * _env(dur, 0.35)
    crack = _bandnoise(n, 2000, 12000, rng) * _env(dur, 0.02)
    bell = clang(0.55, rng)
    out = 1.2 * sub + 0.6 * crash + 0.6 * crack
    out[:len(bell)] += 0.4 * bell
    return _norm(out)


def whoosh(dur: float, rng: np.random.Generator, rise: bool = True) -> np.ndarray:
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    env = (t ** 2.2) if rise else ((1 - t) ** 2)
    lo = _bandnoise(n, 200, 1500, rng)
    hi = _bandnoise(n, 1500, 7000, rng)
    mix = lo * (1 - t) + hi * t if rise else lo * t + hi * (1 - t)
    return _norm(mix * env)


def riser(dur: float, rng: np.random.Generator) -> np.ndarray:
    t = _t(dur)
    f = 180 + 900 * (t / dur) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 1.5
    return _norm(0.6 * tone + 0.7 * whoosh(dur, rng))


def slam(rng: np.random.Generator) -> np.ndarray:
    """VS slam / FIGHT impact."""
    dur = 1.2
    n = int(dur * SR)
    s = _sweep(110, 38, dur, curve=5) * _env(dur, 0.3)
    s += _bandnoise(n, 300, 8000, rng) * _env(dur, 0.12) * 0.7
    return _norm(s)


def kick() -> np.ndarray:
    dur = 0.35
    return _norm(_sweep(150, 42, dur, curve=22) * _env(dur, 0.11))


def hat(rng: np.random.Generator) -> np.ndarray:
    dur = 0.08
    return _norm(_bandnoise(int(dur * SR), 6000, 14000, rng) * _env(dur, 0.018))


def chime(rng: np.random.Generator) -> np.ndarray:
    """Victory chord arpeggio."""
    notes = [523.25, 659.25, 783.99, 1046.5]
    dur = 1.8
    out = np.zeros(int(dur * SR))
    for i, f in enumerate(notes):
        t = _t(dur - i * 0.09)
        tone = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2.01 * f * t)) * np.exp(-t / 0.6)
        start = int(i * 0.09 * SR)
        out[start:start + len(tone)] += tone
    return _norm(out)


def warning(rng: np.random.Generator) -> np.ndarray:
    """Arena-shrink alarm: two-tone pulse."""
    seg = []
    for f in (880, 660, 880, 660):
        t = _t(0.14)
        seg.append(np.sign(np.sin(2 * np.pi * f * t)) * 0.4 * _env(0.14, 0.1))
    return _norm(np.concatenate(seg))
