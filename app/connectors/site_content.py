"""Живая страница сайта: что он ОБЕЩАЕТ посетителю.

Самый сильный признак пирамиды — не возраст домена и не зона .xyz, а текст
на лендинге: «гарантированный доход 300% в месяц», «приведи друга и получи
бонус», «осталось 5 мест». До этого коннектора весь доменный пайплайн
работал только с регистрационными данными (WHOIS, DNS, сертификаты) и ни
разу не открывал сам сайт — поэтому 81.6% доменных проверок давали риск 0,
а сработавшие флаги почти целиком приходились на слова в ИМЕНИ домена.

Паттерны портированы из настольного Guardian (guardian-electron/src/detect.js),
где они ловят те же схемы в тексте на экране: они описывают СТРУКТУРУ развода
(обещание % за срок, «вложи → получи», искусственная срочность, вербовка
рефералов), а не конкретные фразы, поэтому переживают переформулировки.
"""

import asyncio
import re

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

MAX_BYTES = 400_000  # лендинги укладываются; отсекает случайные тяжёлые файлы
MAX_TEXT = 40_000

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# Структурные паттерны: русский, казахский и английский — продукт для РК,
# и англоязычного словаря (как в monitor/markers.py) тут заведомо мало.
PYRAMID_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\d{2,4}\s?%.{0,30}(прибыл|доход|дней|недел|месяц|күн|апта|ай|табыс)", re.I),
     "обещание конкретного % прибыли за срок"),
    (re.compile(r"(вложите?|инвестируй|переведите|салыңыз|салып).{0,45}(получите|заработа|прибыл|аласыз|табыс)", re.I),
     "схема «вложи сейчас → получи потом»"),
    (re.compile(r"(количество мест|осталось \d+ мест|только сегодня|акция закан|орын қалды|бүгін ғана)", re.I),
     "искусственная срочность или ограниченность мест"),
    (re.compile(r"(не рассказывайте|никому не говор|держите в тайне|ешкімге айтпа)", re.I),
     "просьба скрывать предложение от других"),
    (re.compile(r"(вы (были )?выбраны|эксклюзивн(ая|ое) (программ|предложени|возможност)|сіз таңдалдыңыз)", re.I),
     "фальшивая эксклюзивность «вас выбрали»"),
    (re.compile(r"(привед[иі]|пригласи).{0,25}(друг|дос).{0,25}(получ|бонус|%|ал)", re.I),
     "реферальная вербовка"),
    (re.compile(r"(гарантированн\w*|кепілдендірілген)\s*(доход|прибыл|заработок|табыс|пайда)", re.I),
     "обещание гарантированного дохода"),
    (re.compile(r"(пассивн\w+ доход|passive income).{0,30}(без риск|гарант|ежедневн)", re.I),
     "«пассивный доход без риска»"),
    (re.compile(r"(бинарн\w+ маркетинг|матричн\w+ (план|маркетинг)|matrix plan|бинар)", re.I),
     "матричный/бинарный план вознаграждения"),
    (re.compile(r"(удво[ий]|x2|х2|double your).{0,25}(деньг|депозит|вложен|money|ақша)", re.I),
     "обещание удвоения вложений"),
    (re.compile(r"(вывод средств|снятие).{0,40}(заблокир|заморож|комисси\w+ \d{2,})", re.I),
     "признаки блокировки вывода средств"),
    (re.compile(r"(лицензи\w*\s*(отсутств|не требуется)|без лицензии|лицензиясыз)", re.I),
     "прямое указание на работу без лицензии"),
]

# Слова, по которым видно, что сайт вообще про инвестиции/заработок —
# без них процентные обещания часто оказываются скидками интернет-магазина.
FINANCE_CONTEXT = re.compile(
    r"(инвест|вклад|депозит|доход|прибыл|заработок|трейд|крипт|forex|invest|profit|табыс|ақша)", re.I
)

# Домен куплен, но сайта ещё нет: заглушка регистратора/хостинга или
# страница «продаётся». Важно отличать от работающей пирамиды — иначе
# домен вроде clickprofitlab.site получает высокий риск за одно лишь имя,
# хотя предъявить посетителю ему пока нечего. Для мониторинга это отдельный
# статус: «зарегистрирован, ещё не запущен» — повод вернуться позже.
# Пирамида редко выкладывает условия на главную: там обычно вывеска и
# кнопка «войти», а сам оффер («доход 25% в месяц», «партнёрская программа
# 5 уровней») живёт на внутренней странице. Поэтому после главной обходим
# несколько подстраниц — сначала те, чьи ссылки прямо намекают на оффер.
_LINK_RE = re.compile(r"""<a\s[^>]*?href\s*=\s*["']([^"'#>]+)["']""", re.I)

INTERESTING_PATH = re.compile(
    r"(invest|tariff|price|pricing|plan|partner|referral|program|income|profit|"
    r"earn|deposit|bonus|marketing|faq|about|team|инвест|тариф|цен|план|партн|"
    r"реферал|программ|доход|заработ|вклад|депозит|бонус|маркетинг|о-нас|о_нас|"
    r"about-us|условия|салым|табыс|серіктес)", re.I
)

MAX_INNER_PAGES = 4  # бюджет: коннектор целиком должен уложиться в таймаут

PARKED_PATTERNS = re.compile(
    r"(parked (domain|free|at)|domain (is )?(parked|for sale)|buy this domain|"
    r"этот домен (продаётся|припаркован)|домен (продается|продаётся)|"
    r"coming soon|under construction|сайт в разработке|страница в разработке|"
    r"default (web ?)?page|welcome to nginx|apache2 (ubuntu|debian) default|"
    r"hostinger dns|godaddy|sedo|namecheap parking|это временная страница)", re.I
)


