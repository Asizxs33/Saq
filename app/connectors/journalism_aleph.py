"""OCCRP Aleph — база расследовательской журналистики.

Aleph хранит документы и структурированные данные, собранные OCCRP и
партнёрскими редакциями: утечки, корпоративные реестры, судебные дела,
санкционные списки, базы госзакупок — десятки миллионов записей из
более чем сотни источников.

Зачем это в SAQ: если организатор пирамиды или её юрлицо уже фигурировали
в журналистском расследовании, Aleph это покажет — а такие материалы обычно
куда содержательнее, чем всё, что даёт обычный поиск. Особенно полезно по
постсоветскому пространству: OCCRP плотно работает по региону.

Доступ: публичный поиск закрыт (401 без ключа), но регистрация на
aleph.occrp.org бесплатна и даёт API-ключ сразу. Без ключа коннектор не
ломает прогон, а честно сообщает, что источник не подключён — тот же
шаблон, что у OpenCorporates в этом проекте.
"""

import os

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

API_URL = "https://aleph.occrp.org/api/2/entities"


class AlephConnector(OSINTConnector):
    name = "occrp_aleph"
    applicable_types = {QueryType.NAME_OR_ORG, QueryType.DOMAIN, QueryType.USERNAME}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        api_key = os.getenv("ALEPH_API_KEY")
        if not api_key:
            return {
                "note": (
                    "ALEPH_API_KEY не задан — база расследований OCCRP не опрашивалась. "
                    "Бесплатный ключ: зарегистрируйтесь на aleph.occrp.org, затем "
                    "Profile → API Key."
                ),
                "results": [],
            }

        resp = await client.get(
            API_URL,
            params={"q": query, "limit": 10},
            headers={"Authorization": f"ApiKey {api_key}", "Accept": "application/json"},
        )
        if resp.status_code in (401, 403):
            return {"note": "ALEPH_API_KEY недействителен или истёк", "results": []}
        if resp.status_code == 429:
            return {"note": "Aleph: превышен лимит запросов, попробуйте позже", "results": []}
        resp.raise_for_status()

        payload = resp.json()
        results = []
        for item in payload.get("results", [])[:10]:
            props = item.get("properties", {}) or {}
            # collection — это конкретное расследование/датасет, из которого
            # запись; для читателя это и есть «где именно всплыло»
            collection = (item.get("collection") or {}).get("label")
            results.append(
                {
                    "name": (props.get("name") or [item.get("caption", "—")])[0],
                    "schema": item.get("schema"),
                    "collection": collection,
                    "countries": props.get("country") or props.get("jurisdiction") or [],
                    "url": f"https://aleph.occrp.org/entities/{item.get('id')}" if item.get("id") else None,
                }
            )

        return {
            "total": payload.get("total", 0),
            "results": results,
        }
