#!/usr/bin/env python3
"""Career Radar ETL - pulls public ATS job boards (Greenhouse, Lever) and
writes a compact, filtered jobs.json for the static site.

Zero API keys required. Run:  python3 etl/fetch_jobs.py
Output: web/data/jobs.json
"""
import json, re, sys
from html.parser import HTMLParser
from html import unescape as html_unescape
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import requests

UA = {"User-Agent": "career-radar/1.0 (+github pages daily refresh)"}
TIMEOUT = 25
WORKERS = 20

# ---------------------------------------------------------------- boards ---
GREENHOUSE_BOARDS = [
    'adyen','amperity','anthropic','asana','attentive','bird','blueshift',
    'bolcom','brex','buildkite','careem','circleci','cloudflare','collibra',
    'cultureamp','databricks','datadog','deliveroo','discord','dremio',
    'dropbox','druva','elastic','fastly','figma','fivetran','flipp','geotab',
    'getyourguide','gitlab','greenhouse','gremlin','groww','gusto','honeycomb',
    'hootsuite','instacart','intercom','jfrog','klaviyo','lattice','lyft',
    'mercury','mongodb','monzo','n26','netlify','newrelic','okta','pagerduty',
    'planetscale','pushpay','reddit','robinhood','roblox','rocketlab','rubrik',
    'salesloft','singlestore','slice','starburst','sumup','tailscale','tamara',
    'togetherai','twilio','vercel','webflow','wise','wolt','zscaler',
    'doctolib','anaplan','sigmacomputing','algolia','trivago','platformsh',
    'imply','acryldata','onemedical','oscar','scopely','riotgames','epicgames',
    'tide','carta','duolingo','zocdoc','mixpanel','datacamp','mavenclinic',
    'pendo','udacity','coursera','doximity','yotpo','saltsecurity','amwell',
    'handshake','udemy','masterclass','calm','cresta','sonicwall','huntress',
    'otterai','descript','orcasecurity','observeai','consensys','calendly',
    'expel','stackblitz','udio','lightmatter','pantheon','acquia','duda',
    'tigera','upbound','scaleai','snorkelai','labelbox','voxel51',
]
LEVER_BOARDS = ['prosper']

# ------------------------------------------------- country/threshold config --
COUNTRIES = ["USA", "India", "United Kingdom", "UAE", "Saudi Arabia",
             "Kuwait", "Canada", "Netherlands", "New Zealand", "Poland"]
COUNTRY_CURRENCY = {"USA": "USD", "India": "INR", "United Kingdom": "GBP",
                    "UAE": "AED", "Saudi Arabia": "SAR", "Kuwait": "KWD",
                    "Canada": "CAD", "Netherlands": "EUR",
                    "New Zealand": "NZD", "Poland": "PLN"}
# Annual gross salary in local currency at/above which the INR 5L/month
# post-tax-and-expenses savings goal is considered met (midpoint of range).
THRESHOLDS = {"USA": 175000, "India": 9500000, "United Kingdom": 128000,
              "UAE": 420000, "Saudi Arabia": 370000, "Kuwait": 29000,
              "Canada": 190000, "Netherlands": 128000,
              "New Zealand": 225000, "Poland": 660000}

FALLBACK_RATES = {  # per USD, captured 2026-10-12
    "USD": 1.0, "INR": 95.90693, "EUR": 0.895156, "GBP": 0.756615,
    "AED": 3.6725, "SAR": 3.75, "KWD": 0.311015, "QAR": 3.64,
    "CAD": 1.427373, "NZD": 1.788691, "PLN": 3.92703, "SGD": 1.30,
    "CHF": 0.86, "AUD": 1.52, "SEK": 9.4, "JPY": 149.0,
}

# ------------------------------------------------------- location mapping ---
US_STATES = ["alabama","alaska","arizona","arkansas","california","colorado",
    "connecticut","delaware","florida","georgia","hawaii","idaho","illinois",
    "indiana","iowa","kansas","kentucky","louisiana","maine","maryland",
    "massachusetts","michigan","minnesota","mississippi","missouri","montana",
    "nebraska","nevada","new hampshire","new jersey","new mexico","new york",
    "north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania",
    "rhode island","south carolina","south dakota","tennessee","texas","utah",
    "vermont","virginia","washington","west virginia","wisconsin","wyoming",
    "district of columbia"]