def extract_text(html: str) -> str:
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    body = _TAG_RE.sub(" ", body)
    body = (
        body.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&quot;", '"').replace("&#39;", "'")
        .replace("&lt;", "<").replace("&gt;", ">")
    )
    return _WS_RE.sub(" ", body).strip()[:MAX_TEXT]


class SiteContentConnector(OSINTConnector):
    """Открывает сайт домена (главную и несколько внутренних страниц) и
    разбирает их текст на признаки пирамиды."""

    name = "site_content"
    applicable_types = {QueryType.DOMAIN}

    @staticmethod
    def _scan(text: str) -> list[dict]:
        found = []
        for pattern, label in PYRAMID_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            start = max(0, m.start() - 60)
            found.append({
                "signal": label,
                # цитата — чтобы вывод был проверяемым, а не «поверьте на слово»
                "quote": text[start:m.end() + 60].strip(),
            })
        return found

    @staticmethod
    def _inner_links(html: str, base: str, domain: str) -> list[str]:
        """Ссылки со страницы, ведущие на тот же домен и похожие на оффер."""
        from urllib.parse import urljoin, urlparse

        seen, out = set(), []
        for href in _LINK_RE.findall(html):
            if href.lower().startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            url = urljoin(base, href)
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                continue
            # только тот же сайт: уходить на внешние ресурсы здесь незачем
            host = parsed.netloc.lower().removeprefix("www.")
            if host != domain.lower().removeprefix("www."):
                continue
            path = parsed.path or "/"
            if path.rstrip("/") in ("", base.rstrip("/")):
                continue
            if not INTERESTING_PATH.search(path):
                continue
            key = path.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
        return out[:MAX_INNER_PAGES]

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Текст одной внутренней страницы; ошибки здесь не фатальны."""
        try:
            resp = await client.get(
                url,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
                    ),
                    "Accept-Language": "ru,kk;q=0.9,en;q=0.8",
                },
            )
        except Exception:
            return None
        if "html" not in resp.headers.get("content-type", "").lower():
            return None
        return extract_text(resp.text[:MAX_BYTES])

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        domain = query.strip().rstrip("/").replace("https://", "").replace("http://", "")
        last_error = None
        for scheme in ("https", "http"):
            try:
                resp = await client.get(
                    f"{scheme}://{domain}",
                    follow_redirects=True,
                    headers={
                        # без обычного UA часть лендингов отдаёт заглушку
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
                        ),
                        "Accept-Language": "ru,kk;q=0.9,en;q=0.8",
                    },
                )
            except Exception as exc:
                last_error = str(exc)
                continue

            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype.lower():
                return {"reachable": True, "status": resp.status_code,
                        "note": f"не HTML ({ctype[:40]})", "matches": []}

            html = resp.text[:MAX_BYTES]
            text = extract_text(html)
            title_m = _TITLE_RE.search(html)
            has_finance = bool(FINANCE_CONTEXT.search(text))

            matches = [{**m, "page": "/"} for m in self._scan(text)]

            title = title_m.group(1).strip()[:200] if title_m else None
            # заглушки короткие и содержат характерные фразы — проверяем и
            # заголовок, и текст, но только на небольшой странице, чтобы не
            # принять за парковку реальный сайт, упомянувший «coming soon»
            parked = bool(
                PARKED_PATTERNS.search(f"{title or ''} {text[:2000]}")
            ) and len(text) < 2500

            # Главная у пирамиды часто пустая вывеска, а условия («доход 25%
            # в месяц», «5 уровней партнёрки») лежат на внутренней странице.
            # На припаркованном домене обходить нечего.
            pages_read = ["/"]
            if not parked:
                inner = self._inner_links(html, str(resp.url), domain)
                if inner:
                    fetched = await asyncio.gather(
                        *(self._fetch_page(client, u) for u in inner),
                        return_exceptions=True,
                    )
                    seen_signals = {m["signal"] for m in matches}
                    for url, page_text in zip(inner, fetched):
                        if isinstance(page_text, BaseException) or not page_text:
                            continue
                        from urllib.parse import urlparse
                        path = urlparse(url).path or "/"
                        pages_read.append(path)
                        if not has_finance:
                            has_finance = bool(FINANCE_CONTEXT.search(page_text))
                        for m in self._scan(page_text):
                            # один и тот же сигнал с двух страниц — всё ещё
                            # один сигнал, иначе оценка накручивается повтором
                            if m["signal"] in seen_signals:
                                continue
                            seen_signals.add(m["signal"])
                            matches.append({**m, "page": path})
                        text += " " + page_text

            return {
                "reachable": True,
                "final_url": str(resp.url),
                "status": resp.status_code,
                "title": title,
                "text_length": len(text),
                "pages_read": pages_read,
                "finance_context": has_finance,
                "parked": parked,
                "matches": [] if parked else matches,
                "excerpt": text[:600],
            }

        return {"reachable": False, "error": last_error or "сайт не открылся", "matches": []}

    def _scan_red_flags(self, data, query: str) -> list[str]:
        if not isinstance(data, dict):
            return []
        if data.get("parked"):
            # это наблюдение, а не обвинение: домен куплен, но пуст
            return ["сайт не запущен: домен припаркован"]
        matches = data.get("matches") or []
        if not matches:
            return []
        # процентные обещания без финансового контекста — обычно распродажа,
        # а не пирамида; на такой странице сигнал не поднимаем
        if not data.get("finance_context"):
            matches = [m for m in matches if "%" not in m["signal"]]
        return [f"на сайте: {m['signal']}" for m in matches]
