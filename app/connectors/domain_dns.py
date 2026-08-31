import asyncio

import dns.resolver
import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class DnsRecordsConnector(OSINTConnector):
    """A / MX / TXT / NS records. Shared hosting IPs or nameservers across
    multiple "unrelated" projects are a strong signal of a common operator.
    """

    name = "dns_records"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        return await asyncio.to_thread(self._resolve, query)

    def _resolve(self, domain: str):
        resolver = dns.resolver.Resolver()
        resolver.timeout = 4
        resolver.lifetime = 4
        result = {}
        for record_type in ("A", "MX", "TXT", "NS"):
            try:
                answers = resolver.resolve(domain, record_type)
                result[record_type] = [str(a).strip('"') for a in answers]
            except Exception:
                result[record_type] = []
        return result
