"""A/B report: Instagram stats per video draft -> REPORT.md.

Stats keep growing for days, so each post is re-fetched until it is a week old.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_config
from .data import history

INSIGHTS_PATH = ROOT / "data" / "insights.json"
REPORT_PATH = ROOT / "REPORT.md"
METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
           "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def refresh_insights(ig, hist: list[dict], insights: dict, now: datetime, log=print) -> dict:
    seen = set()
    for e in hist:
        mid = e.get("media_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        posted = datetime.fromisoformat(e.get("posted_at") or f"{e['date']}T16:00:00+00:00")
        prev = insights.get(mid)
        if prev and now - posted > timedelta(days=8):
            continue  # final numbers already stored
        try:
            m = ig.insights(mid, METRICS)
        except Exception as ex:
            log(f"[report] {mid}: {ex}")
            continue
        insights[mid] = {"fetched_at": now.isoformat(), "metrics": m}
        log(f"[report] {e['date']} {e.get('slot', 'main')} {e.get('variant', '?')}: {m}")
    return insights


def _fmt(x, digits=1):
    return "–" if x is None else (f"{x:,.{digits}f}" if isinstance(x, float) else f"{x:,}")


def build_report(hist: list[dict], insights: dict, cfg: dict, now: datetime) -> str:
    labels = {k: v.get("label", k) for k, v in cfg.get("variants", {}).get("defs", {}).items()}
    labels["night"] = "Night · European night"
    posts = {}
    for e in hist:
        mid = e.get("media_id")
        if mid and mid in insights:
            p = posts.setdefault(mid, {"entry": e, "m": insights[mid]["metrics"], "hits": [], "n": 0})
            if e.get("outcome") in ("hit", "miss", "draw"):
                p["hits"].append(e["outcome"] == "hit")
    by_var = defaultdict(list)
    for p in posts.values():
        by_var[p["entry"].get("variant", "classic")].append(p)

    def avg(ps, key, scale=1.0):
        vals = [p["m"].get(key) for p in ps if p["m"].get(key) is not None]
        return sum(vals) / len(vals) * scale if vals else None

    def eng(ps):
        rates = []
        for p in ps:
            m = p["m"]
            views = m.get("views") or m.get("reach")
            inter = sum((m.get(k) or 0) for k in ("likes", "comments", "shares", "saved"))
            if views:
                rates.append(inter / views * 100)
        return sum(rates) / len(rates) if rates else None

    lines = [
        "# 📊 Draft report (A/B test)",
        f"_Updated {now:%Y-%m-%d %H:%M} UTC. Numbers keep growing for ~a week after each post._",
        "",
        "| Draft | Posts | Avg views | Avg watch time | Likes | Comments | Shares | Saves | Engagement | Predictions right |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    ranking = []
    for v, ps in sorted(by_var.items()):
        hits = [h for p in ps for h in p["hits"]]
        watch = avg(ps, "ig_reels_avg_watch_time", 0.001)
        e = eng(ps)
        lines.append(f"| {labels.get(v, v)} | {len(ps)} | {_fmt(avg(ps, 'views'), 0)} | "
                     f"{_fmt(watch)} s | {_fmt(avg(ps, 'likes'))} | {_fmt(avg(ps, 'comments'))} | "
                     f"{_fmt(avg(ps, 'shares'))} | {_fmt(avg(ps, 'saved'))} | {_fmt(e)} % | "
                     f"{sum(hits)}/{len(hits)} |")
        if v != "night":
            ranking.append((v, len(ps), watch, e))
    lines += ["", "## Verdict"]
    ready = [r for r in ranking if r[1] >= 3 and r[2] is not None]
    if len(ready) >= 2:
        best_watch = max(ready, key=lambda r: r[2])
        best_eng = max(ready, key=lambda r: r[3] or 0)
        lines.append(f"- Longest average watch time: **{labels.get(best_watch[0], best_watch[0])}** ({best_watch[2]:.1f} s)")
        lines.append(f"- Highest engagement: **{labels.get(best_eng[0], best_eng[0])}** ({(best_eng[3] or 0):.1f} %)")
        lines.append("- Watch time matters most for Reels reach; keep the leader, drop the weakest draft from "
                     "`variants.rotation` in config.yaml once every draft has ~5 posts.")
    else:
        lines.append("- Not enough data yet: wait until every draft has at least 3 posts with stats.")
    lines += ["", "## Posts", "", "| Date | Slot | Draft | Match | Views | Avg watch | Likes | Comments | Shares |",
              "|---|---|---|---|---|---|---|---|---|"]
    for p in sorted(posts.values(), key=lambda p: p["entry"]["date"], reverse=True)[:30]:
        e, m = p["entry"], p["m"]
        match = "European night" if e.get("slot") == "night" else f"{e['home']} vs {e['away']}"
        w = m.get("ig_reels_avg_watch_time")
        lines.append(f"| {e['date']} | {e.get('slot', 'main')} | {labels.get(e.get('variant', 'classic'), '?')} | {match} | "
                     f"{_fmt(m.get('views'))} | {_fmt(w / 1000 if w else None)} s | {_fmt(m.get('likes'))} | "
                     f"{_fmt(m.get('comments'))} | {_fmt(m.get('shares'))} |")
    return "\n".join(lines) + "\n"


def run_report(ig=None, log=print, now: datetime | None = None) -> Path:
    from .publish.instagram import Instagram

    cfg = load_config()
    now = now or datetime.now(timezone.utc)
    hist = history.load()
    insights = _load(INSIGHTS_PATH)
    insights = refresh_insights(ig or Instagram.from_env(cfg, log), hist, insights, now, log)
    INSIGHTS_PATH.write_text(json.dumps(insights, indent=1) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(hist, insights, cfg, now), encoding="utf-8")
    log(f"[report] wrote {REPORT_PATH.name}")
    return REPORT_PATH
