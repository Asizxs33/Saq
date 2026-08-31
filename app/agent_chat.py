"""Agentic chat: Aqyl as a real tool-use agent (Claude decides which OSINT
connectors to call and in what order), instead of the fixed one-shot
pipeline in orchestrator.investigate(). That pipeline is still exposed
here as the `investigate_full` tool — the fast path for "just check this
object" — while the smaller per-source tools let the agent chain lookups
based on what it actually finds (e.g. WHOIS reveals a registrant pattern
-> agent decides to check crt.sh for related domains -> checks blacklist
on those too), and answer natural-language follow-ups with real memory of
the conversation.
"""

import asyncio
import json
import os
import re
import sys
import uuid
from typing import Any

import httpx

from app.connectors import ALL_CONNECTORS
from app.connectors.base import CONNECTOR_TIMEOUT
from app.detect import detect_query_type, normalize_telegram_handle
from app.heuristics import collector_wallet_flags
from app.models import ConnectorResult, InvestigateResponse, QueryType
from app.orchestrator import investigate as run_full_investigation
from app import registry

CONNECTORS_BY_NAME = {c.name: c for c in ALL_CONNECTORS}

SYSTEM_PROMPT = """Ты — Aqyl, финансовый защитник-агент SAQ. Ты расследуешь подозрительные \
домены, кошельки, username и организации на признаки финансовых пирамид, используя \
инструменты (OSINT-коннекторы), а не догадки.

Принципы, которым ты обязан следовать:
- Досье, а не приговор: risk score и red flags — повод для дальнейшей проверки, не \
финальное обвинение. Никогда не утверждай, что объект "точно пирамида", если у тебя нет \
конкретного факта из инструмента, который это подтверждает.
- Каждый факт — со ссылкой на источник (какой инструмент это дал).
- Если данных недостаточно — прямо скажи об этом, не выдумывай факты.
- Сама решай, какие инструменты вызывать и в каком порядке, исходя из вопроса \
пользователя и того, что ты уже узнал. Если WHOIS показал общий регистратор с другими \
доменами — это повод проверить их через crt.sh. Если нашёлся владелец — стоит проверить \
его по блэклисту и username.
- При ПЕРВОМ упоминании нового объекта (домен, кошелёк, @канал, username, название) \
ВСЕГДА начинай с investigate_full: именно он собирает досье и рисует пользователю граф \
связей и risk score на экране. Точечные инструменты (check_whois, check_wallet, ...) — \
только ПОСЛЕ полного прогона, для уточняющих вопросов по уже проверенному объекту.
- Если просят НАЙТИ пирамиду/подозрительные проекты БЕЗ конкретного объекта — не \
отказывайся: возьми list_watchlist (живые находки автомониторинга новых доменов и \
прошлых проверок), выбери самого свежего или рискового кандидата, прогони его через \
investigate_full и расскажи, что нашлось. Дополнительно можно искать кандидатов через \
search_web по маркерным запросам («гарантированный доход инвестиции» и т.п.). Если в \
этом разговоре уже разбирал какой-то кандидат — при следующей такой просьбе бери \
ДРУГОЙ объект из списка, не повторяйся.
- Если просят найти пирамиду в КОНКРЕТНОМ регионе/городе ("найди пирамиду в \
Туркестане") — используй search_by_region с этим регионом. Он вернёт сырую поисковую \
выдачу по маркерным запросам, привязанным к региону. Изучи её сам: найди конкретное \
название организации/сайта/проекта, которое реально упоминается в связке с этим \
регионом и признаками пирамиды (обещания дохода, жалобы, "кинули"), и прогони его через \
investigate_full. Если ничего убедительного не нашлось — прямо скажи, что подтверждённого \
кандидата в этом регионе сейчас нет, не выдумывай и не выдавай нерелевантный результат \
за находку.
- Если просят найти НОВУЮ, ещё никому не известную пирамиду ИМЕННО ЧЕРЕЗ ДАРКНЕТ (не \
"проверь X", а "найди/обнаружь через даркнет") — используй darknet_browse. Это НЕ поиск \
по слову (у поиска по слову нет смысла без уже известного имени) — инструмент листает \
целый раздел каталога даркнета и отдаёт сырые объявления с описаниями. Изучи описания \
сам: ищи классическую риторику пирамиды — гарантированный/фиксированный процент, "удвой \
свои деньги", отсутствие объяснения, откуда берётся прибыль, давление срочностью. Если \
нашёл подозрительное объявление — назови его прямо (название, .onion-ссылка, что именно \
в описании похоже на пирамиду), и честно предупреди: это НЕПОДТВЕРЖДЁННАЯ даркнет-наводка \
(даркнет-сервисы обычно не имеют клирнет-следа для independent проверки через \
investigate_full), а не установленный факт со статусом регулятора. Не приукрашивай и не \
выдавай обычный сервис (эскроу, микс-сервис) за пирамиду только потому что он в даркнете — \
там много нелегального, но НЕ всё это финансовые пирамиды в узком смысле.
- После investigate_full пользователь видит справа ГРАФ СВЯЗЕЙ: объект в центре, вокруг \
— источники (красная связь и красный бейдж с цифрой = источник дал сигналы риска), на \
внешнем кольце — найденные сущности (домены, кошельки, профили, юрлица). Заверши ответ \
одной строкой-навигацией по графу: на какие узлы смотреть и почему, например: "На графе: \
красные связи — WHOIS и Блэклист, это главные улики; кликните узел, чтобы увидеть сырые \
данные источника". Называй источники по-русски (Метапоиск, WHOIS, Блэклист, Сертификаты, \
Веб-архив), а не техническими именами.
- Отвечай на русском, по-деловому, без воды.
- Формат ответа — простой текст для чат-пузыря, НЕ markdown: без заголовков (#), без \
таблиц, без звёздочек **жирного**. Структурируй короткими абзацами и тире-списками \
("— факт: ..."), это читается как сообщение в мессенджере, а не как документ.
- В САМОМ КОНЦЕ ответа, если ты только что провела расследование (investigate_full, \
search_by_region, darknet_browse или уточняющий инструмент) и есть что развить дальше — \
добавь на новой строке блок с 2-4 конкретными уточняющими вопросами, которые пользователь \
мог бы задать дальше. Вопросы должны быть КОНКРЕТНЫМИ, основанными на том, что реально \
нашлось в этом расследовании (имена, домены, кошельки, регион), а не общими шаблонами \
("расскажи подробнее"). Формат блока строго такой (сам маркер и вопросы не показываются \
пользователю как обычный текст — это отдельный служебный блок):
###SUGGESTIONS###
Первый конкретный вопрос?
Второй конкретный вопрос?
Третий конкретный вопрос?
Если продолжать нечего (простой факт, отказ, ошибка) — не добавляй этот блок вообще."""


