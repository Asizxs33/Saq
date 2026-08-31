import logging
import os

from dotenv import load_dotenv

load_dotenv()

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

from app import auth, auth_store, live, quota, registry
from app import settings as app_settings
from app.db import get_connection, init_db
from app.models import (
    AdminStats,
    AdminUserOut,
    BridgeAlert,
    ChatMessageOut,
    ChatRequest,
    ChatSessionOut,
    ChatResponse,
    InvestigateRequest,
    InvestigateResponse,
    LoginRequest,
    ProfileResponse,
    QuotaState,
    RegisterRequest,
    SetRoleRequest,
    SetTipStatusRequest,
    TipRequest,
    TipResponse,
    TokenResponse,
    UserOut,
    WatchlistEntry,
)
from app.orchestrator import investigate

app = FastAPI(
    title="OSINT Pyramid-Scheme Aggregator",
    description=(
        "Агрегирует бесплатные публичные OSINT-источники (метапоиск, "
        "certificate transparency, WHOIS/RDAP, блокчейн-эксплореры, "
        "реестры компаний, публичные соцсети) под один запрос и считает "
        "rule-based risk score по маркерам финансовых пирамид."
    ),
)


_background_tasks: list[asyncio.Task] = []


@app.on_event("startup")
async def on_startup():
    # users — первой: остальные таблицы ссылаются на неё через FOREIGN KEY,
    # а Postgres, в отличие от SQLite, проверяет существование целевой
    # таблицы сразу при CREATE TABLE, а не отложенно
    auth_store.init_users_table()
    init_db()

    # наводки, оставшиеся 'pending' (бэкенд был выключен в момент отправки),
    # уходят на автопроверку при старте
    from app.tips_worker import reschedule_pending_tips

    reschedule_pending_tips()

    # Opt-in, like the darknet module: requires a local certstream-server-go
    # instance (see vendor/certstream-server-go) already running. Off by
    # default so cloning the repo never silently opens a websocket or starts
    # auto-investigating domains without the operator choosing to.
    if os.getenv("ENABLE_CERTSTREAM_WATCHER", "false").lower() == "true":
        from app.monitor.candidate_runner import run_candidate_runner_forever
        from app.monitor.certstream_watcher import run_watcher_forever

        _background_tasks.append(asyncio.create_task(run_watcher_forever()))
        _background_tasks.append(asyncio.create_task(run_candidate_runner_forever()))

    # Local SearXNG dev server dies occasionally under a burst of concurrent
    # requests (observed during testing) — supervise and auto-restart it,
    # same resilience pattern as the CertStream watcher above.
    if os.getenv("ENABLE_LOCAL_SEARXNG", "true").lower() == "true":
        from app.monitor.searxng_supervisor import run_searxng_supervisor_forever

        _background_tasks.append(asyncio.create_task(run_searxng_supervisor_forever()))


@app.on_event("shutdown")
async def on_shutdown():
    for task in _background_tasks:
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/live")
async def live_feed(ws: WebSocket):
    """Живая лента находок: автомониторинг CertStream шлёт сюда каждое
    расследование, как только оно завершилось, — Watchlist пополняется в
    открытых вкладках без перезагрузки."""
    await ws.accept()
    await live.register(ws)
    try:
        await ws.send_json({"type": "hello", "clients": live.client_count()})
        while True:
            # ждём закрытия сокета; клиент может слать пинги, они игнорируются
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await live.unregister(ws)


@app.post("/investigate", response_model=InvestigateResponse)
async def investigate_endpoint(req: InvestigateRequest) -> InvestigateResponse:
    investigation_id, query_type, connectors_run, results, risk_score, risk_flags, summary, recurrence = (
        await investigate(req.query, req.query_type, req.synthesize)
    )
    return InvestigateResponse(
        investigation_id=investigation_id,
        query=req.query,
        detected_type=query_type,
        connectors_run=connectors_run,
        results=results,
        risk_score=risk_score,
        risk_flags=risk_flags,
        summary=summary,
        recurrence=recurrence,
    )


@app.get("/registry", response_model=list[WatchlistEntry])
async def registry_endpoint(min_score: int = Query(default=30, ge=0, le=100), limit: int = Query(default=100, le=200)):
    return registry.list_watchlist(min_score=min_score, limit=limit)


