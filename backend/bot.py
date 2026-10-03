"""Computer opponents.

A bot is an ordinary Player with `bot_level` set. Its decisions are made from a
BotView: only what a human sitting in that seat could know -- its own hand,
the top of the table, the cards played onto the pile, everyone's card counts
and scores. It never looks at the other hands or the order of the deck.

The rules themselves stay in the Engine: the bot asks it which cards may be
led (leadable_cards, can_draw, can_pass) and only picks among those.

Levels:
- easy: random legal moves, sometimes draws instead of playing, random choices
- medium: sheds expensive cards first, keeps jacks for later, hits the next
  player with 7 / 8 / Q♠, names the suit it holds most of, weighs Bridge and
  the jack ending by the points in play
- hard: medium plus card counting (which cards are still unseen), and
  elimination at 125 taken into account; on its turn and when naming a suit
  it looks ahead: for each option it deals the unseen cards out at random a
  number of times, plays the round to the end with medium bots and keeps the
  option that scored best on average
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field, replace

from .cards import RANKS, SUITS, Card, card_value, hand_score
from .engine import MAX_SCORE, Engine, GameError, Player

LEVELS = ("easy", "medium", "hard")
BOT_NAMES = ("Борис", "Вера", "Глеб", "Дина", "Ефим")

# expected penalty of an unseen card at round end: the deck holds 220 points
# over 36 cards
AVG_CARD_POINTS = 6
# forced draws a card puts on the next player, and skips it hands out
DRAW_EFFECT = {7: 1, 8: 2}
SKIP_RANKS = (8, 14)


@dataclass
class Action:
    kind: str  # "play" | "draw" | "pass" | "suit" | "bridge" | "jack_end"
    cards: list[Card] = field(default_factory=list)
    value: str | bool | None = None


@dataclass
class Opponent:
    id: str
    hand_count: int
    score: int


@dataclass
class BotView:
    """Everything the bot is allowed to know when it decides."""
    hand: list[Card]
    score: int
    top: Card | None
    effective_suit: str | None
    leadable: list[Card]
    must_cover_six: bool
    can_draw: bool
    can_pass: bool
    played_this_turn: bool
    drawn_this_turn: bool
    fresh_lead: bool  # may lead anything matching (start of turn, or the turn comes straight back)
    multiplier: int
    table: list[Card]  # the pile since the last reshuffle, all of it seen by everyone
    opponents: list[Opponent]  # alive ones, in turn order starting after the bot
    prompt_kind: str | None
    prompt_data: dict

    @property
    def next_opponent(self) -> Opponent | None:
        return self.opponents[0] if self.opponents else None

    def unseen(self) -> list[Card]:
        """Cards the bot hasn't seen: in other hands or still in the deck."""
        known = set(self.hand) | set(self.table)
        return [Card(r, s) for s in SUITS for r in RANKS if Card(r, s) not in known]


def view_for(engine: Engine, player: Player) -> BotView:
    n = len(engine.players)
    me = engine.players.index(player)
    opponents = []
    for step in range(1, n):
        p = engine.players[(me + step) % n]
        if not p.eliminated:
            opponents.append(Opponent(p.id, len(p.hand), p.score))
    prompt = engine.prompt if engine.prompt is not None and engine.prompt.player_id == player.id else None
    my_turn = engine.round_active and engine.current_player() is player
    return BotView(
        hand=list(player.hand),
        score=player.score,
        top=engine.top_card(),
        effective_suit=engine.effective_suit(),
        leadable=engine.leadable_cards(player.hand) if my_turn else [],
        must_cover_six=engine.must_cover_six(),
        can_draw=my_turn and engine.can_draw(),
        can_pass=my_turn and engine.can_pass(),
        played_this_turn=engine.played_this_turn,
        drawn_this_turn=engine.drawn_this_turn,
        fresh_lead=not engine.played_this_turn or engine.must_cover_six() or engine._turn_returns_to_current(),
        multiplier=engine.multiplier,
        table=list(engine.table),
        opponents=opponents,
        prompt_kind=prompt.kind if prompt else None,
        prompt_data=dict(prompt.data) if prompt else {},
    )


