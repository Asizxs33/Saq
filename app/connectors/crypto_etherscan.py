import os

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class EtherscanConnector(OSINTConnector):
    """Etherscan account balance + last txs, via the V2 API (V1 was
    deprecated — every V1 call now returns HTTP 200 with an embedded
    "NOTOK"/deprecation error, which silently looked like an empty-but-ok
    result until this was caught). Works with the public demo key
    ("YourApiKeyToken") under a very tight shared rate limit; set
    ETHERSCAN_API_KEY (free registration) for reliable use.
    """

    name = "etherscan_eth"
    applicable_types = {QueryType.ETH_ADDRESS}
    BASE_URL = "https://api.etherscan.io/v2/api"
    ETH_MAINNET_CHAINID = 1

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        api_key = os.getenv("ETHERSCAN_API_KEY", "YourApiKeyToken")
        balance_resp = await client.get(
            self.BASE_URL,
            params={
                "chainid": self.ETH_MAINNET_CHAINID,
                "module": "account", "action": "balance", "address": query,
                "tag": "latest", "apikey": api_key,
            },
        )
        balance_resp.raise_for_status()
        balance_payload = balance_resp.json()
        if balance_payload.get("status") == "0" and not str(balance_payload.get("result", "")).isdigit():
            return {"note": f"Etherscan: {balance_payload.get('result')}"}

        tx_resp = await client.get(
            self.BASE_URL,
            params={
                "chainid": self.ETH_MAINNET_CHAINID,
                "module": "account", "action": "txlist", "address": query,
                "startblock": 0, "endblock": 99999999, "page": 1, "offset": 10,
                "sort": "desc", "apikey": api_key,
            },
        )
        tx_resp.raise_for_status()
        tx_payload = tx_resp.json()

        balance_wei = balance_payload.get("result", "0")
        try:
            balance_eth = int(balance_wei) / 1e18
        except ValueError:
            balance_eth = None

        txs = tx_payload.get("result", []) if isinstance(tx_payload.get("result"), list) else []
        return {
            "balance_eth": balance_eth,
            "recent_tx_count": len(txs),
            "recent_txs": [
                {"from": t.get("from"), "to": t.get("to"), "value_eth": int(t.get("value", 0)) / 1e18}
                for t in txs[:10]
            ],
        }
