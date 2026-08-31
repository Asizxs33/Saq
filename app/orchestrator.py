import asyncio
import inspect

import httpx

from app.connectors import ALL_CONNECTORS
from app.connectors.base import CONNECTOR_TIMEOUT
from app.detect import detect_query_type, normalize_telegram_handle
from app.entities import extract_entities
from app.heuristics import collector_wallet_flags, domain_flags, sanctions_flags
from app.models import ConnectorResult, QueryType, RecurrenceEntry
from app import registry


# Наблюдения, которые полезно показать в досье, но которые сами по себе
# ничего не доказывают — в сумму риска не идут. Припаркованный домен не
# мошенник: он просто ещё ничего не предлагает посетителю.
NEUTRAL_FLAGS = {"сайт не запущен: домен припаркован"}


def _score_risk(results: list[ConnectorResult], heuristic_flags: list[str]) -> tuple[int, list[str]]:
    all_flags: list[str] = []
    for r in results:
        all_flags.extend(r.red_flags)
    all_flags.extend(heuristic_flags)

    unique_flags = sorted(set(all_flags))
    scoring_flags = [f for f in unique_flags if f not in NEUTRAL_FLAGS]
    # simple additive score: each distinct red-flag keyword found across
    # sources contributes; blacklist/scam-report hits are weighted heavily
    # since they're independent third-party corroboration, not a keyword
    # coincidence.
    score = len(scoring_flags) * 10
    for r in results:
        if r.source == "regulator_blacklist_local" and r.data:
            # Реальный регулятор (АФМ РК, ЦБ) — независимое подтверждение.
            if r.data.get("regulator_matches"):
                score += 50
            elif r.data.get("matches"):
                # Совпадение только с собственной базой SAQ: объект уже
                # попадался и был помечен нашей же автопроверкой. Это повод
                # присмотреться, но не независимая улика — иначе оценка
                # растёт от самого факта повторной проверки.
                score += 15
        if r.source == "chainabuse_scam_reports" and r.data and r.data.get("report_count"):
            score += 40
        # Точное попадание в санкционные списки/PEP — независимое
        # подтверждение уровня регулятора, а не совпадение ключевого слова.
        # Частичные совпадения (однофамильцы) намеренно НЕ учитываем.
        if r.source == "opensanctions_lists" and r.data and r.data.get("exact_match"):
            score += 50
        # Текст на самом лендинге — прямая улика: не «слово invest в имени
        # домена», а то, что сайт буквально обещает посетителю. Несколько
        # независимых сигналов подряд (доход + срочность + рефералы) — это
        # уже узнаваемая схема, а не совпадение, поэтому к базовым 10 за флаг
        # добавляем вес за их совокупность.
        if r.source == "site_content" and r.data and r.data.get("finance_context"):
            n = len(r.data.get("matches") or [])
            if n >= 3:
                score += 30
            elif n == 2:
                score += 15
    return min(score, 100), unique_flags


async def investigate(
    raw_query: str,
    forced_type: QueryType | None,
    synthesize: bool,
    exclude_connectors: set[str] | None = None,
    user_id: int | None = None,
    on_progress=None,
):
    """on_progress: необязательный колбэк (sync или async), который вызывается
    по мере готовности КАЖДОГО источника — сигнатура (done, total, result).
    Нужен чату: без него интерфейс 18 секунд показывает одну и ту же строку
    «прогон по всем источникам», хотя источники отвечают вразнобой и уже
    есть что показать."""
    query_type = forced_type or detect_query_type(raw_query)

    query = raw_query.strip()
    if query_type == QueryType.TELEGRAM_HANDLE:
        query = normalize_telegram_handle(raw_query)

    applicable = [
        c for c in ALL_CONNECTORS if c.supports(query_type) and c.name not in (exclude_connectors or set())
    ]

    async with httpx.AsyncClient(timeout=CONNECTOR_TIMEOUT) as client:
        tasks = [c.run(client, query, query_type) for c in applicable]
        if on_progress is None:
            results = await asyncio.gather(*tasks)
        else:
            # as_completed вместо gather: источники по-прежнему работают
            # параллельно, но каждый отдаёт результат сразу, а не ждёт самый
            # медленный — так интерфейс успевает показать их поимённо.
            total = len(tasks)
            results = []
            for fut in asyncio.as_completed(tasks):
                res = await fut
                results.append(res)
                try:
                    maybe = on_progress(len(results), total, res)
                    if inspect.isawaitable(maybe):
                        await maybe
                except Exception:
                    pass  # прогресс — украшение, его сбой не должен ронять проверку

    heuristic_flags = (
        collector_wallet_flags(results)
        + domain_flags(query, query_type, results)
        + sanctions_flags(results)
    )
    risk_score, risk_flags = _score_risk(results, heuristic_flags)

    summary = None
    if synthesize:
        from app.llm_summary import summarize  # local import: optional dependency path

        summary = await summarize(raw_query, query_type, results, risk_score, risk_flags)

    # cross-reference this query + everything it turned up against every
    # past investigation, then persist this one for future cross-refs.
    entity_values: list[tuple[str, str]] = [("target", query)]
    for r in results:
        entity_values.extend(extract_entities(r))

    all_values = [query] + [v for _, v in entity_values]
    prior = registry.find_prior_appearances(all_values)
    recurrence = [RecurrenceEntry(**p) for p in prior]

    investigation_id = registry.record_investigation(
        query=query,
        query_type=query_type.value,
        risk_score=risk_score,
        risk_flags=risk_flags,
        connectors_run=[c.name for c in applicable],
        entity_values=entity_values,
        user_id=user_id,
    )

    return (
        investigation_id,
        query_type,
        [c.name for c in applicable],
        list(results),
        risk_score,
        risk_flags,
        summary,
        recurrence,
    )
