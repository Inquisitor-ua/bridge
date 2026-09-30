"""Card model and deck helpers for the 36-card Bridge deck."""
from __future__ import annotations

import random
from dataclasses import dataclass

SUITS = ("hearts", "diamonds", "clubs", "spades")
# Order matters only for display; index-based rank comparisons use the values below.
RANKS = (6, 7, 8, 9, 10, 11, 12, 13, 14)  # 11=J, 12=Q, 13=K, 14=A

RANK_NAMES = {6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}
SUIT_SYMBOLS = {"hearts": "♥", "diamonds": "♦", "clubs": "♣", "spades": "♠"}


@dataclass(frozen=True)
class Card:
    rank: int
    suit: str

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_dict(d: dict) -> "Card":
        return Card(rank=int(d["rank"]), suit=str(d["suit"]))

    @property
    def label(self) -> str:
        return f"{RANK_NAMES[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    @property
    def is_jack(self) -> bool:
        return self.rank == 11

    @property
    def is_queen_of_spades(self) -> bool:
        return self.rank == 12 and self.suit == "spades"


def build_deck() -> list[Card]:
    deck = [Card(rank=r, suit=s) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def card_value(card: Card, hand_size: int) -> int:
    """Penalty value of a single card when tallying a hand at round end."""
    if card.rank in (6, 7, 8, 9):
        return 0
    if card.rank == 14:
        return 15
    if card.rank == 11 and hand_size == 1:
        return 20
    # 10, J (not alone), Q, K
    return 10


def hand_score(cards: list[Card]) -> int:
    n = len(cards)
    return sum(card_value(c, n) for c in cards)
