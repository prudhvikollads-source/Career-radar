#!/usr/bin/env python3
"""Career Radar India ETL -- attempts Naukri.com (naukri.com) for data/AI roles
in 8 Indian cities.

Keyless. Run:  python3 etl/fetch_india_jobs.py
Output: web/india/jobs.json  (same compact schema as web/data/jobs.json)

STATUS (verified 2026-10-13): naukri.com blocks keyless automated access.
  - Search pages return HTTP 200 but are client-rendered Next.js shells with
    zero job data in the HTML (jobs load via XHR after page load).
  - The internal jobapi/v3/search endpoint returns 406 "recaptcha required"
    even with the correct appid/systemid headers (109, as embedded in the
    site's own JS). Without appid it returns 400.
  - Legacy RSS endpoints redirect to the search page.

The script still attempts a small number of API calls each run (in case the
source ever unblocks), then writes a valid jobs.json with meta.error set, so
the page shows an honest "source unavailable" state -- never fabricated
listings. The main feed already covers India via public ATS boards.

If the source is unreachable the script still writes a valid jobs.json with
meta.error set, so the page shows an honest "source unavailable" state --
never fabricated listings.
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, "etl")
from fetch_jobs import (  # noqa: E402  (reuse: title filter, sponsorship, FX)
    title_match,
    sponsorship_signal,
    get_rates,
    to_local,
)

BASE = "https://www.naukri.com"
API = BASE + "/jobapi/v3/search"

# Small bounded attempt set: keyword + city. If the API ever unblocks, this
# is enough to seed the feed; the hourly schedule keeps it fresh.
SEARCHES = [
    ("data engineer", "bangalore"),
    ("data scientist", "bangalore"),
    ("machine learning engineer", "hyderabad"),
    ("data analyst", "mumbai"),
    ("ai engineer", "delhi"),
]
NO_OF_RESULTS = 20
TIMEOUT = 20

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/",
    # appid 109 is what naukri.com's own JS sends; still 406s for bots.
    "appid": "109",
    "systemid": "109",
}

CITIES = ["Bengaluru", "Hyderabad", "Mumbai", "Delhi NCR", "Chennai",
          "Pune", "Kolkata", "Ahmedabad"]
CITY_SLUGS = {"bengaluru": "Bengaluru", "bangalore": "Bengaluru",
              "hyderabad": "Hyderabad", "mumbai": "Mumbai", "bombay": "Mumbai",
              "delhi": "Delhi NCR", "new delhi": "Delhi NCR", "noida": "Delhi NCR",
              "gurgaon": "Delhi NCR", "gurugram": "Delhi NCR",
              "chennai": "Chennai", "pune": "Pune", "kolkata": "Kolkata",
              "calcutta": "Kolkata", "ahmedabad": "Ahmedabad"}

INDIA_THRESHOLD = 9500000  # INR/year for the Rs.5L/month savings badge

ERROR_NOTE = ("Naukri.com blocks automated access (its jobs API answers "
              "'recaptcha required' to keyless requests and search pages "
              "carry no job data in HTML). India roles are still covered "
              "on the main feed via public ATS boards.")


def map_city(loc):
    if not loc:
        return None
    s = loc.lower()
    for slug, city in CITY_SLUGS.items():
        if slug in s:
            return city
    return None


def parse_salary_lpa(text):
    """Naukri shows '10-20 Lacs PA'. Return (lo, hi) annual INR or None."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(lacs?|lakhs?)",
                  text, re.I)
    if m:
        return (float(m.group(1)) * 100000, float(m.group(2)) * 100000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lacs?|lakhs?)\s*pa", text, re.I)
    if m:
        v = float(m.group(1)) * 100000
        return (v, v)
    return None


