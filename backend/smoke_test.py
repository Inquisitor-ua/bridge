"""Manual smoke test: drives the Engine directly with scripted plays to sanity
check turn order, forced draws/skips, wild jacks and round scoring. Not a
pytest suite -- just a quick sanity harness run with `python -m backend.smoke_test`.
"""
from . import engine as engine_mod
from .cards import Card
from .engine import Engine, GameError, Player


def with_fixed_deck(fixed_pop_order):
    """Context manager that makes build_deck() return a deck whose pop()
    order matches fixed_pop_order exactly (index 0 popped first)."""
    class _Ctx:
        def __enter__(self):
            self._orig = engine_mod.build_deck
            engine_mod.build_deck = lambda: list(reversed(fixed_pop_order))
            return self

        def __exit__(self, *exc):
            engine_mod.build_deck = self._orig

    return _Ctx()


def make_engine(n=3):
    players = [Player(id=str(i), name=f"P{i}") for i in range(n)]
    return Engine(players), players


def test_basic_flow():
    eng, players = make_engine(2)
    eng.start_round()
    assert eng.round_active
    cur = eng.current_player()
    print("opening top:", eng.top_card().label, "turn:", cur.name)
    print("hand:", [c.label for c in cur.hand])
    assert eng.has_legal_move(cur.hand) or True  # not guaranteed, just informational


def test_seven_forces_draw():
    eng, players = make_engine(2)
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0, p1 = players
    p0.hand = [Card(7, "hearts"), Card(6, "clubs")]
    # p1 already holds a heart, so after the forced draw they have a legal move
    # and the engine should NOT fall through to the general extra-draw rule.
    p1.hand = [Card(10, "hearts")]
    eng.deck = [Card(9, "clubs")]
    eng.round_active = True
    before = len(p1.hand)
    eng.play_cards(p0.id, [Card(7, "hearts")])
    assert eng.current_player().id == p0.id, "turn stays with p0 until they explicitly end it"
    eng.pass_turn(p0.id)  # p0 ends their turn -> now the 7's forced draw resolves for p1
    assert eng.pending_draw == 0, "pending draw should have resolved once p0 ended their turn"
    assert len(p1.hand) == before + 1, f"expected forced draw of exactly 1, hand={p1.hand}"
    assert eng.current_player().id == p1.id
    print("seven forces draw: OK, p1 hand now", [c.label for c in p1.hand])


def test_eight_draw_and_skip():
    eng, players = make_engine(3)
    p0, p1, p2 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(8, "hearts"), Card(6, "spades")]
    p1.hand = [Card(10, "spades")]
    p2.hand = [Card(10, "clubs")]
    eng.deck = [Card(6, "diamonds"), Card(6, "clubs")]
    eng.round_active = True
    eng.play_cards(p0.id, [Card(8, "hearts")])
    assert eng.current_player().id == p0.id, "turn stays with p0 until they explicitly end it"
    eng.pass_turn(p0.id)
    # p1 should have drawn 2 and been skipped; turn should now be p2
    assert len(p1.hand) == 3, f"p1 should have 2 drawn + original = 3, got {len(p1.hand)}"
    assert eng.current_player().id == p2.id, f"expected p2's turn, got {eng.current_player().name}"
    print("eight draw+skip: OK")


def test_jack_wild_and_suit():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(11, "clubs"), Card(6, "diamonds")]
    p1.hand = [Card(10, "spades"), Card(9, "spades")]
    eng.deck = []
    eng.round_active = True
    eng.play_cards(p0.id, [Card(11, "clubs")])
    assert eng.prompt is None, "the suit is asked for only when the turn is ended"
    eng.pass_turn(p0.id)
    assert eng.prompt is not None and eng.prompt.kind == "suit"
    eng.declare_suit(p0.id, "spades")
    assert eng.declared_suit == "spades"
    assert eng.current_player().id == p1.id, "a jack always ends the turn once its suit is named"
    startable = eng.legal_sets(p1.hand)
    ranks = {s[0].rank for s in startable}
    assert 10 in ranks and 9 in ranks, f"expected spade cards playable, got {ranks}"
    print("jack wild: OK")


