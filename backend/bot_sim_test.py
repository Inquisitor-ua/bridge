"""Bots against bots: plays many whole games with computer players only, to
check that a bot never makes an illegal move or gets the game stuck, and to
see that the harder levels actually win more often. Not a pytest suite -- run
with `python -m backend.bot_sim_test [games] [hard_games]`. The hard bot plays
rounds ahead on every move, so its games are slow (a few seconds each) and get
their own, smaller count.

For reference, over 600 two-player games hard beat medium about 60% of the
time; medium beats easy about 80%.
"""
import random
import sys

from . import bot
from .engine import GameError
from .room_manager import Room

MAX_STEPS = 20000  # far more than any real game takes


def play_game(levels: list[str], seed: int) -> Room:
    random.seed(seed)
    room = Room(code="SIM", host_id="")
    for level in levels:
        room.add_bot(level)
    room.host_id = room.players[0].id
    room.start_game(room.host_id)
    eng = room.engine
    for _ in range(MAX_STEPS):
        if eng.game_over:
            return room
        player = room.bot_to_act()
        assert player is not None, f"seed {seed}: the game waits on nobody"
        if eng.awaiting_continue:
            room.bot_step(player)
            continue
        action = bot.decide(eng, player)
        try:
            # straight to the engine, skipping bot_step's fallback: a move
            # the engine rejects is a bug in the bot
            room._apply_bot_action(player, action)
        except GameError as e:
            raise AssertionError(f"seed {seed}: {player.name} ({player.bot_level}) {action} -> {e}\n"
                                 f"hand={[c.label for c in player.hand]} top={eng.top_card().label}") from e
    raise AssertionError(f"seed {seed}: no result after {MAX_STEPS} moves")


def winner_level(room: Room) -> str:
    best = room.engine.standings[0]["id"]
    return room.player(best).bot_level


def test_no_illegal_moves(games: int, hard_games: int) -> None:
    rng = random.Random(1)
    for seed in range(games):
        # every game has some bots, but only the first hard_games mix in hard ones
        pool = bot.LEVELS if seed < hard_games else ("easy", "medium")
        levels = [rng.choice(pool) for _ in range(rng.randint(2, 6))]
        room = play_game(levels, seed)
        assert room.engine.rounds_completed > 0
    print(f"{games} games with 2-6 mixed bots ({min(hard_games, games)} with hard ones): no illegal moves, no stuck games")


def test_harder_wins_more(games: int, hard_games: int) -> None:
    for strong, weak, n, must_win in (
        ("medium", "easy", games, True),
        ("hard", "easy", hard_games, True),
        # too close to call on a few dozen games: reported, not asserted
        ("hard", "medium", hard_games, False),
    ):
        if n == 0:
            continue
        wins = 0
        for seed in range(n):
            # alternate the seats so neither side keeps the first move
            levels = [strong, weak] if seed % 2 else [weak, strong]
            wins += winner_level(play_game(levels, 10_000 + seed)) == strong
        rate = wins / n
        print(f"{strong} vs {weak}: {strong} wins {rate:.0%} of {n}")
        if must_win:
            assert rate > 0.5, f"{strong} should beat {weak} more often than not"


def test_hard_bot_leaves_game_untouched() -> None:
    """The hard bot plays rounds ahead on copies of the game: deciding must
    not change a single field of the real one (a list the copy forgot to
    duplicate would be shared and quietly corrupted)."""
    import copy
    checked = 0
    orig = bot.decide

    def checking_decide(engine, player, rng=None):
        nonlocal checked
        if player.bot_level != "hard":
            return orig(engine, player, rng)
        before = copy.deepcopy(vars(engine))
        action = orig(engine, player, rng)
        after = vars(engine)
        changed = [k for k in before if before[k] != after[k]]
        assert not changed, f"deciding changed the real game: {changed}"
        checked += 1
        return action

    bot.decide = checking_decide
    try:
        for seed in range(3):
            play_game(["hard", "medium", "easy"], 500 + seed)
    finally:
        bot.decide = orig
    print(f"hard bot: {checked} decisions, the real game untouched by the look-ahead")


def test_bot_room_lifecycle() -> None:
    from .room_manager import RoomManager
    manager = RoomManager()
    room, me = manager.create_bot_room("Я", None, None, None, "medium", 2)
    assert room.engine is not None and len(room.players) == 3
    assert [p.is_bot for p in room.players] == [False, True, True]
    assert len({p.name for p in room.players}) == 3
    assert not room.is_empty
    # the only person leaves: the bots don't keep the room alive
    manager.leave_room(room, me.id)
    assert manager.get_room(room.code) is None
    for bad in (("medium", 0), ("medium", 6), ("impossible", 1)):
        try:
            manager.create_bot_room("Я", None, None, None, *bad)
        except GameError:
            continue
        raise AssertionError(f"accepted a bot game with {bad}")
    print("bot room lifecycle: OK")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    n_hard = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    test_bot_room_lifecycle()
    test_hard_bot_leaves_game_untouched()
    test_no_illegal_moves(n, n_hard)
    test_harder_wins_more(n, n_hard)
    print("\nAll bot simulation tests passed.")