@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register_endpoint(req: RegisterRequest) -> TokenResponse:
    email = req.email.strip().lower()
    if not auth.is_valid_email(email):
        raise HTTPException(status_code=422, detail="Некорректный email")
    if len(req.password) < 8:
        raise HTTPException(status_code=422, detail="Пароль должен быть не короче 8 символов")
    if auth_store.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже зарегистрирован")

    user_id = auth_store.create_user(email, auth.hash_password(req.password))
    user = auth_store.get_user_by_id(user_id)
    quota.record_login(user_id)
    token = auth.create_access_token(user_id, email)
    return TokenResponse(access_token=token, user=UserOut(**user))


@app.post("/auth/login", response_model=TokenResponse)
async def login_endpoint(req: LoginRequest) -> TokenResponse:
    email = req.email.strip().lower()
    user = auth_store.get_user_by_email(email)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    quota.record_login(user["id"])
    token = auth.create_access_token(user["id"], email)
    return TokenResponse(
        access_token=token,
        user=UserOut(
            id=user["id"],
            email=user["email"],
            created_at=user["created_at"],
            role=user.get("role", "user"),
        ),
    )


@app.get("/auth/me", response_model=UserOut)
async def me_endpoint(current_user: dict = Depends(auth.get_current_user)) -> UserOut:
    return UserOut(**current_user)


@app.post("/tips", response_model=TipResponse)
async def create_tip_endpoint(
    tip: TipRequest, current_user: dict | None = Depends(auth.get_current_user_optional)
) -> TipResponse:
    # авторизация опциональна: анонимные наводки всё ещё принимаются, но
    # если пришёл валидный токен — наводка привязывается к аккаунту
    tip_id = registry.create_tip(
        tip.target, tip.note, tip.contact,
        user_id=current_user["id"] if current_user else None,
        source=tip.source if tip.source in ("web", "guardian_app") else "web",
    )

    # наводка сразу уходит на автопроверку: Aqyl прогоняет объект через
    # полный пайплайн, вердикт появляется в ленте, подтверждённые объекты
    # пополняют community-блэклист (см. app/tips_worker.py)
    from app.tips_worker import schedule_tip_check

    schedule_tip_check(tip_id, tip.target)
    return TipResponse(id=tip_id, status="pending")


@app.get("/tips")
async def list_tips_endpoint(limit: int = Query(default=100, le=200)):
    return registry.list_tips(limit=limit)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest, current_user: dict = Depends(auth.get_current_user)
) -> ChatResponse:
    from app.agent_chat import run_chat_turn

    allowed, state = quota.check_and_consume(current_user)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Суточный лимит исчерпан ({state['limit']} запросов). Обновится в течение 24 часов.",
        )

    quota.ensure_session(req.session_id, current_user["id"], req.message)
    quota.save_message(req.session_id, "user", req.message)

    reply, dossier, suggestions, dossiers = await run_chat_turn(
        req.session_id, req.message, current_user["id"]
    )
    quota.save_message(
        req.session_id, "assistant", reply, dossier.investigation_id if dossier else None
    )
    return ChatResponse(reply=reply, dossier=dossier, dossiers=dossiers, suggestions=suggestions)


@app.post("/chat/stream")
async def chat_stream_endpoint(
    req: ChatRequest, current_user: dict = Depends(auth.get_current_user)
):
    """Same agent turn as /chat, but as Server-Sent Events: progress lines
    ({"type": "status", ...}) while tools run, then a final
    {"type": "done", "reply", "dossier"} event."""
    import json

    from fastapi.responses import StreamingResponse

    from app.agent_chat import run_chat_turn_events

    allowed, state = quota.check_and_consume(current_user)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Суточный лимит исчерпан ({state['limit']} запросов). Обновится в течение 24 часов.",
        )

    quota.ensure_session(req.session_id, current_user["id"], req.message)
    quota.save_message(req.session_id, "user", req.message)

    async def event_source():
        async for event in run_chat_turn_events(req.session_id, req.message, current_user["id"]):
            if event["type"] == "done":
                dossier = event["dossier"]
                quota.save_message(
                    req.session_id,
                    "assistant",
                    event.get("reply", ""),
                    dossier.investigation_id if dossier else None,
                )
                # клиент показывает остаток лимита сразу после ответа
                event = {**event, "quota": quota.quota_state(current_user)}
                if dossier is not None:
                    event = {**event, "dossier": dossier.model_dump(mode="json")}
                if event.get("dossiers"):
                    event = {
                        **event,
                        "dossiers": [d.model_dump(mode="json") for d in event["dossiers"]],
                    }
            yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Профиль и история переписки ────────────────────────────────────────


