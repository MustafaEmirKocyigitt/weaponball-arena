"""Render a BattleResult + Timeline into an MP4."""
from __future__ import annotations

import math
import os
import random
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from ..audio.mixer import build_soundtrack  # noqa: E402
from ..data.teams import readable_on_dark  # noqa: E402
from ..encode import VideoWriter  # noqa: E402
from ..sim.world import ARENA_CX, ARENA_CY, ARENA_R0, BALL_R, SIM_HZ, BattleResult  # noqa: E402
from . import draw  # noqa: E402
from .effects import FloatingTexts, GlowCache, Particles, Shake, brighten  # noqa: E402
from .scenes import MatchCard, draw_banner, draw_footer, draw_hud, draw_intro, draw_outro, make_rays, seg  # noqa: E402
from .timeline import SLOWMO_WINDOW, Timeline, build_timeline  # noqa: E402

RIBBON_LEN = 9
BEAT = 60 / 128
RING_COLOR = (120, 170, 255)
DANGER_COLOR = (255, 50, 60)


def _init_pygame(w: int, h: int):
    if not pygame.get_init():
        pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


class Renderer:
    def __init__(self, card: MatchCard, result: BattleResult, video_cfg: dict, audio_cfg: dict):
        self.card = card
        self.result = result
        self.vc = video_cfg
        self.ac = audio_cfg
        self.W, self.H, self.fps = video_cfg["width"], video_cfg["height"], video_cfg["fps"]
        _init_pygame(self.W, self.H)
        self.tl: Timeline = build_timeline(result, self.fps, video_cfg["intro_seconds"],
                                           video_cfg["post_ko_seconds"], video_cfg["outro_seconds"],
                                           video_cfg.get("slowmo_window", SLOWMO_WINDOW),
                                           video_cfg.get("ko_hold", 18))
        self.screen = pygame.Surface((self.W, self.H))
        self.fx = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        teams = card.teams
        self.sprites = [draw.BallSprites(t) for t in teams]
        self.bg = draw.make_background(self.W, self.H, teams[0].primary, teams[1].primary)
        self.floor = draw.make_floor(int(ARENA_R0))
        self.ring_glow = draw.make_ring_glow(int(ARENA_R0), RING_COLOR)
        self.ring_glow_danger = draw.make_ring_glow(int(ARENA_R0), DANGER_COLOR)
        self._ring_cache: dict = {}
        self.dim = pygame.Surface((self.W, self.H))
        self.dim.fill((6, 7, 14))
        self.flash_surf = pygame.Surface((self.W, self.H))
        self.flash_surf.fill((255, 255, 255))
        self.rays = make_rays(readable_on_dark(teams[result.winner].primary, teams[result.winner].secondary))
        self.glow = GlowCache()
        self.rng = random.Random(result.seed * 7919 + 17)
        self.particles = Particles(self.rng, self.glow)
        self.texts = FloatingTexts()
        self.shake = Shake(result.seed)
        self.flash = 0.0
        self.ball_flash = [0.0, 0.0]
        self.ball_punch = [0.0, 0.0]
        self.hp_trail = [100.0, 100.0]
        self.trail_delay = [0.0, 0.0]
        self.banners: list[tuple[str, int, float, tuple, float, int]] = []  # label, start_frame, dur, color, y, size
        self.loser_gone = False
        self.weapon_kinds = [t.weapon for t in teams]
        self.history: list[tuple] = []
        self.cam_buf = pygame.Surface((self.W, self.H))
        self.zoom = 1.0
        self.zoom_punch = 0.0
        self.focus = (ARENA_CX, ARENA_CY)
        self.ko_point = None
        self.impact = 0
        mr = random.Random(result.seed + 99)
        self.motes = [[mr.uniform(0, self.W), mr.uniform(0, self.H), mr.uniform(-8, 8), mr.uniform(-40, -12),
                       mr.uniform(1.2, 3.2), mr.randint(35, 85)] for _ in range(70)]

    # ------------------------------------------------------------------ state
    def state_at(self, t: float) -> tuple:
        states = self.result.states
        f = t * SIM_HZ
        i0 = min(len(states) - 1, int(f))
        i1 = min(len(states) - 1, i0 + 1)
        k = f - i0
        a, b = states[i0], states[i1]
        if k <= 1e-6 or i0 == i1:
            return a
        out = list(a)
        for j in (0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 13):
            out[j] = a[j] + (b[j] - a[j]) * k
        return tuple(out)

    @staticmethod
    def fighter(st: tuple, i: int):
        o = 1 + i * 7
        # x, y, angle, length, hp, roll, level
        return st[o], st[o + 1], st[o + 2], st[o + 3], st[o + 4], st[o + 5], st[o + 6]

    # ------------------------------------------------------------------ events
    def on_event(self, e, frame_idx: int):
        teams = self.card.teams
        if e.kind == "hit":
            vic, att = teams[e.b], teams[e.a]
            heavy = min(1.0, e.value / 18)
            self.particles.sparks(e.x, e.y, 16 + int(10 * heavy), brighten(att.primary, 0.3))
            self.particles.chunks(e.x, e.y, 10 + int(8 * heavy), vic.primary, vic.secondary)
            self.particles.ring(e.x, e.y, brighten(vic.primary, 0.4), max_r=120 + 60 * heavy)
            self.particles.flare(e.x, e.y, (255, 240, 210), radius=150 + 80 * heavy)
            self.shake.kick(12 + 14 * heavy + 2 * min(e.combo, 5))
            self.ball_flash[e.b] = 1.0
            self.ball_punch[e.b] = 1.0
            ax, ay = self.fighter(self.state_at(e.t), e.a)[:2]
            self.particles.slash(e.x, e.y, math.atan2(e.y - ay, e.x - ax) + math.pi / 2,
                                 brighten(att.primary, 0.3), length=230 + 120 * heavy)
            self.zoom_punch = max(self.zoom_punch, 0.025 + 0.03 * heavy)
            if e.combo >= 4 or e.value >= 18:
                self.impact = max(self.impact, 1)
            label = f"-{int(e.value)}"
            surf = draw.text(label, 78 + int(26 * heavy), (255, 255, 255), outline=5, shadow=5,
                             outline_color=tuple(int(c * 0.3) for c in vic.primary),
                             gradient=((255, 255, 255), (255, 214, 110)))
            self.texts.add(surf, e.x, e.y - 30)
            if e.combo >= 3:
                self.texts.add(draw.text(f"x{e.combo} COMBO", 50, (255, 210, 80), outline=4, shadow=3,
                                         gradient=((255, 245, 200), (255, 170, 40))), e.x, e.y - 110, life=1.0)
            self.trail_delay[e.b] = 0.35
        elif e.kind == "parry":
            self.particles.sparks(e.x, e.y, 22, (255, 220, 120), speed=(400, 1100))
            self.particles.ring(e.x, e.y, (255, 230, 160), max_r=90, life=0.25, width=6)
            self.particles.flare(e.x, e.y, (255, 220, 140), radius=130, life=0.2)
            self.shake.kick(7)
        elif e.kind == "wall":
            col = teams[e.a].primary if e.a >= 0 else RING_COLOR
            self.particles.sparks(e.x, e.y, 4, brighten(col, 0.4), speed=(200, 500), life=(0.1, 0.25), size=3)
        elif e.kind == "bump":
            self.particles.ring(e.x, e.y, (255, 255, 255), max_r=70, life=0.22, width=5)
            self.shake.kick(5)
        elif e.kind == "levelup":
            pass
        elif e.kind == "shrink":
            self.banners.append(("SUDDEN DEATH", frame_idx, 1.4, DANGER_COLOR, ARENA_CY - 90, 96))
        elif e.kind == "ko":
            loser = teams[e.b]
            self.particles.chunks(e.x, e.y, 70, loser.primary, loser.secondary, speed=(300, 1400), life=(0.9, 1.8), size=(7, 18))
            self.particles.sparks(e.x, e.y, 50, (255, 240, 200), speed=(600, 1800), life=(0.3, 0.8), size=5)
            for k in range(3):
                self.particles.ring(e.x, e.y, brighten(loser.primary, 0.3 * k), max_r=260 + 140 * k, life=0.5 + 0.2 * k, width=14)
            self.particles.flare(e.x, e.y, (255, 255, 255), radius=420, life=0.5)
            self.shake.kick(38)
            self.flash = 1.0
            self.ko_point = (e.x, e.y)
            self.impact = 3
            for a in (0.4, 1.9):
                self.particles.slash(e.x, e.y, a, (255, 255, 255), length=620, life=0.4, width=26)
            self.loser_gone = True
            self.banners.append(("K.O.", frame_idx, 2.2, (255, 255, 255), ARENA_CY, 210))

    # ------------------------------------------------------------------ drawing
    def _ring_glow(self, R: float, danger: float):
        key = (int(R) // 2 * 2, danger > 0.5)
        s = self._ring_cache.get(key)
        if s is None:
            base = self.ring_glow_danger if danger > 0.5 else self.ring_glow
            scale = key[0] / ARENA_R0
            s = base if abs(scale - 1) < 1e-3 else pygame.transform.smoothscale_by(base, scale)
            if len(self._ring_cache) > 8:
                self._ring_cache.clear()
            self._ring_cache[key] = s
        return s

    def draw_arena(self, R: float, ox: float, oy: float, t_video: float, shrinking: bool, beat: float = 0.0):
        cx, cy = ARENA_CX + ox, ARENA_CY + oy
        if R < ARENA_R0 - 0.5:
            # outer danger zone
            pygame.draw.circle(self.screen, (40, 8, 14), (cx, cy), ARENA_R0)
            fl = pygame.transform.smoothscale_by(self.floor, R / ARENA_R0)
            self.screen.blit(fl, (cx - fl.get_width() / 2, cy - fl.get_height() / 2))
        else:
            self.screen.blit(self.floor, (cx - ARENA_R0, cy - ARENA_R0))
        danger = 1.0 if shrinking else 0.0
        color = DANGER_COLOR if shrinking else RING_COLOR
        if shrinking:
            pulse = 0.5 + 0.5 * math.sin(t_video * 10)
            color = brighten(DANGER_COLOR, 0.25 * pulse)
        g = self._ring_glow(R, danger)
        self.screen.blit(g, (cx - g.get_width() / 2, cy - g.get_height() / 2), special_flags=pygame.BLEND_ADD)
        if beat > 0.15:  # pulse with the music
            self.screen.blit(g, (cx - g.get_width() / 2, cy - g.get_height() / 2), special_flags=pygame.BLEND_ADD)
        draw.draw_ring(self.screen, cx, cy, R, brighten(color, 0.5 * beat))

    def draw_fighters(self, st: tuple, ox: float, oy: float):
        fx = self.fx
        fx.fill((0, 0, 0, 0))
        hist = self.history[-RIBBON_LEN:]
        for i in (0, 1):
            if self.loser_gone and i != self.result.winner:
                continue
            team = self.card.teams[i]
            # ball trail
            for k, h in enumerate(hist[-7:-1]):
                hx, hy = h[i][0], h[i][1]
                a = int(14 + 9 * k)
                pygame.draw.circle(fx, (*team.primary, a), (hx + ox, hy + oy), BALL_R * (0.5 + 0.07 * k))
            # weapon ribbon: quads between the blade's past positions, fading out
            col = brighten(team.primary, 0.45)
            blades = 2 if self.weapon_kinds[i] == "daggers" else 1
            extra = 14 if self.weapon_kinds[i] in ("hammer", "axe") else 0
            for blade in range(blades):
                pts = []
                for h in hist:
                    hx, hy, ha, hl = h[i]
                    a = ha + blade * math.pi
                    ca, sa = math.cos(a), math.sin(a)
                    r_in = BALL_R + 6 + hl * 0.35
                    r_out = BALL_R + 6 + hl + extra
                    pts.append(((hx + ca * r_in + ox, hy + sa * r_in + oy), (hx + ca * r_out + ox, hy + sa * r_out + oy)))
                n = len(pts)
                for j in range(n - 1):
                    k = (j + 1) / (n - 1)
                    quad = [pts[j][0], pts[j][1], pts[j + 1][1], pts[j + 1][0]]
                    pygame.draw.polygon(fx, (*col, int(170 * k ** 1.7)), quad)
        self.screen.blit(fx, (0, 0))

        for i in (0, 1):
            if self.loser_gone and i != self.result.winner:
                continue
            team = self.card.teams[i]
            x, y, ang, ln, hp, roll, lvl = self.fighter(st, i)
            kind = self.weapon_kinds[i]
            if lvl >= 2:
                inten = min(1.0, lvl / 9)
                for tx, ty in draw.weapon_tip(kind, x + ox, y + oy, ang, ln):
                    self.glow.blit(self.screen, brighten(team.primary, 0.2), tx, ty, 50 + 40 * inten, 0.35 + 0.5 * inten)
            draw.draw_weapon(self.screen, kind, team, x + ox, y + oy, ang, ln, lvl)
            punch = 1 + 0.16 * self.ball_punch[i] ** 2
            self.sprites[i].draw(self.screen, x + ox, y + oy, roll, scale=punch, flash=self.ball_flash[i], hp=hp)

    # ------------------------------------------------------------------ camera / ambience
    def _update_camera(self, fr, idx: int, st: tuple, dt: float):
        tl, r = self.tl, self.result
        alive = [i for i in (0, 1) if not (self.loser_gone and i != r.winner)]
        fxs = [self.fighter(st, i)[:2] for i in alive]
        focus = (sum(p[0] for p in fxs) / len(fxs), sum(p[1] for p in fxs) / len(fxs))
        target = 1.0
        if fr.phase == "fight" and not r.timeout:
            if r.duration - fr.t < self.vc.get("slowmo_window", SLOWMO_WINDOW) + 0.05:
                target = 1.32
            if tl.ko_frame > 0 and idx >= tl.ko_frame:
                target, focus = 1.42, self.ko_point or focus
        elif fr.phase == "post" and fr.p < 0.25:
            target, focus = 1.25, self.ko_point or focus
        k = 1 - math.exp(-dt / 0.13)
        self.zoom += (target - self.zoom) * k
        self.focus = (self.focus[0] + (focus[0] - self.focus[0]) * k, self.focus[1] + (focus[1] - self.focus[1]) * k)
        self.zoom_punch *= math.exp(-dt / 0.09)

    def _apply_camera(self):
        z = self.zoom + self.zoom_punch
        if z < 1.003:
            return
        w, h = self.W / z, self.H / z
        cx = min(max(self.focus[0], w / 2), self.W - w / 2)
        cy = min(max(self.focus[1], h / 2), self.H - h / 2)
        rect = pygame.Rect(int(cx - w / 2), int(cy - h / 2), int(w), int(h)).clip(self.screen.get_rect())
        pygame.transform.smoothscale(self.screen.subsurface(rect), (self.W, self.H), self.cam_buf)
        self.screen.blit(self.cam_buf, (0, 0))

    def _impact_frame(self):
        self.cam_buf.fill((255, 255, 255))
        self.cam_buf.blit(self.screen, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        self.screen.blit(self.cam_buf, (0, 0))

    def _draw_motes(self, dt: float, ox: float, oy: float):
        for m in self.motes:
            m[1] += m[3] * dt
            m[0] += m[2] * dt
            if m[1] < -10:
                m[1] = self.H + 10
            b = m[5]
            pygame.draw.circle(self.screen, (b, b, min(255, b + 30)), (m[0] + ox * 0.5, m[1] + oy * 0.5), m[4])

    # ------------------------------------------------------------------ main loop
    def render(self, out_path: Path, log_every: int = 600) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tl = self.tl
        dt = 1.0 / self.fps
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            build_soundtrack(tl, self.result.seed, self.ac, self.vc["intro_seconds"]).write_wav(str(wav))
            writer = VideoWriter(out_path, wav, self.W, self.H, self.fps, self.vc.get("crf", 19),
                                 self.vc.get("preset", "veryfast"), self.ac.get("music_volume", 0.35))
            t0 = time.time()
            try:
                for idx, fr in enumerate(tl.frames):
                    self._render_frame(idx, fr, dt)
                    writer.write(pygame.image.tobytes(self.screen, "RGB"))
                    if log_every and idx % log_every == 0:
                        print(f"  frame {idx}/{len(tl.frames)}  ({time.time() - t0:.0f}s)", flush=True)
            finally:
                writer.close()
        return out_path

    def _render_frame(self, idx: int, fr, dt: float):
        tl = self.tl
        t_video = idx * dt
        for e in tl.events_at.get(idx, []):
            self.on_event(e, idx)

        st = self.state_at(fr.t)
        if not fr.hold:
            # per fighter: (x, y, weapon_angle, weapon_length)
            self.history.append(tuple(self.fighter(st, i)[:4] for i in (0, 1)))
            if len(self.history) > RIBBON_LEN + 1:
                self.history.pop(0)
            if fr.phase == "fight":
                for i in (0, 1):
                    x, y, _, _, hp, _, _ = self.fighter(st, i)
                    if 0 < hp < 30 and self.rng.random() < 0.3:
                        self.particles.smoke(x, y)
        self._update_camera(fr, idx, st, dt)

        # effect timers (run in video time, also during hit-stop)
        self.particles.update(dt)
        self.texts.update(dt)
        self.shake.update(dt)
        if self.impact == 0:  # the KO flash starts after the inverted impact frames
            self.flash *= math.exp(-dt / 0.12)
        for i in (0, 1):
            self.ball_flash[i] = max(0.0, self.ball_flash[i] - dt / 0.10)
            self.ball_punch[i] = max(0.0, self.ball_punch[i] - dt / 0.18)
            hp = self.fighter(st, i)[4]
            if self.trail_delay[i] > 0:
                self.trail_delay[i] -= dt
            elif self.hp_trail[i] > hp:
                self.hp_trail[i] = max(hp, self.hp_trail[i] - 80 * dt)
            if self.hp_trail[i] < hp:
                self.hp_trail[i] = hp
        if fr.phase in ("post", "outro") and self.rng.random() < (0.55 if fr.phase == "post" else 0.3):
            w = self.card.teams[self.result.winner]
            self.particles.confetti(self.W, 3, [w.primary, w.secondary, (255, 255, 255)])

        ox, oy = self.shake.offset()
        scr = self.screen
        scr.blit(self.bg, (ox * 0.3, oy * 0.3))
        self._draw_motes(dt, ox, oy)

        R = st[0]
        shrinking = R < ARENA_R0 - 0.5
        beat = 0.0
        if fr.phase == "fight" and (tl.ko_frame < 0 or idx < tl.ko_frame):
            beat = math.exp(-(((idx - tl.fight_start) * dt) % BEAT) / BEAT * 6)
        self.draw_arena(R, ox, oy, t_video, shrinking, beat)
        if fr.phase != "intro" or fr.p > 0.8:
            self.draw_fighters(st, ox, oy)
        self.particles.draw_additive(scr, ox, oy)
        self.particles.draw(scr, ox, oy)
        self.texts.draw(scr, ox, oy)
        self._apply_camera()
        if self.impact > 0:
            self._impact_frame()
            self.impact -= 1

        # HUD + footer
        hud_alpha = seg(idx, tl.fight_start - 4, tl.fight_start + 8) if fr.phase in ("intro", "fight") else (
            1.0 if fr.phase == "post" else 0.0)
        hp = [self.fighter(st, i)[4] for i in (0, 1)]
        levels = [self.fighter(st, i)[6] for i in (0, 1)]
        if fr.phase in ("fight", "post", "intro"):
            draw_hud(scr, self.card, hp, self.hp_trail, t_video, hud_alpha, levels)
            draw_footer(scr, self.card, hud_alpha)

        # banners
        if idx == tl.fight_start and self.vc.get("fight_banner", True):
            self.banners.append(("FIGHT!", idx, 0.8, (255, 210, 80), ARENA_CY, 150))
        for label, start, dur, color, y, size in self.banners:
            draw_banner(scr, label, (idx - start) * dt, dur, color, y, size)

        if fr.phase == "intro":
            draw_intro(scr, self.card, self.sprites, fr.p, t_video, self.dim)
        elif fr.phase == "outro":
            draw_outro(scr, self.card, self.result.winner, self.sprites, fr.p, t_video, self.dim, self.rays)
            self.particles.draw(scr, 0, 0)  # confetti keeps raining over the winner card

        if self.flash > 0.02 and self.impact == 0:
            self.flash_surf.set_alpha(int(220 * self.flash))
            scr.blit(self.flash_surf, (0, 0))


def render_video(card: MatchCard, result: BattleResult, out_path: Path, video_cfg: dict, audio_cfg: dict) -> Path:
    return Renderer(card, result, video_cfg, audio_cfg).render(out_path)