US_ABBR = ["al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il",
    "in","ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne",
    "nv","nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd",
    "tn","tx","ut","vt","va","wa","wv","wi","wy","dc"]
US_CITIES = ["new york city","nyc","los angeles","san francisco","san jose",
    "san diego","sacramento","oakland","san antonio","dallas","fort worth",
    "houston","austin","el paso","plano","frisco","irvine","fremont",
    "santa clara","sunnyvale","mountain view","palo alto","menlo park",
    "cupertino","redwood city","santa monica","culver city","pasadena",
    "long beach","anaheim","riverside","chicago","naperville","evanston",
    "seattle","bellevue","redmond","kirkland","tacoma","portland","beaverton",
    "hillsboro","denver","boulder","boston","somerville","waltham","lowell",
    "worcester","quincy","brooklyn","queens","manhattan","bronx",
    "white plains","stamford","hartford","new haven","philadelphia",
    "pittsburgh","reston","tyson","tysons","mclean","bethesda","baltimore",
    "atlanta","alpharetta","sandy springs","marietta","charlotte","raleigh",
    "durham","cary","morrisville","nashville","miami","tampa","orlando",
    "jacksonville","fort lauderdale","detroit","ann arbor","minneapolis",
    "st paul","saint paul","kansas city","st louis","saint louis","cleveland",
    "columbus","cincinnati","indianapolis","milwaukee","madison","des moines",
    "omaha","oklahoma city","tulsa","memphis","louisville","birmingham",
    "new orleans","albuquerque","santa fe","phoenix","tempe","scottsdale",
    "mesa","tucson","las vegas","reno","salt lake city","lehi","draper",
    "boise","helena","billings","fargo","sioux falls","lincoln","topeka",
    "wichita","springfield","columbia","little rock","jackson","charleston",
    "columbia","richmond","norfolk","virginia beach","raleigh","wilmington",
    "asheville","greensboro","knoxville","chattanooga","lexington",
    "louisville","des moines","cedar rapids","davenport","fargo","bismarck",
    "sioux city","grand forks","duluth","rochester","buffalo","syracuse",
    "albany","yonkers","new rochelle","ithaca","binghamton","erie","allentown",
    "harrisburg","lancaster","reading","scranton","trenton","newark",
    "jersey city","princeton","wilmington","dover","annapolis","frederick",
    "gaithersburg","rockville","silver spring","alexandria","fairfax",
    "manassas","woodbridge","harrisonburg","lynchburg","roanoke","newport news",
    "chesapeake","suffolk","hampton","portsmouth","hopewell","petersburg"]

def map_country(loc):
    """Map a free-text ATS location to one of the 10 countries, else None."""
    if not loc:
        return None
    s = loc.lower().split(";")[0].strip().replace(".", "")
    if not s or s in ("remote", "hybrid", "in-office", "in office",
                      "on-site", "onsite", "flexible"):
        return None
    # remote with explicit geography
    if "remote" in s:
        if re.search(r"\bunited states\b|\busa?\b|[- ]us\b", s): return "USA"
        if "india" in s: return "India"
        if re.search(r"\buk\b|united kingdom|england", s): return "United Kingdom"
        if "canada" in s: return "Canada"
        if "netherlands" in s: return "Netherlands"
        if "poland" in s: return "Poland"
        if "uae" in s or "emirates" in s or "dubai" in s: return "UAE"
        if "saudi" in s: return "Saudi Arabia"
        if "kuwait" in s: return "Kuwait"
        if "new zealand" in s: return "New Zealand"
        # no explicit remote geography: fall through to city matching below
    if "india" in s or any(c in s for c in
        ["bengaluru","bangalore","hyderabad","mumbai","bombay","delhi",
         "gurgaon","gurugram","chennai","pune","noida","kolkata","ahmedabad",
         "kochi","cochin","jaipur","lucknow","indore","mohali","chandigarh",
         "coimbatore","nagpur","mysore","mysuru","thiruvananthapuram",
         "visakhapatnam","vijayawada","surat","vadodara","bhopal"]):
        return "India"
    if ("united arab emirates" in s or re.search(r"\buae\b", s)
            or "dubai" in s or "abu dhabi" in s or "sharjah" in s):
        return "UAE"
    if ("saudi" in s or "riyadh" in s or "jeddah" in s or "khobar" in s
            or "dammam" in s or "neom" in s):
        return "Saudi Arabia"
    if "kuwait" in s:
        return "Kuwait"
    if ("united kingdom" in s or re.search(r"\buk\b", s) or "england" in s
            or any(c in s for c in ["london","manchester","birmingham",
                "edinburgh","glasgow","leeds","bristol","cambridge","oxford",
                "sheffield","liverpool","newcastle","cardiff","belfast"])):
        return "United Kingdom"
    if ("canada" in s or ("ca remote" in s and "bc" in s)
            or any(c in s for c in
            ["toronto","vancouver","montreal","ottawa","calgary","waterloo",
             "mississauga","edmonton"])):
        return "Canada"
    if ("netherlands" in s or any(c in s for c in ["amsterdam","rotterdam",
            "utrecht","eindhoven","the hague","den haag"])):
        return "Netherlands"
    if ("new zealand" in s or "auckland" in s or "wellington" in s
            or "christchurch" in s):
        return "New Zealand"
    if ("poland" in s or "warsaw" in s or "krakow" in s or "kraków" in s
            or "wroclaw" in s or "wrocław" in s or "gdansk" in s
            or "gdańsk" in s or "poznan" in s or "poznań" in s):
        return "Poland"
    # USA last (broadest)
    if ("united states" in s or re.search(r"\busa\b", s)
            or any(st in s for st in US_STATES)
            or any(c in s for c in US_CITIES)
            or re.search(r",\s*(" + "|".join(US_ABBR) + r")\b", s)):
        return "USA"
    return None