def try_api(session):
    """One bounded pass over SEARCHES. Returns (jobs, blocked_reason)."""
    jobs = []
    blocked = None
    for keyword, city in SEARCHES:
        params = {"noOfResults": NO_OF_RESULTS, "urlType": "search_by_keyword",
                  "searchType": "adv", "k": keyword, "l": city, "pageNo": 1}
        try:
            r = session.get(API, params=params, timeout=TIMEOUT)
        except Exception as e:
            blocked = f"request failed ({type(e).__name__})"
            break
        if r.status_code == 406:
            blocked = "API requires recaptcha (HTTP 406)"
            break
        if r.status_code != 200:
            blocked = f"API HTTP {r.status_code}"
            break
        try:
            data = r.json()
        except Exception:
            blocked = "API returned non-JSON"
            break
        for j in (data.get("jobDetails") or []):
            title = j.get("title", "")
            if not title_match(title):
                continue
            loc = j.get("placeholders", [{}])[0].get("label", "") \
                if j.get("placeholders") else j.get("location", "")
            mapped = map_city(loc)
            if not mapped:
                continue
            jobs.append({
                "title": title[:120],
                "company": (j.get("companyName") or "")[:60],
                "city": mapped,
                "salary_text": j.get("placeholders", [{}])[1].get("label", "")
                if len(j.get("placeholders") or []) > 1 else "",
                "posted": j.get("footerPlaceholderLabel", ""),
                "url": BASE + (j.get("jdURL") or ""),
            })
        time.sleep(2)
    return jobs, blocked


def parse_posted_age(text, now):
    """Naukri footer labels like '2 Days Ago', 'Today', 'Few Hours Ago'."""
    if not text:
        return None
    s = text.lower()
    if "hour" in s or "today" in s or "few" in s or "just" in s:
        return now
    m = re.search(r"(\d+)\s*day", s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*week", s)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    m = re.search(r"(\d+)\s*month", s)
    if m:
        return now - timedelta(days=30 * int(m.group(1)))
    return None


def main():
    now = datetime.now(timezone.utc)
    session = requests.Session()
    session.headers.update(UA)

    raw, blocked = try_api(session)

    jobs = []
    if raw:
        rates = get_rates()
        for c in raw:
            pub_dt = parse_posted_age(c["posted"], now)
            if pub_dt is not None and now - pub_dt > timedelta(days=60):
                continue  # same 60-day freshness rule as the main feed
            pub_iso = pub_dt.astimezone(timezone.utc).isoformat() \
                if pub_dt else None
            sal = parse_salary_lpa(c["salary_text"])
            smin = smax = goal = None
            if sal:
                lo, hi = sal
                smin, smax = round(lo), round(hi)
                goal = ((smin + smax) / 2) >= INDIA_THRESHOLD
            jobs.append({
                "t": c["title"], "co": c["company"], "city": c["city"],
                "country": "India", "cur": "INR",
                "smin": smin, "smax": smax, "goal": goal,
                "spon": "unknown",  # India: no sponsorship needed
                "pub": pub_iso, "url": c["url"],
            })
        jobs.sort(key=lambda j: j["pub"] or "", reverse=True)

    meta = {
        "refreshed_at": now.isoformat(),
        "source": "naukri.com",
        "total": len(jobs),
        "thresholds": {"India": INDIA_THRESHOLD},
        "cities": CITIES,
        "status": "blocked" if blocked else "ok",
    }
    if blocked and not jobs:
        # Fallback: serve India jobs from the main ATS feed so the page
        # stays useful while naukri.com blocks automated access. The main
        # ETL runs first in the hourly workflow, so this data is fresh.
        try:
            with open("web/data/jobs.json") as f:
                main_feed = json.load(f)
            for j in main_feed.get("jobs", []):
                if j.get("country") == "India":
                    jobs.append(j)
            jobs.sort(key=lambda j: j["pub"] or "", reverse=True)
            if jobs:
                meta["warning"] = (
                    "naukri.com blocks automated access -- showing India "
                    "jobs from the main ATS feed instead")
                meta["total"] = len(jobs)
                # error cleared: page shows real jobs, not an empty state
            else:
                meta["error"] = ERROR_NOTE
        except Exception:
            meta["error"] = ERROR_NOTE
    elif blocked:
        meta["warning"] = blocked + " -- showing cached/partial results"

    out = {"jobs": jobs, "meta": meta}
    with open("web/india/jobs.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {len(jobs)} India jobs "
          f"({'blocked: ' + blocked if blocked else 'ok'})")


if __name__ == "__main__":
    main()
