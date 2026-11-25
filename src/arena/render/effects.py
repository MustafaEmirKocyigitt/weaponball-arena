"""Particles, glows, screen shake, floating text: the 'juice'."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import pygame

Color = tuple[int, int, int]


def lerp_color(a: Color, b: Color, k: float) -> Color:
    k = max(0.0, min(1.0, k))
    return (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k), int(a[2] + (b[2] - a[2]) * k))


def brighten(c: Color, k: float) -> Color:
    return lerp_color(c, (255, 255, 255), k)


def darken(c: Color, k: float) -> Color:
    return lerp_color(c, (0, 0, 0), k)


class GlowCache:
    """Pre-rendered radial glow sprites for additive blending."""

    LEVELS = 12

    def __init__(self):
        self._cache: dict = {}

    def get(self, color: Color, radius: int, intensity: float) -> pygame.Surface:
        radius = max(4, int(radius) // 4 * 4)
        lvl = max(1, min(self.LEVELS, round(intensity * self.LEVELS)))
        key = (color, radius, lvl)
        s = self._cache.get(key)
        if s is None:
            size = radius * 2
            yy, xx = np.mgrid[0:size, 0:size]
            d = np.sqrt((xx - radius + 0.5) ** 2 + (yy - radius + 0.5) ** 2) / radius
            fall = np.clip(1 - d, 0, 1) ** 2.2 * (lvl / self.LEVELS)
            arr = np.zeros((size, size, 3), dtype=np.uint8)
            for ch in range(3):
                arr[..., ch] = np.clip(fall * color[ch], 0, 255).astype(np.uint8)
            s = pygame.surfarray.make_surface(arr.swapaxes(0, 1))
            self._cache[key] = s
        return s

    def blit(self, target: pygame.Surface, color: Color, x: float, y: float, radius: float, intensity: float):
        if intensity <= 0.02:
            return
        s = self.get(color, radius, intensity)
        target.blit(s, (int(x - s.get_width() / 2), int(y - s.get_height() / 2)), special_flags=pygame.BLEND_ADD)


@dataclass
class Particle:
    kind: str
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: Color
    gravity: float = 0.0
    drag: float = 0.0
    rot: float = 0.0
    vrot: float = 0.0
    color2: Color | None = None


class Particles:
    def __init__(self, rng: random.Random, glow: GlowCache):
        self.rng = rng
        self.items: list[Particle] = []
        self.glow = glow

    # ---- spawners ----------------------------------------------------------
    def sparks(self, x, y, n, color: Color, speed=(500, 1300), life=(0.18, 0.45), size=4.0, direction=None, spread=math.pi):
        r = self.rng
        for _ in range(n):
            a = r.uniform(-math.pi, math.pi) if direction is None else direction + r.uniform(-spread, spread)
            v = r.uniform(*speed)
            lf = r.uniform(*life)
            self.items.append(Particle("spark", x, y, math.cos(a) * v, math.sin(a) * v, lf, lf,
                                       size * r.uniform(0.7, 1.3), color, gravity=600, drag=3.5))

    def chunks(self, x, y, n, color: Color, color2: Color, speed=(150, 650), life=(0.5, 1.0), size=(5, 12)):
        r = self.rng
        for _ in range(n):
            a = r.uniform(-math.pi, math.pi)
            v = r.uniform(*speed)
            lf = r.uniform(*life)
            c = color if r.random() < 0.65 else color2
            self.items.append(Particle("chunk", x, y, math.cos(a) * v, math.sin(a) * v, lf, lf,
                                       r.uniform(*size), c, gravity=1400, drag=1.2,
                                       rot=r.uniform(0, 6.28), vrot=r.uniform(-12, 12)))

    def ring(self, x, y, color: Color, max_r=140, life=0.35, width=10):
        self.items.append(Particle("ring", x, y, 0, 0, life, life, max_r, color, rot=width))

    def flare(self, x, y, color: Color, radius=160, life=0.25):
        self.items.append(Particle("flare", x, y, 0, 0, life, life, radius, color))

    def slash(self, x, y, angle: float, color: Color, length=260, life=0.22, width=16):
        """Bright streak across the impact point (drawn additively)."""
        self.items.append(Particle("slash", x, y, 0, 0, life, life, length, color, rot=angle, vrot=width))

    def smoke(self, x, y, n=1):
        r = self.rng
        for _ in range(n):
            lf = r.uniform(0.6, 1.1)
            self.items.append(Particle("smoke", x + r.uniform(-20, 20), y + r.uniform(-20, 20),
                                       r.uniform(-30, 30), r.uniform(-120, -60), lf, lf,
                                       r.uniform(14, 24), (70, 72, 82), drag=1.0))

    def confetti(self, w, n, colors: list[Color], y=-20):
        r = self.rng
        for _ in range(n):
            lf = r.uniform(2.0, 3.5)
            self.items.append(Particle("confetti", r.uniform(0, w), y + r.uniform(-200, 0),
                                       r.uniform(-120, 120), r.uniform(150, 450), lf, lf,
                                       r.uniform(9, 16), r.choice(colors), gravity=260, drag=0.9,
                                       rot=r.uniform(0, 6.28), vrot=r.uniform(-9, 9)))

    _smoke_cache: dict = {}

    def _smoke_sprite(self, r: int) -> pygame.Surface:
        r = max(4, r // 2 * 2)
        s = self._smoke_cache.get(r)
        if s is None:
            size = r * 2
            yy, xx = np.mgrid[0:size, 0:size]
            d = np.sqrt((xx - r + 0.5) ** 2 + (yy - r + 0.5) ** 2) / r
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            s.fill((70, 72, 82, 255))
            pa = pygame.surfarray.pixels_alpha(s)
            pa[...] = (np.clip(1 - d, 0, 1) ** 1.5 * 255).astype(np.uint8)
            del pa
            self._smoke_cache[r] = s
        return s

    # ---- simulation --------------------------------------------------------
    def update(self, dt: float):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            if p.drag:
                f = math.exp(-p.drag * dt)
                p.vx *= f
                p.vy *= f
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.vrot * dt
            alive.append(p)
        self.items = alive

    # ---- drawing -----------------------------------------------------------
    def draw(self, screen: pygame.Surface, ox: float, oy: float):
        for p in self.items:
            k = p.life / p.max_life
            x, y = p.x + ox, p.y + oy
            if p.kind == "spark":
                speed = math.hypot(p.vx, p.vy)
                ln = min(60.0, speed * 0.03 + 4)
                if speed > 0:
                    ex, ey = x - p.vx / speed * ln, y - p.vy / speed * ln
                else:
                    ex, ey = x, y
                c = lerp_color(p.color, (255, 255, 240), k * 0.8)
                pygame.draw.line(screen, c, (x, y), (ex, ey), max(1, int(p.size * (0.4 + 0.6 * k))))
            elif p.kind == "chunk":
                s = p.size * (0.35 + 0.65 * k)
                ca, sa = math.cos(p.rot), math.sin(p.rot)
                pts = [(x + (ca * dx - sa * dy) * s, y + (sa * dx + ca * dy) * s)
                       for dx, dy in ((-1, -0.7), (1, -0.9), (0.8, 0.9), (-0.9, 0.6))]
                pygame.draw.polygon(screen, p.color, pts)
            elif p.kind == "smoke":
                s = int(p.size * (1.0 + 1.4 * (1 - k)))
                spr = self._smoke_sprite(s)
                spr.set_alpha(int(150 * k))
                screen.blit(spr, (x - s, y - s))
            elif p.kind == "confetti":
                s = p.size
                sq = abs(math.cos(p.rot * 1.7))  # flip effect
                ca, sa = math.cos(p.rot), math.sin(p.rot)
                pts = [(x + (ca * dx * s - sa * dy * s * 0.55 * sq), y + (sa * dx * s + ca * dy * s * 0.55 * sq))
                       for dx, dy in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))]
                pygame.draw.polygon(screen, p.color, pts)

    def draw_additive(self, screen: pygame.Surface, ox: float, oy: float):
        for p in self.items:
            k = p.life / p.max_life
            x, y = p.x + ox, p.y + oy
            if p.kind == "ring":
                rr = p.size * (1 - k ** 2) + 8
                w = max(1, int(p.rot * k))
                pygame.draw.circle(screen, lerp_color((0, 0, 0), p.color, k), (int(x), int(y)), int(rr), w)
            elif p.kind == "flare":
                self.glow.blit(screen, p.color, x, y, p.size * (0.7 + 0.3 * k), k)
            elif p.kind == "slash":
                grow = min(1.0, (1 - k) / 0.25 + 0.3)
                ln = p.size * grow / 2
                w = p.vrot * k
                ux, uy = math.cos(p.rot), math.sin(p.rot)
                nx, ny = -uy, ux
                pts = [(x - ux * ln, y - uy * ln), (x + nx * w, y + ny * w),
                       (x + ux * ln, y + uy * ln), (x - nx * w, y - ny * w)]
                pygame.draw.polygon(screen, lerp_color((0, 0, 0), p.color, k), pts)
                core = [(x - ux * ln * 0.8, y - uy * ln * 0.8), (x + nx * w * 0.35, y + ny * w * 0.35),
                        (x + ux * ln * 0.8, y + uy * ln * 0.8), (x - nx * w * 0.35, y - ny * w * 0.35)]
                pygame.draw.polygon(screen, lerp_color((0, 0, 0), (255, 255, 255), k), core)
            elif p.kind == "spark" and k > 0.5:
                self.glow.blit(screen, p.color, x, y, 18, (k - 0.5) * 0.8)


class FloatingTexts:
    """Damage numbers that pop and float up."""

    def __init__(self):
        self.items: list[list] = []  # [surface, x, y, vy, life, max_life]

    def add(self, surf: pygame.Surface, x: float, y: float, life=0.9):
        self.items.append([surf, x, y, -260.0, life, life])

    def update(self, dt: float):
        alive = []
        for it in self.items:
            it[4] -= dt
            if it[4] <= 0:
                continue
            it[2] += it[3] * dt
            it[3] *= math.exp(-3.5 * dt)
            alive.append(it)
        self.items = alive

    def draw(self, screen: pygame.Surface, ox: float, oy: float):
        for surf, x, y, _, life, max_life in self.items:
            age = max_life - life
            pop = 1.0 + 0.6 * max(0.0, 1 - age / 0.12)
            s = surf if pop == 1.0 else pygame.transform.smoothscale_by(surf, pop)
            if life < 0.25:
                s = s.copy()
                s.set_alpha(int(255 * life / 0.25))
            screen.blit(s, (x + ox - s.get_width() / 2, y + oy - s.get_height() / 2))


class Shake:
    def __init__(self, seed: int):
        r = random.Random(seed)
        self.phase = [r.uniform(0, 100) for _ in range(4)]
        self.amp = 0.0
        self.t = 0.0

    def kick(self, amount: float):
        self.amp = max(self.amp, amount)

    def update(self, dt: float):
        self.t += dt
        self.amp *= math.exp(-dt / 0.11)

    def offset(self) -> tuple[float, float]:
        if self.amp < 0.3:
            return 0.0, 0.0
        p = self.phase
        x = math.sin(self.t * 71 + p[0]) * 0.6 + math.sin(self.t * 113 + p[1]) * 0.4
        y = math.sin(self.t * 83 + p[2]) * 0.6 + math.sin(self.t * 127 + p[3]) * 0.4
        return x * self.amp, y * self.amp
