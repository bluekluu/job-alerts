#!/usr/bin/env python3
"""Generate the daily JobsAlert page from public structured job sources."""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = REPO_ROOT / "index.html"
ARCHIVE = REPO_ROOT / "archive"
REPORTS = REPO_ROOT / "reports"
PT = ZoneInfo("America/Los_Angeles")

GREENHOUSE = {
    "anthropic": "Anthropic",
    "reddit": "Reddit",
    "scaleai": "Scale AI",
    "discord": "Discord",
    "coinbase": "Coinbase",
    "databricks": "Databricks",
    "okta": "Okta",
    "block": "Block",
}
LEVER = {
    "moonpay": "MoonPay",
    "palantir": "Palantir",
}
ASHBY = {
    "openai": "OpenAI",
}
AMAZON_QUERIES = [
    "responsible ai",
    "privacy",
    "trust safety",
    "technical program manager",
    "compliance",
]

DOMAIN_KEYWORDS = [
    "trust",
    "safety",
    "responsible ai",
    "privacy",
    "compliance",
    "governance",
    "risk",
    "integrity",
    "abuse",
    "security",
    "policy",
    "moderation",
    "child safety",
    "youth",
]
PRIMARY_DOMAIN_KEYWORDS = [
    "trust",
    "safety",
    "responsible ai",
    "privacy",
    "compliance",
    "governance",
    "integrity",
    "abuse",
    "moderation",
    "child safety",
    "youth",
]
SENIORITY_KEYWORDS = [
    "director",
    "sr. director",
    "senior director",
    "vp",
    "vice president",
    "head",
    "principal",
    "staff",
    "lead",
]
FUNCTION_KEYWORDS = [
    "program manager",
    "technical program",
    "product manager",
    "tpm",
    "trust",
    "safety",
    "privacy",
    "governance",
    "risk",
    "compliance",
]
EXCLUDED_COMPANIES = ["meta", "instagram", "whatsapp", "reality labs"]

COMPANY_ALIASES = [
    (re.compile(r"\bamazon\b", re.I), "Amazon"),
    (re.compile(r"\bopenai\b", re.I), "OpenAI"),
    (re.compile(r"\breddit\b", re.I), "Reddit"),
    (re.compile(r"\banthropic\b", re.I), "Anthropic"),
    (re.compile(r"\bdiscord\b", re.I), "Discord"),
    (re.compile(r"\bdatabricks\b", re.I), "Databricks"),
    (re.compile(r"\bokta\b", re.I), "Okta"),
    (re.compile(r"\bcoinbase\b", re.I), "Coinbase"),
    (re.compile(r"\bscale ai\b|\bscaleai\b", re.I), "Scale AI"),
    (re.compile(r"\bblock\b", re.I), "Block"),
    (re.compile(r"\bmoonpay\b", re.I), "MoonPay"),
    (re.compile(r"\bpalantir\b", re.I), "Palantir"),
]

COMPANY_DOMAINS = {
    "Amazon": "amazon.com",
    "Anthropic": "anthropic.com",
    "Reddit": "redditinc.com",
    "Scale AI": "scale.com",
    "Discord": "discord.com",
    "Coinbase": "coinbase.com",
    "Databricks": "databricks.com",
    "Okta": "okta.com",
    "Block": "block.xyz",
    "MoonPay": "moonpay.com",
    "Palantir": "palantir.com",
    "OpenAI": "openai.com",
}

STATE_ALIASES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "washington d.c.": "DC",
    "washington dc": "DC",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
STATE_ABBRS = set(STATE_ALIASES.values())


@dataclass
class Candidate:
    title: str
    company: str
    location: str
    url: str
    source: str
    source_url: str
    description: str
    posted: str = ""
    comp: str = "Not listed"
    engagement: str = "full-time"


@dataclass
class Evaluated:
    candidate: Candidate
    score: int
    band: str
    included: bool
    reason: str
    tags: list[str]
    gaps: str


def fetch_json(url: str, timeout: int = 25) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "JobsAlert/1.0"})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JobsAlert/1.0"})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        return response.read().decode("utf-8", "ignore")


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def clean_location(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("location") or "Not listed")
    return str(value or "Not listed")


def clean_location_list(values: list[object]) -> str:
    cleaned = []
    for value in values:
        if not value:
            continue
        cleaned.append(clean_location(value))
    return ", ".join(cleaned) or "Not listed"


