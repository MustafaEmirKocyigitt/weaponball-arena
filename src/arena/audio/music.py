"""Procedural background music: a 128 BPM electronic loop in A minor.

Kick + clap + hats, a pumping bass line and a plucky arpeggio over
Am - F - C - G. It builds when the arena starts shrinking (16th hats,
arp up an octave) and stops dead on the knock-out. Fully generated, so
there is nothing to license.
"""
from __future__ import annotations

import numpy as np

from . import synth

SR = synth.SR
BPM = 128
BEAT = 60 / BPM
# chord roots (Hz) per bar and the chord tones used by the arpeggio
PROGRESSION = [
    (55.00, [220.00, 261.63, 329.63]),   # Am
    (43.65, [174.61, 220.00, 261.63]),   # F
    (65.41, [261.63, 329.63, 392.00]),   # C
    (49.00, [196.00, 246.94, 293.66]),   # G
]


def _saw(freq: float, n: int, harmonics: int = 10) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, harmonics + 1):
        if freq * k > SR / 2.5:
            break
        out += np.sin(2 * np.pi * freq * k * t) / k
    return out


def _lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same") if k > 1 else x


def _bass(freq: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    s = _lowpass(_saw(freq, n, 8), 6) + 0.6 * np.sin(2 * np.pi * freq * np.arange(n) / SR)
    env = np.minimum(1, np.arange(n) / (0.004 * SR)) * np.exp(-np.arange(n) / (dur * SR * 0.9))
    return s * env


def _pluck(freq: float, dur: float, bright: float) -> np.ndarray:
    n = int(dur * SR)
    s = _saw(freq, n, 6 + int(6 * bright))
    s = _lowpass(s, max(1, int(6 - 4 * bright)))
    return s * np.exp(-np.arange(n) / (0.09 * SR))


def _clap(rng: np.random.Generator) -> np.ndarray:
    n = int(0.25 * SR)
    noise = synth._bandnoise(n, 900, 5000, rng)
    env = np.zeros(n)
    for off in (0, 0.012, 0.024):  # three quick bursts = hand clap
        i = int(off * SR)
        env[i:] += np.exp(-np.arange(n - i) / (0.03 * SR)) * (0.6 if off else 1)
    return noise * env


def build_music(total_s: float, start: float, stop: float, build_at: float, seed: int) -> np.ndarray:
    """Mono music bed from `start` to `stop` (seconds)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(total_s * SR) + SR)
    drums = np.zeros_like(out)
    duck = np.ones_like(out)
    kick = synth.kick()
    hat = synth.hat(rng)
    clap = _clap(rng)

    def put(sig, at, gain, buf=None):
        buf = out if buf is None else buf
        i = int(at * SR)
        if i < 0 or i >= len(buf):
            return
        j = min(len(buf), i + len(sig))
        buf[i:j] += sig[: j - i] * gain

    beat = 0
    t = start
    while t < stop - 0.02:
        bar = beat // 4
        root, chord = PROGRESSION[bar % 4]
        building = t >= build_at
        # drums
        put(kick, t, 1.0, drums)
        i = int(t * SR)
        d = np.arange(min(int(0.25 * SR), len(out) - i))
        duck[i:i + len(d)] = np.minimum(duck[i:i + len(d)], 1 - 0.65 * np.exp(-d / (0.07 * SR)))
        if beat % 2 == 1:
            put(clap, t, 0.55, drums)
        steps = 4 if building else 2
        for s in range(steps):
            if s == 0 and not building:
                continue
            put(hat, t + s * BEAT / steps, 0.35 if s % 2 else 0.22, drums)
        # bass: off-beat eighths (pumps against the kick)
        put(_bass(root * (2 if beat % 4 == 3 else 1), BEAT / 2 * 0.9), t + BEAT / 2, 0.55)
        # arpeggio: 16ths over chord tones, enters after 2 bars
        if bar >= 2 or building:
            octave = 2 if building else 1
            for s in range(4):
                note = chord[(beat * 4 + s) % 3] * octave
                if s == 3:
                    note *= 2
                put(_pluck(note, BEAT / 4 * 1.6, 0.8 if building else 0.4), t + s * BEAT / 4, 0.16)
        t += BEAT
        beat += 1

    # victory pad after the KO
    pad_n = int(2.4 * SR)
    pad = np.zeros(pad_n)
    for f in (220.0, 277.18, 329.63, 440.0):  # A major: bright, triumphant
        pad += _lowpass(_saw(f, pad_n, 6), 8)
    env = np.minimum(1, np.arange(pad_n) / (0.25 * SR)) * np.exp(-np.arange(pad_n) / (1.4 * SR))
    put(pad * env, stop + 0.9, 0.12)

    out = out * duck + drums
    peak = np.max(np.abs(out)) or 1.0
    return (out / peak).astype(np.float32)
