"""In-memory room/session management on top of the game Engine."""
from __future__ import annotations

import random
import string
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from .cards import Card
from .engine import Engine, GameError, Player

MIN_PLAYERS = 2
MAX_PLAYERS = 6
EMOTE_COOLDOWN = 1.0  # seconds between two emotes from one player
ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _gen_room_code() -> str:
    return "".join(random.choices(ROOM_CODE_ALPHABET, k=4))


@dataclass
class Room:
    code: str
    host_id: str
    players: list[Player] = field(default_factory=list)
    sockets: dict[str, WebSocket] = field(default_factory=dict)
    engine: Engine | None = None
    left: set[str] = field(default_factory=set)  # players who quit a started game
    # after game over: players who pressed "new game"; the rematch starts once
    # everyone still in the room has voted
    rematch_ids: set[str] = field(default_factory=set)
    emote_at: dict[str, float] = field(default_factory=dict)  # player id -> time of their last emote

    def allow_emote(self, pid: str) -> bool:
        now = time.monotonic()
        if now - self.emote_at.get(pid, -EMOTE_COOLDOWN) < EMOTE_COOLDOWN:
            return False
        self.emote_at[pid] = now
        return True

    def player(self, pid: str) -> Player | None:
        for p in self.players:
            if p.id == pid:
                return p
        return None

    def add_player(
        self, name: str, user_id: int | None = None, avatar_url: str | None = None, username: str | None = None,
    ) -> Player:
        if len(self.players) >= MAX_PLAYERS:
            raise GameError("комната уже заполнена")
        if self.engine is not None:
            raise GameError("игра уже началась")
        if user_id is not None and any(p.user_id == user_id for p in self.players):
            raise GameError("вы уже в этой комнате")
        p = Player(
            id=str(uuid.uuid4()), name=name[:24] or "Игрок", user_id=user_id, avatar_url=avatar_url, username=username,
        )
        self.players.append(p)
        return p

    def start_game(self, requester_id: str) -> None:
        if requester_id != self.host_id:
            raise GameError("только хост может начать игру")
        if self.engine is not None:
            raise GameError("игра уже началась")
        if not (MIN_PLAYERS <= len(self.players) <= MAX_PLAYERS):
            raise GameError(f"нужно от {MIN_PLAYERS} до {MAX_PLAYERS} игроков")
        self.engine = Engine(list(self.players))
        self.engine.start_round()

    def present_players(self) -> list[Player]:
        return [p for p in self.players if p.id not in self.left]

    def vote_rematch(self, pid: str) -> None:
        if self.engine is None or not self.engine.game_over:
            raise GameError("игра ещё не закончена")
        if self.player(pid) is None or pid in self.left:
            raise GameError("вы не в комнате")
        self.rematch_ids.add(pid)
        self._maybe_start_rematch()

    def _maybe_start_rematch(self) -> None:
        if self.engine is None or not self.engine.game_over:
            return
        present = self.present_players()
        if len(present) < MIN_PLAYERS or not {p.id for p in present} <= self.rematch_ids:
            return
        # fresh game with whoever is still here; players who quit are dropped
        for p in present:
            p.hand = []
            p.score = 0
            p.eliminated = False
        self.players = present
        self.left = set()
        self.rematch_ids = set()
        self.engine = Engine(list(self.players))
        self.engine.start_round()

    def leave(self, pid: str) -> None:
        self.sockets.pop(pid, None)
        if self.engine is None:
            self.players = [p for p in self.players if p.id != pid]
        else:
            self.engine.leave(pid)
            self.left.add(pid)
        if pid == self.host_id:
            remaining = [p for p in self.players if p.id not in self.left]
            self.host_id = remaining[0].id if remaining else ""
        # the one who left may have been the last vote holding the rematch up
        self.rematch_ids.discard(pid)
        self._maybe_start_rematch()

    @property
    def is_empty(self) -> bool:
        return all(p.id in self.left for p in self.players)

    def public_state(self, viewer_id: str) -> dict:
        base = {
            "room": self.code,
            "host_id": self.host_id,
            "started": self.engine is not None,
            "lobby_players": [
                {"id": p.id, "name": p.name, "avatar_url": p.avatar_url, "username": p.username} for p in self.players
            ],
        }
        if self.engine is not None:
            base.update(self.engine.state_for(viewer_id))
            base["log"] = self.engine.log[-30:]
            if self.engine.game_over:
                base["rematch_ids"] = sorted(self.rematch_ids)
                base["rematch_player_ids"] = [p.id for p in self.present_players()]
        return base


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def create_room(
        self, host_name: str, user_id: int | None = None, avatar_url: str | None = None, username: str | None = None,
    ) -> tuple[Room, Player]:
        code = _gen_room_code()
        while code in self.rooms:
            code = _gen_room_code()
        # host_id assigned after the player object exists
        room = Room(code=code, host_id="")
        player = room.add_player(host_name, user_id, avatar_url, username)
        room.host_id = player.id
        self.rooms[code] = room
        return room, player

    def join_room(
        self, code: str, name: str, user_id: int | None = None, avatar_url: str | None = None,
        username: str | None = None,
    ) -> tuple[Room, Player]:
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameError("комната не найдена")
        player = room.add_player(name, user_id, avatar_url, username)
        return room, player

    def get_room(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def leave_room(self, room: Room, player_id: str) -> None:
        room.leave(player_id)
        if room.is_empty:
            self.rooms.pop(room.code, None)

    def rejoin(self, code: str, player_id: str) -> tuple[Room, Player] | None:
        room = self.rooms.get(code.upper())
        if room is None:
            return None
        player = room.player(player_id)
        if player is None or player_id in room.left:
            return None
        player.connected = True
        return room, player


def parse_cards(raw: list[dict]) -> list[Card]:
    return [Card.from_dict(d) for d in raw]
