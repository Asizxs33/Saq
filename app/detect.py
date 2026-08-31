import re

from app.models import QueryType

_BTC_RE = re.compile(r"^(bc1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")
_ETH_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))+$"
)
_TELEGRAM_RE = re.compile(r"^(@|https?://t\.me/)[A-Za-z0-9_]{4,32}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{2,32}$")
# Телефон: международный формат с + либо казахстанский 8/7XXXXXXXXXX.
# Разделители (пробелы, скобки, дефисы) допускаются и вычищаются отдельно.
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,20}$")


def detect_query_type(raw_query: str) -> QueryType:
    q = raw_query.strip()

    if _BTC_RE.match(q):
        return QueryType.BTC_ADDRESS
    if _ETH_RE.match(q):
        return QueryType.ETH_ADDRESS
    if _TELEGRAM_RE.match(q):
        return QueryType.TELEGRAM_HANDLE
    if _DOMAIN_RE.match(q) and "." in q and " " not in q:
        return QueryType.DOMAIN
    # телефон проверяем после домена: "8.800.555.35.35" формально похож на
    # домен, но точек-разделителей в реальных доменах верхнего уровня нет
    if _PHONE_RE.match(q) and sum(c.isdigit() for c in q) >= 7:
        return QueryType.PHONE
    if _USERNAME_RE.match(q) and " " not in q and not q.isdigit():
        # short single-token alnum string without spaces: treat as a
        # candidate username/handle rather than a full name/org
        return QueryType.USERNAME

    return QueryType.NAME_OR_ORG


def normalize_phone(raw_query: str) -> str:
    """К цифрам в международном виде: 8 (777) 123-45-67 → +77771234567.
    Казахстанский и российский ведущий 8 заменяется на 7 — иначе один и тот
    же номер не схлопнется с записанным как +7."""
    digits = "".join(c for c in raw_query if c.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return "+" + digits if digits else raw_query.strip()


def normalize_telegram_handle(raw_query: str) -> str:
    q = raw_query.strip()
    q = q.replace("https://t.me/", "").replace("http://t.me/", "")
    return q.lstrip("@")
