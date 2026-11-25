"""Build the soundtrack from timeline events, perfectly synced to frames."""
from __future__ import annotations

import wave

import numpy as np

from ..render.timeline import Timeline
from . import synth
from .music import build_music

# Intro choreography (fractions of the intro), shared with the renderer.
INTRO_VS_AT = 0.32


class Mixer:
    def __init__(self, duration: float, sr: int = synth.SR):
        self.sr = sr
        self.buf = np.zeros((int(duration * sr) + sr, 2), dtype=np.float32)

    def add(self, sound: np.ndarray, at: float, gain: float = 1.0, pan: float = 0.0):
        start = int(at * self.sr)
        if start >= len(self.buf) or start < 0:
            return
        end = min(len(self.buf), start + len(sound))
        s = sound[: end - start] * gain
        left = np.cos((pan + 1) * np.pi / 4)
        right = np.sin((pan + 1) * np.pi / 4)
        self.buf[start:end, 0] += s * left * 1.414
        self.buf[start:end, 1] += s * right * 1.414

    def master(self) -> np.ndarray:
        x = self.buf
        peak = np.max(np.abs(x)) or 1.0
        x = x / peak * 1.4
        return (np.tanh(x) / np.tanh(1.4) * 0.92).astype(np.float32)

    def write_wav(self, path: str):
        data = (self.master() * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(data.tobytes())


def _pan(x: float) -> float:
    return max(-0.7, min(0.7, (x - 540) / 540 * 0.7))


def build_soundtrack(tl: Timeline, seed: int, audio_cfg: dict, intro_s: float) -> Mixer:
    rng = np.random.default_rng(seed)
    sr = audio_cfg.get("sample_rate", synth.SR)
    mix = Mixer(tl.duration, sr)
    sfx = audio_cfg.get("sfx_volume", 1.0)
    fps = tl.fps

    # --- intro: riser -> VS slam -> FIGHT slam
    vs_t = intro_s * INTRO_VS_AT
    mix.add(synth.riser(max(0.3, vs_t), rng), 0.0, 0.45 * sfx)
    mix.add(synth.slam(rng), vs_t, 0.9 * sfx)
    fight_t = tl.fight_start / fps
    mix.add(synth.whoosh(0.35, rng), fight_t - 0.35, 0.5 * sfx)
    mix.add(synth.slam(rng), fight_t, 0.8 * sfx)

    # --- background beat during the fight
    end_beat = (tl.ko_frame if tl.ko_frame > 0 else tl.outro_start) / fps
    if audio_cfg.get("beat", True):
        vol = audio_cfg.get("beat_volume", 0.2)
        shrink_frames = [i for i, evs in tl.events_at.items() if any(e.kind == "shrink" for e in evs)]
        build_at = shrink_frames[0] / fps if shrink_frames else end_beat
        bed = build_music(tl.duration, fight_t - 60 / 128 * 2, end_beat, build_at, seed)
        mix.add(bed, 0.0, vol)

    # --- fight events
    for idx, evs in sorted(tl.events_at.items()):
        at = idx / fps
        for e in evs:
            pan = _pan(e.x)
            if e.kind == "hit":
                pitch = 2 ** (min(e.combo - 1, 7) / 12 * 1.5) * rng.uniform(0.96, 1.04)
                heavy = min(1.0, e.value / 20)
                mix.add(synth.hit(pitch, rng, heavy), at, (0.85 + 0.15 * heavy) * sfx, pan)
            elif e.kind == "parry":
                mix.add(synth.clang(rng.uniform(0.9, 1.15), rng), at, 0.55 * sfx, pan)
            elif e.kind == "wall":
                mix.add(synth.tick(1.0 + 0.25 * e.a + rng.uniform(-0.05, 0.05), rng), at, 0.14 * sfx, pan)
            elif e.kind == "bump":
                mix.add(synth.bump(rng), at, 0.4 * sfx, pan)
            elif e.kind == "levelup":
                base = 660 * 2 ** (min(e.level, 10) / 12)
                mix.add(synth.blip([base, base * 1.25, base * 1.5]), at + 0.05, 0.16 * sfx, pan)
            elif e.kind == "shrink":
                mix.add(synth.warning(rng), at, 0.3 * sfx)
            elif e.kind == "ko":
                mix.add(synth.ko(rng), at, 1.0 * sfx, pan)

    # --- outro
    mix.add(synth.whoosh(0.4, rng), tl.outro_start / fps - 0.2, 0.4 * sfx)
    mix.add(synth.chime(rng), tl.outro_start / fps + 0.1, 0.55 * sfx)
    return mix