def snapshot(engine: Engine, player: Player) -> tuple[Engine, Player]:
    """A private copy of the game to decide on off the event loop (the hard
    bot's look-ahead takes a moment): decide(*snapshot(engine, player))."""
    eng = _clone(engine)
    return eng, eng.player_by_id(player.id)


def decide(engine: Engine, player: Player, rng: random.Random | None = None) -> Action:
    """The bot's next move: an answer to its prompt, or one step of its turn."""
    rng = rng or random
    level = player.bot_level or "medium"
    view = view_for(engine, player)
    if level == "hard" and view.prompt_kind in (None, "suit"):
        options = hard_options(view, rng)
        if len(options) > 1:
            if view.prompt_kind == "suit":
                default = Action("suit", value=choose_suit(view, "medium", rng))
            else:
                default = choose_turn(view, "medium", rng)
            return look_ahead(engine, player, options, default, rng)
        if options:
            return options[0]
    if view.prompt_kind == "suit":
        return Action("suit", value=choose_suit(view, level, rng))
    if view.prompt_kind == "bridge":
        return Action("bridge", value=choose_bridge(view, level, rng))
    if view.prompt_kind == "jack_end":
        return Action("jack_end", value=choose_jack_end(view, level, rng))
    return choose_turn(view, level, rng)


# ---------- the turn ----------

def candidate_plays(view: BotView, want_top: str | None) -> list[list[Card]]:
    """Legal plays worth considering: for each rank that can be led, the whole
    group of that rank (in an order the engine accepts), plus a lone jack so
    the others can be kept as wilds."""
    by_rank: dict[int, list[Card]] = {}
    for c in view.hand:
        by_rank.setdefault(c.rank, []).append(c)
    plays = []
    for rank in sorted({c.rank for c in view.leadable}):
        group = by_rank[rank]
        plays.append(arrange(group, view.leadable, want_top))
        if rank == 11 and len(group) > 1:
            plays.append([next(c for c in group if c in view.leadable)])
    return plays


def arrange(group: list[Card], leadable: list[Card], want_top: str | None) -> list[Card]:
    """Order a same-rank group for play_cards: the first card must be leadable
    on its own, and the last one stays on top -- of `want_top` suit if any."""
    tops = sorted(group, key=lambda c: c.suit != want_top)
    for top in tops:
        rest = [c for c in group if c != top]
        if not rest:
            return [top]
        lead = next((c for c in rest if c in leadable), None)
        if lead is not None:
            return [lead] + [c for c in rest if c != lead] + [top]
    lead = next(c for c in group if c in leadable)
    return [lead] + [c for c in group if c != lead]


def choose_turn(view: BotView, level: str, rng) -> Action:
    if level == "easy":
        plays = candidate_plays(view, rng.choice(SUITS))
        if view.fresh_lead and plays and view.can_draw and not view.must_cover_six and rng.random() < 0.25:
            return Action("draw")
        if plays and (view.fresh_lead or rng.random() < 0.5):
            return Action("play", cards=rng.choice(plays))
        return _draw_or_pass(view, plays)

    plays = candidate_plays(view, None)
    plays = [arrange(p, view.leadable, _best_top_suit(view, p, level)) for p in plays]
    if not plays:
        return _draw_or_pass(view, plays)

    scored = sorted(((score_play(view, p, level), p) for p in plays), key=lambda sp: sp[0], reverse=True)
    best_score, best = scored[0]

    if view.must_cover_six:
        return Action("play", cards=best)

    if view.fresh_lead:
        only_jacks = all(p[0].rank == 11 for p in plays)
        has_other = any(c.rank != 11 for c in view.hand)
        # a jack is worth more held than spent on a turn it isn't needed for:
        # try the one free draw first, maybe it brings a card that fits
        if only_jacks and has_other and view.can_draw and not view.drawn_this_turn:
            return Action("draw")
        return Action("play", cards=best)

    # the turn is already open: only more of the same rank (or more jacks
    # on jacks). Worth it to go out, or to shed points that aren't jacks.
    if best_score > 0 and (len(best) == len(view.hand) or best[0].rank != 11):
        return Action("play", cards=best)
    return _draw_or_pass(view, plays)


