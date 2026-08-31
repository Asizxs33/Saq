import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class RdapWhoisConnector(OSINTConnector):
    """RDAP (modern WHOIS) via rdap.org bootstrap — free, no key, no
    native whois binary required. Gives registration/expiry dates and
    registrar, useful for spotting brand-new domains (a classic pyramid
    red flag: site is weeks old but claims "years of trusted operation").
    """

    name = "rdap_whois"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(f"https://rdap.org/domain/{query}", follow_redirects=True)
        if resp.status_code == 404:
            return {"found": False}
        resp.raise_for_status()
        payload = resp.json()

        events = {e.get("eventAction"): e.get("eventDate") for e in payload.get("events", [])}
        registrar = None
        for entity in payload.get("entities", []):
            if "registrar" in entity.get("roles", []):
                vcard = entity.get("vcardArray", [None, []])[1]
                for field in vcard:
                    if field[0] == "fn":
                        registrar = field[3]

        return {
            "found": True,
            "registered": events.get("registration"),
            "last_changed": events.get("last changed"),
            "expires": events.get("expiration"),
            "registrar": registrar,
            "status": payload.get("status", []),
            "nameservers": [ns.get("ldhName") for ns in payload.get("nameservers", [])],
        }