def test_rejects_mixed_rank_play():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(9, "hearts"), Card(10, "clubs")]
    p1.hand = [Card(6, "spades")]
    eng.deck = []
    eng.round_active = True
    try:
        eng.play_cards(p0.id, [Card(9, "hearts"), Card(10, "clubs")])
        raise AssertionError("expected mixed-rank play to be rejected")
    except Exception as e:
        assert "одного номинала" in str(e), e
    print("rejects mixed rank play: OK")


def test_two_player_skip_returns_turn():
    """The mechanic behind the user's long combo example: in a 2-player game,
    a skip effect (8 or Ace) has nowhere else to go, so the turn comes right
    back to the player who just played -- letting them take another normal
    turn immediately, which from the outside looks like one long combo but is
    actually a sequence of separate turns."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(8, "clubs"), Card(9, "spades")]  # spare card so hand isn't emptied
    p1.hand = [Card(10, "clubs")]
    eng.deck = [Card(6, "hearts"), Card(6, "diamonds"), Card(10, "hearts")]
    eng.round_active = True

    eng.play_cards(p0.id, [Card(8, "clubs")])
    assert eng.current_player().id == p0.id, "turn stays with p0 until they explicitly end it"

    # ending the turn is pointless here (it would come straight back), so
    # passing is refused; drawing instead closes the turn implicitly
    assert not eng.can_pass()
    try:
        eng.pass_turn(p0.id)
        raise AssertionError("pass should be refused while the skip hands the turn back")
    except GameError:
        pass
    eng.draw_card(p0.id)

    assert eng.current_player().id == p0.id, f"skip should ping-pong back to p0 in a 2-player game, got {eng.current_player().name}"
    assert len(p1.hand) == 3, f"p1 should have drawn 2 penalty cards, got {p1.hand}"
    assert eng.pending_draw == 0 and eng.pending_skip == 0
    assert len(p0.hand) == 2 and not eng.can_draw(), "the draw belongs to p0's new turn"
    print("two player skip returns turn: OK")


def test_skips_only_hit_opponents():
    """Skips never land on whoever played them: two Aces in a 2-player game
    still hand the turn straight back (opponent skips twice), so a fresh lead
    by suit is allowed right away; in 3-player, three Aces skip P1, P2, P1."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(13, "diamonds")]
    eng.turn_index = 0
    eng.round_active = True
    eng.deck = [Card(10, "hearts") for _ in range(5)]
    p0.hand = [Card(14, "diamonds"), Card(14, "clubs"), Card(9, "clubs"), Card(12, "spades")]
    p1.hand = [Card(10, "spades")]
    eng.play_cards(p0.id, [Card(14, "diamonds")])
    eng.play_cards(p0.id, [Card(14, "clubs")])
    assert Card(9, "clubs") in eng.leadable_cards(p0.hand)
    eng.play_cards(p0.id, [Card(9, "clubs")])
    assert eng.current_player().id == p0.id and eng.pending_skip == 0

    eng, players = make_engine(3)
    p0, p1, p2 = players
    eng.table = [Card(13, "diamonds")]
    eng.turn_index = 0
    eng.round_active = True
    aces = [Card(14, "diamonds"), Card(14, "clubs"), Card(14, "hearts")]
    p0.hand = aces + [Card(9, "clubs")]
    eng.play_cards(p0.id, aces)
    eng.pass_turn(p0.id)
    assert eng.current_player().id == p2.id, f"expected P1, P2, P1 to skip, got {eng.current_player().name}"
    print("skips only hit opponents: OK")


