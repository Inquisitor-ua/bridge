"""Friends: requests by username, accepting / declining, removing.

Each pair of users has at most one row in `friendships`. Whoever's list
changes gets a "friends_changed" push over their sockets, so open screens
refresh at once instead of polling.
"""
from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import db, presence
from .auth import RateLimiter, current_user, public_user

MAX_FRIENDS = 200
MAX_OUTGOING = 50  # pending requests one user may have out at a time

friend_requests = RateLimiter(limit=30, window=60 * 60)

router = APIRouter(prefix="/api/friends")

CHANGED = {"type": "friends_changed"}


def _pair(conn: sqlite3.Connection, a: int, b: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM friendships WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (a, b, b, a),
    ).fetchone()


def _user(conn: sqlite3.Connection, username: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if row is None:
        raise HTTPException(404, "пользователь не найден")
    return row


def friend_ids(user_id: int) -> list[int]:
    with db.connect() as conn:
        return [
            r[0] for r in conn.execute(
                """SELECT CASE WHEN requester_id = ? THEN addressee_id ELSE requester_id END
                   FROM friendships WHERE status = 'accepted' AND (requester_id = ? OR addressee_id = ?)""",
                (user_id, user_id, user_id),
            )
        ]


def friend_by_username(user_id: int, username: str) -> sqlite3.Row | None:
    """The user with that login, if they are user_id's friend."""
    with db.connect() as conn:
        other = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        if other is None:
            return None
        pair = _pair(conn, user_id, other["id"])
    return other if pair is not None and pair["status"] == "accepted" else None


def _friend_count(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM friendships WHERE status = 'accepted' AND (requester_id = ? OR addressee_id = ?)",
        (user_id, user_id),
    ).fetchone()[0]


@router.get("")
def list_friends(request: Request) -> dict:
    me = current_user(request)
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT f.requester_id, f.status, f.created_at AS since, u.*
               FROM friendships f
               JOIN users u ON u.id = CASE WHEN f.requester_id = ? THEN f.addressee_id ELSE f.requester_id END
               WHERE f.requester_id = ? OR f.addressee_id = ?""",
            (me["id"], me["id"], me["id"]),
        ).fetchall()
    friends, incoming, outgoing = [], [], []
    for r in rows:
        if r["status"] == "accepted":
            friends.append({**public_user(r), "online": presence.is_online(r["id"])})
        elif r["requester_id"] == me["id"]:
            outgoing.append(public_user(r))
        else:
            incoming.append({**public_user(r), "requested_at": r["since"]})
    friends.sort(key=lambda f: (not f["online"], f["display_name"].lower()))
    incoming.sort(key=lambda f: -f["requested_at"])
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


class FriendRequestIn(BaseModel):
    username: str


@router.post("/requests")
async def send_request(body: FriendRequestIn, request: Request) -> dict:
    me = current_user(request)
    username = body.username.strip().lstrip("@")
    if not username:
        raise HTTPException(400, "введите логин друга")
    if friend_requests.blocked(f"user:{me['id']}"):
        raise HTTPException(429, "слишком много заявок, попробуйте позже")
    with db.connect() as conn:
        other = _user(conn, username)
        if other["id"] == me["id"]:
            raise HTTPException(400, "нельзя добавить в друзья самого себя")
        pair = _pair(conn, me["id"], other["id"])
        if pair is not None and pair["status"] == "accepted":
            raise HTTPException(409, "вы уже друзья")
        if pair is not None and pair["requester_id"] == me["id"]:
            raise HTTPException(409, "заявка уже отправлена")
        if _friend_count(conn, me["id"]) >= MAX_FRIENDS:
            raise HTTPException(400, f"в друзьях не больше {MAX_FRIENDS} человек")
        if pair is not None:
            # they already asked us: sending back means yes
            conn.execute(
                "UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?",
                (other["id"], me["id"]),
            )
            result = "accepted"
        else:
            outgoing = conn.execute(
                "SELECT COUNT(*) FROM friendships WHERE status = 'pending' AND requester_id = ?", (me["id"],),
            ).fetchone()[0]
            if outgoing >= MAX_OUTGOING:
                raise HTTPException(400, "слишком много неотвеченных заявок")
            conn.execute(
                "INSERT INTO friendships (requester_id, addressee_id, status, created_at) VALUES (?, ?, 'pending', ?)",
                (me["id"], other["id"], int(time.time())),
            )
            result = "sent"
    friend_requests.hit(f"user:{me['id']}")
    await presence.send(other["id"], CHANGED)
    return {"result": result, "user": public_user(other)}


@router.post("/requests/{username}/accept")
async def accept_request(username: str, request: Request) -> dict:
    me = current_user(request)
    with db.connect() as conn:
        other = _user(conn, username)
        pair = _pair(conn, me["id"], other["id"])
        if pair is None or pair["status"] != "pending" or pair["requester_id"] != other["id"]:
            raise HTTPException(404, "заявки нет")
        if _friend_count(conn, me["id"]) >= MAX_FRIENDS:
            raise HTTPException(400, f"в друзьях не больше {MAX_FRIENDS} человек")
        conn.execute(
            "UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?",
            (other["id"], me["id"]),
        )
    await presence.send(other["id"], CHANGED)
    return {"ok": True}


@router.delete("/requests/{username}")
async def drop_request(username: str, request: Request) -> dict:
    """Decline a request to me, or take back one I sent."""
    me = current_user(request)
    with db.connect() as conn:
        other = _user(conn, username)
        deleted = conn.execute(
            """DELETE FROM friendships WHERE status = 'pending'
               AND ((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))""",
            (me["id"], other["id"], other["id"], me["id"]),
        ).rowcount
    if not deleted:
        raise HTTPException(404, "заявки нет")
    await presence.send(other["id"], CHANGED)
    return {"ok": True}


@router.delete("/{username}")
async def remove_friend(username: str, request: Request) -> dict:
    me = current_user(request)
    with db.connect() as conn:
        other = _user(conn, username)
        deleted = conn.execute(
            """DELETE FROM friendships WHERE status = 'accepted'
               AND ((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))""",
            (me["id"], other["id"], other["id"], me["id"]),
        ).rowcount
    if not deleted:
        raise HTTPException(404, "этого пользователя нет в друзьях")
    await presence.send(other["id"], CHANGED)
    return {"ok": True}
