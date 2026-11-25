"""Command line entry point: `arena preview`, `arena daily`, `arena publish`, ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import OUTPUT, load_config


def _cmd_preview(args):
    from .data.teams import resolve_clash, resolve_team
    from .director import pick_battle
    from .render.renderer import render_video
    from .render.scenes import MatchCard
    from .sim.world import simulate

    cfg = load_config()
    home, away = resolve_clash(resolve_team(args.home), resolve_team(args.away))
    if args.seed is not None:
        result = simulate(args.seed, (home.weapon, away.weapon))
        prob = None
    else:
        pick = pick_battle(home, away, strength=(args.home_strength, args.away_strength),
                           day_seed=args.day_seed, director_cfg=cfg["director"])
        result, prob = pick.result, pick.win_prob
    card = MatchCard(league=args.league, tag=args.tag, home=home, away=away,
                     form=(args.home_form, args.away_form), win_prob=prob, brand=cfg.get("brand", ""))
    out = Path(args.out) if args.out else OUTPUT / "preview" / f"{home.short}_vs_{away.short}_{result.seed}.mp4"
    print(f"seed={result.seed} winner={card.teams[result.winner].name} fight={result.duration:.1f}s "
          f"hits={result.hits} parries={result.parries} hp={tuple(round(h) for h in result.hp)}")
    render_video(card, result, out, cfg["video"], cfg["audio"])
    print(f"wrote {out}")


def _cmd_daily(args):
    from datetime import date

    from .pipeline import run_daily

    day = date.fromisoformat(args.date) if args.date else None
    out = run_daily(day, Path(args.out_root) if args.out_root else OUTPUT, render=not args.no_render)
    if args.github_output:
        import os
        gh = os.environ.get("GITHUB_OUTPUT")
        if gh:
            with open(gh, "a", encoding="utf-8") as f:
                f.write(f"dir={out.as_posix()}\n")


def _cmd_publish(args):
    from datetime import date, datetime, timezone

    from .data.select_match import post_time_utc
    from .pipeline import local_today
    from .publish.instagram import post_reel

    cfg = load_config()
    d = Path(args.dir)
    video, caption = d / "video.mp4", (d / "caption.txt").read_text(encoding="utf-8")
    if not video.exists():
        raise SystemExit(f"missing {video}")
    when = None
    if not args.now:
        day = date.fromisoformat(d.name) if len(d.name) == 10 else local_today(cfg)
        when = post_time_utc(day, cfg)
        if when < datetime.now(timezone.utc):
            print(f"[publish] post time {when.isoformat()} already passed, publishing now")
            when = None
    if args.dry_run:
        print(f"[publish] DRY RUN: would post {video} at {when or 'now'}\n---\n{caption}\n---")
        return
    media_id = post_reel(video, caption, cfg, when)
    (d / "published.json").write_text(
        f'{{"media_id": "{media_id}", "at": "{datetime.now(timezone.utc).isoformat()}"}}\n', encoding="utf-8")


def _cmd_whoami(args):
    from .publish.instagram import Instagram

    me = Instagram.from_env(load_config(), log=lambda *_: None).whoami()
    print(f"token OK -> @{me.get('username')} (id {me.get('id')})")


def _cmd_refresh_token(args):
    from .publish.instagram import Instagram

    token, expires = Instagram.from_env(load_config(), log=lambda *_: None).refresh_token()
    # stdout carries only the token so a workflow can capture it
    print(token)
    print(f"token refreshed, expires in {expires // 86400} days", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(prog="arena", description="Football arena battle video generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("preview", help="render a battle between two teams")
    pv.add_argument("--home", required=True)
    pv.add_argument("--away", required=True)
    pv.add_argument("--seed", type=int, help="render this exact seed (skips the director)")
    pv.add_argument("--day-seed", type=int, default=0, help="seed for the director's coin flips")
    pv.add_argument("--home-strength", type=float, default=0.5)
    pv.add_argument("--away-strength", type=float, default=0.5)
    pv.add_argument("--home-form", default="")
    pv.add_argument("--away-form", default="")
    pv.add_argument("--league", default="SÜPER LIG")
    pv.add_argument("--tag", default="TONIGHT")
    pv.add_argument("--out")
    pv.set_defaults(func=_cmd_preview)

    dy = sub.add_parser("daily", help="pick today's match and render the video + caption")
    dy.add_argument("--date", help="YYYY-MM-DD (local date, default: today)")
    dy.add_argument("--out-root")
    dy.add_argument("--no-render", action="store_true", help="only select + simulate + caption")
    dy.add_argument("--github-output", action="store_true", help="write dir=... to $GITHUB_OUTPUT")
    dy.set_defaults(func=_cmd_daily)

    pb = sub.add_parser("publish", help="upload a rendered day folder to Instagram")
    pb.add_argument("--dir", required=True, help="output/YYYY-MM-DD")
    pb.add_argument("--now", action="store_true", help="publish immediately instead of at post time")
    pb.add_argument("--dry-run", action="store_true")
    pb.set_defaults(func=_cmd_publish)

    wh = sub.add_parser("whoami", help="check that the Instagram token works (read-only)")
    wh.set_defaults(func=_cmd_whoami)

    rt = sub.add_parser("refresh-token", help="refresh a 60-day Instagram-login token (not needed for system-user tokens)")
    rt.set_defaults(func=_cmd_refresh_token)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
