# Domain-name marker lists for the CertStream watcher. A domain is only
# queued as a candidate lead if it matches, and matching a marker is a
# LEAD, not a verdict — it still goes through the full investigate()
# pipeline (WHOIS, blacklist, search, etc.) before it can affect any score.

# Compound, fairly specific phrases with low false-positive rate on their
# own — a domain containing one of these is worth a look regardless of TLD.
STRONG_MARKERS = [
    "guaranteedprofit", "guaranteedreturn", "doubleyourbtc", "doubleyourmoney",
    "2xdaily", "2xreturns", "10xprofit", "x10profit", "dailyroi", "hyipmonitor",
    "matrixplan", "referralbonus", "passiveincomefast", "freedomdao",
]

# Single generic words — meaningful ONLY combined with a cheap/commonly
# abused TLD below (a real bank's "invest" subdomain shouldn't get flagged;
# a same-day-registered "totallyinvest.xyz" is a different story).
WEAK_MARKERS = ["invest", "profit", "hyip", "airdrop", "mlm", "pyramid", "forex", "capitalx"]

# TLDs cheap enough (often free or <$2 first year) to be a favorite for
# short-lived scam infrastructure. Not proof of anything by itself — just
# the second signal required to act on a WEAK_MARKERS hit.
SUSPICIOUS_TLDS = {"xyz", "top", "site", "online", "icu", "cyou", "shop", "vip", "live", "click", "buzz"}


def match_markers(domain: str) -> list[str] | None:
    """Returns the list of matched markers if `domain` is worth queueing,
    else None. Case-insensitive; strips a leading wildcard label.
    """
    d = domain.lower()
    if d.startswith("*."):
        d = d[2:]

    strong_hits = [m for m in STRONG_MARKERS if m in d]
    if strong_hits:
        return strong_hits

    weak_hits = [m for m in WEAK_MARKERS if m in d]
    if weak_hits:
        tld = d.rsplit(".", 1)[-1] if "." in d else ""
        if tld in SUSPICIOUS_TLDS:
            return weak_hits

    return None
