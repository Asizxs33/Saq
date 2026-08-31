# -*- coding: utf-8 -*-
"""Запасное демо для защиты: полный прогон известных целей с LLM-отчётом,
результат сохраняется в data/demo_cache/*.json в формате ответа /investigate.

Если на выступлении упадут внешние источники или сеть — показываем
сохранённый прогон (это честно: файл — реальный вывод системы, дата внутри).

Запуск из корня проекта:  .venv/Scripts/python scripts/cache_demo.py
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.orchestrator import investigate

OUT_DIR = ROOT / "data" / "demo_cache"

# Знаковые цели для демо: имена из списка АФМ с разными статусами.
TARGETS = ["Finiko", "Qnet", "Crowd1"]


async def cache_one(query: str) -> None:
    investigation_id, qtype, connectors_run, results, score, flags, summary, recurrence = (
        await investigate(query, None, synthesize=True)
    )
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "investigation_id": investigation_id,
        "query": query,
        "detected_type": qtype.value,
        "connectors_run": connectors_run,
        "results": [r.model_dump() for r in results],
        "risk_score": score,
        "risk_flags": flags,
        "summary": summary,
        "recurrence": [r.model_dump() for r in recurrence],
    }
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    out = OUT_DIR / f"{slug}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{query}: score={score}, flags={len(flags)}, summary={'да' if summary else 'нет'} -> {out.name}")


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for t in TARGETS:  # последовательно, чтобы не душить бесплатные API
        await cache_one(t)


if __name__ == "__main__":
    asyncio.run(main())