@app.get("/me/profile", response_model=ProfileResponse)
def profile_endpoint(current_user: dict = Depends(auth.get_current_user)) -> ProfileResponse:
    conn = get_connection()
    try:
        inv = conn.execute(
            "SELECT COUNT(*) AS n FROM investigations WHERE user_id = ?", (current_user["id"],)
        ).fetchone()
        tips = conn.execute(
            "SELECT COUNT(*) AS n FROM tips WHERE user_id = ?", (current_user["id"],)
        ).fetchone()
    finally:
        conn.close()

    return ProfileResponse(
        user=UserOut(**current_user),
        quota=QuotaState(**quota.quota_state(current_user)),
        investigations_count=int(inv["n"] if inv else 0),
        tips_count=int(tips["n"] if tips else 0),
    )


@app.get("/me/quota", response_model=QuotaState)
def quota_endpoint(current_user: dict = Depends(auth.get_current_user)) -> QuotaState:
    return QuotaState(**quota.quota_state(current_user))


@app.get("/me/chats", response_model=list[ChatSessionOut])
def chat_history_endpoint(
    current_user: dict = Depends(auth.get_current_user), limit: int = Query(default=50, le=200)
):
    return quota.list_sessions(current_user["id"], limit=limit)


@app.get("/me/chats/{session_id}", response_model=list[ChatMessageOut])
def chat_messages_endpoint(
    session_id: str, current_user: dict = Depends(auth.get_current_user)
):
    msgs = quota.session_messages(
        session_id, current_user["id"], is_admin_user=quota.is_admin(current_user)
    )
    if msgs is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return msgs


@app.delete("/me/chats/{session_id}")
async def delete_chat_endpoint(
    session_id: str, current_user: dict = Depends(auth.get_current_user)
):
    ok = quota.delete_session(session_id, current_user["id"], is_admin_user=quota.is_admin(current_user))
    if not ok:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return {"status": "deleted"}


# ── Админ-панель ───────────────────────────────────────────────────────


@app.get("/admin/stats", response_model=AdminStats)
async def admin_stats_endpoint(_: dict = Depends(auth.require_admin)) -> AdminStats:
    conn = get_connection()
    try:
        def count(sql: str) -> int:
            row = conn.execute(sql).fetchone()
            return int(row[0] if row else 0)

        return AdminStats(
            users=len(auth_store.list_users(limit=10000)),
            investigations=count("SELECT COUNT(*) FROM investigations"),
            tips=count("SELECT COUNT(*) FROM tips"),
            chat_sessions=count("SELECT COUNT(*) FROM chat_sessions"),
            queries_24h=count(
                "SELECT COUNT(*) FROM usage_log WHERE created_at > datetime('now','-1 day')"
            ),
            watchlist_high_risk=count("SELECT COUNT(*) FROM investigations WHERE risk_score >= 60"),
        )
    finally:
        conn.close()


@app.get("/admin/users", response_model=list[AdminUserOut])
async def admin_users_endpoint(
    _: dict = Depends(auth.require_admin), limit: int = Query(default=200, le=1000)
):
    users = auth_store.list_users(limit=limit)
    activity = quota.users_activity([u["id"] for u in users])
    for u in users:
        u.update(activity.get(u["id"], {}))
    return users


@app.get("/admin/users/{user_id}/logins")
async def admin_user_logins_endpoint(user_id: int, _: dict = Depends(auth.require_admin)):
    """Полная история входов конкретного пользователя — раскрывается по клику
    в списке пользователей, не грузится сразу для всех, чтобы не гонять
    лишние запросы."""
    return {"logins": quota.login_history(user_id, limit=50)}


