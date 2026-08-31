import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class BlockchairConnector(OSINTConnector):
    """Blockchair dashboard endpoint — free tier without a key for light,
    non-commercial use (rate-limited). Cross-checks blockchain.info and
    covers Bitcoin + Ethereum from one API.
    """

    name = "blockchair_multichain"
    applicable_types = {QueryType.BTC_ADDRESS, QueryType.ETH_ADDRESS}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        chain = "bitcoin" if query_type == QueryType.BTC_ADDRESS else "ethereum"
        resp = await client.get(f"https://api.blockchair.com/{chain}/dashboards/address/{query}")
        if resp.status_code == 430:
            return {"note": "rate-limited without API key"}
        resp.raise_for_status()
        payload = resp.json()
        entry = payload.get("data", {}).get(query, {})
        addr = entry.get("address", {})
        return {
            "chain": chain,
            "balance": addr.get("balance"),
            "transaction_count": addr.get("transaction_count"),
            "first_seen": addr.get("first_seen_receiving") or addr.get("first_seen"),
            "last_seen": addr.get("last_seen_spending") or addr.get("last_seen"),
        }
