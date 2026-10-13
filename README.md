# Career Radar

An hourly-refreshed international job board for data professionals — Data Engineers,
Data Scientists, GenAI/AI/ML Engineers, Data Analysts, and data/AI Product Managers
with ~4+ years of experience.

Live site: `https://prudhvikollads-source.github.io/career-radar/web/`
Gulf portal: `https://prudhvikollads-source.github.io/career-radar/web/gulf/`
India portal: `https://prudhvikollads-source.github.io/career-radar/web/india/`

## What it does

- Pulls live postings from **public** company job boards via the Greenhouse
  (`boards-api.greenhouse.io`) and Lever (`api.lever.co`) APIs. No API keys,
  no login, no scraping of private pages.
- Keeps only titles matching the target profiles and maps each posting to one
  of 9 countries: India, United Kingdom, UAE, Saudi Arabia, Kuwait,
  Canada, Netherlands, New Zealand, Poland. Everything else is dropped
  (USA excluded by design).
- A separate **Gulf portal** (`/web/gulf/`) scrapes **NaukriGulf**
  (naukrigulf.com) public search pages for the same profiles across the
  6 Gulf countries: UAE, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman —
  with Gulf-specific savings thresholds:

| Country | Threshold (annual, local) |
|---|---|
| UAE | AED 420,000 |
| Saudi Arabia | SAR 370,000 |
| Qatar | QAR 348,000 |
| Kuwait | KWD 29,000 |
| Bahrain | BHD 34,000 |
| Oman | OMR 35,000 |
- A separate **India portal** (`/web/india/`) attempts **Naukri.com**
  (naukri.com) for the same profiles across 8 Indian cities: Bengaluru,
  Hyderabad, Mumbai, Delhi NCR, Chennai, Pune, Kolkata, Ahmedabad.
  **Status: blocked** — Naukri.com's jobs API answers "recaptcha required"
  to keyless requests and its search pages carry no job data in HTML, so
  the portal shows an honest "temporarily unavailable" state. India roles
  remain covered on the main feed via public ATS boards. The scraper
  re-tries each run in case the source ever unblocks.
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
│   ├── fetch_jobs.py        # main ETL: ATS boards -> web/data/jobs.json
│   ├── fetch_gulf_jobs.py   # Gulf ETL: NaukriGulf search pages -> web/gulf/jobs.json
│   └── fetch_india_jobs.py  # India ETL: Naukri.com API attempt -> web/india/jobs.json
├── web/
│   ├── index.html           # single-page frontend (no frameworks, no build)
│   ├── app.js
│   ├── styles.css
│   ├── data/
│   │   └── jobs.json        # generated hourly; compact, one file
│   ├── gulf/
│   │   ├── index.html       # Gulf portal frontend
│   │   ├── app.js
│   │   └── jobs.json        # generated hourly; compact, one file
│   └── india/
│       ├── index.html       # India portal frontend
│       ├── app.js
│       └── jobs.json        # generated hourly; compact, one file
└── .github/workflows/
    └── etl.yml              # hourly cron: run all ETLs, commit jobs.json files
```

## Refresh cadence

The GitHub Action runs all three ETLs hourly (minute 0, UTC) and commits the
fresh `web/data/jobs.json`, `web/gulf/jobs.json`, and `web/india/jobs.json`.
Each page header shows "listings refreshed X ago" from the embedded timestamp.
A manual run is available via *workflow_dispatch*.

**Freshness policy:** postings older than 60 days are dropped on all feeds.
Stale listings are usually already filled, and keeping them drowns out real
openings.

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

- Salary mining is best-effort: only ~65% of ATS postings disclose pay, and
  NaukriGulf cards rarely show salaries at all. "Salary not disclosed" is
  common and says nothing about the actual pay.
- Currency conversion uses a daily FX snapshot; thresholds are estimates, not
  financial advice. The Netherlands figure assumes 30% ruling eligibility.
- Sponsorship detection is keyword-based and misses nuance. Most Gulf
  employers sponsor work visas by default — always confirm in the posting.
- Remote roles without a stated country are excluded; multi-location postings
  map to the first target-country location found (e.g. "Dublin, Ireland;
  London, England" counts as United Kingdom).
- Board coverage reflects which companies publish public ATS boards — Gulf and
  NZ markets are thin on these APIs. The Gulf portal exists precisely to
  cover that gap via NaukriGulf.
- NaukriGulf scraping is polite (browser UA, ~2.5s between requests, one pass
  per run) but the site may throttle datacenter IPs; if a refresh can't reach
  it, the Gulf page shows an honest "temporarily unavailable" state instead
  of stale or fabricated listings.
- **Naukri.com (India portal) is currently blocked**: its jobs API requires
  recaptcha for keyless requests and search pages embed no job data. The
  portal shows an honest unavailable state and re-tries hourly; India roles
  are covered on the main feed via public ATS boards in the meantime.
- Postings can close or change between refreshes; the apply link is the source
  of truth.
