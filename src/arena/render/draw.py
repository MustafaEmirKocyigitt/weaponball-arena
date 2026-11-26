"""Drawing primitives: fonts, text, ball sprites, weapons, background, arena."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pygame

from ..config import ASSETS
from ..data.teams import Team, luminance
from ..sim.world import BALL_R, GAP
from .effects import Color, brighten, darken, lerp_color

STEEL = (226, 232, 242)
STEEL_DARK = (120, 128, 145)
WOOD = (122, 84, 52)
INK = (12, 12, 18)


# ---------------------------------------------------------------- fonts / text
# Two typefaces: a heavy condensed display face for headlines / names /
# numbers that must punch, and a bold body face for labels. Both are OFL
# fonts in assets/fonts; if they are missing we fall back to pygame's font.
FACES = {
    "display": ("Anton-Regular.ttf", False),
    "body": ("Oswald-Variable.ttf", True),   # variable font: synthetic bold on the default instance
}


def _face_path(face: str):
    name, _ = FACES.get(face, FACES["display"])
    p = ASSETS / "fonts" / name
    return str(p) if p.exists() else None


@lru_cache(maxsize=128)
def font(size: int, face: str = "display") -> pygame.font.Font:
    path = _face_path(face)
    f = pygame.font.Font(path, size)
    if path is None or FACES.get(face, (None, False))[1]:
        f.set_bold(True)
    return f


_text_cache: dict = {}


def _gradient_fill(base: pygame.Surface, top: Color, bottom: Color) -> pygame.Surface:
    """Recolor a white text render with a vertical gradient."""
    h = base.get_height()
    grad = pygame.Surface((1, h), pygame.SRCALPHA)
    for y in range(h):
        k = y / max(1, h - 1)
        # bright band on top half, richer color at the bottom
        k = min(1.0, max(0.0, (k - 0.25) / 0.6))
        grad.set_at((0, y), (*lerp_color(top, bottom, k), 255))
    grad = pygame.transform.scale(grad, base.get_size())
    out = base.copy()
    out.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def text(s: str, size: int, color: Color = (255, 255, 255), outline: int = 0,
         outline_color: Color = INK, face: str = "display", shadow: int = 0,
         gradient: tuple[Color, Color] | None = None) -> pygame.Surface:
    """Rendered, cached text with optional outline, hard drop shadow and gradient fill."""
    key = (s, size, color, outline, outline_color, face, shadow, gradient)
    surf = _text_cache.get(key)
    if surf is not None:
        return surf
    f = font(size, face)
    if gradient:
        base = _gradient_fill(f.render(s, True, (255, 255, 255)), *gradient)
    else:
        base = f.render(s, True, color)
    pad = outline
    w, h = base.get_width() + pad * 2, base.get_height() + pad * 2 + shadow
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    if outline or shadow:
        o = f.render(s, True, outline_color)
        offsets = [(dx, dy) for dx in range(-outline, outline + 1) for dy in range(-outline, outline + 1)
                   if dx * dx + dy * dy <= outline * outline + 1] or [(0, 0)]
        if shadow:
            sh = f.render(s, True, (0, 0, 0))
            sh.set_alpha(170)
            for dx, dy in offsets:
                surf.blit(sh, (dx + pad, dy + pad + shadow))
        for dx, dy in offsets:
            if outline:
                surf.blit(o, (dx + pad, dy + pad))
    surf.blit(base, (pad, pad))
    if len(_text_cache) > 800:
        _text_cache.clear()
    _text_cache[key] = surf
    return surf


def headline(s: str, size: int, color: Color, outline: int = 6) -> pygame.Surface:
    """Big punchy title: gradient from near-white to the color, thick outline, drop shadow."""
    return text(s, size, color, outline=outline, gradient=(brighten(color, 0.75), color),
                shadow=max(4, outline + 2))


def blit_center(screen, surf, x, y, scale: float = 1.0, alpha: int = 255):
    if scale != 1.0:
        surf = pygame.transform.smoothscale_by(surf, max(0.01, scale))
    if alpha < 255:
        surf = surf.copy()
        surf.set_alpha(max(0, alpha))
    screen.blit(surf, (x - surf.get_width() / 2, y - surf.get_height() / 2))


def fit_text(s: str, size: int, max_w: int, **kw) -> pygame.Surface:
    surf = text(s, size, **kw)
    while surf.get_width() > max_w and size > 16:
        size -= 4
        surf = text(s, size, **kw)
    return surf


# ---------------------------------------------------------------- ball sprites
def _circle_alpha(size: int, radius: float) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - size / 2 + 0.5) ** 2 + (yy - size / 2 + 0.5) ** 2)
    return (np.clip(radius - d + 0.5, 0, 1) * 255).astype(np.uint8)


class BallSprites:
    """Pre-rendered layers for one team's ball."""

    SS = 3  # supersampling

    def __init__(self, team: Team, radius: float = BALL_R):
        self.team = team
        self.r = radius
        size = int(radius * 2 + 6)
        self.size = size
        big = size * self.SS
        R = radius * self.SS

        # Body variants: pristine, cracked (<55 HP), shattered (<25 HP)
        self.bodies = [self._make_body(team, big, R, n) for n in (0, 3, 7)]
        self.body = self.bodies[0]
        self._finish(team, big, R, size)

    def _make_body(self, team: Team, big: int, R: float, cracks: int) -> pygame.Surface:
        size = self.size
        # Body: primary color + diagonal band of secondary + thin pin-stripes
        body = pygame.Surface((big, big), pygame.SRCALPHA)
        body.fill((*team.primary, 255))
        band = big * 0.34
        c = big / 2
        pygame.draw.polygon(body, team.secondary, [(0, c - band / 2), (big, c - band / 2), (big, c + band / 2), (0, c + band / 2)])
        edge = lerp_color(team.secondary, team.primary, 0.5)
        for off in (-band / 2, band / 2):
            pygame.draw.line(body, edge, (0, c + off), (big, c + off), max(2, int(big * 0.012)))
        # inner shading: darker toward the rim
        yy, xx = np.mgrid[0:big, 0:big]
        d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / R
        shade = np.clip(1 - 0.35 * np.clip(d - 0.55, 0, 1) / 0.45, 0, 1)
        px = pygame.surfarray.pixels3d(body)
        px[...] = (px * shade.T[..., None]).astype(np.uint8)
        del px
        if cracks:
            import random as _r
            rng = _r.Random(team.key or team.name)
            for _ in range(cracks):
                a = rng.uniform(0, 2 * math.pi)
                x, y = c + math.cos(a) * R, c + math.sin(a) * R
                heading = a + math.pi + rng.uniform(-0.5, 0.5)
                pts = [(x, y)]
                for _ in range(rng.randint(3, 5)):
                    step = R * rng.uniform(0.15, 0.3)
                    heading += rng.uniform(-0.7, 0.7)
                    x, y = x + math.cos(heading) * step, y + math.sin(heading) * step
                    pts.append((x, y))
                pygame.draw.lines(body, (*INK, 255), False, pts, int(self.SS * 3.2))
                light = brighten(team.primary, 0.5)
                pygame.draw.lines(body, (*light, 255), False, [(px + self.SS * 2, py + self.SS * 2) for px, py in pts],
                                  self.SS)
        pa = pygame.surfarray.pixels_alpha(body)
        pa[...] = _circle_alpha(big, R).T
        del pa
        return pygame.transform.smoothscale(body, (size, size))

    def _finish(self, team: Team, big: int, R: float, size: int):
        c = big / 2
        radius = self.r
        # Rim + gloss (does not rotate: light comes from top-left)
        over = pygame.Surface((big, big), pygame.SRCALPHA)
        rim = darken(team.primary, 0.55) if luminance(team.primary) > 0.3 else brighten(team.primary, 0.35)
        pygame.draw.circle(over, (*rim, 255), (c, c), R, max(3, int(R * 0.07)))
        gloss = pygame.Surface((big, big), pygame.SRCALPHA)
        pygame.draw.ellipse(gloss, (255, 255, 255, 70), (c - R * 0.62, c - R * 0.78, R * 0.9, R * 0.55))
        over.blit(gloss, (0, 0))
        self.overlay = pygame.transform.smoothscale(over, (size, size))

        # White silhouette for hit flashes
        white = pygame.Surface((big, big), pygame.SRCALPHA)
        white.fill((255, 255, 255, 255))
        wa = pygame.surfarray.pixels_alpha(white)
        wa[...] = _circle_alpha(big, R).T
        del wa
        self.white = pygame.transform.smoothscale(white, (size, size))

        self.label = text(team.short, int(radius * 0.72), (255, 255, 255), outline=4)
        self._scaled: dict = {}

    def draw(self, screen, x, y, roll: float, scale: float = 1.0, flash: float = 0.0, hp: float = 100.0):
        src = self.bodies[2] if hp < 25 else self.bodies[1] if hp < 55 else self.bodies[0]
        body = pygame.transform.rotozoom(src, -math.degrees(roll), scale)
        screen.blit(body, (x - body.get_width() / 2, y - body.get_height() / 2))
        ov = self.overlay if scale == 1.0 else pygame.transform.smoothscale_by(self.overlay, scale)
        screen.blit(ov, (x - ov.get_width() / 2, y - ov.get_height() / 2))
        lab = self.label if scale == 1.0 else pygame.transform.smoothscale_by(self.label, scale)
        screen.blit(lab, (x - lab.get_width() / 2, y - lab.get_height() / 2))
        if flash > 0:
            w = self.white if scale == 1.0 else pygame.transform.smoothscale_by(self.white, scale)
            w = w.copy()
            w.set_alpha(int(255 * min(1.0, flash)))
            screen.blit(w, (x - w.get_width() / 2, y - w.get_height() / 2))


