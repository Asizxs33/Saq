# -*- coding: utf-8 -*-
"""Валидация пайплайна на списке пирамид АФМ РК.

Прогоняет каждую организацию из data/blacklists/afm_kz_pyramids.json через
полный investigate() и считает два скора:

  - full_score      — штатный режим (все коннекторы, включая локальный
                      чёрный список, в котором эти же имена и лежат);
  - external_score  — тот же прогон, но с исключёнными из подсчёта
                      результатами regulator_blacklist_local: сколько риска
                      набирается ТОЛЬКО по внешним независимым источникам.
                      Это честная метрика "нашла бы система пирамиду,
                      не зная списка АФМ".

Результаты пишутся инкрементально в data/validation/afm_validation.json,
итоговая сводка — в data/validation/afm_validation_report.md.

Запуск из корня проекта:  .venv/Scripts/python scripts/validate_afm.py
"""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.models import QueryType
from app.orchestrator import _score_risk, investigate

BLACKLIST = ROOT / "data" / "blacklists" / "afm_kz_pyramids.json"
OUT_DIR = ROOT / "data" / "validation"
OUT_JSON = OUT_DIR / "afm_validation.json"
OUT_MD = OUT_DIR / "afm_validation_report.md"

CONCURRENCY = 3
THRESHOLD = 30  # порог "система подняла тревогу" (min_score дефолта watchlist)


async def check_one(sem: asyncio.Semaphore, name: str, note: str) -> dict:
    async with sem:
        try:
            _, qtype, connectors_run, results, full_score, full_flags, _, _ = await investigate(
                name, QueryType.NAME_OR_ORG, synthesize=False
            )
        except Exception as exc:
            return {"name": name, "note": note, "error": str(exc)}

    external_results = [r for r in results if r.source != "regulator_blacklist_local"]
    external_score, external_flags = _score_risk(external_results, [])

    ok_sources = [r.source for r in results if r.ok]
    return {
        "name": name,
        "note": note,
        "full_score": full_score,
        "full_flags": full_flags,
        "external_score": external_score,
        "external_flags": external_flags,
        "connectors_ok": len(ok_sources),
        "connectors_run": len(connectors_run),
    }


async def main() -> None:
    entries = json.loads(BLACKLIST.read_text(encoding="utf-8"))["entries"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    rows: list[dict] = []
    tasks = [check_one(sem, e["name"], e.get("note", "")) for e in entries]
    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        row = await coro
        rows.append(row)
        print(f"[{i}/{len(tasks)}] {row['name']}: "
              f"full={row.get('full_score', '-')} ext={row.get('external_score', '-')}"
              + (f" ERROR: {row['error']}" if "error" in row else ""))
        OUT_JSON.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    scored = [r for r in rows if "error" not in r]
    n = len(scored)
    full_hits = sum(1 for r in scored if r["full_score"] >= THRESHOLD)
    ext_hits = sum(1 for r in scored if r["external_score"] >= THRESHOLD)
    ext_any = sum(1 for r in scored if r["external_flags"])

    def pct(x: int) -> str:
        return f"{x}/{n} ({x / n * 100:.0f}%)" if n else "0/0"

    lines = [
        "# Валидация SAQ на списке пирамид АФМ РК",
        "",
        f"Дата прогона: {date.today().isoformat()}. Источник эталона: "
        f"`data/blacklists/afm_kz_pyramids.json` ({len(entries)} организаций, "
        "статусы от досудебного расследования до вынесенного приговора).",
        "",
        f"Порог тревоги: risk score >= {THRESHOLD}.",
        "",
        "| Метрика | Результат |",
        "|---|---|",
        f"| Полный пайплайн поднял тревогу | {pct(full_hits)} |",
        f"| Только внешние источники (без чёрного списка АФМ) — тревога | {pct(ext_hits)} |",
        f"| Внешние источники дали хотя бы один красный флаг | {pct(ext_any)} |",
        f"| Ошибок прогона | {len(rows) - n} |",
        "",
        "`external_score` — риск, набранный без учёта локального чёрного списка "
        "регулятора: показывает, что система находит независимые подтверждения "
        "(поисковая выдача, архивы, скам-отчёты), а не просто сверяется со своим же файлом.",
        "",
        "## По организациям",
        "",
        "| Организация | Полный скор | Внешний скор | Внешние флаги |",
        "|---|---|---|---|",
    ]
    for r in sorted(scored, key=lambda x: -x["external_score"]):
        lines.append(
            f"| {r['name']} | {r['full_score']} | {r['external_score']} | "
            f"{', '.join(r['external_flags']) or '—'} |"
        )
    errors = [r for r in rows if "error" in r]
    if errors:
        lines += ["", "## Ошибки", ""]
        lines += [f"- {r['name']}: {r['error']}" for r in errors]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nГотово: {OUT_JSON}\n        {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())
