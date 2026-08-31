"use strict";
/**
 * Детектор подозрительного текста — портирован из Python-версии
 * (guardian/guardian_app.py), логика и паттерны 1-в-1, только синтаксис JS.
 */

const DOMAIN_RE = /\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b/gi;
const PHONE_RE = /(?<!\d)(\+?\d[\d\-\s()]{7,16}\d)(?!\d)/g;

const PYRAMID_KEYWORDS = [
  "гарантированный доход",
  "гарантированная прибыль",
  "x2 за неделю",
  "удвоим ваш",
  "пассивный доход от",
  "инвестируй сегодня",
  "приведи друга и получи",
  "быстрый заработок без вложений",
];

// точные фразы ловят мало — реальное сообщение мошенника («вложите 50 000,
// через неделю получите 300% прибыли, не рассказывайте никому») ни одной
// из PYRAMID_KEYWORDS не поймало. Паттерны ловят СТРУКТУРУ развода.
const PYRAMID_PATTERNS = [
  [/\d{2,4}\s?%.{0,25}(прибыл|доход|дней|недел|месяц)/i, "обещание конкретного % прибыли за срок"],
  [/(вложите?|инвестируй|переведите).{0,40}(получите|заработа|прибыл)/i, "схема «вложи сейчас → получи потом»"],
  [/(количество мест|осталось \d+ мест|только сегодня|акция закан)/i, "искусственная срочность/ограниченность"],
  [/(не рассказывайте|никому не говор|держите в тайне)/i, "просьба скрывать предложение от других"],
  [/(вы (были )?выбраны|эксклюзивн(ая|ое) (программ|предложени|возможност)|избранн)/i, "фальшивая эксклюзивность «вас выбрали»"],
  [/приведи? друга.{0,20}(получ|бонус|%)/i, "реферальная вербовка"],
];

// отдельная категория — не «пирамида», а азартные игры/казино-контент.
// Другой тип риска (финансовый/психологический, часто нацелен на несовершеннолетних
// через стримы), поэтому размечаем отдельным kind и даём другой совет в UI.
const CASINO_KEYWORDS = [
  "gates of olympus", "sweet bonanza", "book of ra", "sugar rush",
  "фриспины", "фри спины", "бонус на депозит", "промокод на казино",
  "выбил миллион", "занос недели", "слот-машина", "джекпот казино",
];
const CASINO_PATTERNS = [
  [/(казино|слот|автомат).{0,25}(депозит|ставк|выигрыш|занос)/i, "реклама онлайн-казино/ставок"],
  [/(выбил|занёс|сорвал).{0,20}(миллион|тысяч|\d{3,}\s?[₽р$])/i, "демонстрация «выигрыша» — приманка для зрителя"],
];

const DOMAIN_IGNORE_SUFFIXES = [
  "microsoft.com", "windows.com", "google.com", "gstatic.com",
  "localhost", "vercel.app",
];

// без этого списка «домен» ловится в любом имени файла (ui.html, test.txt) —
// проверено вживую, реестр забивался хламом из OCR-мусора
const VALID_TLDS = new Set([
  "com", "net", "org", "info", "biz", "io", "co", "app", "dev", "ai", "me",
  "shop", "site", "online", "store", "club", "top", "xyz", "pro", "cc", "tv",
  "kz", "ru", "ua", "by", "uz", "kg", "tj", "az", "ge", "am", "md",
  "tr", "cn", "in", "de", "fr", "uk", "eu", "pl", "cz", "lv", "lt", "ee",
  "su", "рф", "қаз", "onion",
]);

/** Возвращает [{value, kind}], kind ∈ 'domain' | 'phone' | 'phrase'. */
function extractCandidates(text) {
  const out = [];
  const lower = text.toLowerCase();

  for (const m of text.matchAll(DOMAIN_RE)) {
    const d = m[0].toLowerCase();
    const tld = d.split(".").pop();
    if (!VALID_TLDS.has(tld)) continue; // имя файла или мусор OCR
    if (!DOMAIN_IGNORE_SUFFIXES.some((s) => d === s || d.endsWith("." + s))) {
      out.push({ value: d, kind: "domain" });
    }
  }

  for (const m of text.matchAll(PHONE_RE)) {
    const raw = m[0].trim();
    const digits = raw.replace(/\D/g, "");
    // настоящий номер: 10-13 цифр И ведущая 7/8 — иначе случайный забег
    // цифр вроде risk-score, попавшего в кадр
    if (digits.length >= 10 && digits.length <= 13 && (digits[0] === "7" || digits[0] === "8")) {
      out.push({ value: raw, kind: "phone" });
    }
  }

  for (const kw of PYRAMID_KEYWORDS) {
    if (lower.includes(kw)) out.push({ value: kw, kind: "phrase" });
  }

  for (const [rex, label] of PYRAMID_PATTERNS) {
    const m = text.match(rex);
    if (m) {
      let snippet = m[0].trim();
      if (snippet.length > 80) snippet = snippet.slice(0, 80) + "…";
      out.push({ value: `${snippet} (${label})`, kind: "phrase" });
    }
  }

  for (const kw of CASINO_KEYWORDS) {
    if (lower.includes(kw)) out.push({ value: kw, kind: "casino" });
  }
  for (const [rex, label] of CASINO_PATTERNS) {
    const m = text.match(rex);
    if (m) {
      let snippet = m[0].trim();
      if (snippet.length > 80) snippet = snippet.slice(0, 80) + "…";
      out.push({ value: `${snippet} (${label})`, kind: "casino" });
    }
  }

  return out;
}

module.exports = { extractCandidates };
