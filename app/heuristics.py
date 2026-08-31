from datetime import datetime, timezone

from app.models import ConnectorResult, QueryType
from app.monitor.markers import STRONG_MARKERS, SUSPICIOUS_TLDS, WEAK_MARKERS

# Approximate, transparent pattern-matching — not a definitive verdict.
# A "collector" wallet receives from many distinct counterparties and
# passes most of it straight through (or is actively accumulating faster
# than it pays out) — the shape money takes in an active pyramid before
# payouts stop.
MIN_TX = 15
MIN_COUNTERPARTIES = 8
PASS_THROUGH_RATIO = 0.15
ACCUMULATION_RATIO = 1.5


def sanctions_flags(results: list[ConnectorResult]) -> list[str]:
    """Точное совпадение с санкционными списками/PEP выносим отдельным
    флагом — иначе самый весомый сигнал виден только в сырых данных узла,
    но не в списке красных флагов объекта."""
    for r in results:
        if r.source == "opensanctions_lists" and r.ok and isinstance(r.data, dict):
            if r.data.get("exact_match"):
                return ["в санкционных списках / PEP"]
    return []


def collector_wallet_flags(results: list[ConnectorResult]) -> list[str]:
    flags: list[str] = []
    for r in results:
        if r.source != "blockchain_info_btc" or not r.ok or not isinstance(r.data, dict):
            continue

        data = r.data
        if not data.get("found"):
            continue

        n_tx = data.get("n_tx") or 0
        counterparties = data.get("distinct_counterparties_sample") or []
        received = data.get("total_received_btc") or 0
        sent = data.get("total_sent_btc") or 0
        balance = data.get("final_balance_btc") or 0

        if n_tx < MIN_TX or len(counterparties) < MIN_COUNTERPARTIES or received <= 0:
            continue

        kept_ratio = balance / received if received else 0
        is_pass_through = kept_ratio < PASS_THROUGH_RATIO
        is_accumulating = sent > 0 and received > sent * ACCUMULATION_RATIO

        if is_pass_through or is_accumulating:
            flags.append("паттерн кошелька-сборщика")
    return flags


# A freshly registered domain has no text trail yet (no archive snapshots,
# no search results), so keyword red-flags can't fire — every auto-caught
# CertStream candidate used to score 0 and never surface in the watchlist.
# These are infrastructure-level signals instead: each is weak alone (+10
# via the shared flag scoring), meaningful in combination.
FRESH_DOMAIN_DAYS = 90


def domain_flags(query: str, query_type: QueryType, results: list[ConnectorResult]) -> list[str]:
    if query_type != QueryType.DOMAIN:
        return []

    flags: list[str] = []
    d = query.lower().strip().rstrip(".")

    if any(m in d for m in STRONG_MARKERS) or any(m in d for m in WEAK_MARKERS):
        flags.append("маркер-приманка в имени домена")

    tld = d.rsplit(".", 1)[-1] if "." in d else ""
    if tld in SUSPICIOUS_TLDS:
        flags.append("дешёвая TLD-зона, типичная для скам-инфраструктуры")

    registered_days_ago: float | None = None
    for r in results:
        if r.source != "rdap_whois" or not r.ok or not isinstance(r.data, dict):
            continue
        raw = r.data.get("registered")
        if not raw:
            continue
        try:
            registered = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if registered.tzinfo is None:
                registered = registered.replace(tzinfo=timezone.utc)
            registered_days_ago = (datetime.now(timezone.utc) - registered).days
        except ValueError:
            pass

    if registered_days_ago is not None and registered_days_ago <= FRESH_DOMAIN_DAYS:
        flags.append(f"домен свежерегистрирован ({int(registered_days_ago)} дн. назад)")

        # no archive history is only meaningful for a fresh domain that
        # already runs marketing-looking infrastructure; on old domains
        # it's noise (plenty of legit sites are simply never archived)
        for r in results:
            if r.source == "wayback_machine" and r.ok and isinstance(r.data, dict):
                if not r.data.get("snapshot_count"):
                    flags.append("нет истории в веб-архиве")

    return flags
