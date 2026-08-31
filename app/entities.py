from app.models import ConnectorResult


def _rec(x) -> dict:
    return x if isinstance(x, dict) else {}


def _arr(x) -> list:
    return x if isinstance(x, list) else []


def extract_entities(result: ConnectorResult) -> list[tuple[str, str]]:
    """Mirrors the extraction logic in web/src/lib/graph.ts so the backend
    registry can cross-reference the same entities the graph visualizes.
    Returns (kind, value) pairs.
    """
    if not result.ok:
        return []
    d = _rec(result.data)
    out: list[tuple[str, str]] = []

    if result.source == "crtsh_cert_transparency":
        for name in _arr(d.get("related_names"))[:10]:
            name = str(name)
            if name and not name.startswith("*"):
                out.append(("domain", name))

    elif result.source == "dns_records":
        for ip in _arr(d.get("A"))[:5]:
            out.append(("ip", str(ip)))

    elif result.source == "blockchain_info_btc":
        for addr in _arr(d.get("distinct_counterparties_sample"))[:10]:
            out.append(("wallet", str(addr)))

    elif result.source == "username_enumeration":
        for platform, info in d.items():
            if _rec(info).get("exists") is True:
                out.append(("profile", platform))

    elif result.source == "opencorporates_registry":
        for company in _arr(d.get("companies"))[:5]:
            name = _rec(company).get("name")
            if name:
                out.append(("org", str(name)))

    return out
