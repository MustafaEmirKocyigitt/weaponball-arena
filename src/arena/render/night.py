"""European night format: several fast mini battles in one ~30 s Reel.

  intro   "CHAMPIONS LEAGUE / NIGHT" + every matchup of the night
  N x     quick battle (4-6 s fight, slow-mo KO, winner stamp), "1/3" counter on top
  outro   scoreboard of all predictions + "HOW MANY WILL WE GET RIGHT?"
"""
from __future__ import annotations

import math
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame

from ..audio import synth
from ..audio.mixer import Mixer, add_fight_sfx
from ..audio.music import build_music
from ..encode import VideoWriter
from ..sim.world import ARENA_CY, BattleResult
from . import draw
from .effects import brighten
from .renderer import Renderer, _init_pygame
from .scenes import GOLD, LABEL, MatchCard, bar_color, blit_center, ease_in, ease_out, ease_out_back, seg


@dataclass
class NightBattle:
    card: MatchCard
    result: BattleResult


class NightRenderer:
    def __init__(self, title: str, battles: list[NightBattle], video_cfg: dict, audio_cfg: dict, night_cfg: dict,
                 brand: str = "", record: tuple[int, int] | None = None):
        self.title = title
        self.battles = battles
        self.vc, self.ac, self.nc = video_cfg, audio_cfg, night_cfg
        self.brand, self.record = brand, record
        self.W, self.H, self.fps = video_cfg["width"], video_cfg["height"], video_cfg["fps"]
        _init_pygame(self.W, self.H)
        mini = dict(video_cfg, intro_seconds=0, post_ko_seconds=night_cfg.get("post_ko_seconds", 0.8),
                    outro_seconds=0, slowmo_window=night_cfg.get("slowmo_window", 0.3),
                    ko_hold=night_cfg.get("ko_hold", 14), fight_banner=False)
        self.renderers = [Renderer(b.card, b.result, mini, audio_cfg) for b in battles]
        self.n_intro = round(night_cfg.get("intro_seconds", 1.9) * self.fps)
        self.n_outro = round(night_cfg.get("outro_seconds", 3.0) * self.fps)
        self.screen = pygame.Surface((self.W, self.H))
        self.bg = draw.make_background(self.W, self.H, (30, 60, 170), (150, 160, 190))
        self.dim = pygame.Surface((self.W, self.H))
        self.dim.fill((6, 7, 14))

    # ------------------------------------------------------------------ layout helpers
    @property
    def total_frames(self) -> int:
        return self.n_intro + sum(len(r.tl.frames) for r in self.renderers) + self.n_outro

    def _starts(self) -> list[int]:
        out, f = [], self.n_intro
        for r in self.renderers:
            out.append(f)
            f += len(r.tl.frames)
        return out

    # ------------------------------------------------------------------ audio
    def build_audio(self) -> Mixer:
        fps = self.fps
        seed = self.battles[0].result.seed
        rng = np.random.default_rng(seed)
        mix = Mixer(self.total_frames / fps, self.ac.get("sample_rate", synth.SR))
        sfx = self.ac.get("sfx_volume", 1.0)
        starts = self._starts()
        intro_s = self.n_intro / fps
        mix.add(synth.riser(intro_s * 0.3, rng), 0.0, 0.4 * sfx)
        mix.add(synth.slam(rng), intro_s * 0.3, 0.9 * sfx)
        last = self.renderers[-1]
        end_music = (starts[-1] + max(0, last.tl.ko_frame)) / fps
        if self.ac.get("beat", True):
            bed = build_music(self.total_frames / fps, intro_s * 0.3, end_music, starts[-1] / fps, seed)
            mix.add(bed, 0.0, self.ac.get("beat_volume", 0.3))
        for r, st in zip(self.renderers, starts):
            t0 = st / fps
            mix.add(synth.whoosh(0.3, rng), t0 - 0.3, 0.45 * sfx)
            mix.add(synth.slam(rng), t0, 0.6 * sfx)
            add_fight_sfx(mix, r.tl, rng, sfx, offset=t0)
        out_t = (self.total_frames - self.n_outro) / fps
        mix.add(synth.whoosh(0.4, rng), out_t - 0.2, 0.4 * sfx)
        mix.add(synth.chime(rng), out_t + 0.1, 0.55 * sfx)
        return mix

    # ------------------------------------------------------------------ scenes
    def _intro(self, p: float, t: float):
        scr = self.screen
        W = self.W
        scr.blit(self.bg, (0, 0))
        out = ease_in(seg(p, 0.86, 1.0))
        a = int(255 * (1 - out))
        blit_center(scr, draw.text(self.title, 66, LABEL, outline=3, shadow=4), W / 2, 360 - 200 * out,
                    alpha=int(a * seg(p, 0.0, 0.1)))
        nk = seg(p, 0.08, 0.2)
        if nk > 0:
            scale = (1 + 1.8 * (1 - ease_out(nk))) * (1 - out)
            blit_center(scr, draw.headline("NIGHT", 210, GOLD, outline=8), W / 2, 520, scale=max(0.01, scale), alpha=a)
        n = len(self.battles)
        gap = 230 if n <= 3 else 190
        y0 = 800 if n <= 3 else 760
        for i, (b, r) in enumerate(zip(self.battles, self.renderers)):
            k = ease_out_back(seg(p, 0.22 + i * 0.08, 0.40 + i * 0.08))
            if k <= 0:
                continue
            side = -1 if i % 2 == 0 else 1
            dx = side * (1 - k) * 900 + side * out * 1200
            y = y0 + i * gap
            pygame.draw.rect(scr, (12, 14, 26), (60 + dx, y - 85, W - 120, 170), border_radius=26)
            pygame.draw.rect(scr, brighten((30, 60, 170), 0.2), (60 + dx, y - 85, W - 120, 170), 3, border_radius=26)
            r.sprites[0].draw(scr, 170 + dx, y, roll=0, scale=1.05)
            r.sprites[1].draw(scr, W - 170 + dx, y, roll=0, scale=1.05)
            for j, team in enumerate(b.card.teams):
                lab = draw.fit_text(team.short, 84, 180, color=(255, 255, 255), outline=4, shadow=4)
                blit_center(scr, lab, (355 if j == 0 else W - 355) + dx, y)
            blit_center(scr, draw.headline("VS", 64, GOLD, outline=3), W / 2 + dx, y)
        sk = seg(p, 0.6, 0.75)
        if sk > 0:
            blit_center(scr, draw.text(f"{n} BATTLES  ·  {n} PREDICTIONS", 40, GOLD, outline=2, face="body"),
                        W / 2, y0 + n * gap + 20, alpha=int(a * sk))
        if self.brand:
            blit_center(scr, draw.text(self.brand, 28, (150, 155, 175), face="body"), W / 2, 1596, alpha=a)

    def _battle_overlay(self, scr, i: int, f: int, r: Renderer):
        W = self.W
        n = len(self.battles)
        # counter pill on top
        pill = draw.text(f"{self.title} NIGHT   {i + 1} / {n}", 34, (16, 16, 24), face="body")
        rect = pygame.Rect(0, 0, pill.get_width() + 50, pill.get_height() + 14)
        rect.center = (W // 2, 150)
        pygame.draw.rect(scr, GOLD, rect, border_radius=24)
        blit_center(scr, pill, W / 2, 150)
        # big "BATTLE 2" for the first moment of each battle
        age = f / self.fps
        if age < 0.7:
            k = ease_out_back(min(1.0, age / 0.15), 2.0)
            fade = 1.0 if age < 0.45 else max(0.0, (0.7 - age) / 0.25)
            blit_center(scr, draw.headline(f"BATTLE {i + 1}", 130, (255, 255, 255), outline=7), W / 2, ARENA_CY,
                        scale=0.4 + 0.6 * k, alpha=int(255 * fade))
        # winner stamp after the KO
        tl = r.tl
        if tl.ko_frame > 0 and f > tl.ko_frame + 6:
            wk = ease_out_back(min(1.0, (f - tl.ko_frame - 6) / (0.18 * self.fps)), 2.2)
            team = r.card.teams[r.result.winner]
            col = bar_color(team)
            stamp = draw.fit_text(team.name.upper(), 96, 900, color=col, outline=6, shadow=6,
                                  gradient=(brighten(col, 0.7), col))
            blit_center(scr, stamp, W / 2, ARENA_CY + 175, scale=0.5 + 0.5 * wk)

    def _outro(self, p: float, t: float):
        scr = self.screen
        W = self.W
        scr.blit(self.bg, (0, 0))
        self.dim.set_alpha(150)
        scr.blit(self.dim, (0, 0))
        blit_center(scr, draw.text("ARENA PREDICTIONS", 40, GOLD, outline=3, face="body"), W / 2, 330,
                    alpha=int(255 * seg(p, 0.0, 0.1)))
        blit_center(scr, draw.headline("TONIGHT", 120, (255, 255, 255), outline=6), W / 2, 420,
                    scale=0.5 + 0.5 * ease_out_back(seg(p, 0.02, 0.14)))
        if self.record:
            blit_center(scr, draw.text(f"ARENA RECORD  {self.record[0]}/{self.record[1]}", 30, LABEL, outline=2,
                                       face="body"), W / 2, 505, alpha=int(255 * seg(p, 0.08, 0.18)))
        n = len(self.battles)
        gap = 210 if n <= 3 else 170
        for i, (b, r) in enumerate(zip(self.battles, self.renderers)):
            k = ease_out_back(seg(p, 0.1 + i * 0.07, 0.24 + i * 0.07))
            if k <= 0:
                continue
            y = 660 + i * gap
            win = b.card.teams[b.result.winner]
            lose = b.card.teams[1 - b.result.winner]
            col = bar_color(win)
            r.sprites[b.result.winner].draw(scr, 190, y, roll=math.sin(t * 2 + i) * 0.2, scale=1.2 * k)
            name = draw.fit_text(win.name.upper(), 86, 640, color=col, outline=5, shadow=5,
                                 gradient=(brighten(col, 0.7), col))
            scr.blit(name, (310, y - name.get_height() / 2 - 22 + (1 - k) * 40))
            vs = draw.text(f"BEATS {lose.name.upper()}", 30, LABEL, outline=2, face="body")
            vs.set_alpha(int(255 * k))
            scr.blit(vs, (318, y + 36))
        ck = ease_out_back(seg(p, 0.35, 0.47))
        if ck > 0:
            pulse = 1 + 0.035 * math.sin(t * 7)
            cy = 660 + n * gap + 40
            blit_center(scr, draw.headline("HOW MANY WILL WE GET RIGHT?", 64, GOLD, outline=5), W / 2, cy,
                        scale=pulse * ck)
            blit_center(scr, draw.text("COMMENT YOUR PICKS", 36, LABEL, outline=2, face="body"), W / 2, cy + 70,
                        alpha=int(255 * seg(p, 0.4, 0.5)))
        if self.brand:
            blit_center(scr, draw.text(self.brand, 30, (150, 155, 175), face="body"), W / 2, 1590)

    # ------------------------------------------------------------------ main loop
    def render(self, out_path: Path, log=print) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        dt = 1.0 / self.fps
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            self.build_audio().write_wav(str(wav))
            writer = VideoWriter(out_path, wav, self.W, self.H, self.fps, self.vc.get("crf", 19),
                                 self.vc.get("preset", "veryfast"), self.ac.get("music_volume", 0.35))
            g = 0
            try:
                for f in range(self.n_intro):
                    self._intro(f / max(1, self.n_intro - 1), g * dt)
                    writer.write(pygame.image.tobytes(self.screen, "RGB"))
                    g += 1
                for i, r in enumerate(self.renderers):
                    r.flash = 0.7  # white flash cut into each battle
                    for f, fr in enumerate(r.tl.frames):
                        r._render_frame(f, fr, dt)
                        self._battle_overlay(r.screen, i, f, r)
                        writer.write(pygame.image.tobytes(r.screen, "RGB"))
                        g += 1
                    log(f"  battle {i + 1}/{len(self.renderers)} done ({time.time() - t0:.0f}s)")
                for f in range(self.n_outro):
                    self._outro(f / max(1, self.n_outro - 1), g * dt)
                    writer.write(pygame.image.tobytes(self.screen, "RGB"))
                    g += 1
            finally:
                writer.close()
        return out_path
