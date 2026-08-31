import asyncio

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

# Sherlock-style: just check whether a public profile page exists for the
# handle on each platform. No login, no scraping of private data.
PLATFORM_URLS = {
    "github": "https://github.com/{u}",
    "instagram": "https://www.instagram.com/{u}/",
    "x_twitter": "https://x.com/{u}",
    "tiktok": "https://www.tiktok.com/@{u}",
    "telegram": "https://t.me/{u}",
    "reddit": "https://www.reddit.com/user/{u}",
    "youtube": "https://www.youtube.com/@{u}",
}


class UsernameEnumConnector(OSINTConnector):
    """Checks whether a handle exists across common platforms. Useful for
    mapping an organizer's presence/consistency (or spotting a fresh
    account with no history, another common red flag).
    """

    name = "username_enumeration"
    applicable_types = {QueryType.USERNAME, QueryType.TELEGRAM_HANDLE}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        handle = query.lstrip("@").replace("https://t.me/", "").replace("http://t.me/", "")

        async def check(platform: str, url_template: str):
            url = url_template.format(u=handle)
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (OSINT-research-bot)"},
                    follow_redirects=True,
                )
                return platform, {"url": url, "exists": resp.status_code == 200, "status": resp.status_code}
            except Exception as exc:
                return platform, {"url": url, "exists": None, "error": str(exc)}

        results = await asyncio.gather(*(check(p, t) for p, t in PLATFORM_URLS.items()))
        return {platform: info for platform, info in results}
