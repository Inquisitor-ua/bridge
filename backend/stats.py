"""Player statistics: a finished game goes to the database once, profiles read
aggregates over it.

The engine already counts everything per round (Engine.round_stats) and sums
it over the game (Engine.game_stats); this module only persists the result
and answers the profile page.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from . import db
from .engine import Engine

# per-player counters copied from Engine.game_stats into game_players
COUNTERS = (
    "rounds_played", "rounds_won", "bridges", "resets", "turns", "cards_played", "cards_drawn",
    "penalty_drawn", "penalty_dealt", "skips_dealt", "turns_skipped", "jacks_played", "sixes_played",
    "biggest_play", "max_hand",
)
MAX_COUNTERS = ("biggest_play", "max_hand")
RECENT_GAMES = 10

router = APIRouter(prefix="/api")


def record_game(engine: Engine | None) -> None:
    """Save a just-finished game. Safe to call after every state change: it
    acts once per engine (a rematch gets a fresh Engine, so a fresh flag)."""
    if engine is None or not engine.game_over or getattr(engine, "recorded", False):
        return
    engine.recorded = True
    # nothing to remember: only guests played, or the game fell apart before
    # a single round was scored (also keeps "join, leave, free win" out)
    if engine.rounds_completed == 0 or not any(p.user_id for p in engine.players):
        return

    place_of = {row["id"]: i + 1 for i, row in enumerate(engine.standings or [])}
    with db.connect() as conn:
        game_id = conn.execute(
            "INSERT INTO games (started_at, finished_at, rounds, player_count) VALUES (?, ?, ?, ?)",
            (int(engine.started_at), int(time.time()), engine.rounds_completed, len(engine.players)),
        ).lastrowid
        for p in engine.players:
            totals = engine.game_stats.get(p.id, {})
            place = place_of.get(p.id, len(engine.players))
            conn.execute(
                f"INSERT INTO game_players (game_id, user_id, name, place, score, won, eliminated, left_game, "
                f"{', '.join(COUNTERS)}) VALUES ({', '.join('?' * (8 + len(COUNTERS)))})",
                (
                    game_id, p.user_id, p.name, place, p.score,
                    int(place == 1 and not p.eliminated), int(p.eliminated), int(p.id in engine.quit_ids),
                    *(totals.get(k, 0) for k in COUNTERS),
                ),
            )


def _streaks(results: list[int]) -> tuple[int, int]:
    """(current, best) runs of wins in chronological win/loss flags."""
    best = run = 0
    for won in results:
        run = run + 1 if won else 0
        best = max(best, run)
    return run, best


def user_stats(user_id: int) -> dict:
    sums = ", ".join(
        f"{'MAX' if k in MAX_COUNTERS else 'SUM'}(gp.{k}) AS {k}" for k in COUNTERS
    )
    with db.connect() as conn:
        agg = conn.execute(
            f"""SELECT COUNT(*) AS games, SUM(gp.won) AS wins, SUM(gp.left_game) AS left_games,
                       SUM(g.finished_at - g.started_at) AS play_seconds, {sums}
                FROM game_players gp JOIN games g ON g.id = gp.game_id
                WHERE gp.user_id = ?""",
            (user_id,),
        ).fetchone()
        results = [
            r["won"] for r in conn.execute(
                """SELECT gp.won FROM game_players gp JOIN games g ON g.id = gp.game_id
                   WHERE gp.user_id = ? ORDER BY g.finished_at, g.id""",
                (user_id,),
            )
        ]
        recent = conn.execute(
            """SELECT g.id, g.started_at, g.finished_at, g.rounds, g.player_count,
                      gp.place, gp.score, gp.won, gp.left_game
               FROM game_players gp JOIN games g ON g.id = gp.game_id
               WHERE gp.user_id = ? ORDER BY g.finished_at DESC, g.id DESC LIMIT ?""",
            (user_id, RECENT_GAMES),
        ).fetchall()
        players_by_game: dict[int, list[dict]] = {}
        if recent:
            ids = [r["id"] for r in recent]
            for r in conn.execute(
                f"""SELECT gp.game_id, gp.user_id, gp.name, gp.place, gp.score, u.username
                    FROM game_players gp LEFT JOIN users u ON u.id = gp.user_id
                    WHERE gp.game_id IN ({', '.join('?' * len(ids))}) ORDER BY gp.place""",
                ids,
            ):
                if r["user_id"] == user_id:
                    continue
                players_by_game.setdefault(r["game_id"], []).append(
                    {"name": r["name"], "username": r["username"], "place": r["place"], "score": r["score"]}
                )

    current, best = _streaks(results)
    totals = {k: agg[k] or 0 for k in (*COUNTERS, "games", "wins", "left_games", "play_seconds")}
    return {
        **totals,
        "current_streak": current,
        "best_streak": best,
        "recent_games": [
            {
                "finished_at": r["finished_at"],
                "duration_sec": r["finished_at"] - r["started_at"],
                "rounds": r["rounds"],
                "player_count": r["player_count"],
                "place": r["place"],
                "score": r["score"],
                "won": bool(r["won"]),
                "left": bool(r["left_game"]),
                "opponents": players_by_game.get(r["id"], []),
            }
            for r in recent
        ],
    }


@router.get("/users/{username}/stats")
def get_user_stats(username: str) -> dict:
    with db.connect() as conn:
        user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        raise HTTPException(404, "пользователь не найден")
    return user_stats(user["id"])