def _draw_or_pass(view: BotView, plays: list[list[Card]]) -> Action:
    if view.must_cover_six:
        if plays:
            return Action("play", cards=plays[0])
        return Action("draw") if view.can_draw else Action("pass")
    if view.can_pass:
        return Action("pass")
    if view.can_draw:
        return Action("draw")
    if plays:
        return Action("play", cards=plays[0])
    return Action("pass")  # nothing is legal; the engine will say why


def score_play(view: BotView, play: list[Card], level: str) -> float:
    rank = play[0].rank
    remaining = [c for c in view.hand if c not in play]
    score = float(sum(card_value(c, len(view.hand)) for c in play)) + 3 * len(play)

    if not remaining:
        # going out wins the round -- unless it's on a six, which still has
        # to be covered from the deck
        return score + (-25 if rank == 6 else 200)

    if rank == 11:
        # a jack fits on anything: keep it for the end (a lone jack is a
        # good last card) unless the hand is all jacks anyway
        if any(c.rank != 11 for c in remaining):
            score -= 22 * len(play)
        else:
            score += 10

    if rank == 6:
        top_suit = play[-1].suit
        cover = [c for c in remaining if c.suit == top_suit or c.rank in (6, 11)]
        score += 4 if cover else -18

    nxt = view.next_opponent
    draws = sum(DRAW_EFFECT.get(c.rank, 0) + (5 if c.is_queen_of_spades else 0) for c in play)
    skips = sum(1 for c in play if c.rank in SKIP_RANKS)
    attack = 2 * draws + 3 * skips
    if nxt is not None and nxt.hand_count <= 2:
        attack *= 2 if level == "medium" else 3
    score += attack

    if level == "hard":
        # after the play the next player must match the top suit: better a
        # suit the opponents are short of
        unseen = view.unseen()
        top = play[-1]
        if rank != 11:
            in_suit = sum(1 for c in unseen if c.suit == top.suit and c.rank != 11)
            score -= 0.6 * in_suit
        # a player about to go out: don't hand them a lead they can finish on
        if nxt is not None and nxt.hand_count == 1 and not skips and not draws:
            score -= 6
    return score


def _best_top_suit(view: BotView, play: list[Card], level: str) -> str | None:
    """The suit to leave on top: for a six, one the bot can cover; otherwise
    one it holds more of for its next turn."""
    remaining = [c for c in view.hand if c not in play and c.rank != 11]
    if not remaining:
        return None
    counts = {s: 0.0 for s in SUITS}
    for c in remaining:
        counts[c.suit] += 1
    if level == "hard" and play[0].rank != 6:
        unseen = view.unseen()
        for s in SUITS:
            counts[s] -= 0.15 * sum(1 for c in unseen if c.suit == s and c.rank != 11)
    suits = {c.suit for c in play}
    return max(suits, key=lambda s: counts[s])


# ---------- prompts ----------

def choose_suit(view: BotView, level: str, rng) -> str:
    own = [c for c in view.hand if c.rank != 11]
    if level == "easy" or not own:
        if own and rng.random() < 0.5:
            return rng.choice(own).suit
        return rng.choice(SUITS)
    weight = {s: 0.0 for s in SUITS}
    for c in own:
        # the suit with the most cards, and the most points to shed
        weight[c.suit] += 1 + card_value(c, len(view.hand)) / 15
    if level == "hard":
        unseen = view.unseen()
        for s in SUITS:
            weight[s] -= 0.2 * sum(1 for c in unseen if c.suit == s and c.rank != 11)
    return max(SUITS, key=lambda s: weight[s])


