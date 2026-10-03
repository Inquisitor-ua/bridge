"""Accounts: registration, login/logout, profiles.

A login creates a random session token. The browser keeps it in an httpOnly
cookie; the database stores only its sha256, so a leaked DB doesn't hand out
live sessions. The same cookie reaches the /ws handshake (same origin), which
is how the game knows who is playing.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import db

COOKIE_NAME = "bridge_auth"
SESSION_TTL = 60 * 60 * 24 * 30  # 30 days

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
PASSWORD_MIN, PASSWORD_MAX = 6, 128
DISPLAY_NAME_MAX = 24  # same limit as a player name in a room
# the client sends a 256x256 picture (tens of KB); the cap only stops abuse
AVATAR_MAX_BYTES = 512 * 1024

# scrypt from the standard library (OWASP-recommended parameters), so no
# extra dependency; hashes look like "scrypt$n$r$p$salt$hash"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1

router = APIRouter(prefix="/api")


# --- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual.hex(), digest)


# checked against when the username doesn't exist, so a failed login takes the
# same time either way and doesn't reveal which usernames are taken
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# --- sessions ----------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, now, now + SESSION_TTL),
        )
    return token


def user_by_token(token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    with db.connect() as conn:
        return conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token), int(time.time())),
        ).fetchone()


def _set_cookie(request: Request, response: Response, token: str) -> None:
    # behind Cloudflare/nginx the scheme comes from X-Forwarded-Proto
    # (uvicorn --proxy-headers); BRIDGE_COOKIE_SECURE=1 forces it
    secure = request.url.scheme == "https" or os.environ.get("BRIDGE_COOKIE_SECURE") == "1"
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True, samesite="lax", secure=secure, path="/",
    )


# --- rate limiting -----------------------------------------------------------

class RateLimiter:
    """At most `limit` hits per `window` seconds per key. In memory: there is
    exactly one worker process (see Dockerfile)."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def blocked(self, key: str) -> bool:
        q = self.hits[key]
        now = time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            del self.hits[key]
            return False
        return len(q) >= self.limit

    def hit(self, key: str) -> None:
        self.hits[key].append(time.monotonic())


failed_logins = RateLimiter(limit=10, window=10 * 60)
registrations = RateLimiter(limit=5, window=60 * 60)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


# --- API ---------------------------------------------------------------------

class Credentials(BaseModel):
    username: str
    password: str


class RegisterIn(Credentials):
    display_name: str = ""


class ProfileIn(BaseModel):
    display_name: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


def public_user(row: sqlite3.Row) -> dict:
    version = row["avatar_version"]
    return {
        "username": row["username"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
        "avatar_url": f"/api/users/{row['username']}/avatar?v={version}" if version else None,
    }


def _check_password_length(password: str) -> None:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise HTTPException(400, f"пароль: от {PASSWORD_MIN} до {PASSWORD_MAX} символов")


def _clean_display_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(400, "имя не может быть пустым")
    if len(name) > DISPLAY_NAME_MAX:
        raise HTTPException(400, f"имя длиннее {DISPLAY_NAME_MAX} символов")
    return name


def current_user(request: Request) -> sqlite3.Row:
    user = user_by_token(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, "нужно войти")
    return user


# Handlers are plain `def` on purpose: scrypt takes tens of milliseconds and
# FastAPI runs sync handlers in a threadpool, off the event loop that serves
# the game's WebSockets.

@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response) -> dict:
    ip = _client_ip(request)
    if registrations.blocked(ip):
        raise HTTPException(429, "слишком много регистраций, попробуйте позже")
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "логин: 3–20 символов, латиница, цифры и _")
    _check_password_length(body.password)
    display_name = _clean_display_name(body.display_name or username)

    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, display_name, hash_password(body.password), int(time.time())),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "этот логин уже занят")
    registrations.hit(ip)

    _set_cookie(request, response, create_session(user_id))
    with db.connect() as conn:
        return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


@router.post("/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    ip = _client_ip(request)
    if failed_logins.blocked(ip):
        raise HTTPException(429, "слишком много попыток, попробуйте через несколько минут")
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (body.username.strip(),)).fetchone()
    ok = verify_password(body.password, user["password_hash"] if user else _DUMMY_HASH)
    if user is None or not ok:
        failed_logins.hit(ip)
        raise HTTPException(401, "неверный логин или пароль")
    _set_cookie(request, response, create_session(user["id"]))
    return public_user(user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict | None:
    # null rather than 401 for a guest: every page load asks, and a guest is
    # the normal case, not an error
    user = user_by_token(request.cookies.get(COOKIE_NAME))
    return public_user(user) if user else None


@router.patch("/me")
def update_me(body: ProfileIn, request: Request) -> dict:
    user = current_user(request)
    display_name = _clean_display_name(body.display_name)
    with db.connect() as conn:
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user["id"]))
        return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())


@router.post("/me/password")
def change_password(body: PasswordIn, request: Request) -> dict:
    user = current_user(request)
    # wrong old passwords count like failed logins, per account: a stolen
    # session shouldn't allow guessing the password at full speed
    key = f"password:{user['id']}"
    if failed_logins.blocked(key):
        raise HTTPException(429, "слишком много попыток, попробуйте через несколько минут")
    if not verify_password(body.old_password, user["password_hash"]):
        failed_logins.hit(key)
        raise HTTPException(400, "старый пароль неверный")
    _check_password_length(body.new_password)
    if body.new_password == body.old_password:
        raise HTTPException(400, "новый пароль совпадает со старым")
    current = _token_hash(request.cookies.get(COOKIE_NAME, ""))
    with db.connect() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), user["id"]))
        # log out every other device; this one stays signed in
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user["id"], current))
    return {"ok": True}


IMAGE_SIGNATURES = [
    (bytes.fromhex("89504e470d0a1a0a"), "image/png"),
    (bytes.fromhex("ffd8ff"), "image/jpeg"),
]


def _sniff_image(data: bytes) -> str | None:
    """Image type from the file's own signature, never from the client's
    Content-Type. Only raster formats: an SVG could carry a script."""
    for signature, mime in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.put("/me/avatar")
async def upload_avatar(request: Request) -> dict:
    user = current_user(request)
    if int(request.headers.get("content-length") or 0) > AVATAR_MAX_BYTES:
        raise HTTPException(413, "картинка слишком большая")
    data = await request.body()
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(413, "картинка слишком большая")
    mime = _sniff_image(data)
    if mime is None:
        raise HTTPException(400, "нужна картинка PNG, JPEG или WebP")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO avatars (user_id, image, mime) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET image = excluded.image, mime = excluded.mime",
            (user["id"], data, mime),
        )
        conn.execute("UPDATE users SET avatar_version = avatar_version + 1 WHERE id = ?", (user["id"],))
        return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())


@router.delete("/me/avatar")
def delete_avatar(request: Request) -> dict:
    user = current_user(request)
    with db.connect() as conn:
        conn.execute("DELETE FROM avatars WHERE user_id = ?", (user["id"],))
        conn.execute("UPDATE users SET avatar_version = 0 WHERE id = ?", (user["id"],))
        return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())


@router.get("/users/{username}/avatar")
def get_avatar(username: str) -> Response:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT a.image, a.mime FROM avatars a JOIN users u ON u.id = a.user_id WHERE u.username = ?",
            (username,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "аватара нет")
    # the URL carries ?v=<avatar_version>, so a cached copy never goes stale
    return Response(
        row["image"],
        media_type=row["mime"],
        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/users/{username}")
def get_user(username: str) -> dict:
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        raise HTTPException(404, "пользователь не найден")
    return public_user(user)
