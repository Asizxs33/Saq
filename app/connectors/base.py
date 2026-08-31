import os
from abc import ABC, abstractmethod

import httpx

from app.models import ConnectorResult, QueryType

CONNECTOR_TIMEOUT = float(os.getenv("CONNECTOR_TIMEOUT", "12"))

# Keyword markers commonly used by financial pyramids / Ponzi schemes.
# Matched case-insensitively against any text a connector returns.
PYRAMID_RED_FLAGS = [
    "гарантированн", "guaranteed return", "guaranteed profit",
    "пассивный доход без риска", "приведи друга", "referral bonus",
    "рефераль", "double your", "удвои свои", "пирамид", "ponzi",
    "financial pyramid", "инвестируй сейчас", "места заканчиваются",
    "limited slots", "без лицензии", "unregistered securities",
    "matrix scheme", "hyip", "airdrop guaranteed",
]


class OSINTConnector(ABC):
    name: str = "base"
    applicable_types: set[QueryType] = set()

    def supports(self, query_type: QueryType) -> bool:
        return query_type in self.applicable_types

    async def run(self, client: httpx.AsyncClient, query: str, query_type: QueryType) -> ConnectorResult:
        try:
            data = await self._fetch(client, query, query_type)
            flags = self._scan_red_flags(data, query)
            return ConnectorResult(source=self.name, ok=True, data=data, red_flags=flags)
        except httpx.TimeoutException:
            return ConnectorResult(source=self.name, ok=False, error="timeout")
        except Exception as exc:  # connector failures must not break the batch
            return ConnectorResult(source=self.name, ok=False, error=str(exc))

    @abstractmethod
    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        ...

    def _scan_red_flags(self, data, query: str) -> list[str]:
        # Some connectors legitimately echo the query itself back (e.g.
        # crt.sh's related_names always includes the domain you searched
        # for, as a SAN on its own certificate). Strip it out before
        # scanning, or a domain like "aihyip.online" trivially "matches"
        # the "hyip" marker against itself — a false positive with zero
        # independent corroboration, not a real finding.
        text = str(data).lower()
        query_lower = query.lower().strip()
        if query_lower:
            text = text.replace(query_lower, "")
        return [flag for flag in PYRAMID_RED_FLAGS if flag in text]