def test_six_keeps_turn_with_same_player():
    """Playing a six never resolves a turn: the SAME player must keep
    drawing/covering it, even if it emptied their hand."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(6, "hearts")]  # this is p0's whole hand
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(9, "diamonds")]  # p0 will draw this next, matching the 6's suit? no -- just filler
    eng.round_active = True

    eng.play_cards(p0.id, [Card(6, "hearts")])

    assert eng.round_active, "emptying the hand with a six must not end the round"
    assert eng.current_player().id == p0.id, "turn must stay with the player who played the six"
    assert eng.must_cover_six() is True
    print("six keeps turn with same player: OK")


def test_pass_blocked_while_six_uncovered():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(6, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(10, "clubs")]  # nothing matching hearts/6 yet
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(9, "clubs")]  # something left to draw, so passing isn't the only way out
    eng.round_active = True
    try:
        eng.pass_turn(p0.id)
        raise AssertionError("expected pass to be blocked while a six is uncovered")
    except Exception as e:
        assert "шестёрку" in str(e), e
    print("pass blocked while six uncovered: OK")


def test_draw_card_and_voluntary_pass():
    """A player may draw voluntarily and pass even while holding a playable
    card -- playing is never forced."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(11, "hearts")]  # a jack -- always legal, but p0 won't play it
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(6, "diamonds")]
    eng.round_active = True

    eng.draw_card(p0.id)
    assert len(p0.hand) == 2, p0.hand
    assert eng.current_player().id == p0.id, "drawing must not end the turn"

    eng.pass_turn(p0.id)
    assert eng.current_player().id == p1.id, "pass must hand the turn over even though p0 held a jack"
    print("draw card and voluntary pass: OK")


def test_draw_capped_at_one_on_normal_turn():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(10, "clubs")]
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(6, "diamonds"), Card(7, "hearts")]
    eng.round_active = True

    eng.draw_card(p0.id)
    assert len(p0.hand) == 2
    try:
        eng.draw_card(p0.id)
        raise AssertionError("expected a second voluntary draw to be rejected")
    except Exception as e:
        assert "одну карту" in str(e), e
    print("draw capped at one on normal turn: OK")


def test_six_allows_unlimited_draws():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(6, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(10, "clubs")]  # nothing matching hearts/6 yet
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(9, "diamonds"), Card(8, "diamonds"), Card(10, "hearts")]
    eng.round_active = True

    eng.draw_card(p0.id)
    eng.draw_card(p0.id)
    eng.draw_card(p0.id)  # three draws in a row must all succeed while a six is uncovered
    assert len(p0.hand) == 4
    print("six allows unlimited draws: OK")


def test_partial_dump_keeps_turn_open_until_explicit_end_turn():
    """Playing one card of a same-rank pair must not end the turn; the same
    player may add the second one, and only actually ends their turn by
    calling pass_turn."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(13, "clubs"), Card(13, "hearts"), Card(10, "diamonds")]
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    eng.play_cards(p0.id, [Card(13, "clubs")])
    assert eng.current_player().id == p0.id, "playing one card of a pair must not end the turn"

    eng.play_cards(p0.id, [Card(13, "hearts")])  # the second king: matches by rank, still fine
    assert eng.current_player().id == p0.id
    assert p0.hand == [Card(10, "diamonds")]

    eng.pass_turn(p0.id)
    assert eng.current_player().id == p1.id, "explicit pass must finally hand the turn over"
    print("partial dump keeps turn open until explicit end turn: OK")


def test_continuation_locked_to_the_rank_led_this_turn():
    """Regression: once a turn is open, adding more cards is restricted to
    the rank already led this turn -- a card that only matches by SUIT to
    whatever was just placed (a different rank) must be rejected. This is
    what stopped a player who led a 7 from immediately continuing with an 8
    of the same suit without ever ending their turn: 7 carries no skip, so
    the opponent must get a real turn first."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(7, "clubs"), Card(7, "hearts"), Card(8, "hearts"), Card(6, "spades")]  # spare so hand isn't emptied
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    eng.play_cards(p0.id, [Card(7, "clubs")])  # matches top (9 clubs) by suit
    assert eng.current_player().id == p0.id

    eng.play_cards(p0.id, [Card(7, "hearts")])  # same rank as what's already led -- fine
    assert eng.current_player().id == p0.id
    assert eng.top_card() == Card(7, "hearts")

    try:
        eng.play_cards(p0.id, [Card(8, "hearts")])  # matches 7-hearts by suit, but a DIFFERENT rank -- must be rejected
        raise AssertionError("expected switching rank mid-turn (via suit match) to be rejected")
    except Exception as e:
        assert "номинала" in str(e), e
    assert eng.current_player().id == p0.id
    assert p0.hand == [Card(8, "hearts"), Card(6, "spades")], "the rejected play must not have been consumed"
    print("continuation locked to the rank led this turn: OK")


