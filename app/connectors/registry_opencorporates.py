import os

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class OpenCorporatesConnector(OSINTConnector):
    """OpenCorporates company search. OpenCorporates closed anonymous
    access to this endpoint (every request now 401s without a token) —
    register a free self-service token at
    https://opencorporates.com/plug-in-our-data/ and set
    OPENCORPORATES_API_TOKEN to enable this source.
    """

    name = "opencorporates_registry"
    applicable_types = {QueryType.NAME_OR_ORG}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        api_token = os.getenv("OPENCORPORATES_API_TOKEN")
        if not api_token:
            return {
                "note": (
                    "OPENCORPORATES_API_TOKEN не задан — OpenCorporates требует токен "
                    "для всех запросов (анонимный доступ закрыт). Зарегистрируйте бесплатный "
                    "токен на https://opencorporates.com/plug-in-our-data/"
                ),
                "companies": [],
            }

        resp = await client.get(
            "https://api.opencorporates.com/v0.4/companies/search",
            params={"q": query, "per_page": 10, "api_token": api_token},
        )
        if resp.status_code == 401:
            return {"note": "OPENCORPORATES_API_TOKEN недействителен или истёк", "companies": []}
        if resp.status_code in (403, 429):
            return {"note": "rate-limited even with API token", "companies": []}
        resp.raise_for_status()
        payload = resp.json()
        companies = payload.get("results", {}).get("companies", [])
        return {
            "match_count": payload.get("results", {}).get("total_count", 0),
            "companies": [
                {
                    "name": c["company"].get("name"),
                    "jurisdiction": c["company"].get("jurisdiction_code"),
                    "status": c["company"].get("current_status"),
                    "incorporation_date": c["company"].get("incorporation_date"),
                    "url": c["company"].get("opencorporates_url"),
                }
                for c in companies
            ],
        }