def _tool_result(results: list[ConnectorResult]) -> list[dict]:
    return [r.model_dump() for r in results]


async def _run_connectors(names: list[str], query: str, query_type: QueryType) -> list[ConnectorResult]:
    applicable = [CONNECTORS_BY_NAME[n] for n in names if n in CONNECTORS_BY_NAME]
    async with httpx.AsyncClient(timeout=CONNECTOR_TIMEOUT) as client:
        results = await asyncio.gather(*(c.run(client, query, query_type) for c in applicable))
    return list(results)


async def tool_investigate_full(
    query: str,
    query_type: str | None = None,
    _user_id: int | None = None,
    _progress=None,
) -> dict:
    qt = QueryType(query_type) if query_type else None
    investigation_id, detected_type, connectors_run, results, risk_score, risk_flags, _summary, recurrence = (
        await run_full_investigation(query, qt, False, user_id=_user_id, on_progress=_progress)
    )
    dossier = InvestigateResponse(
        investigation_id=investigation_id,
        query=query,
        detected_type=detected_type,
        connectors_run=connectors_run,
        results=results,
        risk_score=risk_score,
        risk_flags=risk_flags,
        summary=None,
        recurrence=recurrence,
    )
    return {
        "_dossier": dossier,  # stripped before sending to Claude, used by the chat endpoint for graph rendering
        "detected_type": detected_type.value,
        "risk_score": risk_score,
        "risk_flags": risk_flags,
        "connectors_run": connectors_run,
        "results": _tool_result(results),
        "recurrence": [r.model_dump() for r in recurrence],
    }


