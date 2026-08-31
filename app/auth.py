"""Общая аутентификация для сайта и мобильного приложения — оба клиента
бьют в одни и те же /auth/register, /auth/login, /auth/me и один и тот же
JWT verifier, так что учётная запись, заведённая на сайте, работает и в
приложении, и наоборот. Пароли хранятся только как bcrypt-хэш.
"""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException

from app import auth_store

JWT_ALGORITHM = "HS256"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_env_secret = os.getenv("JWT_SECRET")
if not _env_secret:
    # Без своего секрета в .env — генерируем на старте процесса. Токены
    # переживут только до следующего перезапуска бэкенда; ок для
    # разработки, но задайте JWT_SECRET в .env перед реальным использованием.
    import logging

    logging.getLogger("auth").warning(
        "JWT_SECRET не задан в .env — используется случайный секрет на этот "
        "запуск процесса, все выданные токены станут недействительны после "
        "перезапуска бэкенда"
    )
    _env_secret = secrets.token_hex(32)
JWT_SECRET = _env_secret
JWT_EXPIRES_DAYS = int(os.getenv("JWT_EXPIRES_DAYS", "30"))


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False  # malformed hash — never crash auth on bad stored data


def create_access_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRES_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк, войдите заново")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Недействительный токен")


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI-зависимость: обязательная авторизация. Кладите в Depends()
    на роуты, доступные только вошедшим пользователям.

    Намеренно НЕ async def: auth_store.get_user_by_id() — синхронный
    блокирующий вызов psycopg (даже из пула соединений это сетевой
    round-trip до Neon, ~сотни мс). Если бы эта зависимость была async def,
    вызов блокировал бы единственный event loop целиком на всё это время —
    и 5 параллельных запросов дашборда выполнялись бы по факту
    последовательно. Обычная def-функция FastAPI сам уводит в threadpool,
    и запросы реально идут параллельно."""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется авторизация — заголовок Authorization: Bearer <token>")
    payload = decode_access_token(token)
    user = auth_store.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден — токен выдан для удалённого аккаунта")
    return user


def require_admin(authorization: Optional[str] = Header(default=None)) -> dict:
    """Как get_current_user, но пускает только администраторов."""
    user = get_current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user


def get_current_user_optional(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    """Как get_current_user, но не требует токена — для роутов, где
    авторизация опциональна (например, наводка от анонима vs от аккаунта)."""
    token = _extract_token(authorization)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None  # неверный/просроченный токен на опциональном роуте — просто анонимно
    return auth_store.get_user_by_id(int(payload["sub"]))
