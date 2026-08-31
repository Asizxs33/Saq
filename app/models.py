from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class QueryType(str, Enum):
    DOMAIN = "domain"
    BTC_ADDRESS = "btc_address"
    ETH_ADDRESS = "eth_address"
    TELEGRAM_HANDLE = "telegram_handle"
    USERNAME = "username"
    PHONE = "phone"
    NAME_OR_ORG = "name_or_org"


class ConnectorResult(BaseModel):
    source: str
    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    red_flags: list[str] = []


class InvestigateRequest(BaseModel):
    query: str
    query_type: Optional[QueryType] = None
    synthesize: bool = True


class RecurrenceEntry(BaseModel):
    id: int
    query: str
    query_type: str
    risk_score: int
    created_at: str


class InvestigateResponse(BaseModel):
    investigation_id: int
    query: str
    detected_type: QueryType
    connectors_run: list[str]
    results: list[ConnectorResult]
    risk_score: int
    risk_flags: list[str]
    summary: Optional[str] = None
    recurrence: list[RecurrenceEntry] = []


class TipRequest(BaseModel):
    target: str
    note: str
    contact: Optional[str] = None
    # "web" (форма на сайте, по умолчанию) | "guardian_app" (desktop-программа
    # SAQ Guardian прислала находку с экрана пользователя)
    source: str = "web"


class TipResponse(BaseModel):
    id: int
    status: str


class WatchlistEntry(BaseModel):
    id: int
    query: str
    query_type: str
    risk_score: int
    risk_flags: list[str]
    connectors_run: list[str]
    created_at: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    dossier: Optional[InvestigateResponse] = None
    # все объекты, проверенные за этот ход — фронтенд строит по ним общий граф
    dossiers: list[InvestigateResponse] = []
    suggestions: list[str] = []


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    created_at: str
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class QuotaState(BaseModel):
    unlimited: bool
    used: int
    limit: Optional[int] = None
    remaining: Optional[int] = None


class ProfileResponse(BaseModel):
    user: UserOut
    quota: QuotaState
    investigations_count: int = 0
    tips_count: int = 0


class ChatSessionOut(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessageOut(BaseModel):
    role: str
    content: str
    investigation_id: Optional[int] = None
    created_at: str


class AdminUserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: str
    last_login: Optional[str] = None
    login_count: int = 0
    investigations_count: int = 0
    chats_count: int = 0


class SetRoleRequest(BaseModel):
    role: str


class SetTipStatusRequest(BaseModel):
    status: str


class BridgeAlert(BaseModel):
    my_id: int
    my_query: str
    shared_kind: str
    shared_value: str
    other_id: int
    other_query: str
    other_risk_score: int
    other_created_at: str


class AdminStats(BaseModel):
    users: int
    investigations: int
    tips: int
    chat_sessions: int
    queries_24h: int
    watchlist_high_risk: int
