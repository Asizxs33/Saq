import base64
import os

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class ChainabuseConnector(OSINTConnector):
    """Chainabuse (chainabuse.com) — multi-chain community scam-report
    database backed by Circle/Solana Foundation/Binance.US/TRM Labs.
    Checks whether a BTC/ETH address has already been reported as
    malicious, independent of our own local regulator blacklist.

    Opt-in and off by default: the free tier is capped at 10 calls/month
    (not/day) — get your own key at chainabuse.com (profile > Settings >
    API key) and set ENABLE_CHAINABUSE=true + CHAINABUSE_API_KEY once you
    understand that budget. Left on by default, a single day of normal
    wallet-checking traffic would exhaust the whole month's quota.
    """

    name = "chainabuse_scam_reports"
    applicable_types = {QueryType.BTC_ADDRESS, QueryType.ETH_ADDRESS}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        if os.getenv("ENABLE_CHAINABUSE", "false").lower() != "true":
            return {"note": "выключено по умолчанию (ENABLE_CHAINABUSE=false) — лимит 10 запросов/месяц"}

        api_key = os.getenv("CHAINABUSE_API_KEY")
        if not api_key:
            return {
                "note": (
                    "CHAINABUSE_API_KEY не задан. Бесплатный ключ: chainabuse.com — "
                    "профиль → Settings → API key (лимит 10 запросов/месяц)"
                )
            }

        basic = base64.b64encode(f"{api_key}:{api_key}".encode()).decode()
        resp = await client.get(
            "https://api.chainabuse.com/v0/reports",
            params={"address": query},
            headers={"Authorization": f"Basic {basic}"},
        )
        if resp.status_code == 401:
            return {"note": "CHAINABUSE_API_KEY недействителен"}
        if resp.status_code == 429:
            return {"note": "месячный лимit Chainabuse (10 запросов) исчерпан"}
        resp.raise_for_status()
        payload = resp.json()
        # real shape: {"count": N, "reports": [{"scamCategory": ..., "createdAt": ...,
        # "trusted": bool, "addresses": [{"address","chain","domain"}, ...]}, ...]}
        reports = payload.get("reports", [])

        return {
            "report_count": payload.get("count", len(reports)),
            "reports": [
                {
                    "category": r.get("scamCategory"),
                    "trusted": r.get("trusted"),
                    "reported_at": r.get("createdAt"),
                    "chains": sorted({a["chain"] for a in r.get("addresses", []) if a.get("chain")}),
                    "related_domains": sorted(
                        {a["domain"] for a in r.get("addresses", []) if a.get("domain")}
                    )[:10],
                }
                for r in reports[:10]
            ],
        }