async def tool_check_whois(domain: str) -> dict:
    results = await _run_connectors(["rdap_whois", "dns_records"], domain, QueryType.DOMAIN)
    return {"results": _tool_result(results)}


async def tool_check_related_domains(domain: str) -> dict:
    results = await _run_connectors(["crtsh_cert_transparency"], domain, QueryType.DOMAIN)
    return {"results": _tool_result(results)}


async def tool_check_blacklist(query: str, query_type: str | None = None) -> dict:
    qt = QueryType(query_type) if query_type else detect_query_type(query)
    results = await _run_connectors(["regulator_blacklist_local"], query, qt)
    return {"results": _tool_result(results)}


async def tool_check_wallet(address: str) -> dict:
    qt = detect_query_type(address)
    if qt == QueryType.BTC_ADDRESS:
        names = ["blockchain_info_btc", "blockchair_multichain"]
    elif qt == QueryType.ETH_ADDRESS:
        names = ["blockchair_multichain", "etherscan_eth"]
    else:
        return {"error": f"'{address}' не похож на BTC или ETH адрес"}
    results = await _run_connectors(names, address, qt)
    flags = collector_wallet_flags(results)
    return {"results": _tool_result(results), "heuristic_flags": flags}


async def tool_check_username(handle: str) -> dict:
    is_telegram = handle.startswith("@") or "t.me/" in handle
    qt = QueryType.TELEGRAM_HANDLE if is_telegram else QueryType.USERNAME
    query = normalize_telegram_handle(handle) if is_telegram else handle
    names = ["username_enumeration", "threat_actor_username_search", "regulator_blacklist_local"]
    if is_telegram:
        names.append("telegram_public_preview")
    results = await _run_connectors(names, query, qt)
    return {"results": _tool_result(results)}


async def tool_search_web(query: str) -> dict:
    results = await _run_connectors(
        ["searx_metasearch", "duckduckgo_instant_answer"], query, QueryType.NAME_OR_ORG
    )
    return {"results": _tool_result(results)}


# Маркерные фразы для регионального поиска ("найди пирамиду в Туркестане"):
# смесь рекламных обещаний (то, чем зазывают жертв) и жалоб постфактум
# (то, что пишут пострадавшие), на русском и казахском — пирамиды в
# регионах РК вербуют на обоих языках в зависимости от аудитории.
REGION_MARKER_QUERIES = [
    "{region} инвестиции гарантированный доход в день",
    "{region} финансовая пирамида жалобы",
    "{region} вложи деньги процент кинули",
    "{region} инвестиция кепілдік пайыз күнделікті",
    "{region} пирамида шағым алдау ақша",
]


async def tool_search_by_region(region: str) -> dict:
    """Гоняет маркерные запросы, привязанные к региону, через метапоиск и
    возвращает сырую (дедуплицированную) выдачу — агент сам выбирает из
    неё кандидата и прогоняет его через investigate_full.
    """
    region = region.strip()
    if not region:
        return {"error": "region пуст"}

    queries = [q.format(region=region) for q in REGION_MARKER_QUERIES]
    connector = CONNECTORS_BY_NAME["searx_metasearch"]
    async with httpx.AsyncClient(timeout=CONNECTOR_TIMEOUT) as client:
        results = await asyncio.gather(
            *(connector.run(client, q, QueryType.NAME_OR_ORG) for q in queries)
        )

    seen_urls: set[str] = set()
    hits: list[dict] = []
    for q, r in zip(queries, results):
        if not r.ok or not isinstance(r.data, dict):
            continue
        for item in r.data.get("results") or []:
            url = item.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hits.append({
                "matched_query": q,
                "title": item.get("title"),
                "url": url,
                "content": item.get("content"),
            })

    return {"region": region, "queries_used": queries, "hits_count": len(hits), "hits": hits[:25]}