@app.post("/admin/users/{user_id}/role")
async def admin_set_role_endpoint(
    user_id: int, req: SetRoleRequest, admin: dict = Depends(auth.require_admin)
):
    if req.role not in (quota.ROLE_USER, quota.ROLE_ADMIN):
        raise HTTPException(status_code=422, detail="Роль может быть 'user' или 'admin'")
    if user_id == admin["id"] and req.role != quota.ROLE_ADMIN:
        # иначе последний администратор может случайно разжаловать сам себя
        raise HTTPException(status_code=400, detail="Нельзя снять роль администратора с самого себя")
    if not auth_store.set_role(user_id, req.role):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"status": "ok", "user_id": user_id, "role": req.role}


@app.get("/admin/tips")
async def admin_tips_endpoint(
    _: dict = Depends(auth.require_admin), limit: int = Query(default=200, le=500)
):
    """Все наводки сообщества со статусами — для модерации. source
    различает происхождение: web (форма на сайте) / guardian_app
    (desktop-программа сама заметила что-то на экране пользователя)."""
    return registry.list_tips(limit=limit)


@app.get("/admin/monitor/settings")
def admin_monitor_settings_endpoint(_: dict = Depends(auth.require_admin)):
    """Текущее состояние автомониторинга CertStream — включён ли сам процесс
    на этом сервере (ENABLE_CERTSTREAM_WATCHER в .env, нужен перезапуск) и
    стоит ли он на паузе (app_settings, переключается на лету)."""
    return {
        "watcher_enabled_in_env": os.getenv("ENABLE_CERTSTREAM_WATCHER", "false").lower() == "true",
        "paused": app_settings.is_certstream_paused(),
    }


@app.post("/admin/monitor/certstream")
def admin_toggle_certstream_endpoint(paused: bool, _: dict = Depends(auth.require_admin)):
    """Пауза/возобновление автомониторинга без перезапуска сервера. Если
    watcher вообще не запущен (ENABLE_CERTSTREAM_WATCHER=false в .env),
    переключатель просто ни на что не влияет — сначала нужно включить его
    в .env и перезапустить бэкенд."""
    app_settings.set_setting("certstream_paused", "true" if paused else "false")
    return {"status": "ok", "paused": paused}


@app.get("/admin/monitor/candidates")
def admin_candidates_endpoint(
    _: dict = Depends(auth.require_admin),
    status: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
):
    """Сырая очередь того, что робот нашёл сам — включая то, что не
    набрало риска и потому не попало в Watchlist. status: new/claimed/
    done/failed, не задавать — всё сразу."""
    return registry.list_candidate_leads(status=status, limit=limit)


@app.post("/admin/tips/{tip_id}/status")
async def admin_set_tip_status_endpoint(
    tip_id: int, req: SetTipStatusRequest, _: dict = Depends(auth.require_admin)
):
    """Ручная модерация наводки: подтвердить или отклонить после проверки."""
    if req.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(status_code=422, detail="status должен быть pending/confirmed/rejected")
    if not registry.set_tip_status(tip_id, req.status):
        raise HTTPException(status_code=404, detail="Наводка не найдена")
    return {"status": "ok", "tip_id": tip_id, "new_status": req.status}


@app.get("/admin/export/afm")
async def admin_export_afm_endpoint(
    _: dict = Depends(auth.require_admin), min_score: int = Query(default=60, ge=0, le=100)
):
    """Выгрузка высокорисковых объектов в CSV для передачи в АФМ РК —
    структурированный формат (объект, тип, скор, сигналы риска, дата),
    а не скриншот интерфейса. Порог по умолчанию 60 (высокий риск)."""
    import csv
    import io

    entries = registry.list_watchlist(min_score=min_score, limit=1000)
    buf = io.StringIO()
    buf.write("﻿")  # BOM — чтобы Excel сразу открыл UTF-8 без кракозябр
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        ["ID", "Объект", "Тип", "Risk score", "Сигналы риска", "Источники", "Дата проверки"]
    )
    for e in entries:
        writer.writerow(
            [
                e["id"],
                e["query"],
                e["query_type"],
                e["risk_score"],
                ", ".join(e["risk_flags"]),
                ", ".join(e["connectors_run"]),
                e["created_at"],
            ]
        )
    buf.seek(0)
    filename = f"saq_export_afm_{min_score}plus.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/blacklist")