def test_covering_a_six_may_lead_a_new_rank_then_locks_to_it():
    """Covering a six is still a fresh lead (suit/rank/jack match against the
    six), even though the turn was already open -- it starts a new rank for
    the rest of that turn. After covering, though, the same same-rank-only
    restriction kicks back in: a further suit-only match to yet another rank
    must be rejected."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(6, "hearts"), Card(7, "hearts"), Card(8, "hearts"), Card(7, "clubs")]
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    eng.play_cards(p0.id, [Card(6, "hearts")])  # matches top by suit
    assert eng.must_cover_six() is True

    eng.play_cards(p0.id, [Card(7, "hearts")])  # covers the six: matches its suit -- a fresh lead, rank switch allowed here
    assert eng.must_cover_six() is False
    assert eng.top_card() == Card(7, "hearts")

    try:
        eng.play_cards(p0.id, [Card(8, "hearts")])  # matches 7-hearts by suit, different rank -- rejected, same as any continuation
        raise AssertionError("expected switching rank after covering a six to be rejected")
    except Exception as e:
        assert "номинала" in str(e), e

    eng.play_cards(p0.id, [Card(7, "clubs")])  # same rank as the covering card -- fine
    assert eng.top_card() == Card(7, "clubs")
    print("covering a six may lead a new rank then locks to it: OK")


def test_jack_always_ends_the_turn():
    """Unlike other cards, a Jack always ends the turn once its suit is
    named -- it never stays open for the player to keep building on."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(11, "hearts"), Card(6, "diamonds")]  # spare card so hand isn't emptied
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    eng.play_cards(p0.id, [Card(11, "hearts")])
    eng.pass_turn(p0.id)
    eng.declare_suit(p0.id, "diamonds")
    assert eng.current_player().id == p1.id, "the turn must pass immediately once the jack's suit is named"
    print("jack always ends the turn: OK")


def test_pass_requires_drawing_or_playing_first():
    """A player can't just pass instantly with zero action taken -- they
    must either draw a card or play something first."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(10, "diamonds")]  # no legal move against 9 clubs
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(6, "hearts")]
    eng.round_active = True

    try:
        eng.pass_turn(p0.id)
        raise AssertionError("expected pass to be rejected before any draw/play this turn")
    except Exception as e:
        assert "сначала нужно" in str(e), e

    eng.draw_card(p0.id)
    eng.pass_turn(p0.id)  # now fine, since a draw happened first
    assert eng.current_player().id == p1.id
    print("pass requires drawing or playing first: OK")


def test_jack_always_playable_regardless_of_top():
    """A Jack is wild: it's always a legal play no matter what's on top,
    whether that's the actual table top or whatever the same player played
    earlier in their own still-open turn."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(14, "clubs"), Card(11, "hearts"), Card(9, "diamonds")]  # spare card so hand isn't emptied
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    eng.play_cards(p0.id, [Card(14, "clubs")])  # ace, matches top by suit
    assert eng.current_player().id == p0.id

    eng.play_cards(p0.id, [Card(11, "hearts")])  # jack doesn't match the ace by suit or rank, but is wild
    assert eng.suit_pending()
    eng.pass_turn(p0.id)
    assert eng.prompt is not None and eng.prompt.kind == "suit", "ending the turn on a jack must trigger the suit prompt"
    print("jack always playable regardless of top: OK")


