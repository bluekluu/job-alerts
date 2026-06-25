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
        key = candidate.url or f"{candidate.company}:{candidate.title}:{candidate.location}"
        if not candidate.title or not candidate.url or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


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
    text = candidate.description
    match = re.search(r"\$[0-9]{2,3}(?:,[0-9]{3})?K?\s*[–-]\s*\$?[0-9]{2,3}(?:,[0-9]{3})?K?", text, re.I)
    if match:
        return match.group(0)
    match = re.search(r"\$[0-9]{3},000\s*[–-]\s*\$?[0-9]{3},000", text, re.I)
    if match:
        return match.group(0)
    return "Not listed"


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


def score_color(score: int) -> str:
    if score >= 90:
        return "text-green-700 bg-green-100"
    if score >= 80:
        return "text-sky-700 bg-sky-100"
    if score >= 70:
        return "text-amber-700 bg-amber-100"
    return "text-slate-700 bg-slate-100"


def render_card(item: Evaluated) -> str:
    c = item.candidate
    tags = "".join(
        f'<span class="px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-slate-600">{esc(tag)}</span>'
        for tag in item.tags[:6]
    )
    why = [
        f"{esc(c.company)} role contains {esc(', '.join(item.tags[:3]) or 'relevant trust/safety signals')}.",
        f"Seniority/function score maps to Kevin's T&S, privacy, GenAI trust, and TPM leadership background.",
        f"Location passes current filter: {esc(c.location)}.",
    ]
    why_html = "".join(f"<li>{line}</li>" for line in why)
    return f"""
      <article class="bg-white border border-slate-200 rounded-lg shadow-sm p-4">
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2 mb-1">
              <span class="px-2 py-0.5 rounded text-xs font-semibold {score_color(item.score)}">{item.score}% · {esc(item.band)}</span>
              <span class="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">Verified via {esc(c.source)}</span>
            </div>
            <h2 class="text-lg font-bold text-slate-900">{esc(c.title)}</h2>
            <p class="text-sm text-slate-600">{esc(c.company)} · {esc(c.location)}</p>
          </div>
          <a href="{esc(c.url)}" target="_blank" class="shrink-0 text-center bg-slate-900 text-white text-xs font-semibold px-3 py-2 rounded hover:bg-slate-700">Apply</a>
        </div>
        <div class="flex flex-wrap gap-1.5 mt-3 text-xs">{tags}</div>
        <div class="grid sm:grid-cols-2 gap-3 mt-3 text-xs text-slate-600">
          <div class="bg-slate-50 rounded p-3">
            <p class="font-semibold text-slate-500 uppercase mb-1">Why it matches</p>
            <ul class="list-disc pl-4 space-y-1">{why_html}</ul>
          </div>
          <div class="bg-slate-50 rounded p-3">
            <p class="font-semibold text-slate-500 uppercase mb-1">Gaps</p>
            <p>{esc(item.gaps)}</p>
            <p class="mt-2">Comp: {esc(c.comp)} · Posted: {esc(c.posted or 'Active')}</p>
          </div>
        </div>
      </article>"""


def render_rows(items: list[Evaluated]) -> str:
    rows = []
    for item in items:
        c = item.candidate
        rows.append(
            f"""
            <tr class="hover:bg-slate-50">
              <td class="px-3 py-2 font-bold">{item.score}%</td>
              <td class="px-3 py-2"><a href="{esc(c.url)}" target="_blank" class="font-medium text-slate-800 hover:text-sky-700 hover:underline">{esc(c.company)} · {esc(c.title)}</a></td>
              <td class="px-3 py-2 hidden sm:table-cell">{esc(c.location)}</td>
              <td class="px-3 py-2 hidden md:table-cell">{esc(c.comp)}</td>
              <td class="px-3 py-2">{esc(item.band if item.included else item.reason)}</td>
            </tr>"""
        )
    return "\n".join(rows) or '<tr><td class="px-3 py-3 text-slate-400" colspan="5">No rows.</td></tr>'