def _expected_points(opp: Opponent, multiplier: int) -> float:
    return opp.hand_count * AVG_CARD_POINTS * multiplier


def choose_bridge(view: BotView, level: str, rng) -> bool:
    """Bridge ends the round at once and everyone, the bot included, scores
    what they hold."""
    if not view.hand:
        return False  # going out is at least as good, and it counts as a win
    if level == "easy":
        return rng.random() < 0.5
    mine = hand_score(view.hand) * view.multiplier
    after = view.score + mine
    if after == MAX_SCORE:
        return True  # lands exactly on 125: the score resets to zero
    if after > MAX_SCORE:
        return False
    if not view.opponents:
        return True
    expected = [_expected_points(o, view.multiplier) for o in view.opponents]
    if level == "hard":
        # someone likely knocked out of the game is worth stopping for
        if any(o.score + e > MAX_SCORE for o, e in zip(view.opponents, expected)):
            return mine <= max(expected)
        return mine < 0.8 * min(expected) or mine == 0
    return mine <= 0.7 * sum(expected) / len(expected)


def choose_jack_end(view: BotView, level: str, rng) -> str:
    """The round was won on jacks: -20 per jack to the bot, or the others'
    hands multiplied by (jacks + 1)."""
    if level == "easy":
        return rng.choice(("penalty", "multiply"))
    count = view.prompt_data.get("count", 1)
    if not view.opponents:
        return "penalty"
    expected = [_expected_points(o, view.multiplier) for o in view.opponents]
    if level == "hard":
        for o, e in zip(view.opponents, expected):
            if o.score + e <= MAX_SCORE < o.score + e * (count + 1):
                return "multiply"  # the extra points likely knock someone out
    extra = sum(e * count for e in expected) / len(expected)
    return "multiply" if extra > 20 * count else "penalty"


# ---------- looking ahead (hard) ----------

LOOKAHEAD_SAMPLES = 32  # random deals of the unseen cards per decision
LOOKAHEAD_MARGIN = 1.5  # how sure the look-ahead must be to overrule the medium choice
LOOKAHEAD_MAX_STEPS = 600  # a rollout that runs longer is cut off and scored as is
ELIMINATION_WEIGHT = 150  # going out of the game, in points


def hard_options(view: BotView, rng) -> list[Action]:
    """What the hard bot weighs against each other: every suit, or every
    sensible play plus drawing and passing where allowed."""
    if view.prompt_kind == "suit":
        return [Action("suit", value=s) for s in SUITS]
    plays = candidate_plays(view, None)
    options = [Action("play", cards=arrange(p, view.leadable, _best_top_suit(view, p, "hard"))) for p in plays]
    if view.can_draw:
        options.append(Action("draw"))
    if view.can_pass:
        options.append(Action("pass"))
    if not options:
        options.append(choose_turn(view, "medium", rng))
    return options


def look_ahead(engine: Engine, player: Player, options: list[Action], default: Action, rng) -> Action:
    """Play each option out on random guesses at the hidden cards. The guesses
    are noisy, so the medium choice (`default`) stands unless another option
    beats it clearly: by more than LOOKAHEAD_MARGIN standard errors."""
    if not any(_same(o, default) for o in options):
        options = options + [default]
    base = next(i for i, o in enumerate(options) if _same(o, default))
    results = [[] for _ in options]
    for _ in range(LOOKAHEAD_SAMPLES):
        # one guess at the hidden cards, shared by every option so they are
        # compared on the same deal
        world = _determinize(engine, player, rng)
        for i, option in enumerate(options):
            results[i].append(_rollout(world, player.id, option))
    best, best_edge = base, 0.0
    for i in range(len(options)):
        if i == base:
            continue
        diffs = [a - b for a, b in zip(results[i], results[base])]
        mean = sum(diffs) / len(diffs)
        var = sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1)
        if mean > LOOKAHEAD_MARGIN * (var / len(diffs)) ** 0.5 and mean > best_edge:
            best, best_edge = i, mean
    return options[best]


