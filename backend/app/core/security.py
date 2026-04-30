from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import create_engine, text


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    password_hash: str
    role: str
    is_active: bool


class SessionTokenPayload(TypedDict):
    sub: str
    role: str
    pwd: str
    exp: int
    nonce: str
    csrf: str


class AuthCookieSettings(TypedDict):
    httponly: bool
    samesite: str
    secure: bool
    max_age: int
    path: str


class AuthManager:
    cookie_name = "granalia_session"
    session_ttl_seconds = 60 * 60 * 8
    login_window_seconds = 60 * 10
    login_attempt_limit = 5
    lockout_seconds = 30

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_auth_file = self.data_dir / "auth_user.json"
        self.secret_file = self.data_dir / "session_secret.key"
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lockouts: dict[str, float] = {}
        self.url = os.getenv(
            "GRANALIA_POSTGRES_URL",
            "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia",
        )
        self.engine = create_engine(self.url, future=True)
        self.secret = self._load_secret()
        self.bootstrap_default_user()

    def _load_secret(self) -> bytes:
        env_secret = os.getenv("GRANALIA_SESSION_SECRET")
        if env_secret:
            return env_secret.encode("utf-8")

        if self.secret_file.exists():
            return self.secret_file.read_bytes()

        secret = secrets.token_bytes(32)
        self.secret_file.write_bytes(secret)
        return secret

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return f"scrypt$16384$8$1${_b64url_encode(salt)}${_b64url_encode(derived)}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            scheme, n, r, p, salt, digest = password_hash.split("$")
            if scheme != "scrypt":
                return False
            candidate = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_b64url_decode(salt),
                n=int(n),
                r=int(r),
                p=int(p),
            )
            return hmac.compare_digest(candidate, _b64url_decode(digest))
        except Exception:
            return False

    def _fetch_user_by_username(self, username: str) -> AuthUser | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, username, password_hash, role, is_active
                    FROM app_users
                    WHERE username = :username
                    LIMIT 1
                    """
                ),
                {"username": username},
            ).mappings().first()
        if not row:
            return None
        return AuthUser(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            role=str(row.get("role") or "operator"),
            is_active=bool(row["is_active"]),
        )

    def _count_users(self) -> int:
        with self.engine.connect() as connection:
            return int(connection.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one())

    def bootstrap_default_user(self) -> None:
        try:
            if self._count_users() > 0:
                return
        except Exception as exc:
            raise RuntimeError(
                "La tabla app_users no existe. Ejecutá `python3 -m alembic -c alembic.ini upgrade head` antes de iniciar el sistema."
            ) from exc

        env_username = os.getenv("GRANALIA_AUTH_USERNAME")
        env_password_hash = os.getenv("GRANALIA_AUTH_PASSWORD_HASH")
        env_password = os.getenv("GRANALIA_AUTH_PASSWORD")
        env_role = os.getenv("GRANALIA_AUTH_ROLE", "admin")

        username = env_username or "admin"
        password_hash: str | None = None
        generated_password: str | None = None

        if env_password_hash or env_password:
            password_hash = env_password_hash or self.hash_password(env_password or "")
        elif self.legacy_auth_file.exists():
            payload = json.loads(self.legacy_auth_file.read_text())
            username = payload["username"]
            password_hash = payload["password_hash"]
        else:
            generated_password = secrets.token_urlsafe(18)
            password_hash = self.hash_password(generated_password)

        if password_hash is None:
            raise RuntimeError("No se pudo inicializar el password hash del usuario administrador")

        self.upsert_user(username, password_hash=password_hash, role=env_role, is_active=True)

        if generated_password:
            print(
                "[granalia-auth] Credenciales iniciales generadas en PostgreSQL. "
                f"Usuario: {username} | Password: {generated_password}",
                flush=True,
            )

    def upsert_user(
        self,
        username: str,
        *,
        password_hash: str,
        role: str = "operator",
        is_active: bool = True,
    ) -> None:
        now = int(time.time())
        normalized_role = role if role in {"admin", "operator"} else "operator"
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO app_users (username, password_hash, role, is_active, created_at, updated_at)
                    VALUES (:username, :password_hash, :role, :is_active, now(), now())
                    ON CONFLICT (username)
                    DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        is_active = EXCLUDED.is_active,
                        updated_at = now()
                    """
                ),
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": normalized_role,
                    "is_active": is_active,
                    "now": now,
                },
            )

    def verify_credentials(self, username: str, password: str) -> AuthUser | None:
        user = self._fetch_user_by_username(username)
        if not user or not user.is_active:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user

    def _sign(self, payload: bytes) -> str:
        return _b64url_encode(hmac.new(self.secret, payload, hashlib.sha256).digest())

    def create_session_token(self, user: AuthUser) -> str:
        payload = {
            "sub": user.username,
            "role": user.role,
            "pwd": _password_fingerprint(user.password_hash),
            "exp": int(time.time()) + self.session_ttl_seconds,
            "nonce": secrets.token_urlsafe(16),
            "csrf": secrets.token_urlsafe(32),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encoded_payload = _b64url_encode(payload_bytes)
        signature = self._sign(encoded_payload.encode("utf-8"))
        return f"{encoded_payload}.{signature}"

    def verify_session_token(self, token: str | None) -> SessionTokenPayload | None:
        if not token or "." not in token:
            return None
        encoded_payload, signature = token.split(".", 1)
        expected = self._sign(encoded_payload.encode("utf-8"))
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_b64url_decode(encoded_payload))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = payload.get("sub")
        if not username:
            return None
        user = self._fetch_user_by_username(str(username))
        if not user or not user.is_active:
            return None
        if payload.get("pwd") != _password_fingerprint(user.password_hash):
            return None
        if not payload.get("csrf"):
            return None
        return {
            "sub": user.username,
            "role": user.role,
            "pwd": str(payload.get("pwd")),
            "exp": int(payload.get("exp", 0)),
            "nonce": str(payload.get("nonce", "")),
            "csrf": str(payload.get("csrf", "")),
        }

    def verify_csrf_token(self, payload: SessionTokenPayload, csrf_token: str | None) -> bool:
        expected = payload.get("csrf") or ""
        return bool(expected and csrf_token and hmac.compare_digest(csrf_token, expected))

    def auth_cookie_settings(self) -> AuthCookieSettings:
        secure_flag = os.getenv("GRANALIA_SECURE_COOKIES")
        secure = True if secure_flag is None else secure_flag.lower() == "true"
        return {
            "httponly": True,
            "samesite": "lax",
            "secure": secure,
            "max_age": self.session_ttl_seconds,
            "path": "/",
        }

    def ensure_login_allowed(self, client_id: str) -> tuple[bool, int | None]:
        now = time.time()
        lock_until = self._lockouts.get(client_id)
        if lock_until and lock_until > now:
            return False, int(lock_until - now)
        if lock_until and lock_until <= now:
            self._lockouts.pop(client_id, None)
        attempts = self._attempts[client_id]
        while attempts and attempts[0] < now - self.login_window_seconds:
            attempts.popleft()
        return True, None

    def register_failed_login(self, client_id: str) -> None:
        now = time.time()
        attempts = self._attempts[client_id]
        attempts.append(now)
        while attempts and attempts[0] < now - self.login_window_seconds:
            attempts.popleft()
        if len(attempts) >= self.login_attempt_limit:
            self._lockouts[client_id] = now + self.lockout_seconds
            attempts.clear()

    def register_successful_login(self, client_id: str) -> None:
        self._attempts.pop(client_id, None)
        self._lockouts.pop(client_id, None)
