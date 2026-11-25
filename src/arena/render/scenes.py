"""HUD and full-screen scenes (intro, banners, KO, outro)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pygame

from ..data.teams import Team, luminance, readable_on_dark
from .draw import BallSprites, blit_center, fit_text, headline, text
from .effects import Color, brighten, darken, lerp_color

FORM_COLORS = {"W": (46, 204, 113), "D": (149, 165, 166), "L": (231, 76, 60)}
GOLD = (255, 200, 60)
LABEL = (205, 210, 230)


@dataclass
class MatchCard:
    league: str
    tag: str                       # TONIGHT | TODAY | LEGENDS CLASH
    home: Team
    away: Team
    form: tuple[str, str] = ("", "")
    win_prob: tuple[float, float] | None = None
    cta: str = "WHO WINS TONIGHT?"
    sub_cta: str = "DROP YOUR SCORE IN THE COMMENTS"
    brand: str = ""
    record: tuple[int, int] | None = None   # (correct, total) past arena calls
    teams: list = field(default_factory=list)

    def __post_init__(self):
        self.teams = [self.home, self.away]


def ease_out_back(x: float, s: float = 1.7) -> float:
    x = max(0.0, min(1.0, x)) - 1
    return x * x * ((s + 1) * x + s) + 1


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_in(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x ** 3


def seg(p: float, a: float, b: float) -> float:
    """Progress of p inside [a, b] clamped to 0..1."""
    return max(0.0, min(1.0, (p - a) / (b - a))) if b > a else float(p >= a)


def _round_rect(screen, color, rect, radius):
    pygame.draw.rect(screen, color, rect, border_radius=radius)


def bar_color(team: Team) -> Color:
    c = readable_on_dark(team.primary, team.secondary)
    return c if luminance(c) >= 0.18 else (230, 230, 230)


# ---------------------------------------------------------------------- HUD
def draw_hud(screen, card: MatchCard, hp: list[float], trail: list[float], t: float, alpha: float = 1.0,
             levels: list[int] | None = None):
    if alpha <= 0:
        return
    layer = screen if alpha >= 1 else pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    W = screen.get_width()
    bar_w, bar_h, y = 420, 50, 300
    xs = (66, W - 66 - bar_w)
    for i, team in enumerate(card.teams):
        x = xs[i]
        col = bar_color(team)
        name = fit_text(team.name.upper(), 58, bar_w, color=(255, 255, 255), outline=3, shadow=4)
        nx = x - 3 if i == 0 else x + bar_w - name.get_width() + 3
        layer.blit(name, (nx, y - 84))
        # frame + track
        _round_rect(layer, (8, 9, 16), (x - 6, y - 6, bar_w + 12, bar_h + 12), 16)
        _round_rect(layer, (38, 40, 56), (x, y, bar_w, bar_h), 11)
        frac = max(0.0, hp[i]) / 100
        tfrac = max(0.0, trail[i]) / 100
        tw, fw = int(bar_w * tfrac), int(bar_w * frac)
        if tw > fw:
            tx = x + fw if i == 0 else x + bar_w - tw
            _round_rect(layer, (255, 244, 220), (tx, y, tw - fw, bar_h), 11)
        if fw > 0:
            fx = x if i == 0 else x + bar_w - fw
            fill = col
            if frac < 0.25:
                pulse = 0.5 + 0.5 * math.sin(t * 18)
                fill = lerp_color(col, (255, 60, 60), pulse * 0.65)
            _round_rect(layer, darken(fill, 0.25), (fx, y, fw, bar_h), 11)
            _round_rect(layer, fill, (fx, y, fw, bar_h - 10), 11)
            if fw > 16:
                _round_rect(layer, brighten(fill, 0.45), (fx + 8, y + 6, fw - 16, 8), 4)
        num = text(str(int(math.ceil(max(0.0, hp[i])))), 40, (255, 255, 255), outline=3, face="body")
        blit_center(layer, num, x + 48 if i == 0 else x + bar_w - 48, y + bar_h / 2)
        # weapon level pips (power-ups earned by landing hits)
        lvl = int(levels[i]) if levels else 0
        for j in range(10):
            px = x + 12 + j * 26 if i == 0 else x + bar_w - 12 - j * 26
            py = y + bar_h + 24
            pts = [(px, py - 9), (px + 9, py), (px, py + 9), (px - 9, py)]
            if j < lvl:
                pygame.draw.polygon(layer, GOLD if lvl >= 8 else col, pts)
                pygame.draw.polygon(layer, (255, 255, 255), pts, 2)
            else:
                pygame.draw.polygon(layer, (60, 63, 82), pts, 2)
    # VS badge
    cx, cy = W / 2, y + bar_h / 2
    pygame.draw.circle(layer, (8, 9, 16), (cx, cy), 40)
    pygame.draw.circle(layer, GOLD, (cx, cy), 40, 4)
    blit_center(layer, headline("VS", 46, GOLD, outline=2), cx, cy + 2)
    if layer is not screen:
        layer.set_alpha(int(255 * alpha))
        screen.blit(layer, (0, 0))


def draw_footer(screen, card: MatchCard, alpha: float = 1.0):
    W = screen.get_width()
    a = int(255 * alpha)
    blit_center(screen, text(card.league, 50, LABEL, outline=2, shadow=3), W / 2, 1496, alpha=a)
    blit_center(screen, text("ARENA  PREDICTION", 30, GOLD, outline=2, face="body"), W / 2, 1552, alpha=a)
    if card.brand:
        blit_center(screen, text(card.brand, 28, (150, 155, 175), face="body"), W / 2, 1596, alpha=a)


# ---------------------------------------------------------------------- intro
def _slab(screen, color: Color, accent: Color, y0: float, y1: float, x_off: float, slant: float = 140):
    pts = [(x_off - slant, y0), (1080 + x_off + slant, y0), (1080 + x_off, y1), (x_off - 2 * slant, y1)]
    pygame.draw.polygon(screen, color, pts)
    # bright accent edge along the bottom + subtle top highlight
    pygame.draw.line(screen, accent, pts[3], pts[2], 10)
    pygame.draw.line(screen, brighten(color, 0.25), pts[0], pts[1], 4)


def draw_intro(screen, card: MatchCard, sprites: list[BallSprites], p: float, t: float, dim_surface: pygame.Surface):
    W, H = screen.get_size()
    out = ease_in(seg(p, 0.84, 1.0))          # exit transition
    dim_surface.set_alpha(int(215 * (1 - out)))
    screen.blit(dim_surface, (0, 0))
    if out >= 1:
        return
    a = int(255 * (1 - seg(p, 0.86, 0.98)))

    # league + tag
    blit_center(screen, text(card.league, 62, LABEL, outline=3, shadow=4), W / 2, 380 - 300 * out,
                alpha=int(a * seg(p, 0.0, 0.1)))
    tk = ease_out_back(seg(p, 0.42, 0.55))
    if tk > 0:
        pill = text(card.tag, 44, (16, 16, 24))
        pw, ph = pill.get_width() + 64, pill.get_height() + 16
        r = pygame.Rect(0, 0, int(pw * tk), int(ph * tk))
        r.center = (W // 2, int(462 - 300 * out))
        _round_rect(screen, GOLD, r, 30)
        if tk > 0.6:
            blit_center(screen, pill, W / 2, 462 - 300 * out, alpha=a)

    # team slabs slide in from opposite sides (A top, B bottom)
    rows = ((560, 935, 250, 720, 650), (985, 1360, 830, 1170, 430))  # y0, y1, ball_x, ball_y, name_x
    for i, team in enumerate(card.teams):
        y0, y1, bx, by, nx = rows[i]
        k = ease_out(seg(p, 0.0 + i * 0.05, 0.22 + i * 0.05))
        side = -1 if i == 0 else 1
        x_off = side * (1 - k) * 1400 + side * out * 1400
        _slab(screen, darken(team.primary, 0.45), brighten(team.secondary, 0.1), y0, y1, x_off)
        bk = ease_out_back(seg(p, 0.12 + i * 0.05, 0.32 + i * 0.05))
        if bk > 0:
            sprites[i].draw(screen, bx + x_off, by, roll=(1 - bk) * 5 * side, scale=1.9 * bk)
        nk = ease_out(seg(p, 0.2 + i * 0.05, 0.34 + i * 0.05))
        if nk > 0:
            name = fit_text(team.name.upper(), 96, 520, color=(255, 255, 255), outline=4, shadow=6)
            blit_center(screen, name, nx + x_off - side * (1 - nk) * 120, by - 28, alpha=int(a * nk))
        form = (card.form[i] if card.form else "")[-5:]
        for j, ch in enumerate(form):
            pk = ease_out_back(seg(p, 0.36 + j * 0.03, 0.46 + j * 0.03))
            if pk <= 0:
                continue
            cx = nx + x_off + (j - (len(form) - 1) / 2) * 46
            col = FORM_COLORS.get(ch, (120, 120, 120))
            pygame.draw.circle(screen, (8, 9, 16), (cx, by + 62), int(19 * pk))
            pygame.draw.circle(screen, col, (cx, by + 62), int(15 * pk))
            pygame.draw.circle(screen, brighten(col, 0.5), (cx - 4, by + 57), int(5 * pk))

    # VS slam on the seam
    vk = seg(p, 0.28, 0.36)
    if vk > 0 and out < 1:
        scale = (1 + 2.4 * (1 - ease_out(vk))) * (1 - out)
        blit_center(screen, headline("VS", 190, GOLD, outline=8), W / 2, 960, scale=max(0.01, scale), alpha=a)

    # win probability bar
    if card.win_prob:
        bk = ease_out(seg(p, 0.5, 0.72))
        if bk > 0:
            bw, bh, by = 800, 30, 1478
            bx = (W - bw) / 2
            p0 = card.win_prob[0]
            c0, c1 = bar_color(card.home), bar_color(card.away)
            _round_rect(screen, (8, 9, 16), (bx - 5, by - 5, bw + 10, bh + 10), 20)
            left = int(bw * p0 * bk)
            right = int(bw * (1 - p0) * bk)
            if left:
                _round_rect(screen, c0, (bx, by, left, bh), 15)
            if right:
                _round_rect(screen, c1, (bx + bw - right, by, right, bh), 15)
            pa = int(a * bk)
            blit_center(screen, text(f"{round(p0 * 100)}%", 56, (255, 255, 255), outline=3, shadow=3), bx + 60, by - 42, alpha=pa)
            blit_center(screen, text(f"{round((1 - p0) * 100)}%", 56, (255, 255, 255), outline=3, shadow=3), bx + bw - 60, by - 42, alpha=pa)
            blit_center(screen, text("WIN CHANCE", 32, LABEL, outline=2, face="body"), W / 2, by - 40, alpha=pa)


# ---------------------------------------------------------------------- banners
def draw_banner(screen, label: str, age: float, dur: float, color: Color, y: float, size: int = 120):
    if age < 0 or age > dur:
        return
    k_in = ease_out_back(min(1.0, age / 0.16), 2.2)
    fade = 1.0 if age < dur - 0.25 else max(0.0, (dur - age) / 0.25)
    scale = 0.35 + 0.65 * k_in + 0.04 * max(0.0, age - 0.16)  # keeps creeping in, feels alive
    blit_center(screen, headline(label, size, color, outline=7), screen.get_width() / 2, y, scale=scale,
                alpha=int(255 * fade))


# ---------------------------------------------------------------------- outro
def draw_outro(screen, card: MatchCard, winner: int, sprites: list[BallSprites], p: float, t: float,
               dim_surface: pygame.Surface, rays: pygame.Surface):
    W, H = screen.get_size()
    fin = seg(p, 0.0, 0.10)
    dim_surface.set_alpha(int(225 * fin))
    screen.blit(dim_surface, (0, 0))
    team = card.teams[winner]
    col = bar_color(team)

    rk = ease_out(seg(p, 0.02, 0.18))
    if rk > 0:
        r = pygame.transform.rotozoom(rays, t * 25, 0.6 + 0.45 * rk)
        screen.blit(r, (W / 2 - r.get_width() / 2, 800 - r.get_height() / 2), special_flags=pygame.BLEND_ADD)

    blit_center(screen, text("ARENA PREDICTION", 40, GOLD, outline=3, face="body"), W / 2, 440,
                alpha=int(255 * seg(p, 0.03, 0.12)))
    if card.record:
        ok, n = card.record
        blit_center(screen, text(f"ARENA RECORD  {ok}/{n}", 30, LABEL, outline=2, face="body"), W / 2, 490,
                    alpha=int(255 * seg(p, 0.06, 0.16)))
    bk = ease_out_back(seg(p, 0.04, 0.2))
    if bk > 0:
        bob = math.sin(t * 3) * 8
        sprites[winner].draw(screen, W / 2, 790 + bob, roll=math.sin(t * 2) * 0.25, scale=2.6 * bk)
    nk = ease_out_back(seg(p, 0.12, 0.24), 2.0)
    if nk > 0:
        name = fit_text(team.name.upper(), 150, 980, color=col, outline=7, shadow=8,
                        gradient=(brighten(col, 0.7), col))
        blit_center(screen, name, W / 2, 1040, scale=0.4 + 0.6 * nk)
        blit_center(screen, headline("WINS", 84, (255, 255, 255), outline=5), W / 2, 1196, alpha=int(255 * nk))
    ck = ease_out_back(seg(p, 0.26, 0.38))
    if ck > 0:
        pulse = 1 + 0.035 * math.sin(t * 7)
        blit_center(screen, headline(card.cta, 84, GOLD, outline=6), W / 2, 1330, scale=pulse * ck)
        blit_center(screen, text(card.sub_cta, 36, LABEL, outline=2, face="body"), W / 2, 1410,
                    alpha=int(255 * seg(p, 0.3, 0.42)))
        ay = 1468 + math.sin(t * 6) * 10
        pygame.draw.polygon(screen, (8, 9, 16), [(W / 2 - 34, ay - 4), (W / 2 + 34, ay - 4), (W / 2, ay + 34)])
        pygame.draw.polygon(screen, GOLD, [(W / 2 - 26, ay), (W / 2 + 26, ay), (W / 2, ay + 26)])
    if card.brand:
        blit_center(screen, text(card.brand, 30, (150, 155, 175), face="body"), W / 2, 1560, alpha=int(255 * fin))


def make_rays(color: Color, radius: int = 700, n: int = 16) -> pygame.Surface:
    size = radius * 2
    surf = pygame.Surface((size, size))
    surf.fill((0, 0, 0))
    c = (radius, radius)
    dim = darken(color, 0.7)
    for i in range(n):
        a0 = i * 2 * math.pi / n
        a1 = a0 + math.pi / n
        pygame.draw.polygon(surf, dim, [c, (c[0] + math.cos(a0) * radius, c[1] + math.sin(a0) * radius),
                                        (c[0] + math.cos(a1) * radius, c[1] + math.sin(a1) * radius)])
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    px = pygame.surfarray.pixels3d(surf)
    px[...] = (px * np.clip(1 - d, 0, 1).T[..., None] ** 1.2).astype(np.uint8)
    del px
    return surf
