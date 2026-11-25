"""Map simulation time onto video frames.

Adds the "game feel" timing: hit-stop (a few frozen frames on impact),
slow motion right before the knock-out, a long freeze on the KO, plus the
intro and outro sections. Audio uses the same mapping, so sound and
picture stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..sim.world import BattleResult, Event

HOLD = {"hit": 4, "parry": 2}
BIG_HIT_HOLD = 7
KO_HOLD = 18
SLOWMO_WINDOW = 0.55   # seconds of sim time before the KO
SLOWMO_RATE = 0.28


@dataclass
class Frame:
    t: float          # simulation time shown on this frame
    phase: str        # intro | fight | post | outro
    p: float = 0.0    # progress inside the phase, 0..1
    hold: bool = False


@dataclass
class Timeline:
    fps: int
    frames: list[Frame]
    events_at: dict[int, list[Event]] = field(default_factory=dict)
    fight_start: int = 0
    ko_frame: int = -1
    outro_start: int = 0

    @property
    def duration(self) -> float:
        return len(self.frames) / self.fps

    def event_time(self, frame_idx: int) -> float:
        return frame_idx / self.fps


def build_timeline(result: BattleResult, fps: int, intro_s: float, post_s: float, outro_s: float,
                   slowmo_window: float = SLOWMO_WINDOW, ko_hold: int = KO_HOLD) -> Timeline:
    frames: list[Frame] = []
    events_at: dict[int, list[Event]] = {}

    n_intro = round(intro_s * fps)
    for i in range(n_intro):
        frames.append(Frame(0.0, "intro", i / max(1, n_intro - 1)))
    fight_start = len(frames)

    evs = sorted(result.events, key=lambda e: e.t)
    ei = 0
    t = 0.0
    end = result.duration
    ko_frame = -1
    step = 1.0 / fps

    def add_event_frames(e: Event):
        nonlocal ko_frame
        idx = len(frames)
        events_at.setdefault(idx, []).append(e)
        if e.kind == "ko":
            ko_frame = idx
            hold = ko_hold
        elif e.kind == "hit":
            hold = BIG_HIT_HOLD if (e.value >= 16 or e.combo >= 3) else HOLD["hit"]
        else:
            hold = HOLD.get(e.kind, 0)
        if hold:
            for _ in range(hold):
                frames.append(Frame(e.t, "fight", 0.0, hold=True))

    frames.append(Frame(0.0, "fight"))
    while t < end:
        rate = SLOWMO_RATE if (end - t) < slowmo_window and not result.timeout else 1.0
        nt = min(end, t + step * rate)
        # Events that happen between this frame and the next one
        while ei < len(evs) and evs[ei].t <= nt:
            e = evs[ei]
            ei += 1
            if e.kind in ("hit", "parry", "ko"):
                add_event_frames(e)
            else:
                events_at.setdefault(len(frames), []).append(e)
        frames.append(Frame(nt, "fight"))
        t = nt
    while ei < len(evs):  # anything stamped exactly at the end
        add_event_frames(evs[ei])
        ei += 1

    n_post = round(post_s * fps)
    for i in range(n_post):
        frames.append(Frame(end, "post", i / max(1, n_post - 1)))
    outro_start = len(frames)
    n_out = round(outro_s * fps)
    for i in range(n_out):
        frames.append(Frame(end, "outro", i / max(1, n_out - 1)))

    for f in frames[fight_start:outro_start]:
        if f.phase == "fight":
            f.p = f.t / end if end else 0.0

    return Timeline(fps=fps, frames=frames, events_at=events_at, fight_start=fight_start,
                    ko_frame=ko_frame, outro_start=outro_start)
