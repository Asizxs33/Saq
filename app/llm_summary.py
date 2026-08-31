import os

from app.models import ConnectorResult, QueryType


async def summarize(
    raw_query: str,
    query_type: QueryType,
    results: list[ConnectorResult],
    risk_score: int,
    risk_flags: list[str],
) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_summary(raw_query, results, risk_score, risk_flags)

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    raw_dump = "\n\n".join(
        f"### {r.source} (ok={r.ok})\n{r.data if r.ok else r.error}" for r in results
    )

    prompt = f"""Ты — аналитик OSINT-расследования финансовых пирамид.
Объект проверки: "{raw_query}" (тип: {query_type.value}).
Найденные red-flag ключевые слова: {risk_flags or 'нет'}.
Rule-based risk score: {risk_score}/100.

Сырые данные от источников:
{raw_dump}

Дай сжатый отчёт (не более 200 слов): что за объект, есть ли признаки
финансовой пирамиды/мошенничества, какие конкретные факты это подтверждают
или опровергают, и какой следующий шаг проверки стоит сделать. Если данных
недостаточно — прямо скажи об этом, не выдумывай факты."""

    # API сбои не должны ронять весь /investigate: одна повторная попытка,
    # затем мягкий откат на rule-based отчёт.
    for attempt in range(2):
        try:
            response = await client.messages.create(
                model="claude-sonnet-5",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            text_parts = [b.text for b in response.content if getattr(b, "text", None)]
            if text_parts:
                return "\n".join(text_parts)
        except anthropic.APIError:
            if attempt == 0:
                continue
    return _fallback_summary(raw_query, results, risk_score, risk_flags)


def _fallback_summary(raw_query, results, risk_score, risk_flags) -> str:
    ok_sources = [r.source for r in results if r.ok]
    failed_sources = [r.source for r in results if not r.ok]
    lines = [
        f"Rule-based отчёт по «{raw_query}» (ANTHROPIC_API_KEY не задан — LLM-синтез отключён).",
        f"Risk score: {risk_score}/100.",
        f"Сработавшие red-flag ключевые слова: {', '.join(risk_flags) if risk_flags else 'нет'}.",
        f"Успешно опрошено источников: {len(ok_sources)} ({', '.join(ok_sources) or '—'}).",
    ]
    if failed_sources:
        lines.append(f"Не ответили/ошиблись: {', '.join(failed_sources)}.")
    lines.append("Смотри поле 'results' в ответе для сырых данных по каждому источнику.")
    return "\n".join(lines)