async def admin_blacklist_endpoint(_: dict = Depends(auth.require_admin)):
    """Состав локальных чёрных списков: какие файлы подключены и сколько
    в каждом записей. Файлы правятся на диске — эндпоинт даёт увидеть,
    что реально загружено, не заходя на сервер."""
    import json as _json
    from pathlib import Path

    blacklist_dir = Path(__file__).resolve().parent.parent / "data" / "blacklists"
    out = []
    if blacklist_dir.exists():
        for f in sorted(blacklist_dir.glob("*.json")):
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                out.append(
                    {
                        "file": f.name,
                        "regulator": data.get("regulator"),
                        "updated": data.get("updated"),
                        "entries": len(data.get("entries", [])),
                    }
                )
            except Exception as exc:
                out.append({"file": f.name, "error": str(exc)[:120]})
    return {"lists": out, "total_entries": sum(x.get("entries", 0) for x in out)}


@app.post("/admin/bootstrap")
async def admin_bootstrap_endpoint(req: LoginRequest):
    """Назначает первого администратора. Работает ТОЛЬКО пока в системе нет
    ни одного админа — после этого всегда возвращает 403. Нужен, чтобы
    поднять систему с нуля, не залезая в базу руками."""
    existing = [u for u in auth_store.list_users(limit=10000) if u.get("role") == quota.ROLE_ADMIN]
    if existing:
        raise HTTPException(
            status_code=403,
            detail="Администратор уже назначен — используйте /admin/users/{id}/role",
        )

    email = req.email.strip().lower()
    user = auth_store.get_user_by_email(email)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    auth_store.set_role(user["id"], quota.ROLE_ADMIN)
    return {"status": "ok", "user_id": user["id"], "email": email, "role": quota.ROLE_ADMIN}


@app.get("/me/investigations")
def my_investigations_endpoint(
    current_user: dict = Depends(auth.get_current_user), limit: int = Query(default=30, le=100)
):
    """Мои проверки — то, чего нет в общем реестре: только мои объекты."""
    return registry.list_user_investigations(current_user["id"], limit=limit)


@app.get("/me/tips")
def my_tips_endpoint(
    current_user: dict = Depends(auth.get_current_user), limit: int = Query(default=30, le=100)
):
    """Мои наводки со статусом автопроверки — обратная связь по тому,
    что я отправил в сообщество."""
    return registry.list_user_tips(current_user["id"], limit=limit)


@app.get("/me/bridges", response_model=list[BridgeAlert])
def my_bridges_endpoint(
    current_user: dict = Depends(auth.get_current_user), limit: int = Query(default=20, le=100)
):
    """Сущности (домен/кошелёк/IP), общие между моими проверками и любыми
    другими в системе — сигнал, что мой объект связан с другой пирамидой
    через общую инфраструктуру. Тот же принцип, что bridge-узлы на графе,
    но посчитанный по уже сохранённым данным, без повторного прогона."""
    return registry.find_bridges_for_user(current_user["id"], limit=limit)


@app.post("/me/recheck", response_model=InvestigateResponse)
async def recheck_endpoint(
    req: InvestigateRequest, current_user: dict = Depends(auth.get_current_user)
) -> InvestigateResponse:
    """Повторная проверка объекта из кабинета — в отличие от публичного
    /investigate, тратит суточную квоту и привязывает результат к
    аккаунту, так что новая проверка сразу видна в «Мои проверки»."""
    allowed, state = quota.check_and_consume(current_user)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Суточный лимит исчерпан ({state['limit']} запросов). Обновится в течение 24 часов.",
        )

    investigation_id, query_type, connectors_run, results, risk_score, risk_flags, summary, recurrence = (
        await investigate(req.query, req.query_type, req.synthesize, user_id=current_user["id"])
    )
    return InvestigateResponse(
        investigation_id=investigation_id,
        query=req.query,
        detected_type=query_type,
        connectors_run=connectors_run,
        results=results,
        risk_score=risk_score,
        risk_flags=risk_flags,
        summary=summary,
        recurrence=recurrence,
    )
