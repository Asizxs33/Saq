"""Shodan InternetDB — бесплатная замена платному Shodan.

Сам Shodan держит открытый эндпоинт internetdb.shodan.io: без ключа, без
регистрации, без лимита по подписке. Он отдаёт срез своего индекса по
конкретному IP — открытые порты, распознанный софт (CPE), все известные
имена хостов на этом адресе и найденные CVE.

Платный Shodan (от $69) даёт поиск по индексу и историю; здесь только
lookup по известному IP — но для расследования пирамиды этого хватает:
IP мы уже знаем из DNS-коннектора, а вопрос стоит «что ещё живёт на этом
адресе и насколько дырявая там инфраструктура».

Что это даёт: список hostnames на том же IP — это соседи по хостингу.
Если рядом с проверяемым доменом на одном адресе висит десяток других
«инвест-проектов», это одна и та же ферма, а не совпадение. Открытые
панели управления и известные уязвимости дополняют картину качества
площадки — у настоящего финансового сервиса они выглядят иначе.
"""

import asyncio
import ipaddress

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

API_URL = "https://internetdb.shodan.io/{ip}"

# IP берём из результата DNS-коннектора, но он в общем пайплайне выполняется
# параллельно — поэтому резолвим здесь сами, независимо и быстро.
MAX_IPS = 3


class InternetDbConnector(OSINTConnector):
    name = "shodan_internetdb"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        ips = await self._resolve(query)
        if not ips:
            return {"found": False, "note": "домен не резолвится — смотреть нечего"}

        results = []
        for ip in ips[:MAX_IPS]:
            try:
                resp = await client.get(API_URL.format(ip=ip), headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                results.append({"ip": ip, "error": str(exc)[:120]})
                continue

            if resp.status_code == 404:
                # у Shodan просто нет записи по этому адресу — это не ошибка
                results.append({"ip": ip, "indexed": False})
                continue
            if resp.status_code == 429:
                results.append({"ip": ip, "error": "rate limit"})
                continue
            resp.raise_for_status()
            d = resp.json()

            hostnames = [h for h in (d.get("hostnames") or []) if h]
            # сам проверяемый домен среди соседей не показываем — интересны
            # именно чужие имена на том же адресе
            neighbours = [h for h in hostnames if query.lower() not in h.lower()]

            results.append(
                {
                    "ip": ip,
                    "indexed": True,
                    "open_ports": d.get("ports") or [],
                    "software": d.get("cpes") or [],
                    "vulnerabilities": d.get("vulns") or [],
                    "tags": d.get("tags") or [],
                    "hostnames_on_ip": hostnames[:15],
                    "neighbour_count": len(neighbours),
                }
            )

        return {"found": True, "checked_ips": len(results), "results": results}

    async def _resolve(self, domain: str) -> list[str]:
        """A-записи домена. dnspython синхронный — уводим в поток, чтобы не
        блокировать событийный цикл на время резолва."""

        def _lookup() -> list[str]:
            try:
                import dns.resolver

                answers = dns.resolver.resolve(domain, "A", lifetime=5)
                out = []
                for a in answers:
                    ip = str(a)
                    try:
                        # приватные адреса в публичном индексе бессмысленны
                        if not ipaddress.ip_address(ip).is_global:
                            continue
                    except ValueError:
                        continue
                    out.append(ip)
                return out
            except Exception:
                return []

        return await asyncio.to_thread(_lookup)