def clean_city(loc):
    if not loc:
        return ""
    return loc.split(";")[0].strip()[:60]

# --------------------------------------------------------- title filtering --
INCLUDE_RES = [
    r"data\s+engineer", r"analytics\s+engineer", r"data\s+scientist",
    r"machine\s+learning", r"\bml\s+(engineer|scientist)",
    r"\bgenai\b", r"generative\s+ai", r"\bllm\b(\s+engineer)?",
    r"data\s+analyst", r"business\s+intelligence", r"\bbi\b\s+(engineer|analyst)",
    r"data\s+platform", r"\bai\b.{0,15}\bengineer\b",
]
EXCLUDE_RES = [
    r"\bintern(ship|s)?\b", r"\bjunior\b", r"\bjr\.?\b", r"entry[\s\-]?level",
    r"\bstaff\b", r"\bprincipal\b", r"\bdirector\b", r"\bvp\b",
    r"vice\s+president", r"\bhead\s+of\b", r"\bchief\b", r"\bfellow\b",
    r"\bphd\b.{0,10}\bintern\b", r"\bsolutions?\b", r"\barchitect\b",
    r"\bdistinguished\b",
]
PM_RES = [r"product\s+manager", r"product\s+lead"]
PM_CTX_RES = [r"data", r"\bai\b", r"\bml\b", r"machine\s+learning",
              r"analytics", r"platform"]

def title_match(title):
    t = title.lower()
    if any(re.search(p, t) for p in EXCLUDE_RES):
        return False
    # product managers (data/AI context only) are kept
    if any(re.search(p, t) for p in PM_RES):
        return any(re.search(p, t) for p in PM_CTX_RES)
    if re.search(r"\bmanager\b", t):
        return False
    return any(re.search(p, t) for p in INCLUDE_RES)

# ------------------------------------------------------------- sponsorship --
class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, d):
        self.parts.append(d)
    def text(self):
        return " ".join(self.parts)

def strip_html(h):
    if not h:
        return ""
    h = html_unescape(h)  # API content is often entity-escaped
    # unescape twice: some boards double-escape (&amp;lt;)
    if "&lt;" in h:
        h = html_unescape(h)
    s = _Stripper()
    try:
        s.feed(h)
    except Exception:
        return re.sub(r"<[^>]+>", " ", h)
    return s.text()

