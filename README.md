# Career Radar

A daily-refreshed international job board for data professionals — Data Engineers,
Data Scientists, GenAI/AI/ML Engineers, Data Analysts, and data/AI Product Managers
with ~4+ years of experience.

Live site: `https://prudhvikollads-source.github.io/career-radar/web/`

## What it does

- Pulls live postings from **public** company job boards via the Greenhouse
  (`boards-api.greenhouse.io`) and Lever (`api.lever.co`) APIs. No API keys,
  no login, no scraping of private pages.
- Keeps only titles matching the target profiles and maps each posting to one
  of 9 countries: India, United Kingdom, UAE, Saudi Arabia, Kuwait,
  Canada, Netherlands, New Zealand, Poland. Everything else is dropped
  (USA excluded by design).
- Flags every job against a **savings goal**: save **₹5 lakhs/month** after
  taxes and living costs. Per-country annual gross thresholds used for the
  "Meets savings goal" badge:

| Country | Threshold (annual, local) |
|---|---|
| India | INR 9,500,000 |
| United Kingdom | GBP 128,000 |
| UAE | AED 420,000 |
| Saudi Arabia | SAR 370,000 |
| Kuwait | KWD 29,000 |
| Canada | CAD 190,000 |
| Netherlands | EUR 128,000 |
| New Zealand | NZD 225,000 |
| Poland | PLN 660,000 |

- Salary figures are mined from posting text and pay-transparency blocks,
  annualized, and converted to the job's local currency at the day's FX rate
  (via `open.er-api.com`, with a hardcoded fallback table).
- Sponsorship flags come from a heuristic text scan of each posting
  ("visa sponsorship", "will sponsor", "no sponsorship"). **Always confirm in
  the actual posting** — the flag is a signal, not a guarantee.
- Posted times are relative ("3 hours ago") and recompute live in the browser.

## Repository layout

```
career-radar/
├── etl/
│   └── fetch_jobs.py        # the daily ETL: boards -> web/data/jobs.json
├── web/
│   ├── index.html           # single-page frontend (no frameworks, no build)
│   ├── app.js
│   ├── styles.css
│   └── data/
│       └── jobs.json        # generated daily; compact, one file
└── .github/workflows/
    └── etl.yml              # daily cron: run ETL, commit jobs.json
```

## Refresh cadence

The GitHub Action runs `etl/fetch_jobs.py` daily (~06:30 UTC) and commits the
fresh `web/data/jobs.json`. The page header shows "listings refreshed X ago"
from the embedded timestamp. A manual run is available via *workflow_dispatch*.

**Freshness policy:** postings older than 60 days are dropped. Stale listings
are usually already filled, and keeping them drowns out real openings.

**Note:** GitHub does not accept workflow files pushed through the API, so
`.github/workflows/etl.yml` must be added once via the GitHub web UI
(repo → Add file → Upload files). Everything else can be pushed via API.

## Running the ETL locally

```bash
pip install requests
python3 etl/fetch_jobs.py
# serves the site locally:
cd web && python3 -m http.server 8000
# open http://localhost:8000/
```

## Limitations (read before trusting a badge)

- Salary mining is best-effort: only ~65% of postings disclose pay. "Salary not
  disclosed" is common and says nothing about the actual pay.
- Currency conversion uses a daily FX snapshot; thresholds are estimates, not
  financial advice. The Netherlands figure assumes 30% ruling eligibility.
- Sponsorship detection is keyword-based and misses nuance.
- Remote roles without a stated country are excluded; multi-location postings
  use the first listed location.
- Board coverage reflects which companies publish public ATS boards — Gulf and
  NZ markets are thin on these APIs, so low counts there are a coverage gap,
  not proof of no hiring.
- Postings can close or change between refreshes; the apply link is the source
  of truth.