def render_html(evaluated: list[Evaluated], errors: list[str]) -> str:
    now = dt.datetime.now(PT)
    today = now.date()
    included = sorted([item for item in evaluated if item.included], key=lambda i: i.score, reverse=True)[:12]
    discarded = sorted([item for item in evaluated if not item.included and item.score >= 35], key=lambda i: i.score, reverse=True)[:30]
    fulltime = [item for item in included if item.candidate.engagement == "full-time"]
    fractional = [item for item in included if item.candidate.engagement != "full-time"]
    strong = [item for item in fulltime if item.score >= 90]
    source_errors = "".join(f"<li>{esc(error)}</li>" for error in errors) or "<li>No source fetch errors.</li>"
    cards = "\n".join(render_card(item) for item in fulltime) or '<p class="text-sm text-slate-500 italic">No full-time roles passed filters today.</p>'
    fractional_cards = "\n".join(render_card(item) for item in fractional) or '<p class="text-sm text-slate-500 italic">No fractional or advisory roles with verified candidate-usable Apply links today.</p>'
    all_rows = render_rows(included + discarded)
    summary = (
        f"Generated from public ATS APIs across {len(GREENHOUSE) + len(LEVER) + len(ASHBY)} company boards plus Amazon Jobs search. "
        f"{len(included)} roles passed the 60% threshold and hard filters; {len(discarded)} near matches or filtered roles are listed in All Evaluated."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kevin's Daily Job Alert</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <header class="bg-slate-900 text-white">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 py-6">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <p class="text-slate-400 text-xs font-semibold uppercase tracking-widest">Daily Job Alert</p>
          <h1 class="text-3xl font-bold">Kevin Luu</h1>
          <p class="text-slate-400 text-sm">Trust &amp; Safety · Privacy · GenAI Trust · TPM</p>
        </div>
        <div class="sm:text-right">
          <p class="text-2xl font-semibold">{today.strftime('%A, %b %-d %Y')}</p>
          <p class="text-xs text-slate-400">Generated {now.strftime('%I:%M %p')} PT · alert-date: {today.isoformat()}</p>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-slate-700">
        <div><p class="text-2xl font-bold">{len(fulltime)}</p><p class="text-xs text-slate-400">Full-time matches</p></div>
        <div><p class="text-2xl font-bold text-green-400">{len(strong)}</p><p class="text-xs text-slate-400">Strong matches</p></div>
        <div><p class="text-2xl font-bold text-purple-400">{len(fractional)}</p><p class="text-xs text-slate-400">Fractional &amp; Advisory matches</p></div>
        <div><p class="text-2xl font-bold text-sky-400">{len(evaluated)}</p><p class="text-xs text-slate-400">Postings evaluated</p></div>
      </div>
    </div>
    <div class="max-w-5xl mx-auto px-4 sm:px-6 flex">
      <button onclick="switchTab('fulltime')" id="tab-fulltime" class="tab-btn px-4 py-3 text-sm font-semibold text-white border-b-2 border-white">Full-Time Roles <span>{len(fulltime)}</span></button>
      <button onclick="switchTab('fractional')" id="tab-fractional" class="tab-btn px-4 py-3 text-sm font-semibold text-slate-400 border-b-2 border-transparent">Fractional &amp; Advisory <span>{len(fractional)}</span></button>
      <button onclick="switchTab('all')" id="tab-all" class="tab-btn px-4 py-3 text-sm font-semibold text-slate-400 border-b-2 border-transparent">All Evaluated <span>{len(included) + len(discarded)}</span></button>
    </div>
  </header>

  <div id="tab-content-fulltime" class="tab-content active">
    <main class="max-w-5xl mx-auto px-4 sm:px-6 py-5">
      <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-sm text-amber-900">{esc(summary)}</div>
      <div class="space-y-3">{cards}</div>
    </main>
  </div>

  <div id="tab-content-fractional" class="tab-content hidden">
    <main class="max-w-5xl mx-auto px-4 sm:px-6 py-5">
      <div class="space-y-3">{fractional_cards}</div>
    </main>
  </div>

  <div id="tab-content-all" class="tab-content hidden">
    <main class="max-w-5xl mx-auto px-4 sm:px-6 py-5">
      <p class="text-sm text-slate-500 mb-3">Included, discarded, and filtered roles from today's structured source crawl.</p>
      <div class="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table class="w-full text-xs">
          <thead class="bg-slate-50"><tr><th class="text-left px-3 py-2">Score</th><th class="text-left px-3 py-2">Company · Role</th><th class="text-left px-3 py-2 hidden sm:table-cell">Location</th><th class="text-left px-3 py-2 hidden md:table-cell">Comp</th><th class="text-left px-3 py-2">Status</th></tr></thead>
          <tbody class="divide-y divide-slate-100">{all_rows}</tbody>
        </table>
      </div>
      <div class="mt-4 text-xs text-slate-500"><p class="font-semibold">Source fetch notes</p><ul class="list-disc pl-4">{source_errors}</ul></div>
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