def greenhouse_candidates(slug: str, company: str) -> list[Candidate]:
    url = f"https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = fetch_json(url)
    candidates: list[Candidate] = []
    for job in data.get("jobs", []) if isinstance(data, dict) else []:
        title = job.get("title", "")
        description = strip_html(job.get("content", ""))
        candidates.append(
            Candidate(
                title=title,
                company=job.get("company_name") or company,
                location=clean_location(job.get("location")),
                url=job.get("absolute_url", ""),
                source="Greenhouse API",
                source_url=url,
                description=description,
                posted=(job.get("first_published") or "")[:10],
            )
        )
    return candidates


def lever_candidates(slug: str, company: str) -> list[Candidate]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = fetch_json(url)
    candidates: list[Candidate] = []
    for job in data if isinstance(data, list) else []:
        categories = job.get("categories") or {}
        location = categories.get("location") or job.get("country") or "Not listed"
        description = " ".join(
            [
                job.get("descriptionPlain") or "",
                job.get("descriptionBodyPlain") or "",
                job.get("additionalPlain") or "",
            ]
        )
        candidates.append(
            Candidate(
                title=job.get("text", ""),
                company=company,
                location=location,
                url=job.get("hostedUrl") or job.get("applyUrl") or "",
                source="Lever API",
                source_url=url,
                description=strip_html(description),
                posted=str(job.get("createdAt") or "")[:10],
            )
        )
    return candidates


def ashby_candidates(org: str, company: str) -> list[Candidate]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    data = fetch_json(url)
    candidates: list[Candidate] = []
    for job in data.get("jobs", []) if isinstance(data, dict) else []:
        locations = [job.get("location", "")]
        locations.extend(job.get("secondaryLocations") or [])
        candidates.append(
            Candidate(
                title=job.get("title", ""),
                company=company,
                location=clean_location_list(locations),
                url=job.get("jobUrl") or job.get("applyUrl") or "",
                source="Ashby API",
                source_url=url,
                description=strip_html(job.get("descriptionPlain") or job.get("descriptionHtml") or ""),
                posted=(job.get("publishedAt") or "")[:10],
            )
        )
    return candidates


def amazon_candidates() -> list[Candidate]:
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for query in AMAZON_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (
            "https://www.amazon.jobs/en/search.json?"
            f"base_query={encoded}&loc_query=Seattle%2C%20WA&result_limit=20"
        )
        data = fetch_json(url)
        for job in data.get("jobs", []) if isinstance(data, dict) else []:
            job_id = str(job.get("id") or "")
            if job_id in seen:
                continue
            seen.add(job_id)
            path = job.get("job_path") or f"/en/jobs/{job_id}"
            candidates.append(
                Candidate(
                    title=job.get("title", ""),
                    company=job.get("company_name") or "Amazon",
                    location=job.get("location") or job.get("normalized_location") or "Not listed",
                    url="https://www.amazon.jobs" + path if path.startswith("/") else path,
                    source="Amazon Jobs API",
                    source_url=url,
                    description=strip_html(
                        " ".join(
                            [
                                job.get("description", ""),
                                job.get("basic_qualifications", ""),
                                job.get("preferred_qualifications", ""),
                            ]
                        )
                    ),
                    posted=job.get("posted_date") or "",
                )
            )
    return candidates


def collect_candidates() -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    errors: list[str] = []
    source_calls = []
    source_calls.extend((greenhouse_candidates, slug, company) for slug, company in GREENHOUSE.items())
    source_calls.extend((lever_candidates, slug, company) for slug, company in LEVER.items())
    source_calls.extend((ashby_candidates, slug, company) for slug, company in ASHBY.items())

    for fn, slug, company in source_calls:
        try:
            candidates.extend(fn(slug, company))
        except Exception as exc:
            errors.append(f"{company}: {exc}")
    try:
        candidates.extend(amazon_candidates())
    except Exception as exc:
        errors.append(f"Amazon: {exc}")
    return dedupe(candidates), errors


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    deduped: list[Candidate] = []
    for candidate in candidates:
        candidate.company = canonical_company(candidate.company)
        candidate.location = normalize_location(candidate.location)
        key = candidate.url or f"{candidate.company}:{candidate.title}:{candidate.location}"
        if not candidate.title or not candidate.url or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def canonical_company(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name or "").strip()
    for pattern, canonical in COMPANY_ALIASES:
        if pattern.search(cleaned):
            return canonical
    cleaned = re.sub(r"\s+(inc\.?|llc|ltd\.?|corp\.?|corporation|services|technologies)$", "", cleaned, flags=re.I).strip()
    return cleaned or "Unknown"


