# Regulator blacklists

Drop JSON files here, one per regulator, shaped like:

```json
{
  "regulator": "CBR (Bank of Russia) — unlicensed financial market participants",
  "source_url": "https://www.cbr.ru/inside/warning-list/",
  "updated": "2026-06-01",
  "entries": [
    {"name": "Example Invest LLC", "domains": ["example-invest.example"], "note": "unlicensed forex"}
  ]
}
```

These regulator pages generally block naive scraping or change markup
often, so this loader intentionally reads from a local, manually/
periodically refreshed snapshot rather than live-scraping on every
request. Update the files on a schedule (e.g. a weekly cron job you
control) instead of hitting the regulator site per investigation.
