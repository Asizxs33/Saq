import re

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class TelegramPreviewConnector(OSINTConnector):
    """Scrapes the public t.me/s/<channel> preview page — this is the
    same page Telegram serves to search engines for public channels, no
    auth or bot account required. Gives recent post text, which the
    orchestrator/LLM can scan for pyramid-scheme pitch language.
    """

    name = "telegram_public_preview"
    applicable_types = {QueryType.TELEGRAM_HANDLE}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        handle = query.lstrip("@").replace("https://t.me/", "").replace("http://t.me/", "")
        resp = await client.get(
            f"https://t.me/s/{handle}",
            headers={"User-Agent": "Mozilla/5.0 (OSINT-research-bot)"},
        )
        if resp.status_code == 404:
            return {"found": False}
        resp.raise_for_status()
        html = resp.text

        titles = re.findall(r'<div class="tgme_channel_info_header_title"[^>]*>.*?<span dir="auto">(.*?)</span>', html)
        member_count = re.findall(r'<div class="tgme_channel_info_counter">\s*<span class="counter_value">([^<]+)</span>\s*<span class="counter_type">members?', html)
        messages = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.S)
        clean_messages = [re.sub(r"<[^>]+>", " ", m).strip() for m in messages]

        return {
            "found": True,
            "title": titles[0] if titles else None,
            "member_count": member_count[0] if member_count else None,
            "recent_post_count": len(clean_messages),
            "recent_posts_sample": clean_messages[:15],
        }