# Категории каталога Amnesia Directory (тот же .onion, что уже опрашивает
# onionclaw_darknet_search по слову) — здесь мы вместо поиска по имени
# ЛИСТАЕМ разделы каталога целиком, как реальный аналитик открыл бы
# "Cryptocurrency" или "Forums" и читал объявления подряд. Это единственный
# честный способ найти НЕИЗВЕСТНУЮ ранее схему через даркнет: поиск по слову
# требует уже знать это слово, а обход каталога — нет.
DARKNET_CATEGORY_URLS = {
    "marketplaces": "http://amndir7jfxnt5glt2tsevwjlnwdvknttxygubw27ulq5c433en75piyd.onion/?cat=1",
    "cryptocurrency": "http://amndir7jfxnt5glt2tsevwjlnwdvknttxygubw27ulq5c433en75piyd.onion/?cat=5",
    "forums": "http://amndir7jfxnt5glt2tsevwjlnwdvknttxygubw27ulq5c433en75piyd.onion/?cat=8",
    "organizations": "http://amndir7jfxnt5glt2tsevwjlnwdvknttxygubw27ulq5c433en75piyd.onion/?cat=12",
}

_ONION_URL_RE = re.compile(r"https?://[a-z2-7]{16,56}\.onion\S*")


async def tool_darknet_browse(category: str = "cryptocurrency") -> dict:
    """Обходит раздел каталога даркнета (не ищет по слову — читает список
    объявлений целиком) через fetch.py из OnionClaw. Возвращает сырой текст
    листинга — агент сам ищет в описаниях признаки пирамиды/скама.
    """
    if os.getenv("ENABLE_DARKNET_SEARCH", "").lower() not in ("1", "true", "yes"):
        return {"enabled": False, "note": "даркнет-поиск выключен (ENABLE_DARKNET_SEARCH)"}

    onionclaw_path = os.getenv("ONIONCLAW_PATH")
    if not onionclaw_path or not os.path.isdir(onionclaw_path):
        return {"enabled": True, "error": "ONIONCLAW_PATH не задан или не найден"}

    url = DARKNET_CATEGORY_URLS.get(category.lower().strip())
    if not url:
        return {"error": f"неизвестная категория {category!r}, доступны: {list(DARKNET_CATEGORY_URLS)}"}

    script = os.path.abspath(os.path.join(onionclaw_path, "fetch.py"))
    if not os.path.isfile(script):
        return {"enabled": True, "error": f"fetch.py не найден в {onionclaw_path}"}

    proc = await asyncio.create_subprocess_exec(
        sys.executable, script, "--url", url, "--json",
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
        return {"enabled": True, "error": f"обход каталога не уложился в {timeout:.0f}с"}

    if proc.returncode != 0:
        return {"enabled": True, "error": stderr.decode(errors="replace")[:500]}

    try:
        result = json.loads(stdout.decode(errors="replace"))
    except json.JSONDecodeError:
        return {"enabled": True, "error": "не удалось разобрать ответ fetch.py"}

    if result.get("error"):
        return {"enabled": True, "error": result["error"]}

    text = result.get("text", "")
    onion_links = sorted(set(_ONION_URL_RE.findall(text)))
    return {
        "enabled": True,
        "category": category,
        "source": url,
        "onion_links_found": len(onion_links),
        # текст листинга обрезаем, но не слишком — в нём и держатся описания,
        # по которым агент отличает скам-объявление от обычного сервиса
        "raw_listing": text[:6000],
    }


async def tool_check_recurrence(values: list[str]) -> dict:
    prior = registry.find_prior_appearances(values)
    return {"prior_investigations": prior}


async def tool_list_watchlist(min_score: int = 30, limit: int = 15) -> dict:
    entries = registry.list_watchlist(min_score=min_score, limit=limit)
    return {"watchlist": entries}


TOOL_DISPATCH = {
    "investigate_full": tool_investigate_full,
    "check_whois": tool_check_whois,
    "check_related_domains": tool_check_related_domains,
    "check_blacklist": tool_check_blacklist,
    "check_wallet": tool_check_wallet,
    "check_username": tool_check_username,
    "search_web": tool_search_web,
    "check_recurrence": tool_check_recurrence,
    "list_watchlist": tool_list_watchlist,
    "search_by_region": tool_search_by_region,
    "darknet_browse": tool_darknet_browse,
}

CHAT_TOOLS = [
    {
        "name": "investigate_full",
        "description": (
            "Полный прогон объекта через все применимые OSINT-источники и rule-based "
            "risk score — быстрый путь для 'проверь X'. Определяет тип объекта сам, "
            "если query_type не передан."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Домен, кошелёк, @канал, username или название"},
                "query_type": {
                    "type": "string",
                    "enum": [t.value for t in QueryType],
                    "description": "Необязательно — тип объекта, если известен точно",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_whois",
        "description": "RDAP/WHOIS + DNS-записи домена: дата регистрации, регистратор, nameservers.",
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    {
        "name": "check_related_domains",
        "description": (
            "crt.sh Certificate Transparency: находит связанные домены под тем же "
            "сертификатом — вскрывает сеть клонов одного оператора."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    {
        "name": "check_blacklist",
        "description": "Проверка по локальным снимкам списков регуляторов (АФМ РК и др.) по имени/домену.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "query_type": {"type": "string", "enum": [t.value for t in QueryType]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_wallet",
        "description": (
            "Проверка BTC/ETH-адреса по блокчейн-эксплорерам + эвристика "
            "'кошелёк-сборщик' (много контрагентов + быстрый транзит средств)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"address": {"type": "string"}},
            "required": ["address"],
        },
    },
    {
        "name": "check_username",
        "description": (
            "Проверка username/@handle: наличие профиля на платформах, утечки на "
            "киберфорумах, публичный превью Telegram-канала, блэклист."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"handle": {"type": "string"}},
            "required": ["handle"],
        },
    },
    {
        "name": "search_web",
        "description": "Метапоиск (SearXNG + DuckDuckGo) по произвольному запросу — для контекста, отзывов, упоминаний.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_watchlist",
        "description": (
            "Живой реестр SAQ: недавние расследования с risk score выше порога — "
            "включая домены, которые автомониторинг CertStream поймал и проверил "
            "сам. Используй, когда просят НАЙТИ/ПОКАЗАТЬ пирамиды или подозрительные "
            "проекты без конкретного объекта."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_score": {"type": "integer", "description": "минимальный risk score (по умолчанию 30)"},
                "limit": {"type": "integer", "description": "сколько записей вернуть (по умолчанию 15)"},
            },
        },
    },
    {
        "name": "search_by_region",
        "description": (
            "Для запросов вида 'найди пирамиду в <город/регион>'. Гоняет набор "
            "маркерных запросов (обещания дохода + жалобы пострадавших, на русском "
            "и казахском), привязанных к региону, через метапоиск и возвращает сырую "
            "выдачу. Дальше нужно самому найти в ней конкретное название организации "
            "или домен, реально относящиеся к региону, и прогнать через "
            "investigate_full — сам инструмент вердикт не выносит."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"region": {"type": "string", "description": "Город или регион, например 'Түркістан'"}},
            "required": ["region"],
        },
    },
    {
        "name": "darknet_browse",
        "description": (
            "Для запросов вида 'найди НОВУЮ пирамиду через даркнет' — то есть когда просят "
            "не проверить конкретный объект, а именно ОБНАРУЖИТЬ ранее неизвестную схему. "
            "В отличие от обычного даркнет-источника (который ищет упоминания уже известного "
            "имени), этот инструмент ЛИСТАЕТ раздел каталога даркнета целиком и возвращает "
            "сырой текст объявлений с описаниями — реальные данные, а не поиск по слову. "
            "Категории: 'cryptocurrency' (обменники, миксеры — где чаще всего проскакивают "
            "гарантии дохода), 'marketplaces', 'forums', 'organizations'. Требует Tor и "
            "включённый ENABLE_DARKNET_SEARCH, занимает 20-60 секунд."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["cryptocurrency", "marketplaces", "forums", "organizations"],
                    "description": "раздел каталога для обхода, по умолчанию cryptocurrency",
                },
            },
        },
    },
    {
        "name": "check_recurrence",
        "description": "Проверяет, встречались ли эти значения (домены/кошельки/имена) в прошлых расследованиях SAQ.",
        "input_schema": {
            "type": "object",
            "properties": {"values": {"type": "array", "items": {"type": "string"}}},
            "required": ["values"],
        },
    },
]

_SESSIONS: dict[str, list[dict]] = {}
MAX_TOOL_ROUNDS = 6


def new_session_id() -> str:
    return str(uuid.uuid4())


_SUGGESTIONS_MARKER = "###SUGGESTIONS###"

# Инструменты, чей аргумент — свободная поисковая фраза или вообще не
# объект. Их нельзя брать как кандидата для страховочного полного прогона:
# иначе на графе окажется досье на строку вида «онлайн казино схема жалобы»
# — наблюдалось вживую, выглядит как найденный объект, но им не является.
_NON_OBJECT_TOOLS = {
    "check_recurrence",
    "search_web",
    "search_by_region",
    "darknet_browse",
    "list_watchlist",
}


def _split_suggestions(text: str) -> tuple[str, list[str]]:
    """Отделяет служебный блок с предложенными вопросами от текста, который
    реально показывается в чат-пузыре (см. SYSTEM_PROMPT)."""
    if _SUGGESTIONS_MARKER not in text:
        return text, []
    reply, _, block = text.partition(_SUGGESTIONS_MARKER)
    suggestions = [line.strip(" -•\t") for line in block.strip().splitlines() if line.strip()]
    return reply.strip(), suggestions[:4]


# Человекочитаемые имена коннекторов для живого списка источников в чате.
# Без них фронтенд показывал бы служебные слаги вроде "crtsh_cert_transparency".
SOURCE_LABELS = {
    "site_content": "Текст на сайте — что обещают",
    "rdap_whois": "WHOIS — возраст домена",
    "dns_records": "DNS-записи",
    "crtsh_cert_transparency": "Certificate Transparency — клоны",
    "urlscan_search": "urlscan — история сайта",
    "shodan_internetdb": "Shodan — инфраструктура",
    "common_crawl": "Common Crawl — архив веба",
    "duckduckgo_instant_answer": "DuckDuckGo",
    "searx_metasearch": "Метапоиск SearX",
    "regulator_blacklist_local": "Чёрные списки регуляторов РК",
    "opensanctions_lists": "OpenSanctions — санкции",
    "opencorporates_registry": "OpenCorporates — юрлица",
    "gleif_lei_registry": "GLEIF — LEI-реестр",
    "sec_edgar_registry": "SEC EDGAR",
    "occrp_aleph": "OCCRP Aleph — расследования",
    "blockchain_info_btc": "Blockchain.info — BTC",
    "blockchair_multichain": "Blockchair — мультичейн",
    "etherscan_eth": "Etherscan — ETH",
    "chainabuse_scam_reports": "Chainabuse — жалобы",
    "phone_lookup": "Проверка телефона",
    "onionclaw_darknet_search": "Даркнет-поиск через Tor",
}


def _source_label(name: str) -> str:
    return SOURCE_LABELS.get(name, name.replace("_", " "))


def _tool_label(name: str, tool_input: dict) -> str:
    """Human-readable progress line shown live in the chat bubble."""
    q = (
        tool_input.get("query")
        or tool_input.get("domain")
        or tool_input.get("address")
        or tool_input.get("handle")
        or ""
    )
    labels = {
        "investigate_full": f"Полный прогон «{q}» по всем источникам…",
        "check_whois": f"WHOIS и DNS: {q}…",
        "check_related_domains": f"Certificate Transparency: ищу связанные домены {q}…",
        "check_blacklist": f"Сверяю «{q}» с чёрными списками регуляторов…",
        "check_wallet": f"Блокчейн-анализ кошелька {q}…",
        "check_username": f"Проверяю профили и упоминания: {q}…",
        "search_web": f"Метапоиск: {q}…",
        "search_by_region": f"Ищу пирамиды в регионе «{tool_input.get('region', '')}»…",
        "darknet_browse": f"Обхожу раздел даркнета «{tool_input.get('category', 'cryptocurrency')}» через Tor…",
        "check_recurrence": "Сверяю с прошлыми расследованиями SAQ…",
    }
    return labels.get(name, f"{name}…")


async def run_chat_turn_events(session_id: str, user_message: str, user_id: int | None = None):
    """Async-generator core of the agent turn: yields progress events
    ({"type": "status", "label": str}) while Claude works and tools run,
    then exactly one final {"type": "done", "reply": str,
    "dossier": InvestigateResponse | None}.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        yield {
            "type": "done",
            "reply": (
                "Aqyl сейчас работает без LLM-ключа (ANTHROPIC_API_KEY не задан) — "
                "агентный чат недоступен. Используйте обычную проверку."
            ),
            "dossier": None,
            "suggestions": [],
        }
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    history = _SESSIONS.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    dossier: InvestigateResponse | None = None
    # Все объекты, проверенные за этот ход. Раньше держали только последний,
    # и на запрос «проверь Finiko, Qnet и Crowd1» граф показывал одну Crowd1.
    # Теперь фронтенд получает весь список и строит общий граф, где видно
    # пересечения между объектами (общий кошелёк, домен, IP).
    dossiers: list[InvestigateResponse] = []
    # последний объект, который агент проверял точечными инструментами —
    # страховка на случай, если он так и не вызвал investigate_full
    last_object_query: str | None = None

    for round_no in range(MAX_TOOL_ROUNDS):
        yield {
            "type": "status",
            "label": "Aqyl принимает запрос…" if round_no == 0 else "Aqyl анализирует данные…",
        }
        try:
            # stream вместо create: финальный ответ модель пишет ~18 секунд,
            # и при обычном create всё это время экран не меняется. Со стримом
            # текст появляется по мере генерации (события "delta"), а ждать
            # целиком приходится только ходы с вызовом инструментов.
            streamed_text = ""
            async with client.messages.stream(
                model="claude-sonnet-5",
                # generous budget: a multi-candidate summary (e.g. "check these
                # 7 leads") can run long — 1200 was observed truncating mid-word
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=CHAT_TOOLS,
                messages=history,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        piece = event.delta.text
                        streamed_text += piece
                        # «Подсказки:» — служебный хвост для чипов под ответом,
                        # его пользователю показывать не нужно
                        if "Подсказк" not in streamed_text:
                            yield {"type": "delta", "text": piece}
                response = await stream.get_final_message()
        except anthropic.APIError as exc:
            # An unhandled exception here kills the SSE stream mid-flight —
            # the browser just sees a generic network error with no
            # explanation. Surface what actually happened instead (e.g. "credit
            # balance too low", rate limit, provider outage) as a normal done
            # event, so the chat bubble shows a readable message.
            history.pop()  # drop the user turn we couldn't get a response to
            detail = exc.message
            if isinstance(exc.body, dict):
                detail = exc.body.get("error", {}).get("message", detail)
            yield {
                "type": "done",
                "reply": f"Aqyl не смог связаться с ИИ-провайдером: {detail}",
                "dossier": dossier,
                "dossiers": dossiers,
                "suggestions": [],
            }
            return

        # В историю кладём только те блоки, которые API принимает обратно.
        # get_final_message() у стрима может отдать служебные блоки (thinking),
        # которые при отправке следующим ходом отклоняются с ошибкой
        # "content.0.thinking.text: Extra inputs are not permitted" — и весь
        # диалог обрывается после первого же вызова инструмента.
        replayable = [b for b in response.content if b.type in ("text", "tool_use")]
        history.append({"role": "assistant", "content": replayable or response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            # Агент расследовал объект, но не вызвал investigate_full — без
            # этого фронтенд не получает досье (граф связей + risk gauge
            # остаются пустыми). Догоняем полным прогоном молча.
            if dossier is None and last_object_query:
                yield {"type": "status", "label": "Строю граф связей…"}
                try:
                    fallback = await tool_investigate_full(last_object_query, _user_id=user_id)
                    dossier = fallback.pop("_dossier", None)
                    if dossier is not None:
                        dossiers.append(dossier)
                except Exception:
                    pass
            reply, suggestions = _split_suggestions(final_text)
            yield {
                "type": "done",
                "reply": reply,
                "dossier": dossier,
                "dossiers": dossiers,
                "suggestions": suggestions,
            }
            return

        tool_results_content = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            yield {"type": "status", "label": _tool_label(block.name, block.input)}
            fn = TOOL_DISPATCH.get(block.name)
            if fn is None:
                tool_output: dict[str, Any] = {"error": f"unknown tool {block.name}"}
            else:
                try:
                    kwargs = dict(block.input)
                    if block.name == "investigate_full":
                        kwargs["_user_id"] = user_id
                        # источники отвечают вразнобой — показываем каждый сразу,
                        # а не молчим до последнего
                        queue: asyncio.Queue = asyncio.Queue()

                        async def _progress(done: int, total: int, res, _q=queue):
                            await _q.put(
                                {
                                    "type": "source",
                                    "name": _source_label(res.source),
                                    "ok": bool(res.ok),
                                    "flags": len(res.red_flags or []),
                                    "done": done,
                                    "total": total,
                                }
                            )

                        kwargs["_progress"] = _progress
                        task = asyncio.create_task(fn(**kwargs))
                        while True:
                            get = asyncio.ensure_future(queue.get())
                            done_set, _ = await asyncio.wait(
                                {get, task}, return_when=asyncio.FIRST_COMPLETED
                            )
                            if get in done_set:
                                yield get.result()
                                continue
                            get.cancel()
                            break
                        while not queue.empty():
                            yield queue.get_nowait()
                        tool_output = await task
                    else:
                        tool_output = await fn(**kwargs)
                except Exception as exc:
                    tool_output = {"error": str(exc)}

            if "_dossier" in tool_output:
                dossier = tool_output.pop("_dossier")
                if dossier is not None and not any(
                    d.investigation_id == dossier.investigation_id for d in dossiers
                ):
                    dossiers.append(dossier)
                    # граф и risk-gauge рисуем сразу, не дожидаясь, пока модель
                    # допишет текстовый вывод (это ещё ~18 секунд)
                    yield {
                        "type": "dossier",
                        "dossier": dossier.model_dump(mode="json"),
                    }
            elif block.name not in _NON_OBJECT_TOOLS:
                arg = (
                    block.input.get("query")
                    or block.input.get("domain")
                    or block.input.get("address")
                    or block.input.get("handle")
                )
                if isinstance(arg, str) and arg.strip():
                    last_object_query = arg.strip()

            tool_results_content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(tool_output, ensure_ascii=False, default=str),
                }
            )

        history.append({"role": "user", "content": tool_results_content})

    yield {
        "type": "done",
        "reply": "Слишком много шагов проверки за один ход — уточните вопрос.",
        "dossier": dossier,
        "dossiers": dossiers,
        "suggestions": [],
    }


async def run_chat_turn(
    session_id: str, user_message: str, user_id: int | None = None
) -> tuple[str, InvestigateResponse | None, list[str], list[InvestigateResponse]]:
    """Non-streaming wrapper over run_chat_turn_events for the plain /chat
    endpoint: swallows progress events, returns (final_text, dossier, suggestions).
    """
    async for event in run_chat_turn_events(session_id, user_message, user_id):
        if event["type"] == "done":
            return (
                event["reply"],
                event["dossier"],
                event.get("suggestions", []),
                event.get("dossiers", []),
            )
    return "Внутренняя ошибка чата.", None, [], []