# ---------------------------------------------------------------- weapons
def _poly(screen, color, pts, outline: Color | None = None):
    """Filled polygon with a bold dark cartoon outline (reads well on phones)."""
    pygame.draw.polygon(screen, INK, pts, 5)
    pygame.draw.polygon(screen, color, pts)
    pygame.draw.aalines(screen, INK, True, pts)
    if outline:
        pygame.draw.polygon(screen, outline, pts, 1)


def _poly_plain(screen, color, pts):
    pygame.draw.polygon(screen, color, pts)


def _shaft(screen, a, b, width, color):
    pygame.draw.line(screen, INK, a, b, width + 6)
    pygame.draw.line(screen, color, a, b, width)
    pygame.draw.line(screen, brighten(color, 0.3), a, b, max(1, width // 3))


def weapon_tip(kind: str, x, y, angle, length) -> list[tuple[float, float]]:
    r0 = BALL_R + GAP
    tips = []
    for k in range(2 if kind == "daggers" else 1):
        a = angle + k * math.pi
        tips.append((x + math.cos(a) * (r0 + length), y + math.sin(a) * (r0 + length)))
    return tips


def draw_weapon(screen, kind: str, team: Team, x, y, angle, length, level: int):
    r0 = BALL_R + GAP
    accent = team.secondary if luminance(team.secondary) > 0.12 else team.primary
    blades = 2 if kind == "daggers" else 1
    for k in range(blades):
        a = angle + k * math.pi
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux

        def P(along, side):
            return (x + ux * along + nx * side, y + uy * along + ny * side)

        base = r0
        tip = r0 + length
        shine = brighten(STEEL, 0.6)
        if kind in ("sword", "daggers"):
            w = 15 if kind == "sword" else 12
            taper = 30 if kind == "sword" else 20
            _poly(screen, STEEL, [P(base + 6, w), P(tip - taper, w), P(tip, 0), P(tip - taper, -w), P(base + 6, -w)])
            # two-tone bevel: darker half + bright edge
            _poly_plain(screen, STEEL_DARK, [P(base + 8, 0), P(tip - taper, 0), P(tip - 3, 0), P(tip - taper, -w + 3), P(base + 8, -w + 3)])
            pygame.draw.line(screen, shine, P(base + 10, w - 4), P(tip - taper, w - 4), 3)
            _poly(screen, accent, [P(base - 2, 28), P(base + 11, 28), P(base + 11, -28), P(base - 2, -28)])
        elif kind == "spear":
            _shaft(screen, P(base, 0), P(tip - 36, 0), 10, WOOD)
            for s in range(3):
                pygame.draw.line(screen, accent, P(base + 18 + s * 11, 7), P(base + 18 + s * 11, -7), 5)
            _poly(screen, STEEL, [P(tip - 46, 0), P(tip - 30, 18), P(tip, 0), P(tip - 30, -18)])
            _poly_plain(screen, STEEL_DARK, [P(tip - 44, 0), P(tip - 2, 0), P(tip - 30, -16)])
        elif kind == "hammer":
            _shaft(screen, P(base, 0), P(tip - 4, 0), 12, WOOD)
            head = [P(tip - 24, 34), P(tip + 22, 34), P(tip + 22, -34), P(tip - 24, -34)]
            _poly(screen, (150, 156, 170), head)
            _poly_plain(screen, (110, 116, 130), [P(tip - 24, -34), P(tip + 22, -34), P(tip + 22, -12), P(tip - 24, -12)])
            _poly(screen, accent, [P(tip - 7, 35), P(tip + 5, 35), P(tip + 5, -35), P(tip - 7, -35)])
        elif kind == "axe":
            _shaft(screen, P(base, 0), P(tip + 10, 0), 10, WOOD)
            blade = [P(tip - 20, 6), P(tip - 30, 40), P(tip, 52), P(tip + 30, 40), P(tip + 20, 6)]
            _poly(screen, STEEL, blade)
            pygame.draw.line(screen, shine, P(tip - 26, 43), P(tip + 26, 43), 4)
            _poly(screen, accent, [P(tip - 12, -4), P(tip + 12, -4), P(tip, -22)])


# ---------------------------------------------------------------- background / arena
def make_background(w: int, h: int, a: Color, b: Color, theme: dict | None = None) -> pygame.Surface:
    th = theme or {}
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = yy / h
    base = np.zeros((h, w, 3), np.float32)
    top = np.array(th.get("bg_top", (16, 18, 32)), np.float32)
    bottom = np.array(th.get("bg_bottom", (5, 6, 12)), np.float32)
    base[:] = top * (1 - t[..., None]) + bottom * t[..., None]
    for color, cx, cy in ((a, 0.0, 0.18), (b, 1.0, 0.82)):
        d = np.sqrt(((xx / w - cx) * 1.0) ** 2 + ((yy / h - cy) * 0.56) ** 2)
        g = np.clip(1 - d / 0.75, 0, 1) ** 2 * 0.22
        base += g[..., None] * np.array(color, np.float32)
    # vignette
    d = np.sqrt(((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2)
    base *= np.clip(1.1 - d * 0.9, 0.55, 1)[..., None]
    # subtle diagonal grain
    base += ((xx + yy) % 6 < 1).astype(np.float32)[..., None] * 3
    arr = np.clip(base, 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(arr.swapaxes(0, 1))


def make_floor(radius: int, theme: dict | None = None) -> pygame.Surface:
    th = theme or {}
    size = radius * 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    inner = np.array(th.get("floor_inner", (30, 34, 54)), np.float32)
    outer = np.array(th.get("floor_outer", (13, 15, 26)), np.float32)
    col = inner * (1 - d[..., None]) + outer * d[..., None]
    # texture: concentric rings + cross (classic), hex-ish grid (neon), cracks (lava)
    line = np.array(th.get("floor_line", (8, 8, 8)), np.float32)
    pattern = th.get("pattern", "rings")
    if pattern == "grid":
        tex = (((xx % 48) < 2) | ((yy % 48) < 2)).astype(np.float32)
    elif pattern == "cracks":
        ang = np.arctan2(yy - radius, xx - radius)
        tex = ((np.abs(np.sin(ang * 7 + d * 9)) < 0.05) | ((d * 6) % 1 < 0.02)).astype(np.float32)
    else:
        tex = (((d * 9) % 1 < 0.025) | (np.abs(xx - radius) < 1.2) | (np.abs(yy - radius) < 1.2)).astype(np.float32)
    col += tex[..., None] * line
    surf = pygame.surfarray.make_surface(np.clip(col, 0, 255).astype(np.uint8).swapaxes(0, 1)).convert_alpha()
    pa = pygame.surfarray.pixels_alpha(surf)
    pa[...] = _circle_alpha(size, radius - 1).T
    del pa
    return surf


def make_ring_glow(R: int, color: Color, width: float = 22.0) -> pygame.Surface:
    """Black-background glow ring meant for BLEND_ADD blitting."""
    pad = int(width * 3)
    size = (R + pad) * 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2)
    g = np.exp(-((d - R) / width) ** 2) * 0.55 + np.exp(-((d - R) / 4.0) ** 2) * 0.45
    arr = np.clip(g[..., None] * np.array(color, np.float32), 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(arr.swapaxes(0, 1))


def draw_ring(screen, cx, cy, R, color: Color):
    pygame.draw.circle(screen, color, (cx, cy), int(R + 3), 5)
    pygame.draw.circle(screen, brighten(color, 0.7), (cx, cy), int(R + 3), 2)
