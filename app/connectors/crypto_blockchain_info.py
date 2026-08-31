import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class BlockchainInfoConnector(OSINTConnector):
    """blockchain.info raw address endpoint — free, no key. Gives balance,
    tx count and counterparties. A single address reused across many
    "unrelated" projects, or receiving many small inbound txs with almost
    no outbound spread (classic collection wallet), is a strong signal.
    """

    name = "blockchain_info_btc"
    applicable_types = {QueryType.BTC_ADDRESS}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            f"https://blockchain.info/rawaddr/{query}",
            params={"limit": 20},
        )
        if resp.status_code == 500:
            return {"found": False, "note": "address not found or malformed"}
        resp.raise_for_status()
        payload = resp.json()

        counterparties = set()
        for tx in payload.get("txs", [])[:20]:
            for out in tx.get("out", []):
                addr = out.get("addr")
                if addr and addr != query:
                    counterparties.add(addr)

        return {
            "found": True,
            "total_received_btc": payload.get("total_received", 0) / 1e8,
            "total_sent_btc": payload.get("total_sent", 0) / 1e8,
            "final_balance_btc": payload.get("final_balance", 0) / 1e8,
            "n_tx": payload.get("n_tx"),
            "distinct_counterparties_sample": list(counterparties)[:15],
        }
