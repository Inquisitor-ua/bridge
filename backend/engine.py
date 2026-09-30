"""Core game engine for a single Bridge room.

Rules implemented are documented in README.md. This module is transport-agnostic:
it exposes plain-data actions and emits log lines / prompts that the websocket
layer (room_manager.py) turns into JSON messages.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .cards import Card, build_deck, hand_score, RANK_NAMES, SUIT_SYMBOLS

MAX_SCORE = 125


@dataclass
class Player:
    id: str
    name: str
    hand: list[Card] = field(default_factory=list)
    score: int = 0
    eliminated: bool = False
    connected: bool = True


class GameError(Exception):
    pass


@dataclass
class Prompt:
    """A decision the engine is waiting on from a specific player."""
    kind: str  # "suit" | "bridge" | "jack_end"
    player_id: str
    data: dict = field(default_factory=dict)


class Engine:
    def __init__(self, players: list[Player]):
        if not (2 <= len(players) <= 6):
            raise GameError("2 to 6 players required")
        self.players = players
        self.deck: list[Card] = []
        self.stock: list[Card] = []  # cards that go under the pile, used to reshuffle
        self.table: list[Card] = []  # play pile, table[-1] is the visible top card
        self.declared_suit: str | None = None  # active suit when top card is a Jack
        self.turn_index: int = 0
        self.pending_draw: int = 0
        self.pending_skip: int = 0
        self.skip_source: int | None = None  # turn_index of whoever played the pending skips
        self.reshuffle_count: int = 0
        self.round_active: bool = False
        self.drawn_this_turn: bool = False
        self.played_this_turn: bool = False
        self.log: list[str] = []
        self.prompt: Prompt | None = None
        self.game_over: bool = False
        self.standings: list[dict] | None = None
        # per-round bookkeeping for the end-of-round summary screen
        self.round_number: int = 0
        self.round_started_at: float = 0.0
        self.round_turns: int = 0
        self.round_stats: dict[str, dict] = {}  # player id -> counters, only players dealt in
        self.round_scores_before: dict[str, int] = {}
        self.round_end_info: dict = {}
        self.round_summary: dict | None = None
        # between rounds: the next deal starts once every alive player is ready
        self.awaiting_continue: bool = False
        self.ready_ids: set[str] = set()

    # ---------- helpers ----------

    def _say(self, msg: str) -> None:
        self.log.append(msg)

    def _stat(self, player: Player, key: str, amount: int = 1) -> None:
        stats = self.round_stats.get(player.id)
        if stats is not None:
            stats[key] += amount

    def _note_hand_size(self, player: Player) -> None:
        stats = self.round_stats.get(player.id)
        if stats is not None:
            stats["max_hand"] = max(stats["max_hand"], len(player.hand))

    def _require_round_active(self) -> None:
        if not self.round_active:
            raise GameError("раздача не идёт")

    def alive_players(self) -> list[Player]:
        return [p for p in self.players if not p.eliminated]

    def player_by_id(self, pid: str) -> Player | None:
        for p in self.players:
            if p.id == pid:
                return p
        return None

    def current_player(self) -> Player:
        return self.players[self.turn_index]

    def _next_index(self, idx: int) -> int:
        n = len(self.players)
        nxt = (idx + 1) % n
        # skip eliminated players entirely
        guard = 0
        while self.players[nxt].eliminated and guard < n:
            nxt = (nxt + 1) % n
            guard += 1
        return nxt

    def _advance_turn(self) -> None:
        self.turn_index = self._next_index(self.turn_index)

    @property
    def multiplier(self) -> int:
        return self.reshuffle_count + 1

    def top_card(self) -> Card | None:
        return self.table[-1] if self.table else None

    def effective_suit(self) -> str | None:
        top = self.top_card()
        if top is None:
            return None
        if top.is_jack and self.declared_suit:
            return self.declared_suit
        return top.suit

    def effective_rank(self) -> int | None:
        top = self.top_card()
        return top.rank if top else None

    def _continuing_same_rank_only(self) -> bool:
        """True once a turn is already open (something's been played this
        turn) and the top card isn't an uncovered six. In that state, adding
        more cards is restricted to the rank already established this turn --
        switching to a different rank just because it happens to match the
        last card's suit is a fresh lead, not a continuation, and fresh leads
        are only allowed at the start of a turn or to cover a six."""
        top = self.top_card()
        return self.played_this_turn and top is not None and top.rank != 6

    def _turn_returns_to_current(self) -> bool:
        """True if ending the turn right now would, after all pending skips
        (from 8s / Aces) are consumed, hand play straight back to the current
        player -- e.g. an 8 in a two-player game. In that case the player may
        immediately make a fresh lead (by suit or rank) without pressing "end
        turn" first; the lead implicitly ends the turn and applies penalties."""
        if not self.played_this_turn or self.pending_skip <= 0:
            return False
        # mirror _begin_turn: each opponent reached uses up one skip, the
        # current player (the skips' source) is passed over for free
        skips = self.pending_skip
        idx = self._next_index(self.turn_index)
        while skips > 0:
            if idx != self.turn_index:
                skips -= 1
            idx = self._next_index(idx)
        return idx == self.turn_index

    def _jack_may_continue(self) -> bool:
        """Mid-turn, a Jack may only be added on top of an 8 or an Ace -- on
        any other rank the continuation is locked to that rank alone."""
        top = self.top_card()
        return top is not None and top.rank in (8, 14)

    def _fresh_lead_ok(self, card: Card) -> bool:
        return card.is_jack or card.rank == self.effective_rank() or card.suit == self.effective_suit()

    def legal_sets(self, hand: list[Card]) -> list[list[Card]]:
        """All legal same-rank groupings the player could play right now as a
        single move. At the start of a turn (or when covering an uncovered
        six), that's any rank with a card matching the effective top by rank
        or suit (or a Jack), plus every other card of that same rank in hand
        (which may be dumped alongside it without limit). Once a turn is
        already open on a non-six top, only the rank already established this
        turn (or a Jack) may be added -- no switching ranks by suit match."""
        top = self.top_card()
        if top is None:
            return []
        by_rank: dict[int, list[Card]] = {}
        for c in hand:
            by_rank.setdefault(c.rank, []).append(c)

        if self._continuing_same_rank_only() and not self._turn_returns_to_current():
            sets = []
            if 11 in by_rank and self._jack_may_continue():
                sets.append(by_rank[11])
            if top.rank in by_rank:
                sets.append(by_rank[top.rank])
            return sets

        eff_suit = self.effective_suit()
        eff_rank = self.effective_rank()
        sets = []
        for rank, cards in by_rank.items():
            if rank == 11:  # Jack always playable (wild)
                sets.append(cards)
            elif rank == eff_rank:
                sets.append(cards)
            elif any(c.suit == eff_suit for c in cards):
                sets.append(cards)
        return sets

    def has_legal_move(self, hand: list[Card]) -> bool:
        return len(self.legal_sets(hand)) > 0

    def leadable_cards(self, hand: list[Card]) -> list[Card]:
        """Cards that could individually be played right now: each one, on
        its own, matches the effective top by rank or suit, or is a Jack --
        unless a turn is already open on a non-six top, in which case only
        the rank already established this turn (or a Jack) qualifies. Unlike
        legal_sets, this does NOT include a same-rank sibling just because
        some other card of that rank happens to match -- e.g. with a King on
        top and 8-hearts + 8-clubs in hand, only 8-hearts can lead (8-clubs
        may only be added afterwards, once 8-hearts is down)."""
        top = self.top_card()
        if top is None:
            return []
        if self._continuing_same_rank_only() and not self._turn_returns_to_current():
            return [c for c in hand if c.rank == top.rank or (c.is_jack and self._jack_may_continue())]
        eff_suit = self.effective_suit()
        eff_rank = self.effective_rank()
        return [c for c in hand if c.is_jack or c.rank == eff_rank or c.suit == eff_suit]

    def _draw_one(self, player: Player) -> Card | None:
        if not self.deck:
            self._reshuffle()
        if not self.deck:
            return None  # nothing left anywhere; degenerate edge case
        card = self.deck.pop()
        player.hand.append(card)
        self._note_hand_size(player)
        return card

    def _reshuffle(self) -> None:
        if len(self.table) <= 1:
            return  # nothing to reshuffle from
        top = self.table[-1]
        pool = self.table[:-1]
        self.table = [top]
        random.shuffle(pool)
        self.deck = pool
        self.reshuffle_count += 1
        self._say(f"Колода закончилась — перетасована заново (множитель x{self.multiplier}).")

    # ---------- round lifecycle ----------

    def start_round(self) -> None:
        alive = self.alive_players()
        if len(alive) < 2:
            self._finish_game()
            return

        self.deck = build_deck()
        self.table = []
        self.declared_suit = None
        self.pending_draw = 0
        self.pending_skip = 0
        self.skip_source = None
        self.reshuffle_count = 0
        self.round_active = True
        self.prompt = None
        self.awaiting_continue = False
        self.ready_ids = set()
        self.round_summary = None
        self.round_number += 1
        self.round_started_at = time.monotonic()
        self.round_turns = 0
        self.round_end_info = {}
        self.round_scores_before = {p.id: p.score for p in alive}
        self.round_stats = {
            p.id: {
                "cards_played": 0,     # cards put on the table from hand
                "biggest_play": 0,     # most cards laid down in a single move
                "cards_drawn": 0,      # voluntary draws (incl. digging for a six cover)
                "penalty_drawn": 0,    # cards forced on this player by 7 / 8 / Q-spades
                "penalty_dealt": 0,    # penalty cards this player's plays loaded onto others
                "skips_dealt": 0,      # skips handed out by this player's 8s / Aces
                "turns_skipped": 0,
                "jacks_played": 0,
                "sixes_played": 0,
                "turns": 0,
                "max_hand": 0,
            }
            for p in alive
        }
        for p in alive:
            p.hand = []

        top_score = max(p.score for p in alive)
        dealer_candidates = [p for p in alive if p.score == top_score]
        dealer = random.choice(dealer_candidates)

        for p in alive:
            count = 4 if p is dealer else 5
            for _ in range(count):
                p.hand.append(self.deck.pop())
            self._note_hand_size(p)

        opener = self.deck.pop()
        self.table.append(opener)
        self._say(f"Новая раздача. {dealer.name} сдаёт, на столе {opener.label}.")

        # The dealer's reserve card opens the table as if the dealer had just
        # played it. Most cards are a one-shot event: resolve whatever they
        # do (nothing, or a draw/skip effect on the next player) and move
        # straight on -- the dealer doesn't get an open-ended turn out of it.
        # Six and Jack are the exceptions: covering a six or naming a wild
        # suit is an obligation that belongs to whoever the card "belongs"
        # to, so the dealer is stuck with it exactly like any player who
        # plays one themselves.
        dealer_idx = self.players.index(dealer)

        if opener.rank == 6:
            self.turn_index = dealer_idx
            self.drawn_this_turn = False
            self.played_this_turn = False
            return

        if opener.rank == 11:
            self.turn_index = dealer_idx
            self.prompt = Prompt(kind="suit", player_id=dealer.id, data={"count": 1, "opening": True})
            self._say(f"{dealer.name} должен(-на) назначить масть для открывающего валета.")
            return

        # any other opener opens the dealer's turn exactly as if they had just
        # played it: they may add more of the same rank from hand (no draw --
        # "played" already), and its effect lands when they end the turn. If
        # there's nothing to add, the turn passes on right away.
        self.turn_index = dealer_idx
        self._apply_play_effects([opener])
        self.drawn_this_turn = False
        self.played_this_turn = True
        if not self.leadable_cards(dealer.hand):
            self._advance_turn()
            self._begin_turn()

    # ---------- turn processing ----------

    def must_cover_six(self) -> bool:
        top = self.top_card()
        return top is not None and top.rank == 6

    def _begin_turn(self) -> None:
        """Resolve any pending forced draws/skips (unconditional consequences
        of the previous player's special cards), then wait for the current
        player's explicit action: draw_card / play_cards / pass_turn. Playing
        is never automatic -- a player may hold a legal move and still choose
        to draw or pass instead."""
        if not self.round_active:
            return
        player = self.current_player()

        if self.pending_draw > 0:
            n = self.pending_draw
            self.pending_draw = 0
            drawn = [self._draw_one(player) for _ in range(n)]
            drawn = [c for c in drawn if c]
            self._stat(player, "penalty_drawn", len(drawn))
            self._say(f"{player.name} берёт {len(drawn)} карт(ы) (штраф).")

        if self.pending_skip > 0:
            # skips only ever hit opponents: when the rotation comes back
            # round to whoever played the 8s/Aces, it simply passes over
            # them without using up a skip
            if self.turn_index != self.skip_source:
                self.pending_skip -= 1
                self._stat(player, "turns_skipped")
                self._say(f"{player.name} пропускает ход.")
            self._advance_turn()
            self._begin_turn()
            return

        # a fresh turn starts here: reset the one-voluntary-draw allowance and
        # the "have I played anything yet" flag (the six-obligation ignores
        # the draw allowance; it never lets a turn become "fresh" anyway)
        self.drawn_this_turn = False
        self.played_this_turn = False
        self.round_turns += 1
        self._stat(player, "turns")

    # ---------- player actions ----------

    def draw_card(self, player_id: str) -> None:
        self._require_round_active()
        if self.prompt is not None:
            raise GameError("ожидается решение игрока")
        player = self.current_player()
        if player.id != player_id:
            raise GameError("сейчас не ваш ход")
        if not self.can_draw():
            if not self._can_refill():
                raise GameError("колода пуста")
            if self.played_this_turn:
                raise GameError("после хода картой брать из колоды нельзя — доложите карту того же номинала или закончите ход")
            raise GameError("за ход можно взять только одну карту")
        if not self.must_cover_six() and self._turn_returns_to_current():
            # the opponent's turn is skipped anyway (8/Ace), so drawing now
            # opens the player's next turn: close this one first so the
            # penalties land and the fresh turn's one-draw allowance is used.
            self._advance_turn()
            self._begin_turn()
        card = self._draw_one(player)
        if card is None:
            # only possible when the penalty just handed out took the last
            # cards; the new turn has started, there's simply nothing to take
            self._say("Брать нечего — колода пуста.")
            return
        self.drawn_this_turn = True
        self._stat(player, "cards_drawn")
        self._say(f"{player.name} берёт карту из колоды.")

    def can_draw(self) -> bool:
        """A six must be covered, so drawing is unlimited then. Otherwise only
        one voluntary draw per turn, and only before any card is played --
        unless pending skips hand the turn straight back (see
        _turn_returns_to_current), in which case the draw opens a new turn."""
        if not self._can_refill():
            return False
        if self.must_cover_six():
            return True
        if self.played_this_turn:
            return self._turn_returns_to_current()
        return not self.drawn_this_turn

    def _can_refill(self) -> bool:
        """Whether there's any card left to draw (the deck, or a table pile
        that can be reshuffled into a new deck)."""
        return bool(self.deck) or len(self.table) > 1

    def can_pass(self) -> bool:
        """Passing needs a draw or a play first, and never while a six is
        uncovered. When pending skips (8/Ace) would hand the turn straight
        back, ending it is pointless -- the player must draw or play instead
        (either one closes the turn implicitly). If there's truly no card
        left to draw, passing is allowed whenever the player can't play, so
        they're never stuck."""
        if not self._can_refill():
            if self.must_cover_six():
                return not self.leadable_cards(self.current_player().hand)
            return True
        if self.must_cover_six():
            return False
        if not (self.drawn_this_turn or self.played_this_turn):
            return False
        if self._turn_returns_to_current():
            return False
        return True

    def pass_turn(self, player_id: str) -> None:
        self._require_round_active()
        if self.prompt is not None:
            raise GameError("ожидается решение игрока")
        player = self.current_player()
        if player.id != player_id:
            raise GameError("сейчас не ваш ход")
        if not self.can_pass():
            if self.must_cover_six():
                raise GameError("шестёрку обязательно нужно накрыть")
            if self._turn_returns_to_current():
                raise GameError("ход всё равно возвращается к вам — сначала возьмите карту или сходите")
            raise GameError("сначала нужно взять карту из колоды или сходить")
        self._say(f"{player.name} пропускает ход.")
        self._advance_turn()
        self._begin_turn()

    def play_cards(self, player_id: str, cards: list[Card]) -> None:
        self._require_round_active()
        if self.prompt is not None:
            raise GameError("ожидается решение игрока")
        player = self.current_player()
        if player.id != player_id:
            raise GameError("сейчас не ваш ход")
        if not cards:
            raise GameError("нужно выбрать хотя бы одну карту")
        ranks = {c.rank for c in cards}
        if len(ranks) != 1:
            raise GameError("можно класть карты только одного номинала за раз")
        rank = cards[0].rank

        hand_lookup = {(c.rank, c.suit): c for c in player.hand}
        for c in cards:
            if (c.rank, c.suit) not in hand_lookup:
                raise GameError("этой карты нет у вас на руке")

        # A Jack is wild when leading a fresh turn or covering a six. Otherwise:
        # leading a fresh turn (nothing played yet this turn) or covering an
        # uncovered six must match the actual top card by suit or rank -- a
        # same-rank sibling that only matches because *another* card of that
        # rank would isn't enough on its own, it may only be added afterwards,
        # once the real match has been led. But once a turn is already open
        # on a non-six top, a new rank can no longer be led just because it
        # happens to match the last card's suit -- only more of the rank
        # already established this turn is allowed (plus a Jack on an 8 or
        # Ace); switching rank requires ending the turn first.
        lead = cards[0]
        top = self.top_card()
        if (self._continuing_same_rank_only() and lead.rank != top.rank
                and self._turn_returns_to_current()):
            # e.g. after an 8 in a two-player game the opponent's turn is
            # skipped anyway, so a fresh lead by suit (or a Jack) is allowed
            # right away: close the current turn (penalties hit the opponent,
            # who skips), then this play opens the player's next turn.
            if not self._fresh_lead_ok(lead):
                raise GameError(f"{lead.label} нельзя положить на {top.label} — нужна карта в масть, в номинал, или валет")
            self._advance_turn()
            self._begin_turn()
        elif self._continuing_same_rank_only():
            if lead.rank != top.rank and not (lead.is_jack and self._jack_may_continue()):
                raise GameError(f"{lead.label} нельзя доложить поверх {top.label} — в этом ходу можно класть только карты номинала {RANK_NAMES[top.rank]}, или закончить ход")
        elif not self._fresh_lead_ok(lead):
            raise GameError(f"{lead.label} нельзя положить на {top.label} — нужна карта в масть, в номинал, или валет")

        for c in cards:
            player.hand.remove(c)
            self.table.append(c)
        self._say(f"{player.name} кладёт {', '.join(c.label for c in cards)}.")
        self.played_this_turn = True
        self._stat(player, "cards_played", len(cards))
        stats = self.round_stats.get(player.id)
        if stats is not None:
            stats["biggest_play"] = max(stats["biggest_play"], len(cards))
        if rank == 11:
            self._stat(player, "jacks_played", len(cards))
        elif rank == 6:
            self._stat(player, "sixes_played", len(cards))

        if rank == 11:
            self.prompt = Prompt(kind="suit", player_id=player.id, data={"count": len(cards)})
            return

        self.declared_suit = None
        draw_before, skip_before = self.pending_draw, self.pending_skip
        self._apply_play_effects(cards)
        self._stat(player, "penalty_dealt", self.pending_draw - draw_before)
        self._stat(player, "skips_dealt", self.pending_skip - skip_before)

        if rank == 6:
            # a six never resolves a turn: the same player must keep drawing
            # and covering it (even if this play just emptied their hand --
            # they don't get to end the round on a six) until something else
            # ends up on top.
            return

        if self._check_four_of_a_kind():
            self.prompt = Prompt(kind="bridge", player_id=player.id, data={})
            return

        if not player.hand:
            self._end_round(winner=player, last_played_rank=None, last_played_count=0)
            return

        # stay on the same player: they may add more cards (matching whatever
        # they just played, by suit or rank -- same rule as any lead), draw
        # their one voluntary card, or explicitly end their turn (pass_turn)
        # to hand play to the next player.

    def declare_suit(self, player_id: str, suit: str) -> None:
        if self.prompt is None or self.prompt.kind != "suit" or self.prompt.player_id != player_id:
            raise GameError("сейчас не время выбирать масть")
        if suit not in ("hearts", "diamonds", "clubs", "spades"):
            raise GameError("неизвестная масть")
        declarer = self.player_by_id(player_id)
        count = self.prompt.data.get("count", 1)
        is_opening = self.prompt.data.get("opening", False)
        self.declared_suit = suit
        self.prompt = None
        self._say(f"{declarer.name} назначает масть {SUIT_SYMBOLS[suit]}.")

        if is_opening:
            # the dealer's flipped opening card was a Jack: naming the suit
            # was their whole "move" with it, so play now continues with the
            # next player -- same as any other opener that isn't a six.
            self._advance_turn()
            self._begin_turn()
            return

        player = declarer  # == current_player(), since only the active player can hold this prompt
        if self._check_four_of_a_kind():
            self.prompt = Prompt(kind="bridge", player_id=player.id, data={})
            return

        if not player.hand:
            self._end_round(winner=player, last_played_rank=11, last_played_count=count)
            return

        # unlike other cards, a Jack always ends the turn once its suit is
        # named -- it doesn't stay open for the player to keep building on.
        self._advance_turn()
        self._begin_turn()

    def declare_bridge(self, player_id: str, accept: bool) -> None:
        if self.prompt is None or self.prompt.kind != "bridge" or self.prompt.player_id != player_id:
            raise GameError("сейчас нельзя объявить Бридж")
        player = self.player_by_id(player_id)
        self.prompt = None

        if not accept:
            self._say(f"{player.name} не объявляет Бридж, игра продолжается.")
            if not player.hand:
                self._end_round(winner=player, last_played_rank=None, last_played_count=0)
                return
            # same as any other play: stay on this player -- they may add
            # more (matching whatever's now on top), draw, or end their turn.
            return

        self._say(f"{player.name} объявляет БРИДЖ! Раздача завершена немедленно.")
        self.round_end_info = {"reason": "bridge", "player_id": player.id}
        self._end_round(winner=None, last_played_rank=None, last_played_count=0)

    def resolve_jack_end(self, player_id: str, choice: str) -> None:
        if self.prompt is None or self.prompt.kind != "jack_end" or self.prompt.player_id != player_id:
            raise GameError("сейчас нельзя выбрать эффект валета")
        count = self.prompt.data.get("count", 1)
        winner = self.player_by_id(player_id)
        self.prompt = None
        if choice in ("penalty", "multiply"):
            self.round_end_info["jack_choice"] = choice
        if choice == "penalty":
            winner.score += -20 * count
            self._say(f"{winner.name} берёт себе {-20 * count} очков.")
            self._finalize_scores(exclude_winner=True, extra_multiplier=1)
        elif choice == "multiply":
            factor = count + 1
            self._say(f"Очки на руках у остальных игроков умножаются на x{factor}.")
            self._finalize_scores(exclude_winner=True, extra_multiplier=factor)
        else:
            raise GameError("неизвестный выбор")
        self._after_scoring()

    def leave(self, player_id: str) -> None:
        """A player quits mid-game: they forfeit (eliminated), their hand goes
        under the deck, and play carries on without them."""
        player = self.player_by_id(player_id)
        if player is None or player.eliminated:
            return
        was_current = self.round_active and self.current_player() is player
        player.eliminated = True
        player.connected = False
        self.deck[0:0] = player.hand
        player.hand = []
        self._say(f"{player.name} покидает игру.")

        if self.game_over:
            return
        if len(self.alive_players()) <= 1:
            self.prompt = None
            self.awaiting_continue = False
            self._finish_game()
            return

        if self.awaiting_continue:
            # between rounds: nobody should be left waiting on a player who quit
            self.ready_ids.discard(player.id)
            self._maybe_start_next_round()
            return

        if self.prompt is not None and self.prompt.player_id == player.id:
            kind = self.prompt.kind
            self.prompt = None
            if kind == "jack_end":
                # the round already ended on their Jack; score it plainly
                self._finalize_scores(exclude_winner=True, extra_multiplier=1)
                self._after_scoring()
                return
            if kind == "suit" and self.top_card() is not None:
                self.declared_suit = self.top_card().suit

        if was_current:
            self._advance_turn()
            self._begin_turn()

    # ---------- effects ----------

    def _apply_play_effects(self, cards: list[Card]) -> None:
        """Every special card played this turn contributes its own effect;
        contributions from the whole chain sum together for the next player."""
        for c in cards:
            if c.rank == 7:
                self.pending_draw += 1
            elif c.rank == 8:
                self.pending_draw += 2
                self.pending_skip += 1
            elif c.is_queen_of_spades:
                self.pending_draw += 5
            elif c.rank == 14:
                self.pending_skip += 1
        if self.pending_skip > 0:
            self.skip_source = self.turn_index
            # 6, 9, 10, K and a plain Q carry no special effect

    def _check_four_of_a_kind(self) -> bool:
        if len(self.table) < 4:
            return False
        last4 = self.table[-4:]
        ranks = {c.rank for c in last4}
        return len(ranks) == 1

    # ---------- round end / scoring ----------

    def _end_round(self, winner: Player | None, last_played_rank: int | None, last_played_count: int) -> None:
        self.round_active = False
        if winner is not None:
            ended_on_jack = last_played_rank == 11
            self.round_end_info = {
                "reason": "jack" if ended_on_jack else "out",
                "player_id": winner.id,
                "jack_count": last_played_count if ended_on_jack else 0,
            }
        if winner is not None and last_played_rank == 11:
            self.prompt = Prompt(kind="jack_end", player_id=winner.id, data={"count": last_played_count})
            self._say(f"{winner.name} закончил(а) валетом! Выбор: -{20 * last_played_count} очков себе, либо x{last_played_count + 1} очков у остальных.")
            return
        self._finalize_scores(exclude_winner=winner is not None, extra_multiplier=1)
        self._after_scoring()

    def _finalize_scores(self, exclude_winner: bool, extra_multiplier: int) -> None:
        winner_ids = set()
        if exclude_winner:
            for p in self.players:
                if not p.hand and not p.eliminated:
                    winner_ids.add(p.id)
        for p in self.alive_players():
            if p.id in winner_ids:
                continue
            pts = hand_score(p.hand) * self.multiplier * extra_multiplier
            if pts:
                p.score += pts
                self._say(f"{p.name}: +{pts} очков (на руке {len(p.hand)} карт).")

    def _after_scoring(self) -> None:
        raw_scores = {p.id: p.score for p in self.players}
        for p in self.alive_players():
            if p.score == MAX_SCORE:
                p.score = 0
                self._say(f"{p.name} набрал(а) ровно {MAX_SCORE} — очки обнулены.")
            elif p.score > MAX_SCORE:
                p.eliminated = True
                self._say(f"{p.name} выбывает из игры с {p.score} очками.")

        self._build_round_summary(raw_scores)

        alive = self.alive_players()
        if len(alive) <= 1:
            self._finish_game()
        else:
            # hold here until everyone still in the game has seen the summary
            self.awaiting_continue = True
            self.ready_ids = set()

    def _build_round_summary(self, raw_scores: dict[str, int]) -> None:
        """Snapshot of the round that just ended, taken after scoring (and the
        125-reset / elimination pass) but before hands are cleared for the
        next deal, so the leftover hands can be revealed."""
        rows = []
        for p in self.players:
            stats = self.round_stats.get(p.id)
            if stats is None:
                continue  # wasn't dealt into this round
            before = self.round_scores_before.get(p.id, 0)
            raw = raw_scores.get(p.id, p.score)
            rows.append({
                "id": p.id,
                "name": p.name,
                "hand": [c.to_dict() for c in p.hand],
                "points": raw - before,
                "score_before": before,
                "score_after": p.score,
                "reset": raw == MAX_SCORE,
                "eliminated": p.eliminated,
                "stats": dict(stats),
            })
        info = {"reason": None, "player_id": None, "jack_count": 0, "jack_choice": None}
        info.update(self.round_end_info)
        self.round_summary = {
            "number": self.round_number,
            **info,
            "multiplier": self.multiplier,
            "reshuffles": self.reshuffle_count,
            "turns": self.round_turns,
            "duration_sec": int(time.monotonic() - self.round_started_at) if self.round_started_at else 0,
            "players": rows,
        }

    def continue_round(self, player_id: str) -> None:
        if not self.awaiting_continue:
            raise GameError("сейчас нечего подтверждать")
        player = self.player_by_id(player_id)
        if player is None or player.eliminated:
            raise GameError("вы не участвуете в следующей раздаче")
        self.ready_ids.add(player_id)
        self._maybe_start_next_round()

    def _maybe_start_next_round(self) -> None:
        if not self.awaiting_continue:
            return
        if {p.id for p in self.alive_players()} <= self.ready_ids:
            self.start_round()

    def _finish_game(self) -> None:
        self.game_over = True
        self.round_active = False
        ranked = sorted(self.players, key=lambda p: (p.eliminated, p.score))
        self.standings = [
            {"id": p.id, "name": p.name, "score": p.score, "eliminated": p.eliminated}
            for p in ranked
        ]
        if ranked:
            self._say(f"Игра окончена. Победитель: {ranked[0].name}.")

    # ---------- serialization ----------

    def state_for(self, viewer_id: str) -> dict:
        top = self.top_card()
        return {
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "hand_count": len(p.hand),
                    "score": p.score,
                    "eliminated": p.eliminated,
                    "connected": p.connected,
                }
                for p in self.players
            ],
            "your_hand": [c.to_dict() for c in (self.player_by_id(viewer_id).hand if self.player_by_id(viewer_id) else [])],
            "table_top": top.to_dict() if top else None,
            "declared_suit": self.declared_suit,
            "deck_count": len(self.deck),
            "turn_player_id": self.current_player().id if self.players and self.round_active else None,
            "multiplier": self.multiplier,
            "round_active": self.round_active,
            "game_over": self.game_over,
            "standings": self.standings,
            "round_number": self.round_number,
            "round_summary": self.round_summary,
            "awaiting_continue": self.awaiting_continue,
            "ready_ids": sorted(self.ready_ids),
            "prompt": (
                {"kind": self.prompt.kind, "player_id": self.prompt.player_id, "data": self.prompt.data}
                if self.prompt else None
            ),
            "legal_cards": (
                [c.to_dict() for c in self.leadable_cards(self.player_by_id(viewer_id).hand)]
                if self.round_active and self.player_by_id(viewer_id) and self.current_player().id == viewer_id and self.prompt is None
                else []
            ),
            "must_cover_six": self.must_cover_six(),
            "can_draw": self.can_draw(),
            "can_pass": self.can_pass(),
            "has_played_this_turn": self.played_this_turn,
        }
