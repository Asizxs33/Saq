"""GLEIF — глобальный реестр юридических лиц (LEI).

Бесплатная и полностью открытая альтернатива платному OpenCorporates
(от ~£99/мес). GLEIF — некоммерческий фонд, созданный по инициативе G20
после кризиса 2008 года; ведёт реестр кодов LEI, которые обязаны получать
все участники финансовых рынков. API открыт, ключ не нужен, данные
обновляются ежедневно.

Зачем это в SAQ: проект, называющий себя «международным инвестиционным
фондом» или «финансовой компанией», обязан иметь LEI, если реально
работает на регулируемых рынках. Отсутствие записи — не приговор (LEI
нужен не всем), но в связке с остальными сигналами это довод: контора
не ведёт той деятельности, которой хвастается.

А вот наличие записи даёт проверяемые факты: юрисдикцию регистрации,
официальный адрес, статус (ACTIVE / LAPSED — просроченный LEI сам по себе
показателен) и материнскую структуру, если она раскрыта.
"""

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

API_URL = "https://api.gleif.org/api/v1/lei-records"


class GleifConnector(OSINTConnector):
    name = "gleif_lei_registry"
    applicable_types = {QueryType.NAME_OR_ORG}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            API_URL,
            params={"filter[entity.legalName]": query, "page[size]": 10},
            headers={"Accept": "application/vnd.api+json"},
        )
        if resp.status_code == 429:
            return {"note": "GLEIF: превышен лимит запросов, попробуйте позже", "records": []}
        resp.raise_for_status()
        payload = resp.json()

        total = (payload.get("meta", {}).get("pagination", {}) or {}).get("total", 0)
        records = []
        for item in payload.get("data", [])[:10]:
            attrs = item.get("attributes", {}) or {}
            entity = attrs.get("entity", {}) or {}
            registration = attrs.get("registration", {}) or {}
            legal_addr = entity.get("legalAddress", {}) or {}

            records.append(
                {
                    "lei": attrs.get("lei"),
                    "name": (entity.get("legalName", {}) or {}).get("name"),
                    "jurisdiction": entity.get("jurisdiction"),
                    "status": entity.get("status"),
                    # LAPSED = организация перестала подтверждать данные;
                    # для «действующего фонда» это красноречиво
                    "lei_status": registration.get("status"),
                    "country": legal_addr.get("country"),
                    "city": legal_addr.get("city"),
                    "last_updated": registration.get("lastUpdateDate"),
                }
            )

        return {"total": total, "records": records}