def test_jack_mid_turn_only_on_eight_or_ace():
    """Once a turn is open, a Jack may be added only on top of an 8 or Ace;
    on any other rank only more of that same rank is allowed."""
    eng, players = make_engine(3)
    p0 = players[0]
    eng.table = [Card(13, "hearts")]
    eng.turn_index = 0
    eng.round_active = True
    p0.hand = [Card(13, "clubs"), Card(11, "diamonds"), Card(9, "spades")]
    eng.play_cards(p0.id, [Card(13, "clubs")])
    assert Card(11, "diamonds") not in eng.leadable_cards(p0.hand)
    try:
        eng.play_cards(p0.id, [Card(11, "diamonds")])
        raise AssertionError("a Jack must not be added on top of a King mid-turn")
    except GameError:
        pass

    eng, players = make_engine(3)
    p0 = players[0]
    eng.table = [Card(13, "hearts")]
    eng.turn_index = 0
    eng.round_active = True
    p0.hand = [Card(8, "hearts"), Card(11, "diamonds"), Card(9, "spades")]
    eng.play_cards(p0.id, [Card(8, "hearts")])
    assert Card(11, "diamonds") in eng.leadable_cards(p0.hand)
    eng.play_cards(p0.id, [Card(11, "diamonds")])
    print("jack mid-turn only on eight or ace: OK")


def test_dealer_selected_by_highest_score():
    eng, players = make_engine(3)
    p0, p1, p2 = players
    p0.score, p1.score, p2.score = 10, 50, 20  # p1 has the most points
    eng.start_round()
    dealt_counts = {p.id: len(p.hand) for p in players}
    dealer_id = next(pid for pid, n in dealt_counts.items() if n == 4)
    assert dealer_id == p1.id, f"expected the highest-score player to be dealer, got counts={dealt_counts}"
    print("dealer selected by highest score: OK")


def test_six_opener_obligates_the_dealer():
    """A six binds whoever it 'belongs to' -- for the round-opening card,
    that's the dealer, exactly as if they'd played it themselves."""
    eng, players = make_engine(2)
    p0, p1 = players
    p0.score, p1.score = 0, 50  # p1 is dealer
    filler = [Card(r, s) for r in (9, 10, 13) for s in ("hearts", "diamonds", "clubs", "spades")]
    pop_order = filler[:5] + filler[5:9] + [Card(6, "spades")]  # p0(5), dealer p1(4), opener
    with with_fixed_deck(pop_order):
        eng.start_round()
    assert eng.top_card() == Card(6, "spades")
    assert eng.current_player().id == p1.id, "the dealer must be the one stuck covering their own opening six"
    assert eng.must_cover_six() is True
    print("six opener obligates the dealer: OK")


def test_jack_opener_prompts_dealer_then_passes_on():
    """A jack opener makes the dealer name the wild suit (it's their card),
    but that's a one-shot decision -- once named, play continues with the
    next player, same as any other opener that isn't a six."""
    eng, players = make_engine(2)
    p0, p1 = players
    p0.score, p1.score = 0, 50  # p1 is dealer
    filler = [Card(r, s) for r in (9, 10, 13) for s in ("hearts", "diamonds", "clubs", "spades")]
    pop_order = filler[:5] + filler[5:9] + [Card(11, "hearts")]
    with with_fixed_deck(pop_order):
        eng.start_round()
    assert eng.top_card() == Card(11, "hearts")
    assert eng.prompt is not None and eng.prompt.kind == "suit" and eng.prompt.player_id == p1.id
    eng.declare_suit(p1.id, "diamonds")
    assert eng.declared_suit == "diamonds"
    assert eng.current_player().id == p0.id, "naming the suit was the dealer's whole move -- play now continues with p0"
    print("jack opener prompts dealer then passes on: OK")


def test_plain_opener_passes_turn_immediately():
    """A boring opener (no effect) is a one-shot event: it resolves and play
    continues directly with the next player -- the dealer gets no turn out
    of it at all."""
    eng, players = make_engine(2)
    p0, p1 = players
    p0.score, p1.score = 0, 50  # p1 is dealer
    filler = [Card(r, s) for r in (9, 10, 12) for s in ("hearts", "diamonds", "clubs", "spades")]
    pop_order = filler[:5] + filler[5:9] + [Card(13, "spades")]  # King: no effect
    with with_fixed_deck(pop_order):
        eng.start_round()
    assert eng.top_card() == Card(13, "spades")
    assert eng.current_player().id == p0.id, "a plain opener must hand play straight to the next player"
    assert eng.played_this_turn is False
    print("plain opener passes turn immediately: OK")