def sponsorship_signal(text):
    """Heuristic scan of posting text. Returns 'yes' / 'no' / 'unknown'."""
    t = " ".join(text.lower().split())
    if not t:
        return "unknown"
    if re.search(r"(will not|won't|can't|cannot|unable to|do not|does not"
                 r"|are not|is not)\s[^.]{0,50}sponsor", t):
        return "no"
    if re.search(r"sponsor[^.]{0,40}(not available|unavailable|unable)", t):
        return "no"
    if re.search(r"without\s+.{0,25}sponsorship", t):
        return "no"
    if re.search(r"no\s+.{0,15}(visa\s+)?sponsorship", t):
        return "no"
    if re.search(r"visa\s+sponsorship|sponsorship\s+(available|offered|"
                 r"provided|possible)|will\s+sponsor|can\s+sponsor", t):
        return "yes"
    if "sponsorship" in t or "h-1b" in t or "h1b" in t:
        return "yes"
    return "unknown"

# ------------------------------------------------------------------ salary --
INTERVAL_MULT = {"hour": 2080, "hourly": 2080, "day": 260, "daily": 260,
                 "week": 52, "weekly": 52, "month": 12, "monthly": 12,
                 "year": 1, "yearly": 1, "annual": 1, "annually": 1}

def annualize(amount, interval):
    if amount is None:
        return None
    mult = INTERVAL_MULT.get((interval or "year").lower().strip(), 1)
    return amount * mult

def parse_pay_ranges(pr):
    """Greenhouse pay_ranges -> (min_annual, max_annual, currency)."""
    if not pr:
        return None
    items = pr if isinstance(pr, list) else [pr]
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        lo = annualize(it.get("min"), it.get("interval"))
        hi = annualize(it.get("max"), it.get("interval"))
        cur = (it.get("unit") or it.get("currency") or "USD").upper()
        if lo or hi:
            out.append((lo or hi, hi or lo, cur))
    return out[0] if out else None

def _num(x):
    try:
        return float(x.replace(",", ""))
    except (ValueError, AttributeError):
        return None

def extract_salary_from_text(text):
    """Mine salary figures from posting text. Returns
    (min_annual, max_annual, currency) or None. Figures are very often
    embedded as e.g. '$186,100 USD' or '$215,000 - $270,000' in pay-
    transparency blocks."""
    t = " ".join((text or "").split())
    if not t:
        return None
    cands = []  # (score, start, currency, lo, hi, interval_hint)
    # generous per-currency annual sanity caps (rejects "$5B revenue" noise)
    CAPS = {"USD": 3000000, "GBP": 3000000, "EUR": 3000000, "CHF": 3000000,
            "INR": 300000000, "AED": 12000000, "SAR": 12000000,
            "QAR": 12000000, "KWD": 1000000, "CAD": 5000000, "AUD": 5000000,
            "NZD": 5000000, "SGD": 5000000, "PLN": 15000000, "SEK": 15000000}
    def add(m, cur, lo_s, hi_s, k_lo=False, k_hi=False):
        lo, hi = _num(lo_s), _num(hi_s)
        if lo is None:
            return
        if k_lo: lo *= 1000
        if k_hi: hi = (hi or lo) * 1000
        hi = hi or lo
        cap = CAPS.get(cur, 3000000)
        if not (500 <= hi <= cap and lo <= hi and lo >= 100):
            return
        start = m.start()
        window = t[max(0, start - 90):start].lower()
        score = 2 if re.search(
            r"salar|compensat|pay\s+range|base\s+pay|remuneration|per\s+year"
            r"|annual|on[-\s]?target|\bote\b", window) else 0
        after = t[m.end():m.end() + 40].lower()
        interval = "year"
        if re.search(r"per\s+hour|/hour|hourly", after):
            interval = "hour"
        elif re.search(r"per\s+month|/month|monthly", after):
            interval = "month"
        cands.append((score, start, cur, lo, hi, interval))
    # USD ranges / singles ("$215,000 - $270,000", "$186,100 USD")
    for m in re.finditer(
            r"\$\s*([\d,]{3,}(?:\.\d{2})?)\s*[-–—]\s*\$\s*([\d,]{3,}(?:\.\d{2})?)"
            r"(?:\s*USD)?\b", t):
        add(m, "USD", m.group(1), m.group(2))
    for m in re.finditer(r"\$\s*([\d,]{4,}(?:\.\d{2})?)\s*USD\b", t):
        add(m, "USD", m.group(1), m.group(1))
    for m in re.finditer(
            r"\$\s*([\d,\.]{3,})\s*[kK]\b\s*[-–—]\s*\$\s*([\d,\.]{3,})\s*[kK]\b",
            t):
        add(m, "USD", m.group(1), m.group(2), True, True)
    # GBP / EUR / INR symbols
    for sym, cur in [("£", "GBP"), ("€", "EUR"), ("₹", "INR")]:
        for m in re.finditer(re.escape(sym) +
                r"\s*([\d,]{4,})\s*[-–—]\s*" + re.escape(sym) +
                r"?\s*([\d,]{4,})", t):
            add(m, cur, m.group(1), m.group(2))
    # explicit currency codes
    for m in re.finditer(
            r"\b(AED|SAR|KWD|QAR|CAD|NZD|PLN|INR|CHF|SGD|AUD)\s*"
            r"([\d,]{4,})\s*[-–—]\s*(?:\1\s*)?([\d,]{4,})", t):
        add(m, m.group(1), m.group(2), m.group(3))
    # INR lakhs ("25 LPA", "30 lakhs")
    for m in re.finditer(
            r"\b([\d\.]{1,4})\s*(?:lakh|lac|lpa)\b\s*[-–—]?\s*"
            r"(?:([\d\.]{1,4})\s*(?:lakh|lac|lpa)\b)?", t, re.I):
        lo = _num(m.group(1))
        hi = _num(m.group(2)) if m.group(2) else lo
        if lo and 1 <= lo <= 300 and hi and hi >= lo:
            window = t[max(0, m.start() - 90):m.start()].lower()
            score = 2 if re.search(
                r"salar|compensat|pay|ctc|package", window) else 0
            cands.append((score, m.start(), "INR",
                          lo * 100000, hi * 100000, "year"))
    if not cands:
        return None
    cands.sort(key=lambda c: (-c[0], c[1]))
    _, _, cur, lo, hi, interval = cands[0]
    # guard against truncated figures in the source ("$130,00 - $190,000"):
    # a missing zero makes lo look ~10x smaller than hi
    if hi > lo * 4 and 0.5 <= (lo * 10) / hi <= 1.5:
        return None
    return (annualize(lo, interval), annualize(hi, interval), cur)

