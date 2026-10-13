#!/usr/bin/env python3
"""Career Radar Gulf ETL -- scrapes NaukriGulf (naukrigulf.com) public search
pages for data/AI roles in the 6 Gulf countries.

Keyless. Run:  python3 etl/fetch_gulf_jobs.py
Output: web/gulf/jobs.json  (same compact schema as web/data/jobs.json)

How it works:
  1. Fetch keyword search pages (server-rendered HTML) with a browser UA,
     polite delays, timeouts and retries.
  2. Parse job cards. Primary strategy: JSON-LD JobPosting blocks (class
     independent). Fallback: text-pattern parsing of card text -- every card
     carries a distinctive "- X - Y Years" experience line, a "- City -
     Country" location line and a posting-date line, which anchors extraction
     without depending on exact CSS classes.
  3. Filter titles (shared title_match), map to 6 Gulf countries, drop
     postings older than 60 days (same freshness rule as the main feed).

If the source is unreachable the script still writes a valid jobs.json with
meta.error set, so the page shows an honest "source unavailable" state --
never fabricated listings.
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

sys.path.insert(0, "etl")
from fetch_jobs import (  # noqa: E402  (reuse: title filter, sponsorship, FX)
    title_match,
    sponsorship_signal,
    get_rates,
    to_local,
)

BASE = "https://www.naukrigulf.com"
SEARCHES = [
    "data-engineer-jobs",
    "data-scientist-jobs",
    "data-analyst-jobs",
    "machine-learning-jobs",
    "artificial-intelligence-jobs",
]
MAX_PAGES = 5
REQUEST_DELAY = 2.5   # polite pause between page fetches
TIMEOUT = 25
RETRIES = 2           # keep the hourly run under ~5 min even if throttled

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

GULF_COUNTRIES = ["UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"]
GULF_CURRENCY = {"UAE": "AED", "Saudi Arabia": "SAR", "Qatar": "QAR",
                 "Kuwait": "KWD", "Bahrain": "BHD", "Oman": "OMR"}
# Annual gross salary in local currency at/above which the INR 5L/month
# post-tax-and-expenses savings goal is considered met.
GULF_THRESHOLDS = {"UAE": 420000, "Saudi Arabia": 370000, "Kuwait": 29000,
                   "Qatar": 348000, "Bahrain": 34000, "Oman": 35000}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

# Extra per-USD rates for Gulf currencies not in the main ETL fallback table
# (BHD and OMR are USD-pegged).
EXTRA_RATES = {"BHD": 0.376, "QAR": 3.64, "OMR": 0.3845, "KWD": 0.311015,
               "SAR": 3.75, "AED": 3.6725}

CHROME_PATTERNS = [
    r"^modify search$", r"^filter jobs by", r"^send me jobs", r"^share jobs$",
    r"^login/register$", r"^get personalised", r"^showing \d+$",
    r"^your alert will be created", r"^please enter a valid",
]


def looks_like_chrome(s):
    return any(re.search(p, s, re.I) for p in CHROME_PATTERNS)


# ------------------------------------------------------------ fetching ---

def fetch(url, session):
    """GET with retries and backoff. Returns text or None."""
    for attempt in range(RETRIES):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
            print(f"  HTTP {r.status_code} for {url}")
            if r.status_code in (404, 410):
                return None  # invalid slug -- skip quietly
        except Exception as e:
            print(f"  attempt {attempt + 1} failed for {url}: "
                  f"{type(e).__name__}")
        time.sleep(2 * (attempt + 1))
    return None


# ------------------------------------------------------------- parsing ---

class _BlockText(HTMLParser):
    """Extract page text preserving block structure as lines (stdlib only)."""

    BLOCKS = {"div", "p", "li", "h1", "h2", "h3", "h4", "article",
              "section", "tr", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.buf = []

    def _flush(self):
        s = " ".join(self.buf).strip()
        if s:
            self.lines.append(s)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._flush()

    def handle_data(self, d):
        d = d.strip()
        if d:
            self.buf.append(d)

    def text_lines(self):
        self._flush()
        return self.lines


class _AnchorMap(HTMLParser):
    """Map anchor text -> href for job-title link resolution."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            t = " ".join(self._buf).strip()
            if t:
                self.links.append((t, self._href))
            self._href = None

    def handle_data(self, d):
        if self._href is not None:
            d = d.strip()
            if d:
                self._buf.append(d)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_jsonld(html):
    """Extract JobPosting entries from JSON-LD blocks. Returns list of dicts."""
    jobs = []
    for m in re.finditer(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        # unwrap @graph
        flat = []
        for it in items:
            if isinstance(it, dict) and "@graph" in it:
                g = it["@graph"]
                flat.extend(g if isinstance(g, list) else [g])
            else:
                flat.append(it)
        for it in flat:
            if not isinstance(it, dict):
                continue
            t = it.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if not any("JobPosting" in str(x) for x in types):
                continue
            org = it.get("hiringOrganization") or {}
            loc = it.get("jobLocation") or {}
            addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
            jobs.append({
                "title": it.get("title", ""),
                "company": org.get("name", "") if isinstance(org, dict) else "",
                "loc": " - ".join(x for x in [
                    addr.get("addressLocality", ""),
                    addr.get("addressCountry", "")] if x),
                "pub": it.get("datePosted", ""),
                "url": it.get("url", ""),
                "desc": it.get("description", ""),
            })
    return jobs


EXP_RE = re.compile(r"^-\s*(\d+)\s*-\s*(\d+)\s*years?$", re.I)
LOC_RE = re.compile(r"^-\s*(.+)$")
DATE_RES = [
    (re.compile(r"(\d+)\s*(?:hrs?|hours?)\s*ago", re.I), "hours"),
    (re.compile(r"(\d+)\s*(?:mins?|minutes?)\s*ago", re.I), "minutes"),
    (re.compile(r"(\d+)\+?\s*days?\s*ago", re.I), "days"),
    (re.compile(r"\b(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I), "daymonth"),
]


def parse_relative_date(s, now):
    """Parse NaukriGulf date strings ('14 Sep', '10 hrs ago', '30+ days ago',
    'Employer Active 14 Sep') into a timezone-aware datetime. Returns None."""
    if not s:
        return None
    for pat, kind in DATE_RES:
        m = pat.search(s)
        if not m:
            continue
        if kind == "hours":
            return now - timedelta(hours=int(m.group(1)))
        if kind == "minutes":
            return now - timedelta(minutes=int(m.group(1)))
        if kind == "days":
            return now - timedelta(days=int(m.group(1)))
        if kind == "daymonth":
            day = int(m.group(1))
            mon = MONTHS[m.group(2).lower()[:3]]
            dt = now.replace(month=mon, day=day, hour=12, minute=0,
                             second=0, microsecond=0)
            if dt > now:  # e.g. "Dec" seen in January -> last year
                dt = dt.replace(year=dt.year - 1)
            return dt
    return None


def parse_text_cards(lines):
    """Parse job cards from block-structured text lines.

    Every card carries a distinctive '- X - Y Years' experience line, a
    '- City - Country' location line and a posting-date line, which anchors
    extraction without depending on exact CSS classes. URLs are resolved
    separately by the caller (sequential anchor consumption)."""
    jobs = []
    n = len(lines)
    i = 0
    while i < n:
        m = EXP_RE.match(lines[i])
        if m and i >= 2:
            title, company = lines[i - 2], lines[i - 1]
            if (title and company and not looks_like_chrome(title)
                    and not looks_like_chrome(company)
                    and len(title) < 140):
                # location line follows the experience line
                loc, j = "", i + 1
                if j < n:
                    lm = LOC_RE.match(lines[j])
                    if lm and not EXP_RE.match(lines[j]):
                        loc = lm.group(1).strip()
                        j += 1
                # description + date line
                desc_parts, dateline = [], ""
                k = j
                while k < n:
                    dl = lines[k]
                    if re.match(r"^filter jobs by", dl, re.I):
                        break
                    # start of next card? (title/company/exp triple)
                    if (k + 2 < n and EXP_RE.match(lines[k + 2])
                            and lines[k] and lines[k + 1]
                            and len(lines[k]) < 140
                            and not looks_like_chrome(lines[k])):
                        break
                    if parse_relative_date(dl, datetime.now(timezone.utc)):
                        dateline = dl
                        break
                    desc_parts.append(dl)
                    k += 1
                url = ""
                jobs.append({
                    "title": title,
                    "company": company,
                    "loc": loc,
                    "pub": dateline,
                    "url": url,
                    "desc": " ".join(desc_parts)[:2000],
                })
        i += 1
    return jobs


def parse_search_page(html, now):
    """Parse one search-results page. Returns list of raw job dicts."""
    # Strategy 1: JSON-LD (class-independent, most reliable)
    jobs = parse_jsonld(html)
    if jobs:
        out = []
        for j in jobs:
            dt = None
            if j["pub"]:
                try:
                    dt = datetime.fromisoformat(
                        j["pub"].replace("Z", "+00:00"))
                except Exception:
                    dt = None
            out.append({**j, "pub_dt": dt})
        return out
    # Strategy 2: text-pattern card parsing
    bt = _BlockText()
    try:
        bt.feed(html)
    except Exception:
        return []
    lines = bt.text_lines()
    am = _AnchorMap()
    try:
        am.feed(html)
    except Exception:
        pass
    # Resolve job URLs by sequential anchor consumption: the Nth card with a
    # given title takes the Nth unused anchor with matching text. (A plain
    # text->href dict collapses duplicate titles like "Data Engineer" onto
    # one URL, which then dedupes away real jobs.)
    anchors = am.links  # [(text, href)] in document order
    used = [False] * len(anchors)

    def resolve_url(title):
        key = _norm(title)
        for idx, (text, href) in enumerate(anchors):
            if not used[idx] and _norm(text) == key:
                used[idx] = True
                return BASE + href if href.startswith("/") else href
        return ""

    parsed = parse_text_cards(lines)  # urls resolved below, in order
    out = []
    for j in parsed:
        out.append({**j, "url": resolve_url(j["title"]),
                    "pub_dt": parse_relative_date(j["pub"], now)})
    return out


# -------------------------------------------------------- Gulf mapping ---

def map_gulf_country(loc):
    """Map a free-text location to one of the 6 Gulf countries, else None."""
    if not loc:
        return None
    s = loc.lower()
    if ("united arab emirates" in s or re.search(r"\buae\b", s)
            or "emirates" in s or "dubai" in s or "abu dhabi" in s
            or "sharjah" in s or "ajman" in s or "fujairah" in s):
        return "UAE"
    if ("saudi" in s or "riyadh" in s or "jeddah" in s or "dammam" in s
            or "khobar" in s or "mecca" in s or "medina" in s
            or "tabuk" in s):
        return "Saudi Arabia"
    if "qatar" in s or "doha" in s or "wakra" in s:
        return "Qatar"
    if "kuwait" in s:
        return "Kuwait"
    if "bahrain" in s or "manama" in s:
        return "Bahrain"
    if (re.search(r"\boman\b", s) or "muscat" in s or "sohar" in s
            or "duqm" in s or "salalah" in s):
        return "Oman"
    return None


def clean_city(loc):
    if not loc:
        return ""
    # "Abu Dhabi - United Arab Emirates (UAE)" -> "Abu Dhabi"
    # "Wakra , Doha - Qatar" -> "Wakra, Doha"
    city = loc.split("-")[0].strip()
    city = re.sub(r"\s*,\s*", ", ", city)
    city = re.sub(r"\s+", " ", city)
    return city[:60]


SAL_RE = re.compile(
    r"\$\s*([\d,]+)\s*(?:-|–|to)\s*\$\s*([\d,]+)")


def extract_gulf_salary(text):
    """Best-effort: NaukriGulf cards occasionally show monthly USD pay.
    Returns (annual_lo, annual_hi, 'USD') or None."""
    if not text:
        return None
    m = SAL_RE.search(text)
    if not m:
        return None
    try:
        lo = float(m.group(1).replace(",", "")) * 12
        hi = float(m.group(2).replace(",", "")) * 12
    except ValueError:
        return None
    if lo <= 0 or hi <= 0 or hi > 5_000_000:
        return None
    return (lo, hi, "USD")


# ------------------------------------------------------------------ main ---

def main():
    now = datetime.now(timezone.utc)
    print("Fetching FX rates...")
    rates = get_rates()
    rates.update(EXTRA_RATES)
    print("Fetching NaukriGulf search pages...")
    session = requests.Session()
    session.headers.update(UA)

    raw_jobs, seen_urls, errors = [], set(), []
    consecutive_failures = 0
    for slug in SEARCHES:
        if consecutive_failures >= 2:
            # Circuit breaker: the source is down/throttling this egress --
            # don't burn the hourly budget retrying every search.
            print("  circuit breaker: skipping remaining searches")
            errors.append(slug + " (skipped: source unreachable)")
            continue
        search_ok = False
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE}/{slug}" + (f"?page={page}" if page > 1 else "")
            print(f"  {url}")
            html = fetch(url, session)
            time.sleep(REQUEST_DELAY)
            if not html:
                if page == 1:
                    errors.append(slug)
                break
            search_ok = True
            cards = parse_search_page(html, now)
            new = 0
            for c in cards:
                u = c.get("url") or (c["title"] + "|" + c["company"])
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                raw_jobs.append(c)
                new += 1
            print(f"    -> {len(cards)} cards, {new} new")
            if new == 0:
                break  # pagination exhausted
        consecutive_failures = 0 if search_ok else consecutive_failures + 1

    print(f"\nTotal cards scraped: {len(raw_jobs)}")
    if errors:
        print(f"Searches with no usable response: {errors}")

    # title + country filter
    cand = []
    unmapped = set()
    for c in raw_jobs:
        title = (c.get("title") or "").strip()
        if not title_match(title):
            continue
        country = map_gulf_country(c.get("loc", ""))
        if not country:
            if c.get("loc"):
                unmapped.add(c["loc"][:70])
            continue
        cand.append(c | {"country": country})
    print(f"Title+Gulf matches: {len(cand)}")

    # build records
    jobs, seen = [], set()
    for c in cand:
        url = c.get("url") or ""
        if url in seen:
            continue
        seen.add(url)
        country = c["country"]
        local_cur = GULF_CURRENCY[country]
        sal = extract_gulf_salary(c.get("desc", "") + " " + c.get("title", ""))
        smin = smax = None
        goal = None
        if sal:
            lo, hi, cur = sal
            smin = to_local(lo, cur, local_cur, rates)
            smax = to_local(hi, cur, local_cur, rates)
            if smin is not None and smax is not None:
                mid = (smin + smax) / 2
                goal = mid >= GULF_THRESHOLDS[country]
                smin, smax = round(smin), round(smax)
        pub_dt = c.get("pub_dt")
        pub_iso = pub_dt.astimezone(timezone.utc).isoformat() \
            if pub_dt else None
        # Freshness policy: drop postings older than 60 days (same rule as
        # the main feed). Stale listings are usually already filled.
        if pub_dt is not None and now - pub_dt > timedelta(days=60):
            continue
        jobs.append({
            "t": c["title"][:120], "co": (c.get("company") or "")[:60],
            "city": clean_city(c.get("loc", "")), "country": country,
            "cur": local_cur,
            "smin": smin, "smax": smax, "goal": goal,
            "spon": sponsorship_signal(c.get("desc", "")), "pub": pub_iso,
            "url": url,
        })

    jobs.sort(key=lambda j: j["pub"] or "", reverse=True)
    meta = {
        "refreshed_at": now.isoformat(),
        "source": "naukrigulf.com",
        "searches": SEARCHES,
        "total": len(jobs),
        "thresholds": GULF_THRESHOLDS,
        "countries": GULF_COUNTRIES,
    }
    if not raw_jobs:
        meta["error"] = ("NaukriGulf could not be reached during this refresh "
                         "(network blocked or throttled). No listings were "
                         "fabricated; try again at the next refresh.")
    payload = {"meta": meta, "jobs": jobs}
    out = "web/gulf/jobs.json"
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"\nWrote {out}: {len(jobs)} jobs")

    from collections import Counter
    cc = Counter(j["country"] for j in jobs)
    print("Per-country counts:")
    for ctry in GULF_COUNTRIES:
        print(f"  {ctry:15s} {cc.get(ctry, 0)}")
    if unmapped:
        print(f"\nUnmapped locations ({len(unmapped)}):")
        for u in sorted(unmapped)[:20]:
            print(f"  - {u!r}")


if __name__ == "__main__":
    main()
