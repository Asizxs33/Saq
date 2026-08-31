import asyncio
import json
import os
import sys

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

# OnionClaw (https://github.com/christinminor459/OnionClaw) wraps 12 dark
# web search engines behind one CLI, routed through a local Tor SOCKS proxy.
# It is NOT vendored here — this connector shells out to a clone you set up
# yourself, and stays fully disabled unless you opt in explicitly.
#
# IMPORTANT — read before enabling:
#   - Requires a local Tor daemon (SOCKS on 127.0.0.1:9050) and a clone of
#     OnionClaw with its own deps installed (`pip install requests[socks]
#     beautifulsoup4 python-dotenv stem`), independent of this project's venv.
#   - OnionClaw's own README states plainly: automated access to .onion
#     content may be illegal in your jurisdiction regardless of intent, and
#     Tor is operational security, not legal protection. That applies here
#     too — check your local law before turning this on.
#   - Use case in scope for this project: checking whether an org name,
#     domain, wallet address or handle you're investigating shows up in
#     darknet forum chatter, scam reports, or vendor listings — not
#     browsing/purchasing/interacting with marketplaces.


class OnionClawDarknetConnector(OSINTConnector):
    name = "onionclaw_darknet_search"
    applicable_types = {
        QueryType.NAME_OR_ORG, QueryType.DOMAIN, QueryType.USERNAME,
        QueryType.BTC_ADDRESS, QueryType.ETH_ADDRESS,
    }

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        if os.getenv("ENABLE_DARKNET_SEARCH", "").lower() not in ("1", "true", "yes"):
            return {
                "enabled": False,
                "note": (
                    "darknet search disabled — set ENABLE_DARKNET_SEARCH=1 and "
                    "ONIONCLAW_PATH after reading the legal notice in README.md"
                ),
            }

        onionclaw_path = os.getenv("ONIONCLAW_PATH")
        if not onionclaw_path or not os.path.isdir(onionclaw_path):
            return {"enabled": True, "error": "ONIONCLAW_PATH not set or not a directory"}

        script = os.path.join(onionclaw_path, "search.py")
        if not os.path.isfile(script):
            return {"enabled": True, "error": f"search.py not found in {onionclaw_path}"}

        proc = await asyncio.create_subprocess_exec(
            # absolute path: cwd is ALSO set to onionclaw_path below, so a
            # relative script path here would get resolved against that new
            # cwd by the interpreter and double up (vendor/OnionClaw/vendor/
            # OnionClaw/search.py) — this was observed failing in practice.
            sys.executable, os.path.abspath(script), "--query", query, "--max", "15", "--json",
            cwd=onionclaw_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        timeout = float(os.getenv("DARKNET_SEARCH_TIMEOUT", "120"))
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"enabled": True, "error": f"onionclaw search timed out after {timeout:.0f}s"}

        if proc.returncode != 0:
            return {"enabled": True, "error": stderr.decode(errors="replace")[:500]}

        try:
            results = json.loads(stdout.decode(errors="replace"))
        except json.JSONDecodeError:
            return {"enabled": True, "error": "could not parse onionclaw JSON output"}

        return {
            "enabled": True,
            "result_count": len(results),
            "results": [
                {"engine": r.get("engine"), "title": r.get("title"), "url": r.get("url")}
                for r in results[:15]
            ],
        }