# ------------------------------------------------------------------ fetching --
def get_json(url, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()

def fetch_greenhouse_board(token):
    try:
        d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
        return token, d.get("jobs", [])
    except Exception as e:
        print(f"  [warn] greenhouse/{token}: {e}", file=sys.stderr)
        return token, []

def fetch_lever_board(token):
    try:
        d = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
        jobs = d if isinstance(d, list) else d.get("data", [])
        return token, jobs
    except Exception as e:
        print(f"  [warn] lever/{token}: {e}", file=sys.stderr)
        return token, []

def fetch_greenhouse_detail(token, job_id):
    try:
        return get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}")
    except Exception:
        return {}

def get_rates():
    try:
        d = get_json("https://open.er-api.com/v6/latest/USD")
        if d.get("result") == "success":
            return d["rates"]
    except Exception as e:
        print(f"  [warn] fx api failed, using fallback: {e}", file=sys.stderr)
    return FALLBACK_RATES

def to_local(amount, from_cur, to_cur, rates):
    if amount is None:
        return None
    f = (from_cur or "USD").upper()
    rf = rates.get(f) or FALLBACK_RATES.get(f)
    rt = rates.get(to_cur) or FALLBACK_RATES.get(to_cur)
    if not rf or not rt:
        return None
    usd = amount / rf
    return usd * rt

def norm_lever_location(job):
    cats = job.get("categories") or {}
    loc = cats.get("location") or job.get("location") or ""
    return loc

