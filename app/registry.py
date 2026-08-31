import json

from app.db import get_connection


def record_investigation(
    query: str,
    query_type: str,
    risk_score: int,
    risk_flags: list[str],
    connectors_run: list[str],
    entity_values: list[tuple[str, str]],
    user_id: int | None = None,
) -> int:
    """Persists an investigation and its extracted entities (kind, value)
    pairs so future investigations can cross-reference them. Returns the
    new investigation id.

    user_id проставляется, когда проверку запустил вошедший пользователь —
    так в кабинете видно «мои проверки». Фоновый автомониторинг пишет NULL:
    у его находок нет автора.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO investigations (query, query_type, risk_score, risk_flags, connectors_run, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                query,
                query_type,
                risk_score,
                json.dumps(risk_flags),
                json.dumps(connectors_run),
                user_id,
            ),
        )
        investigation_id = cur.lastrowid

        rows = [(investigation_id, kind, value, value.lower()) for kind, value in entity_values]
        conn.executemany(
            "INSERT INTO saq_entities (investigation_id, kind, value, value_lower) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return investigation_id
    finally:
        conn.close()


def find_prior_appearances(values: list[str], exclude_investigation_id: int | None = None) -> list[dict]:
    """Given a list of raw string values (the query itself plus any
    extracted entities), returns prior investigations that share at least
    one of those values, most recent first. Case-insensitive.
    """
    if not values:
        return []

    lowered = [v.lower() for v in values if v]
    if not lowered:
        return []

    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in lowered)
        query = f"""
            SELECT DISTINCT i.id, i.query, i.query_type, i.risk_score, i.created_at
            FROM investigations i
            JOIN saq_entities e ON e.investigation_id = i.id
            WHERE e.value_lower IN ({placeholders})
            ORDER BY i.created_at DESC
            LIMIT 20
        """
        rows = conn.execute(query, lowered).fetchall()
        results = [dict(r) for r in rows]
        if exclude_investigation_id is not None:
            results = [r for r in results if r["id"] != exclude_investigation_id]
        return results
    finally:
        conn.close()


def list_watchlist(min_score: int = 30, limit: int = 100) -> list[dict]:
    """Latest qualifying investigation per query — one object may be
    re-investigated many times (community tips, monitoring re-runs), and
    without deduplication a single hot domain floods the whole list."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT i.id, i.query, i.query_type, i.risk_score, i.risk_flags, i.connectors_run, i.created_at "
            "FROM investigations i "
            "JOIN (SELECT query, MAX(id) AS max_id FROM investigations "
            "      WHERE risk_score >= ? GROUP BY query) latest ON latest.max_id = i.id "
            "ORDER BY i.created_at DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
        entries = []
        for r in rows:
            d = dict(r)
            d["risk_flags"] = json.loads(d["risk_flags"])
            d["connectors_run"] = json.loads(d["connectors_run"])
            entries.append(d)
        return entries
    finally:
        conn.close()


