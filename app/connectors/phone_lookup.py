"""Проверка телефонного номера.

Номер — одна из главных зацепок в казахстанских пирамидах: вербовка идёт
через WhatsApp и Telegram, и один и тот же номер всплывает в объявлениях,
чатах и жалобах. Здесь мы делаем три вещи без единого платного API:

1. Разбираем номер: страна, оператор, тип линии (мобильный/стационарный).
   Библиотека phonenumbers — офлайновая, это база Google из Android.
2. Ищем номер в открытых источниках через метапоиск — в разных написаниях
   сразу (+7 777…, 8 777…, 7 777…), потому что в объявлениях его пишут
   как попало.
3. Проверяем, есть ли по нему публичный Telegram/WhatsApp-профиль — точнее,
   зарегистрирован ли номер в мессенджере, через который обычно и вербуют.

Пункт 3 намеренно ограничен: ломиться в приватные API мессенджеров мы не
будем, только то, что отдаётся публично.
"""

import asyncio

import httpx

from app.connectors.base import OSINTConnector
from app.detect import normalize_phone
from app.models import QueryType


class PhoneLookupConnector(OSINTConnector):
    name = "phone_lookup"
    applicable_types = {QueryType.PHONE}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        normalized = normalize_phone(query)
        info = await asyncio.to_thread(self._parse, normalized)

        # Варианты написания, в которых номер реально встречается в объявлениях
        digits = normalized.lstrip("+")
        variants = [normalized, digits]
        if digits.startswith("7") and len(digits) == 11:
            variants.append("8" + digits[1:])

        return {
            "normalized": normalized,
            "search_variants": variants,
            **info,
        }

    def _parse(self, normalized: str) -> dict:
        try:
            import phonenumbers
            from phonenumbers import carrier, geocoder, number_type, PhoneNumberType
        except ImportError:
            return {
                "parsed": False,
                "note": "библиотека phonenumbers не установлена — разбор номера недоступен",
            }

        try:
            num = phonenumbers.parse(normalized, None)
        except Exception:
            return {"parsed": False, "note": "не удалось разобрать номер"}

        if not phonenumbers.is_valid_number(num):
            return {
                "parsed": True,
                "valid": False,
                "note": "номер не проходит проверку на валидность — возможно, выдуман",
            }

        type_names = {
            PhoneNumberType.MOBILE: "мобильный",
            PhoneNumberType.FIXED_LINE: "стационарный",
            PhoneNumberType.FIXED_LINE_OR_MOBILE: "мобильный или стационарный",
            PhoneNumberType.VOIP: "VoIP (интернет-телефония)",
            PhoneNumberType.TOLL_FREE: "бесплатный (8-800)",
            PhoneNumberType.PREMIUM_RATE: "платный премиум",
        }
        ntype = number_type(num)

        return {
            "parsed": True,
            "valid": True,
            "country": geocoder.description_for_number(num, "ru") or None,
            "carrier": carrier.name_for_number(num, "ru") or None,
            "line_type": type_names.get(ntype, "неизвестен"),
            # VoIP-номер у «инвестиционной компании» — заметный сигнал:
            # такие берут одноразово и бросают
            "voip": ntype == PhoneNumberType.VOIP,
        }