# ---------------------------------------------------------------------- main --
def main():
    print("Fetching FX rates...")
    rates = get_rates()
    print("Fetching boards...")
    jobs_raw = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = ([ex.submit(fetch_greenhouse_board, t) for t in GREENHOUSE_BOARDS]
                + [ex.submit(fetch_lever_board, t) for t in LEVER_BOARDS])
        for f in futs:
            token, jobs = f.result()
            plat = "lever" if token in LEVER_BOARDS else "greenhouse"
            for j in jobs:
                jobs_raw.append((plat, token, j))
    print(f"Total postings scanned: {len(jobs_raw)}")

    # title filter
    cand = []
    for plat, token, j in jobs_raw:
        title = (j.get("title") or "").strip()
        if plat == "greenhouse":
            loc = (j.get("location") or {}).get("name", "")
            pub = j.get("first_published") or j.get("updated_at")
            url = j.get("absolute_url", "")
            company = j.get("company_name") or token
            jid = j.get("id")
        else:  # lever
            loc = norm_lever_location(j)
            pub = j.get("createdAt")
            urls = j.get("urls") or {}
            url = urls.get("apply") or j.get("hostedUrl") or ""
            company = token
            jid = j.get("id")
        if not title_match(title):
            continue
        country = map_country(loc)
        if not country:
            unmapped.add(loc.split(";")[0].strip()[:70])
            continue
        cand.append({"plat": plat, "token": token, "id": jid, "title": title,
                     "company": company, "loc": loc, "country": country,
                     "pub": pub, "url": url,
                     "lever": j if plat == "lever" else None})
    print(f"Title+country matches: {len(cand)}")

    # detail fetch (salary + sponsorship) for greenhouse; lever inline
    def enrich(c):
        sal = None
        spon = "unknown"
        if c["plat"] == "greenhouse":
            d = fetch_greenhouse_detail(c["token"], c["id"])
            sal = parse_pay_ranges(d.get("pay_ranges"))
            text = strip_html(d.get("content", ""))
            if not sal:
                sal = extract_salary_from_text(text)
            spon = sponsorship_signal(text)
        else:
            j = c["lever"]
            sr = j.get("salaryRange") or {}
            if sr.get("min") or sr.get("max"):
                lo = annualize(sr.get("min"), sr.get("interval"))
                hi = annualize(sr.get("max"), sr.get("interval"))
                sal = (lo or hi, hi or lo,
                       (sr.get("currency") or "USD").upper())
            spon = sponsorship_signal(strip_html(
                j.get("description") or j.get("descriptionPlain", "")))
        c["sal"] = sal
        c["spon"] = spon
        return c

    print("Fetching job details (salary/sponsorship)...")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        cand = list(ex.map(enrich, cand))

    # build records
    jobs, seen = [], set()
    for c in cand:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        country = c["country"]
        local_cur = COUNTRY_CURRENCY[country]
        smin = smax = None
        goal = None
        if c["sal"]:
            lo, hi, cur = c["sal"]
            smin = to_local(lo, cur, local_cur, rates)
            smax = to_local(hi, cur, local_cur, rates)
            if smin is not None and smax is not None:
                mid = (smin + smax) / 2
                goal = mid >= THRESHOLDS[country]
                smin, smax = round(smin), round(smax)
        try:
            pub_dt = datetime.fromisoformat(
                c["pub"].replace("Z", "+00:00")) if c["pub"] else None
            pub_iso = pub_dt.astimezone(timezone.utc).isoformat() \
                if pub_dt else None
        except Exception:
            pub_iso = None
        jobs.append({
            "t": c["title"][:120], "co": c["company"][:60],
            "city": clean_city(c["loc"]), "country": country,
            "cur": local_cur,
            "smin": smin, "smax": smax, "goal": goal,
            "spon": c["spon"], "pub": pub_iso, "url": c["url"],
        })

    # sort newest first
    jobs.sort(key=lambda j: j["pub"] or "", reverse=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "meta": {
            "refreshed_at": now,
            "boards": len(GREENHOUSE_BOARDS) + len(LEVER_BOARDS),
            "total": len(jobs),
            "thresholds": THRESHOLDS,
            "countries": COUNTRIES,
            "fx_date": now[:10],
        },
        "jobs": jobs,
    }
    out = "web/data/jobs.json"
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {out}: {len(jobs)} jobs")

    # report
    from collections import Counter
    cc = Counter(j["country"] for j in jobs)
    print("\nPer-country counts:")
    for ctry in COUNTRIES:
        print(f"  {ctry:15s} {cc.get(ctry, 0)}")
    sal_cov = sum(1 for j in jobs if j["goal"] is not None)
    print(f"\nSalary disclosed: {sal_cov}/{len(jobs)} "
          f"({100*sal_cov//max(len(jobs),1)}%)")
    print(f"Meet savings goal: {sum(1 for j in jobs if j['goal'] is True)}")
    print(f"\nUnmapped locations ({len(unmapped)} unique):")
    for u in sorted(unmapped)[:40]:
        print(f"  - {u!r}")

unmapped = set()

if __name__ == "__main__":
    main()