def create_tip(
    target: str, note: str, contact: str | None, user_id: int | None = None, source: str = "web"
) -> int:
    """source различает, откуда пришла наводка: 'web' — форма на сайте,
    'guardian_app' — desktop-программа SAQ Guardian (фраза-маркер пирамиды
    или казино-контент, замеченные на экране), 'certstream' зарезервирован
    на будущее (сейчас находки CertStream идут напрямую в investigations,
    минуя tips — см. app/monitor/candidate_runner.py)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO tips (target, note, contact, user_id, source) VALUES (?, ?, ?, ?, ?)",
            (target, note, contact, user_id, source),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_tip_status(tip_id: int, status: str) -> bool:
    """Ручная модерация наводки админом: pending -> confirmed/rejected.
    Возвращает False, если такой наводки нет."""
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE tips SET status = ? WHERE id = ?", (status, tip_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_tips(limit: int = 100) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, target, note, contact, status, risk_score, investigation_id, created_at, source "
            "FROM tips ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_candidate_leads(status: str | None = None, limit: int = 200) -> list[dict]:
    """Сырая очередь автомониторинга (CertStream) — то, что робот нашёл и
    либо ещё проверяет, либо уже проверил. Отдельно от Watchlist: сюда
    попадает вообще всё, включая то, что не набрало риска и в Watchlist не
    показывается — админ должен видеть полную картину, что робот ловит."""
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT id, domain, matched_markers, status, investigation_id, first_seen "
                "FROM candidate_leads WHERE status = ? ORDER BY first_seen DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, domain, matched_markers, status, investigation_id, first_seen "
                "FROM candidate_leads ORDER BY first_seen DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["matched_markers"] = json.loads(d["matched_markers"])
            out.append(d)
        return out
    finally:
        conn.close()


def update_tip_result(tip_id: int, status: str, risk_score: int, investigation_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE tips SET status = ?, risk_score = ?, investigation_id = ? WHERE id = ?",
            (status, risk_score, investigation_id, tip_id),
        )
        conn.commit()
    finally:
        conn.close()


def enqueue_candidate_lead(domain: str, matched_markers: list[str]) -> None:
    """Records a domain the CertStream watcher flagged, if not already
    queued. Silently no-ops on duplicates (UNIQUE domain) — the same domain
    can get re-issued certs many times, we only need to investigate it once.
    """
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO candidate_leads (domain, matched_markers) VALUES (?, ?)",
            (domain, json.dumps(matched_markers)),
        )
        conn.commit()
    finally:
        conn.close()


def claim_pending_candidates(limit: int) -> list[dict]:
    """Atomically claims up to `limit` 'new' candidates by flipping them to
    'processing', so a concurrent runner tick can't double-process one.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, domain, matched_markers FROM candidate_leads "
            "WHERE status = 'new' ORDER BY first_seen ASC LIMIT ?",
            (limit,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE candidate_leads SET status = 'processing' WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_candidate_done(candidate_id: int, investigation_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE candidate_leads SET status = 'done', investigation_id = ? WHERE id = ?",
            (investigation_id, candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_candidate_failed(candidate_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE candidate_leads SET status = 'new' WHERE id = ?", (candidate_id,))
        conn.commit()
    finally:
        conn.close()


def list_user_investigations(user_id: int, limit: int = 30) -> list[dict]:
    """Проверки, запущенные конкретным пользователем — для его кабинета.
    Схлопываем по объекту: одна строка на объект, с последним скором."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT i.id, i.query, i.query_type, i.risk_score, i.risk_flags, i.created_at "
            "FROM investigations i "
            "JOIN (SELECT query, MAX(id) AS max_id FROM investigations "
            "      WHERE user_id = ? GROUP BY query) latest ON latest.max_id = i.id "
            "ORDER BY i.created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["risk_flags"] = json.loads(d["risk_flags"])
            out.append(d)
        return out
    finally:
        conn.close()


def find_bridges_for_user(user_id: int, limit: int = 20) -> list[dict]:
    """Сущности (домен/кошелёк/IP/...), общие между проверками ЭТОГО
    пользователя и ЛЮБЫМИ другими проверками в системе — тот же принцип,
    что бридж-узлы на графе (buildMultiGraph), но посчитанный на бэкенде
    по таблице entities, а не требующий заново гонять коннекторы."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT
                i1.id AS my_id, i1.query AS my_query,
                e1.kind AS shared_kind, e1.value AS shared_value,
                i2.id AS other_id, i2.query AS other_query,
                i2.risk_score AS other_risk_score, i2.created_at AS other_created_at
            FROM saq_entities e1
            JOIN investigations i1 ON i1.id = e1.investigation_id AND i1.user_id = ?
            JOIN saq_entities e2 ON e2.value_lower = e1.value_lower AND e2.investigation_id != e1.investigation_id
            JOIN investigations i2 ON i2.id = e2.investigation_id
            WHERE e1.kind != 'target' AND i2.query != i1.query
            ORDER BY i2.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_user_tips(user_id: int, limit: int = 30) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, target, note, status, risk_score, investigation_id, created_at "
            "FROM tips WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