def _same(a: Action, b: Action) -> bool:
    return a.kind == b.kind and a.cards == b.cards and a.value == b.value


def _clone(engine: Engine) -> Engine:
    """A copy of the engine to play forward in, without the history it
    doesn't need (the log)."""
    eng = copy.copy(engine)
    eng.players = [replace(p, hand=list(p.hand)) for p in engine.players]
    eng.deck = list(engine.deck)
    eng.table = list(engine.table)
    eng.stock = list(engine.stock)
    eng.skip_draws = list(engine.skip_draws)
    eng.log = []
    eng.round_stats = {k: dict(v) for k, v in engine.round_stats.items()}
    eng.game_stats = {k: dict(v) for k, v in engine.game_stats.items()}
    eng.round_scores_before = dict(engine.round_scores_before)
    eng.round_end_info = dict(engine.round_end_info)
    eng.ready_ids = set(engine.ready_ids)
    eng.eliminated_in = dict(engine.eliminated_in)
    eng.quit_ids = set(engine.quit_ids)
    return eng


def _determinize(engine: Engine, player: Player, rng) -> Engine:
    """A copy of the game where the cards the bot can't see (other hands and
    the deck) are dealt out again at random, keeping everyone's card count."""
    eng = _clone(engine)
    others = [p for p in eng.players if p.id != player.id]
    hidden = [c for p in others for c in p.hand] + eng.deck
    rng.shuffle(hidden)
    for p in others:
        n = len(p.hand)
        p.hand, hidden = hidden[:n], hidden[n:]
    eng.deck = hidden
    return eng


def _rollout(world: Engine, me_id: str, first: Action) -> float:
    """Play the round to its end from `world` (left untouched), starting with
    `first`; the result is how much better the bot did than the others."""
    eng = _clone(world)
    before = {p.id: p.score for p in eng.players}
    alive_before = {p.id for p in eng.alive_players()}
    try:
        _apply(eng, me_id, first)
        for _ in range(LOOKAHEAD_MAX_STEPS):
            if not eng.round_active and eng.prompt is None:
                break
            actor = eng.player_by_id(eng.prompt.player_id) if eng.prompt else eng.current_player()
            view = view_for(eng, actor)
            if view.prompt_kind == "suit":
                action = Action("suit", value=choose_suit(view, "medium", random))
            elif view.prompt_kind == "bridge":
                action = Action("bridge", value=choose_bridge(view, "medium", random))
            elif view.prompt_kind == "jack_end":
                action = Action("jack_end", value=choose_jack_end(view, "medium", random))
            else:
                action = choose_turn(view, "medium", random)
            _apply(eng, actor.id, action)
    except GameError:
        return -1000.0  # the option led somewhere illegal: never pick it

    def outcome(p: Player) -> float:
        out = ELIMINATION_WEIGHT if p.eliminated and p.id in alive_before else 0
        if eng.round_active:
            # cut off mid-round: count what the hand would score now
            return hand_score(p.hand) * eng.multiplier + out
        return p.score - before[p.id] + out

    me = eng.player_by_id(me_id)
    rivals = [p for p in eng.players if p.id != me_id and p.id in alive_before]
    if not rivals:
        return -outcome(me)
    return sum(outcome(p) for p in rivals) / len(rivals) - outcome(me)


def _apply(eng: Engine, pid: str, action: Action) -> None:
    if action.kind == "play":
        eng.play_cards(pid, action.cards)
    elif action.kind == "draw":
        eng.draw_card(pid)
    elif action.kind == "pass":
        eng.pass_turn(pid)
    elif action.kind == "suit":
        eng.declare_suit(pid, action.value)
    elif action.kind == "bridge":
        eng.declare_bridge(pid, bool(action.value))
    elif action.kind == "jack_end":
        eng.resolve_jack_end(pid, action.value)