def normalize_location(location: str) -> str:
    raw = re.sub(r"\s+", " ", location or "").strip()
    if not raw or raw.lower() == "not listed":
        return "Not listed"

    lowered = raw.lower()
    if "san francisco bay area" in lowered and "los angeles area" in lowered:
        return "Bay Area, CA, US; Los Angeles, CA, US"
    if "remote" in lowered and any(token in lowered for token in ["united states", " u.s.", " usa", " us", "- us"]):
        return "Remote, US"
    remote_state = re.match(r"^Remote\s*[-,]\s*(.+)$", raw, re.I)
    if remote_state:
        state = normalize_state(remote_state.group(1))
        if state:
            return f"Remote, {state}, US"

    raw = raw.replace("United States of America", "US").replace("United States", "US")
    raw = re.sub(r"\bUSA\b|\bU\.S\.\b|\bU\.S\.A\.\b", "US", raw, flags=re.I)
    raw = raw.replace("Washington, D.C.", "Washington, DC").replace("Washington D.C.", "Washington, DC")
    known_city_states = {
        "seattle": ("Seattle", "WA"),
        "bellevue": ("Bellevue", "WA"),
        "redmond": ("Redmond", "WA"),
        "san francisco": ("San Francisco", "CA"),
        "san francisco bay area": ("Bay Area", "CA"),
        "bay area": ("Bay Area", "CA"),
        "new york city": ("New York City", "NY"),
        "new york": ("New York", "NY"),
        "washington": ("Washington", "DC"),
        "chicago": ("Chicago", "IL"),
        "san mateo": ("San Mateo", "CA"),
        "los angeles": ("Los Angeles", "CA"),
    }
    if re.search(r"\s*(?:\||;)\s*", raw):
        parts = []
        for part in re.split(r"\s*(?:\||;)\s*", raw):
            normalized = normalize_location(part)
            if part.strip() and normalized not in parts:
                parts.append(normalized)
        return "; ".join(parts)

    comma_parts = [part.strip().lower() for part in raw.split(",")]
    if len(comma_parts) > 1 and all(part in known_city_states for part in comma_parts):
        normalized_parts = []
        for part in comma_parts:
            city, state = known_city_states[part]
            value = f"{city}, {state}, US"
            if value not in normalized_parts:
                normalized_parts.append(value)
        return "; ".join(normalized_parts)

    us_state_city = re.match(r"^US,\s*([A-Z]{2}|[A-Za-z ]+),\s*(.+)$", raw)
    if us_state_city:
        state = normalize_state(us_state_city.group(1))
        city = clean_city(us_state_city.group(2))
        return f"{city}, {state}, US" if state else f"{city}, US"

    city_state = re.match(r"^(.+?),\s*([A-Z]{2}|[A-Za-z ]+)(?:,\s*US)?$", raw)
    if city_state:
        city = clean_city(city_state.group(1))
        state = normalize_state(city_state.group(2))
        if state:
            return f"{city}, {state}, US"

    city_key = raw.lower().strip(",")
    if city_key in known_city_states:
        city, state = known_city_states[city_key]
        return f"{city}, {state}, US"
    state = normalize_state(raw)
    if state:
        return f"{state}, US"

    return raw


def display_location(location: str) -> str:
    parts = []
    for part in location.split(";"):
        cleaned = part.strip()
        if cleaned == "Remote, US":
            display = "Remote"
        elif cleaned.endswith(", US"):
            display = cleaned[:-4]
        else:
            display = cleaned
        display = re.sub(r",\s*(WA|CA|NY|DC|IL)$", "", display)
        if display and display not in parts:
            parts.append(display)
    return "; ".join(parts) or "Not listed"


def normalize_state(value: str) -> str:
    cleaned = value.strip().strip(",")
    upper = cleaned.upper()
    if upper in STATE_ABBRS:
        return upper
    return STATE_ALIASES.get(cleaned.lower(), "")


def clean_city(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip(","))


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    return [kw for kw in keywords if kw in lower]


def location_pass(location: str, description: str) -> tuple[bool, str]:
    loc = location.lower()
    allowed = any(place in loc for place in ["seattle", "redmond", "bellevue"])
    remote_us = "remote" in loc and ("united states" in loc or "us" in loc or "u.s." in loc or "usa" in loc)
    forbidden = any(place in loc for place in ["san francisco", "bay area", "new york", "nyc", "los angeles", "san mateo"])
    if remote_us:
        return True, "Remote US"
    if allowed:
        return True, "Seattle/Bellevue/Redmond"
    if forbidden:
        return False, "Location hard filter"
    return False, "No Seattle/Redmond/Bellevue/Remote US signal"


def compensation(candidate: Candidate) -> str:
    return extract_compensation(candidate.description)


