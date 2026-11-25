"""Template-based English captions + hashtags (no LLM, no tokens).

Templates rotate deterministically by date, so the same day always gets
the same caption and consecutive days rarely repeat.
"""
from __future__ import annotations

import random
import re

from .data.select_match import Selection

MATCH_TEMPLATES = [
    "⚔️ ARENA PREDICTION | {home} vs {away}\nThe arena has spoken: {winner} takes it. Agree? Drop your score 👇",
    "🏟️ {home} vs {away} {when_lower}\nWe let them fight it out in the arena first. {winner} survived. Your prediction? 👇",
    "🔥 {league}: {home} vs {away}\nArena says {winner}. Will the pitch say the same {when_lower}? Comment your score 👇",
    "⚔️ {home} 🆚 {away}\n{winner} wins the arena battle with {hp} HP left. Who wins for real {when_lower}? 👇",
    "💥 Matchday arena: {home} vs {away}\nPrediction locked: {winner}. Tag a {loser} fan 👇",
    "🎯 {winner} over {loser}. That's the arena call for {when_lower}.\nRight or wrong? Score prediction below 👇",
    "🗡️ {home} vs {away}\n{loser} fought hard, but {winner} had the last hit. Same story {when_lower}? 👇",
    "📊 {winner} had a {prob}% win chance going in, and the arena agreed.\n{home} vs {away}. What's your score? 👇",
    "😮‍💨 That finish though. {winner} survives on {hp} HP.\n{home} vs {away} {when_lower}. Who are you backing? 👇",
    "⚔️ {league} ARENA\n{home} vs {away} → {winner} 🏆\nComment your exact score. Closest one gets bragging rights 👇",
    "🔮 Arena prediction for {home} vs {away}: {winner}.\nScreenshot this and come back after the final whistle 👇",
    "🏆 {winner} wins the arena. {loser} fans, it's your turn to talk 👇\n{home} vs {away} {when_lower}",
    "⚡ {home} vs {away}\nThe arena never lies... or does it? {winner} takes it here. Your call 👇",
    "🥊 {winner} vs {loser}: arena edition.\nOne side walked out, one didn't. Who wins the real one {when_lower}? 👇",
    "📣 {when}: {home} vs {away}\nArena verdict: {winner}. Do you agree? Yes or no 👇",
    "⚔️ {home} vs {away}\nTurn the sound on for this one 🔊 Arena pick: {winner}. Your score? 👇",
    "🧠 Form, table, vibes: the arena crunched it all. {winner} wins.\n{home} vs {away} {when_lower} 👇",
    "🚨 Big game alert: {home} vs {away}\nArena says {winner}. Drop your scoreline 👇",
    "⚔️ {winner} {hp} HP left. {loser} 0.\nWill it be that close {when_lower}? 👇",
    "🎮 We simulated {home} vs {away} in the arena.\nResult: {winner} 🏆 Now it's your prediction 👇",
    "🔥 {league} matchday. {home} vs {away}.\nArena backs {winner}. Who's your pick? 👇",
    "👀 {loser} fans won't like this one...\nArena prediction: {winner} beats {loser} 👇",
    "⚔️ Daily arena: {home} vs {away}\n{winner} survives the shrinking ring. Your score for {when_lower}? 👇",
    "🏟️ {home} or {away}?\nThe arena picked {winner}. Comment the team you're backing 👇",
    "💯 Arena prediction: {winner} ({prob}%).\n{home} vs {away}. Agree or disagree? 👇",
]

LEGEND_TEMPLATES = [
    "⚔️ LEGENDS CLASH | {home} vs {away}\nNo big match today, so the arena picked a classic. {winner} wins it. Who would win in real life? 👇",
    "🏟️ Dream matchup: {home} vs {away}\n{winner} survives the arena with {hp} HP. Your pick? 👇",
    "👑 Legends day: {home} vs {away}\nArena says {winner}. Prime vs prime, who really wins? 👇",
    "⚔️ No matchday? No problem.\n{home} vs {away} in the arena → {winner} 🏆 Agree? 👇",
    "🔥 Classic clash: {home} vs {away}\n{winner} takes the arena. Name your all-time XI for {loser} 👇",
    "🎮 What if {home} played {away} today?\nThe arena says {winner}. You say? 👇",
]