def test_dealer_may_add_same_rank_to_opener():
    """The opener counts as the dealer's own play: holding more of that rank,
    the dealer keeps the turn and may add them (but not draw), then ends it."""
    eng, players = make_engine(2)
    p0, p1 = players
    p0.score, p1.score = 0, 50  # p1 is dealer
    filler = [Card(r, s) for r in (10, 12, 13) for s in ("hearts", "diamonds", "clubs", "spades")]
    dealer_hand = [Card(9, "hearts"), filler[5], filler[6], filler[7]]
    pop_order = filler[:5] + dealer_hand + [Card(9, "spades")]
    with with_fixed_deck(pop_order):
        eng.start_round()
    assert eng.top_card() == Card(9, "spades")
    assert eng.current_player().id == p1.id, "dealer holding another 9 keeps the turn"
    assert not eng.can_draw(), "the opener already counts as a play -- no draw"
    assert eng.leadable_cards(p1.hand) == [Card(9, "hearts")]
    eng.play_cards(p1.id, [Card(9, "hearts")])
    eng.pass_turn(p1.id)
    assert eng.current_player().id == p0.id
    print("dealer may add same rank to opener: OK")


def test_effect_opener_targets_next_player_immediately():
    """A 7 opener (draw 1, no skip) is treated as if the dealer had just
    played it: the penalty lands on the next player right away, and the
    dealer's own hand is untouched."""
    eng, players = make_engine(2)
    p0, p1 = players
    p0.score, p1.score = 0, 50  # p1 is dealer
    filler = [Card(r, s) for r in (9, 10, 13) for s in ("hearts", "diamonds", "clubs", "spades")]
    pop_order = filler[:5] + filler[5:9] + [Card(7, "clubs"), filler[9]]  # p0(5), dealer p1(4), opener, then p0's forced draw
    with with_fixed_deck(pop_order):
        eng.start_round()
    assert eng.top_card() == Card(7, "clubs")
    assert eng.current_player().id == p0.id, "the 7's target (next player) must already have the turn"
    assert len(p0.hand) == 6, f"p0 should have drawn the forced penalty card already, got {p0.hand}"
    assert len(p1.hand) == 4, "the dealer's own hand must not be touched by their opener's effect"
    assert eng.pending_draw == 0
    print("effect opener targets next player immediately: OK")