def extract_compensation(text: str) -> str:
    plain = strip_html(text)
    patterns = [
        r"\$\s?[0-9][0-9,]*(?:\.[0-9]+)?\s*[Kk]\s*(?:[–—-]|to)\s*\$?\s?[0-9][0-9,]*(?:\.[0-9]+)?\s*[Kk]",
        r"\$\s?[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:[–—-]|to)\s*\$?\s?[0-9][0-9,]*(?:\.[0-9]+)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, plain, re.I)
        if match:
            return normalize_compensation(match.group(0))
    return "Not listed"


def normalize_compensation(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*(?:–|—|to|-)\s*", " - ", value, count=1, flags=re.I)
    value = value.replace("$ ", "$")
    amounts = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([Kk])?", value)
    if not amounts:
        return value
    formatted = []
    for number, suffix in amounts[:2]:
        amount = float(number.replace(",", ""))
        if suffix:
            thousands = amount
        else:
            thousands = amount / 1000 if amount >= 1000 else amount
        formatted.append(f"${round(thousands):,}k")
    if len(formatted) == 1:
        return formatted[0]
    return f"{formatted[0]} - {formatted[1]}"


def enrich_compensation(items: list[Evaluated]) -> None:
    for item in items:
        candidate = item.candidate
        if candidate.comp != "Not listed" or not candidate.url:
            continue
        try:
            page_text = fetch_text(candidate.url)
        except Exception:
            continue
        comp = extract_compensation(page_text)
        if comp == "Not listed":
            continue
        candidate.comp = comp
        if item.included and "Compensation not listed" in item.gaps:
            item.gaps = "Review scope, reporting line, and remote expectations before applying."


def evaluate(candidate: Candidate) -> Evaluated:
    title_text = candidate.title.lower()
    short_text = f"{candidate.title} {candidate.company} {candidate.location}".lower()
    text = f"{short_text} {candidate.description}".lower()
    if any(excluded in candidate.company.lower() for excluded in EXCLUDED_COMPANIES):
        return Evaluated(candidate, 0, "Discarded", False, "Excluded company", [], "")

    loc_ok, loc_reason = location_pass(candidate.location, candidate.description)
    title_domain = keyword_hits(title_text, DOMAIN_KEYWORDS)
    title_primary_domain = keyword_hits(title_text, PRIMARY_DOMAIN_KEYWORDS)
    title_seniority = keyword_hits(title_text, SENIORITY_KEYWORDS)
    title_function = keyword_hits(title_text, FUNCTION_KEYWORDS)
    domain = keyword_hits(text, DOMAIN_KEYWORDS)
    seniority = keyword_hits(text, SENIORITY_KEYWORDS)
    function = keyword_hits(text, FUNCTION_KEYWORDS)
    comp = compensation(candidate)
    candidate.comp = comp

    score = 0
    score += min(35, len(title_domain) * 14 + max(0, len(domain) - len(title_domain)) * 3)
    score += 25 if title_seniority else (12 if seniority else 0)
    score += min(20, len(title_function) * 8 + max(0, len(function) - len(title_function)) * 2)
    score += 10 if loc_ok else 0
    score += 10 if comp != "Not listed" else 0
    score = min(score, 100)

    if not loc_ok:
        return Evaluated(candidate, score, "Discarded", False, loc_reason, domain[:5], "Fails location hard filter.")
    if "engineer" in title_text and not any(term in title_text for term in ["manager", "director", "head"]):
        return Evaluated(candidate, score, "Discarded", False, "Pure engineering role", domain[:5], "Role appears to be an engineering IC role rather than TPM/T&S leadership.")
    if not title_seniority:
        return Evaluated(candidate, score, "Discarded", False, "Below seniority threshold", domain[:5], "No Director/Head/Principal/Staff signal.")
    if not title_primary_domain:
        return Evaluated(candidate, score, "Discarded", False, "Weak primary title-domain signal", domain[:5], "Title does not carry a primary trust/safety/privacy/compliance/governance signal.")
    if score < 60:
        return Evaluated(candidate, score, "Discarded", False, "Below 60% threshold", domain[:5], "Insufficient domain/function fit.")

    if score >= 90:
        band = "Strong"
    elif score >= 80:
        band = "Good"
    elif score >= 70:
        band = "Potential"
    else:
        band = "Stretch"
    tags = list(dict.fromkeys(domain[:4] + seniority[:2] + function[:2]))
    gaps = "Compensation not listed or below target." if comp == "Not listed" else "Review scope, reporting line, and remote expectations before applying."
    return Evaluated(candidate, score, band, True, "Included", tags, gaps)


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def logo_url(company: str) -> str:
    domain = COMPANY_DOMAINS.get(canonical_company(company))
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def company_logo_html(company: str, *, size: str = "h-6 w-6") -> str:
    canonical = canonical_company(company)
    url = logo_url(canonical)
    initials = "".join(part[0] for part in canonical.split()[:2]).upper()
    fallback = f'<span class="{size} rounded bg-slate-200 text-slate-700 inline-flex items-center justify-center text-[10px] font-bold">{esc(initials)}</span>'
    if not url:
        return fallback
    return (
        f'<span class="{size} relative rounded bg-slate-100 border border-slate-200 inline-flex items-center justify-center overflow-hidden text-[10px] font-bold text-slate-600">'
        f'<span aria-hidden="true">{esc(initials)}</span>'
        f'<img src="{esc(url)}" alt="{esc(canonical)} logo" class="absolute inset-0 h-full w-full object-contain bg-white" loading="lazy" '
        f'onerror="this.style.display=&quot;none&quot;">'
        "</span>"
    )


def company_name_html(company: str, *, muted: bool = False) -> str:
    text_class = "text-slate-600" if muted else "text-slate-800"
    return (
        f'<span class="inline-flex items-center gap-2 align-middle">'
        f'{company_logo_html(company)}'
        f'<span class="{text_class}">{esc(canonical_company(company))}</span>'
        f'</span>'
    )


def score_color(score: int) -> str:
    if score >= 90:
        return "text-green-700 bg-green-100"
    if score >= 80:
        return "text-sky-700 bg-sky-100"
    if score >= 70:
        return "text-amber-700 bg-amber-100"
    return "text-slate-700 bg-slate-100"


def status_color(item: Evaluated) -> str:
    if item.included:
        return score_color(item.score)
    if item.reason in {"Location hard filter", "No Seattle/Redmond/Bellevue/Remote US signal", "Pure engineering role"}:
        return "text-red-700 bg-red-100"
    if item.reason in {"Weak primary title-domain signal", "Below seniority threshold", "Below 60% threshold"}:
        return "text-amber-700 bg-amber-100"
    return "text-slate-700 bg-slate-100"


def render_card(item: Evaluated) -> str:
    c = item.candidate
    company = canonical_company(c.company)
    location = display_location(c.location)
    tags = "".join(
        f'<span class="px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-slate-600">{esc(tag)}</span>'
        for tag in item.tags[:6]
    )
    why = [
        f"{esc(company)} role contains {esc(', '.join(item.tags[:3]) or 'relevant trust/safety signals')}.",
        f"Seniority/function score maps to Kevin's T&S, privacy, GenAI trust, and TPM leadership background.",
        f"Location passes current filter: {esc(location)}.",
    ]
    why_html = "".join(f"<li>{line}</li>" for line in why)
    return f"""
      <article class="bg-white border border-slate-200 rounded-lg shadow-sm p-4">
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2 mb-1">
              <span class="px-2 py-0.5 rounded text-xs font-semibold {score_color(item.score)}">{item.score}% · {esc(item.band)}</span>
              <span class="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">Verified via {esc(c.source)}</span>
            </div>
            <h2 class="text-base sm:text-lg font-bold text-slate-900 leading-snug break-words">{esc(c.title)}</h2>
            <p class="text-sm text-slate-600 mt-1">{company_name_html(company, muted=True)} <span class="mx-1 text-slate-300">·</span> {esc(location)}</p>
          </div>
          <a href="{esc(c.url)}" target="_blank" class="shrink-0 text-center bg-slate-900 text-white text-xs font-semibold px-3 py-2 rounded hover:bg-slate-700 w-full sm:w-auto">Apply</a>
        </div>
        <div class="flex flex-wrap gap-1.5 mt-3 text-xs">{tags}</div>
        <div class="grid md:grid-cols-2 gap-3 mt-3 text-xs text-slate-600">
          <div class="bg-green-50 border border-green-100 rounded p-3">
            <p class="font-semibold text-green-700 uppercase mb-1">Why it matches</p>
            <ul class="list-disc pl-4 space-y-1">{why_html}</ul>
          </div>
          <div class="bg-red-50 border border-red-100 rounded p-3">
            <p class="font-semibold text-red-700 uppercase mb-1">Gaps</p>
            <p>{esc(item.gaps)}</p>
            <p class="mt-2">Comp: {esc(c.comp)} · Posted: {esc(c.posted or 'Active')}</p>
          </div>
        </div>
      </article>"""


def render_rows(items: list[Evaluated]) -> str:
    rows = []
    for item in items:
        c = item.candidate
        location = display_location(c.location)
        rows.append(
            f"""
            <tr class="hover:bg-slate-50" data-score="{item.score}" data-company="{esc(canonical_company(c.company).lower())}" data-role="{esc(c.title.lower())}" data-location="{esc(location.lower())}" data-comp="{esc(c.comp.lower())}" data-status="{esc((item.band if item.included else item.reason).lower())}">
              <td class="px-2 sm:px-3 py-2"><span class="px-2 py-0.5 rounded text-xs font-bold {score_color(item.score)}">{item.score}%</span></td>
              <td class="px-2 sm:px-3 py-2 whitespace-nowrap">{company_name_html(c.company)}</td>
              <td class="px-2 sm:px-3 py-2 min-w-56"><a href="{esc(c.url)}" target="_blank" class="font-medium text-slate-800 hover:text-sky-700 hover:underline">{esc(c.title)}</a></td>
              <td class="px-2 sm:px-3 py-2 min-w-40">{esc(location)}</td>
              <td class="px-2 sm:px-3 py-2 whitespace-nowrap">{esc(c.comp)}</td>
              <td class="px-2 sm:px-3 py-2 min-w-36"><span class="px-2 py-0.5 rounded text-xs font-semibold {status_color(item)}">{esc(item.band if item.included else item.reason)}</span></td>
            </tr>"""
        )
    return "\n".join(rows) or '<tr><td class="px-3 py-3 text-slate-400" colspan="6">No rows.</td></tr>'


def render_criteria() -> str:
    criteria = [
        ("Domain fit", "Trust & Safety, privacy, regulatory compliance, governance, integrity, abuse prevention, youth safety, responsible AI, and GenAI trust signals in the title and role scope."),
        ("Leadership level", "Director, VP, Head, Principal, Staff, or equivalent senior ownership. IC engineering roles are filtered unless the title clearly carries leadership or product/program ownership."),
        ("Function fit", "TPM, technical program leadership, product management, risk/compliance leadership, platform governance, and cross-functional operating roles."),
        ("Location", "Seattle, Bellevue, Redmond, or Remote US. Bay Area, NYC, LA, and other explicit non-target locations are filtered out."),
        ("Company filter", "Meta, Instagram, WhatsApp, and Reality Labs are excluded. Subsidiary names are normalized so Amazon variants render as Amazon."),
        ("Compensation", "Listed compensation is a positive signal, but missing compensation is treated as a review gap rather than an automatic reject."),
    ]
    profile = [
        "Head of TPM background across Reality Labs Trust and Instagram Trust.",
        "Deep privacy and regulatory compliance experience spanning GDPR, COPPA, AADC, DMA, developer platform compliance, and security/integrity programs.",
        "Strong fit for roles that combine executive stakeholder management, ambiguous regulatory or safety problems, platform/product governance, and AI trust/responsible AI operating models.",
        "Current target: senior trust, safety, privacy, compliance, responsible AI, and TPM/product leadership roles in Seattle-area or Remote US environments.",
    ]
    criteria_html = "".join(
        f"""
        <div class="bg-white border border-slate-200 rounded-lg p-4">
          <p class="font-semibold text-slate-900">{esc(title)}</p>
          <p class="text-sm text-slate-600 mt-1">{esc(body)}</p>
        </div>"""
        for title, body in criteria
    )
    profile_html = "".join(f"<li>{esc(item)}</li>" for item in profile)
    return f"""
      <div class="grid md:grid-cols-2 gap-3">{criteria_html}</div>
      <div class="bg-white border border-slate-200 rounded-lg p-4 mt-4">
        <p class="font-semibold text-slate-900">Kevin profile signals used</p>
        <ul class="list-disc pl-5 mt-2 space-y-1 text-sm text-slate-600">{profile_html}</ul>
      </div>
      <div class="bg-slate-900 text-white rounded-lg p-4 mt-4">
        <p class="font-semibold">Scoring model</p>
        <p class="text-sm text-slate-300 mt-1">Up to 35 points for domain match, 25 for seniority, 20 for function fit, 10 for target location, and 10 for listed compensation. Inclusion requires a passing location, seniority signal, primary title-domain signal, and at least 60% score.</p>
      </div>"""


def render_html(evaluated: list[Evaluated], errors: list[str]) -> str:
    now = dt.datetime.now(PT)
    today = now.date()
    included = sorted([item for item in evaluated if item.included], key=lambda i: i.score, reverse=True)[:12]
    discarded = sorted([item for item in evaluated if not item.included and item.score >= 35], key=lambda i: i.score, reverse=True)[:30]
    enrich_compensation(included + discarded)
    fulltime = [item for item in included if item.candidate.engagement == "full-time"]
    fractional = [item for item in included if item.candidate.engagement != "full-time"]
    strong = [item for item in fulltime if item.score >= 90]
    source_errors = "".join(f"<li>{esc(error)}</li>" for error in errors) or "<li>No source fetch errors.</li>"
    cards = "\n".join(render_card(item) for item in fulltime) or '<p class="text-sm text-slate-500 italic">No full-time roles passed filters today.</p>'
    fractional_cards = "\n".join(render_card(item) for item in fractional) or '<p class="text-sm text-slate-500 italic">No fractional or advisory roles with verified candidate-usable Apply links today.</p>'
    all_rows = render_rows(discarded)
    criteria_html = render_criteria()
    summary = (
        f"Generated from public ATS APIs across {len(GREENHOUSE) + len(LEVER) + len(ASHBY)} company boards plus Amazon Jobs search. "
        f"{len(included)} roles passed the 60% threshold and hard filters; {len(discarded)} near matches or filtered roles are listed in Filtered Out."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kevin's Daily Job Alert</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    html {{ overflow-y: scroll; scrollbar-gutter: stable; }}
    .sort-header {{ cursor: pointer; user-select: none; white-space: nowrap; }}
    .sort-header::after {{ content: "↕"; margin-left: 0.35rem; color: #94a3b8; font-size: 0.7rem; }}
    .sort-header[data-sort-dir="asc"]::after {{ content: "↑"; color: #0f172a; }}
    .sort-header[data-sort-dir="desc"]::after {{ content: "↓"; color: #0f172a; }}
  </style>
</head>
<body class="bg-slate-50 text-slate-900 antialiased">
  <header class="bg-slate-900 text-white">
    <div class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 py-5 sm:py-6">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <p class="text-slate-400 text-xs font-semibold uppercase tracking-widest">Daily Job Alert</p>
          <h1 class="text-2xl sm:text-3xl font-bold">Kevin Luu</h1>
          <p class="text-slate-400 text-sm">Trust &amp; Safety · Privacy · GenAI Trust · TPM</p>
        </div>
        <div class="sm:text-right">
          <p class="text-xl sm:text-2xl font-semibold">{today.strftime('%A, %b %-d %Y')}</p>
          <p class="text-xs text-slate-400">Generated {now.strftime('%I:%M %p')} PT · alert-date: {today.isoformat()}</p>
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3 mt-5 pt-4 border-t border-slate-700">
        <div><p class="text-xl sm:text-2xl font-bold">{len(fulltime)}</p><p class="text-xs text-slate-400">Full-time matches</p></div>
        <div><p class="text-xl sm:text-2xl font-bold text-green-400">{len(strong)}</p><p class="text-xs text-slate-400">Strong matches</p></div>
        <div><p class="text-xl sm:text-2xl font-bold text-purple-400">{len(fractional)}</p><p class="text-xs text-slate-400">Fractional &amp; Advisory matches</p></div>
        <div><p class="text-xl sm:text-2xl font-bold text-sky-400">{len(evaluated)}</p><p class="text-xs text-slate-400">Postings evaluated</p></div>
      </div>
    </div>
  </header>
  <nav class="sticky top-0 z-30 bg-slate-900 shadow-lg">
    <div class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 flex overflow-x-auto whitespace-nowrap">
      <button onclick="switchTab('fulltime')" id="tab-fulltime" class="tab-btn flex-none px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-white border-b-2 border-white">Full-Time <span>{len(fulltime)}</span></button>
      <button onclick="switchTab('fractional')" id="tab-fractional" class="tab-btn flex-none px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-slate-400 border-b-2 border-transparent">Fractional <span>{len(fractional)}</span></button>
      <button onclick="switchTab('all')" id="tab-all" class="tab-btn flex-none px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-slate-400 border-b-2 border-transparent">Filtered Out <span>{len(discarded)}</span></button>
      <button onclick="switchTab('criteria')" id="tab-criteria" class="tab-btn flex-none px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-slate-400 border-b-2 border-transparent">Criteria</button>
    </div>
  </nav>

  <div id="tab-content-fulltime" class="tab-content active">
    <main class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-5">
      <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-sm text-amber-900">{esc(summary)}</div>
      <div class="space-y-3">{cards}</div>
    </main>
  </div>

  <div id="tab-content-fractional" class="tab-content hidden">
    <main class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-5">
      <div class="space-y-3">{fractional_cards}</div>
    </main>
  </div>

  <div id="tab-content-all" class="tab-content hidden">
    <main class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-5">
      <p class="text-sm text-slate-500 mb-3">Job postings that did not make the cut from today's structured source crawl. Roles already shown in Full-Time or Fractional are omitted here.</p>
      <div class="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table id="evaluated-table" class="min-w-[760px] w-full text-[11px] sm:text-xs">
          <thead class="sticky top-12 sm:top-14 z-20 bg-slate-50 shadow-[0_1px_0_rgba(148,163,184,0.3)]"><tr><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="score" data-sort-type="number">Score</th><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="company">Company</th><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="role">Role</th><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="location">Location</th><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="comp">Comp</th><th class="sort-header text-left px-2 sm:px-3 py-2" data-sort-key="status">Status</th></tr></thead>
          <tbody id="evaluated-tbody" class="divide-y divide-slate-100">{all_rows}</tbody>
        </table>
      </div>
      <div class="mt-4 text-xs text-slate-500"><p class="font-semibold">Source fetch notes</p><ul class="list-disc pl-4">{source_errors}</ul></div>
    </main>
  </div>

  <div id="tab-content-criteria" class="tab-content hidden">
    <main class="max-w-5xl mx-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-5">
{criteria_html}
    </main>
  </div>

  <footer class="max-w-5xl mx-auto px-4 sm:px-6 pb-8 text-xs text-slate-400">
    <div class="border-t border-slate-200 pt-4 flex flex-col sm:flex-row sm:justify-between gap-2">
      <p>Filters: Seattle/Bellevue/Redmond/Remote US · Excluded: Meta · Level: Director/VP/Head/Principal/Staff · Score: ≥ 60%</p>
      <p>Generated by Codex/GitHub Actions · <a href="./archive/" class="underline">Past alerts</a></p>
    </div>
  </footer>

  <script>
    function switchTab(name) {{
      document.querySelectorAll('.tab-content').forEach(el => {{
        el.classList.add('hidden');
        el.classList.remove('active');
      }});
      document.getElementById('tab-content-' + name).classList.remove('hidden');
      document.getElementById('tab-content-' + name).classList.add('active');
      document.querySelectorAll('.tab-btn').forEach(btn => {{
        btn.classList.remove('text-white', 'border-white');
        btn.classList.add('text-slate-400', 'border-transparent');
      }});
      const active = document.getElementById('tab-' + name);
      active.classList.add('text-white', 'border-white');
      active.classList.remove('text-slate-400', 'border-transparent');
    }}

    function sortEvaluatedTable(header) {{
      const key = header.dataset.sortKey;
      const type = header.dataset.sortType || 'text';
      const tbody = document.getElementById('evaluated-tbody');
      if (!tbody) return;
      const current = header.dataset.sortDir || 'desc';
      const next = current === 'asc' ? 'desc' : 'asc';
      document.querySelectorAll('.sort-header').forEach(el => el.removeAttribute('data-sort-dir'));
      header.dataset.sortDir = next;
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {{
        const av = a.dataset[key] || '';
        const bv = b.dataset[key] || '';
        if (type === 'number') {{
          return next === 'asc' ? Number(av) - Number(bv) : Number(bv) - Number(av);
        }}
        return next === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }});
      rows.forEach(row => tbody.appendChild(row));
    }}

    document.querySelectorAll('.sort-header').forEach(header => {{
      header.addEventListener('click', () => sortEvaluatedTable(header));
    }});
  </script>
</body>
</html>
"""


def archive_index() -> str:
    files = sorted([path.name for path in ARCHIVE.glob("*.html") if path.name != "index.html"], reverse=True)
    rows = "\n".join(f'<li><a href="{esc(name)}" class="text-blue-600 hover:underline">{esc(name[:-5])}</a></li>' for name in files)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Job Alert Archive</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-50 text-slate-800 p-8"><main class="max-w-lg mx-auto"><h1 class="text-2xl font-bold mb-2">Job Alert Archive</h1><p class="text-slate-500 mb-6"><a href="../" class="text-blue-600 hover:underline">Today's alert</a></p><ul class="space-y-2 text-sm">{rows}</ul></main></body></html>"""


def main() -> int:
    ARCHIVE.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    candidates, errors = collect_candidates()
    evaluated = [evaluate(candidate) for candidate in candidates]
    html_output = render_html(evaluated, errors)
    today = dt.datetime.now(PT).date().isoformat()
    INDEX.write_text(html_output)
    (ARCHIVE / f"{today}.html").write_text(html_output)
    (ARCHIVE / "index.html").write_text(archive_index())
    manifest = {
        "date": today,
        "candidates": len(candidates),
        "included": sum(1 for item in evaluated if item.included),
        "errors": errors,
        "included_urls": [item.candidate.url for item in evaluated if item.included],
    }
    (REPORTS / f"generation-{today}.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