def _tag(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def record_line(last: dict | None, record: tuple[int, int] | None) -> str:
    """'Yesterday's call ✅ Arsenal (2-1) · Arena record 7/10' (empty if unknown)."""
    parts = []
    if last and last.get("outcome") in ("hit", "miss", "draw"):
        mark = {"hit": "✅", "miss": "❌", "draw": "🤝"}[last["outcome"]]
        score = last.get("score", "")
        parts.append(f"Last call {mark} {last['predicted']} ({last['home_short']} {score} {last['away_short']})")
    if record and record[1] >= 3:
        parts.append(f"Arena record: {record[0]}/{record[1]}")
    return " · ".join(parts)


def build_caption(sel: Selection, winner: int, winner_hp: float, day_seed: int, general_tags: list[str],
                  win_prob: tuple[float, float] | None = None, last: dict | None = None,
                  record: tuple[int, int] | None = None, brand: str = "", max_tags: int = 6) -> str:
    rng = random.Random(day_seed)
    teams = (sel.home, sel.away)
    when = "tonight" if sel.tag == "TONIGHT" else "today"
    prob = round((win_prob or (0.5, 0.5))[winner] * 100)
    data = dict(home=sel.home.name, away=sel.away.name, winner=teams[winner].name, loser=teams[1 - winner].name,
                league=sel.league.title() if sel.league.isupper() else sel.league,
                when=when.upper(), when_lower=when, hp=max(1, round(winner_hp)), prob=prob)
    pool = LEGEND_TEMPLATES if sel.legends else MATCH_TEMPLATES
    # Template choice keyed on the date so neighbouring days differ
    body = pool[(day_seed * 7 + rng.randrange(len(pool))) % len(pool)].format(**data)
    extra = record_line(last, record)
    if extra:
        body += "\n\n" + extra
    if brand:
        body += f"\n\nNew arena battle every day ⚔️ Follow {brand}"
    # A few targeted tags beat a wall of them: league, both clubs, then general ones.
    tags = []
    for t in [*sel.tags[:1], sel.home.hashtag, sel.away.hashtag, *general_tags]:
        t = _tag(t)
        if t and t not in tags:
            tags.append(t)
    return body + "\n\n" + " ".join("#" + t for t in tags[:max_tags])


NIGHT_HEADERS = [
    "🌙 {title} NIGHT: the arena called every big game",
    "⚔️ {n} battles, {n} predictions. {title} night in the arena",
    "🔥 Big {title_t} night. We fought them all first",
    "🏟️ {title} NIGHT ARENA: here's how tonight goes",
]


def build_night_caption(title: str, sels: list, winners: list[int], seed: int, general_tags: list[str],
                        record: tuple[int, int] | None = None, brand: str = "", max_tags: int = 6) -> str:
    rng = random.Random(seed)
    head = NIGHT_HEADERS[rng.randrange(len(NIGHT_HEADERS))].format(
        title=title, title_t=title.title(), n=len(sels))
    lines = [f"⚔️ {s.home.name} vs {s.away.name} → {(s.home, s.away)[w].name}" for s, w in zip(sels, winners)]
    body = head + "\n\n" + "\n".join(lines) + "\n\nHow many will we get right? Drop your picks 👇"
    if record and record[1] >= 3:
        body += f"\n\nArena record: {record[0]}/{record[1]}"
    if brand:
        body += f"\n\nNew arena battle every day ⚔️ Follow {brand}"
    tags = []
    for t in [*(sels[0].tags[:1] if sels else []), *(s.home.hashtag for s in sels[:1]),
              *(s.away.hashtag for s in sels[:1]), *general_tags]:
        t = _tag(t)
        if t and t not in tags:
            tags.append(t)
    return body + "\n\n" + " ".join("#" + t for t in tags[:max_tags])
