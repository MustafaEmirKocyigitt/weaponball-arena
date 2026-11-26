"""Today's posting plan -> TODAY.md (readable on GitHub, also from a phone).

Runs the real selection logic for every slot at the time it will run,
without rendering or touching the real history.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_config
from .data import history
from .pipeline import local_today, run_daily

TODAY_PATH = ROOT / "TODAY.md"
SLOT_TIMES = {"early": (11, 0), "main": (15, 35), "late": (18, 15)}   # when each workflow slot runs (UTC)
POST_AT = {"early": (11, 5), "main": (16, 0), "late": (18, 20)}       # roughly when it goes live (UTC)


def _tr(dt: datetime, cfg: dict) -> str:
    return (dt + timedelta(hours=cfg.get("timezone_offset_hours", 3))).strftime("%H:%M")


def build_plan(day: date | None = None, log=lambda *_: None) -> str:
    cfg = load_config()
    day = day or local_today(cfg)
    labels = {k: v.get("label", k) for k, v in cfg.get("variants", {}).get("defs", {}).items()}
    labels["night"] = "European night (3 mini battles)"
    tmp = Path(tempfile.mkdtemp())
    hp = tmp / "history.json"
    if history.HISTORY_PATH.exists():
        shutil.copy(history.HISTORY_PATH, hp)
    already = {e.get("slot", "main") for e in history.posted_on(history.load(hp), day)}

    rows = []
    for slot in ("early", "main", "late"):
        hh, mm = SLOT_TIMES[slot]
        live = datetime(day.year, day.month, day.day, *POST_AT[slot], tzinfo=timezone.utc)
        when = f"{_tr(live, cfg)}"
        if slot in already or (slot == "late" and "night" in already):
            rows.append(f"| {slot} | {when} | ✅ already posted | | | | |")
            continue
        now = datetime(day.year, day.month, day.day, hh, mm, tzinfo=timezone.utc)
        try:
            out = run_daily(day, tmp / "out", render=False, log=log, history_path=hp, slot=slot, now=now)
        except Exception as e:  # the plan must never break the day
            rows.append(f"| {slot} | {when} | ⚠️ could not plan: {e} | | | | |")
            continue
        if out is None:
            rows.append(f"| {slot} | {when} | — no post (no big match in this window) | | | | |")
            continue
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        draft = labels.get(meta.get("variant", ""), meta.get("variant", ""))
        if meta.get("slot") == "night":
            matches = "<br>".join(f"{m['home']} vs {m['away']}" for m in meta["matches"])
            preds = "<br>".join(m["winner"] for m in meta["matches"])
            rows.append(f"| night | {when} | {matches} | {meta['title']} | | {draft} | {preds} |")
        else:
            ko = meta.get("kickoff_utc")
            ko_tr = _tr(datetime.fromisoformat(ko), cfg) if ko else "–"
            rows.append(f"| {slot} | {when} | {meta['home']} vs {meta['away']} | {meta['league']} | {ko_tr} | "
                        f"{draft} | {meta['winner']} |")
    shutil.rmtree(tmp, ignore_errors=True)

    stamp = datetime.now(timezone.utc)
    return "\n".join([
        f"# 📅 Today's plan: {day:%A %d %B %Y}",
        f"_Generated {stamp:%Y-%m-%d %H:%M} UTC · times are Turkey time (UTC+3) · "
        f"bonus slots only post for big matches_",
        "",
        "| Slot | Goes live (TR) | Match | Competition | Kick-off (TR) | Draft | Arena prediction |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "Main post every day at 19:00 TR (16:00 UTC). Details: [README](README.md) · "
        "Draft results: [REPORT.md](REPORT.md)",
        "",
    ])


def write_plan(day: date | None = None, log=print) -> Path:
    TODAY_PATH.write_text(build_plan(day, log), encoding="utf-8")
    log(f"[plan] wrote {TODAY_PATH.name}")
    return TODAY_PATH