def test_must_lead_with_the_actually_matching_card():
    """Regression: with a King of hearts on top and both 8-hearts and
    8-clubs in hand, only 8-hearts (the one that actually matches the top's
    suit) may lead. 8-clubs can only be added afterwards, once 8-hearts is
    down and matches it by rank."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(13, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(8, "hearts"), Card(8, "clubs")]
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True

    leadable = eng.leadable_cards(p0.hand)
    assert leadable == [Card(8, "hearts")], f"only 8-hearts should be leadable, got {leadable}"

    try:
        eng.play_cards(p0.id, [Card(8, "clubs")])
        raise AssertionError("expected leading with the non-matching 8-clubs to be rejected")
    except Exception as e:
        assert "нельзя положить" in str(e), e

    try:
        eng.play_cards(p0.id, [Card(8, "clubs"), Card(8, "hearts")])  # wrong order: still rejected
        raise AssertionError("expected wrong-order lead to be rejected")
    except Exception as e:
        assert "нельзя положить" in str(e), e

    eng.play_cards(p0.id, [Card(8, "hearts")])  # leading with the real match: fine
    assert eng.top_card() == Card(8, "hearts")

    eng.play_cards(p0.id, [Card(8, "clubs")])  # matches by rank now: fine to add (empties p0's hand -> round ends)
    print("must lead with the actually matching card: OK")


def test_double_jack_ending():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    p0.hand = [Card(11, "hearts"), Card(11, "clubs")]
    p1.hand = [Card(6, "spades"), Card(10, "spades")]
    eng.deck = []
    eng.round_active = True
    eng.play_cards(p0.id, [Card(11, "hearts"), Card(11, "clubs")])
    assert eng.prompt.kind == "suit" and eng.prompt.data["count"] == 2, eng.prompt
    eng.declare_suit(p0.id, "spades")
    # p0's hand is now empty and ended on 2 jacks -> jack_end prompt with count=2
    assert eng.prompt.kind == "jack_end" and eng.prompt.data["count"] == 2, eng.prompt
    print("double jack ending: OK")





def test_scoring_basic():
    eng, players = make_engine(2)
    p0, p1 = players
    p1.hand = [Card(6, "hearts"), Card(14, "spades"), Card(10, "clubs")]
    eng.reshuffle_count = 0
    eng._finalize_scores(exclude_winner=True, extra_multiplier=1)
    assert p1.score == 0 + 15 + 10, f"expected 25, got {p1.score}"
    print("scoring: OK, p1.score =", p1.score)


def test_lone_jack_worth_20():
    eng, players = make_engine(2)
    p0, p1 = players
    p1.hand = [Card(11, "hearts")]
    eng._finalize_scores(exclude_winner=True, extra_multiplier=1)
    assert p1.score == 20, f"expected lone jack = 20, got {p1.score}"
    print("lone jack scoring: OK")


def test_round_end_waits_for_everyone_to_continue():
    eng, players = make_engine(3)
    p0, p1, p2 = players
    eng.start_round()
    eng.table = [Card(9, "hearts")]
    eng.turn_index = 0
    eng.pending_draw = eng.pending_skip = 0
    eng.drawn_this_turn = eng.played_this_turn = False
    # the random opener may have been a Jack, leaving the dealer's suit
    # prompt open, which would block the scripted play below
    eng.prompt = None
    eng.declared_suit = None
    eng.jack_run = 0
    eng.skip_source = None
    p0.hand = [Card(9, "clubs")]
    p1.hand = [Card(14, "spades"), Card(10, "clubs")]
    p2.hand = [Card(6, "spades")]
    eng.play_cards(p0.id, [Card(9, "clubs")])
    assert not eng.round_active and eng.awaiting_continue
    summary = eng.round_summary
    assert summary["reason"] == "out" and summary["player_id"] == p0.id, summary
    row1 = next(r for r in summary["players"] if r["id"] == p1.id)
    assert row1["points"] == 25 and row1["score_after"] == 25 and len(row1["hand"]) == 2, row1
    assert next(r for r in summary["players"] if r["id"] == p0.id)["stats"]["cards_played"] == 1
    try:
        eng.draw_card(eng.current_player().id)
        assert False, "no actions allowed between rounds"
    except GameError:
        pass
    eng.continue_round(p0.id)
    eng.continue_round(p1.id)
    assert eng.awaiting_continue and eng.round_number == 1
    eng.continue_round(p2.id)
    assert not eng.awaiting_continue and eng.round_active and eng.round_number == 2
    assert eng.round_summary is None
    print("round end waits for continue: OK")


def test_leaver_does_not_block_continue():
    eng, players = make_engine(3)
    p0, p1, p2 = players
    eng.start_round()
    eng.round_active = False
    eng._end_round(winner=None, last_played_rank=None, last_played_count=0)
    assert eng.awaiting_continue
    eng.continue_round(p0.id)
    eng.continue_round(p1.id)
    eng.leave(p2.id)
    assert eng.round_active and eng.round_number == 2
    print("leaver does not block continue: OK")


def test_jacks_can_be_added_one_by_one_before_naming_suit():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(11, "hearts"), Card(11, "spades"), Card(10, "diamonds")]
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(7, "hearts")]
    eng.round_active = True

    eng.play_cards(p0.id, [Card(11, "hearts")])
    assert eng.prompt is None and eng.current_player() is p0
    assert eng.leadable_cards(p0.hand) == [Card(11, "spades")], "only more jacks may follow"
    assert not eng.can_draw(), "no drawing after playing a jack"
    try:
        eng.play_cards(p0.id, [Card(10, "diamonds")])
        raise AssertionError("a non-jack must not follow the jack")
    except GameError:
        pass
    eng.play_cards(p0.id, [Card(11, "spades")])
    assert eng.prompt is None
    eng.pass_turn(p0.id)
    assert eng.prompt.kind == "suit" and eng.prompt.data["count"] == 2, eng.prompt
    eng.declare_suit(p0.id, "diamonds")
    assert eng.current_player() is p1 and eng.declared_suit == "diamonds"
    print("jacks one by one before naming suit: OK")


def test_eight_then_jack_two_players_still_asks_suit():
    """In a 2-player game an 8 hands the turn back anyway, but once a jack
    is on top the suit must be named before anything else happens."""
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(8, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(8, "hearts"), Card(11, "hearts"), Card(13, "hearts")]
    p1.hand = [Card(10, "spades")]
    eng.deck = [Card(7, "spades"), Card(7, "diamonds"), Card(6, "clubs")]
    eng.round_active = True
    eng.play_cards(p0.id, [Card(8, "hearts")])
    eng.play_cards(p0.id, [Card(11, "hearts")])
    assert not eng.can_draw()
    try:
        eng.play_cards(p0.id, [Card(13, "hearts")])
        raise AssertionError("no fresh lead before the jack's suit is named")
    except GameError:
        pass
    eng.pass_turn(p0.id)
    assert eng.prompt.kind == "suit" and eng.prompt.data["count"] == 1
    eng.declare_suit(p0.id, "hearts")
    assert len(p1.hand) == 3, "the 8's penalty still lands on p1"
    print("eight then jack in two-player game: OK")


def test_last_card_jack_asks_suit_immediately():
    eng, players = make_engine(2)
    p0, p1 = players
    eng.table = [Card(9, "clubs")]
    eng.turn_index = 0
    p0.hand = [Card(11, "hearts")]
    p1.hand = [Card(10, "spades")]
    eng.deck = []
    eng.round_active = True
    eng.play_cards(p0.id, [Card(11, "hearts")])
    assert eng.prompt is not None and eng.prompt.kind == "suit", "empty hand: nothing to add, ask right away"
    eng.declare_suit(p0.id, "spades")
    assert eng.prompt.kind == "jack_end" and eng.prompt.data["count"] == 1
    print("last-card jack asks suit immediately: OK")


if __name__ == "__main__":
    test_basic_flow()
    test_seven_forces_draw()
    test_eight_draw_and_skip()
    test_jack_wild_and_suit()
    test_rejects_mixed_rank_play()
    test_two_player_skip_returns_turn()
    test_skips_only_hit_opponents()
    test_six_keeps_turn_with_same_player()
    test_pass_blocked_while_six_uncovered()
    test_draw_card_and_voluntary_pass()
    test_draw_capped_at_one_on_normal_turn()
    test_six_allows_unlimited_draws()
    test_partial_dump_keeps_turn_open_until_explicit_end_turn()
    test_continuation_locked_to_the_rank_led_this_turn()
    test_covering_a_six_may_lead_a_new_rank_then_locks_to_it()
    test_jack_always_ends_the_turn()
    test_pass_requires_drawing_or_playing_first()
    test_jack_always_playable_regardless_of_top()
    test_jack_mid_turn_only_on_eight_or_ace()
    test_dealer_selected_by_highest_score()
    test_six_opener_obligates_the_dealer()
    test_jack_opener_prompts_dealer_then_passes_on()
    test_plain_opener_passes_turn_immediately()
    test_dealer_may_add_same_rank_to_opener()
    test_effect_opener_targets_next_player_immediately()
    test_must_lead_with_the_actually_matching_card()
    test_double_jack_ending()
    test_scoring_basic()
    test_lone_jack_worth_20()
    test_jacks_can_be_added_one_by_one_before_naming_suit()
    test_eight_then_jack_two_players_still_asks_suit()
    test_last_card_jack_asks_suit_immediately()
    test_round_end_waits_for_everyone_to_continue()
    test_leaver_does_not_block_continue()
    print("\nAll smoke tests passed.")
