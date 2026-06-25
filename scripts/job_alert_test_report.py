#!/usr/bin/env python3
"""Run Job Alerts smoke tests and write a dated Obsidian report."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports"
PUBLIC_URL = "https://bluekluu.github.io/job-alerts/"
PT = ZoneInfo("America/Los_Angeles")

PLACEHOLDERS = [
    "TODAY_DATE",
    "GENERATION_TIME",
    "FULLTIME_COUNT",
    "STRONG_FULLTIME_COUNT",
    "FRACTIONAL_COUNT",
    "FT_CRAWLED_COUNT",
    "FA_CRAWLED_COUNT",
    "SUMMARY_NOTE",
    "APPLY_URL",
]

AGGREGATOR_DOMAINS = [
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "bebee.com",
    "ziprecruiter.com",
    "theladders.com",
]

TAB_IDS = [
    ("Full-Time Roles", "tab-content-fulltime"),
    ("Fractional & Advisory", "tab-content-fractional"),
    ("All Evaluated", "tab-content-all"),
]
LINK_VALIDATION_TAB_IDS = [
    ("Full-Time Roles", "tab-content-fulltime"),
    ("Fractional & Advisory", "tab-content-fractional"),
]

BAD_DATE_STRINGS = [
    "Monday, Jun 16 2026",
    "Monday Jun 16, 2026",
    "Monday, June 16 2026",
    "Monday June 16, 2026",
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        data = {key: value or "" for key, value in attrs}
        if data.get("href", "").startswith("http"):
            self._current = data
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            self._current["text"] = " ".join(t for t in self._text if t)
            self.links.append(self._current)
            self._current = None
            self._text = []


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, str]]] = []
        self._row: list[dict[str, str]] | None = None
        self._cell_text: list[str] = []
        self._cell_href = ""
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._in_cell = True
            self._cell_text = []
            self._cell_href = ""
        elif tag == "a" and self._in_cell and not self._cell_href:
            self._cell_href = data.get("href", "")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            cleaned = data.strip()
            if cleaned:
                self._cell_text.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._in_cell and self._row is not None:
            self._row.append({"text": " ".join(self._cell_text), "href": self._cell_href})
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def fetch_url(url: str, timeout: int = 25) -> tuple[str, int | None, str]:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "--max-time",
            str(timeout),
            "-A",
            "Mozilla/5.0",
            "-sS",
            "-w",
            "\n__HTTP_STATUS__:%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    marker = "\n__HTTP_STATUS__:"
    body, _, status_text = result.stdout.rpartition(marker)
    status = int(status_text.strip()) if status_text.strip().isdigit() else None
    if result.returncode != 0:
        return body, status, result.stderr.strip()
    return body, status, ""


def link_status(url: str) -> tuple[bool, str]:
    if any(domain in url.lower() for domain in AGGREGATOR_DOMAINS):
        return False, "aggregator URL"

    result = subprocess.run(
        [
            "curl",
            "-L",
            "--max-time",
            "20",
            "-A",
            "Mozilla/5.0",
            "-sS",
            "-w",
            "\n__FINAL_URL__:%{url_effective}\n__HTTP_CODE__:%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "curl failed"

    body = result.stdout
    final_url = ""
    http_code = ""
    final_marker = "\n__FINAL_URL__:"
    code_marker = "\n__HTTP_CODE__:"
    if final_marker in body and code_marker in body:
        body, _, tail = body.rpartition(final_marker)
        final_url, _, http_code = tail.partition(code_marker)
        final_url = final_url.strip()
        http_code = http_code.strip()

    if not re.match(r"2\d\d$", http_code):
        return False, f"HTTP {http_code or 'NO_STATUS'} final_url={final_url or 'unknown'}"

    lower_body = body.lower()
    lower_final_url = final_url.lower()
    bad_final_url_markers = [
        "error=true",
        "/404",
        "not-found",
        "not_found",
        "job-not-found",
    ]
    for marker in bad_final_url_markers:
        if marker in lower_final_url:
            return False, f"HTTP {http_code} but final URL is error page: {final_url}"

    original_job_id = re.search(r"/jobs?/(\d+)", url)
    if original_job_id and original_job_id.group(1) not in final_url:
        return False, f"HTTP {http_code} but final URL lost job id {original_job_id.group(1)}: {final_url}"

    bad_body_markers = [
        "isjobpost\":false",
        "error=true",
        "job not found",
        "job no longer available",
        "no longer accepting applications",
        "this job is closed",
        "position has been filled",
        "page not found",
        "404 not found",
    ]
    for marker in bad_body_markers:
        if marker in lower_body:
            return False, f"HTTP {http_code} but page content indicates broken/closed job ({marker}) final_url={final_url}"

    return True, f"HTTP {http_code} final_url={final_url}"


def apply_links(html: str) -> list[dict[str, str]]:
    parser = LinkParser()
    parser.feed(html)
    links = []
    for link in parser.links:
        text = link.get("text", "").lower()
        klass = link.get("class", "").lower()
        if "apply" in text or "apply" in klass:
            links.append(link)
    return links


def tab_sections(html: str) -> dict[str, str]:
    positions = []
    for label, tab_id in TAB_IDS:
        match = re.search(rf'id=["\']{re.escape(tab_id)}["\']', html)
        if match:
            positions.append((match.start(), label, tab_id))
    positions.sort()

    sections: dict[str, str] = {}
    for index, (start, label, _) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(html)
        sections[label] = html[start:end]
    return sections


def job_links_for_tab(tab_html: str) -> list[dict[str, str]]:
    parser = LinkParser()
    parser.feed(tab_html)
    links = []
    for link in parser.links:
        href = link.get("href", "")
        text = link.get("text", "")
        combined = f"{href} {text}".lower()
        if not href.startswith("http"):
            continue
        if any(domain in href.lower() for domain in AGGREGATOR_DOMAINS):
            links.append(link)
            continue
        if "apply" in combined or "jobs" in combined or "careers" in combined:
            links.append(link)
    return links


def tab_job_links(html: str) -> dict[str, list[dict[str, str]]]:
    return {label: job_links_for_tab(section) for label, section in tab_sections(html).items()}


def all_evaluated_reason_rows(html: str) -> list[dict[str, str]]:
    section = tab_sections(html).get("All Evaluated", "")
    parser = TableParser()
    parser.feed(section)
    rows = []
    active_headers: list[str] = []

    for row in parser.rows:
        texts = [cell["text"] for cell in row]
        lowered = [text.lower() for text in texts]
        if any(label in lowered for label in ["reason discarded", "filter failed", "what happened"]):
            active_headers = lowered
            continue
        if not active_headers or len(row) < 3:
            continue
        reason_index = None
        for candidate in ("reason discarded", "filter failed", "what happened"):
            if candidate in active_headers:
                reason_index = active_headers.index(candidate)
                break
        if reason_index is None or reason_index >= len(row):
            continue
        role = row[0]["text"]
        href = row[0]["href"]
        reason = row[reason_index]["text"]
        if role and reason:
            rows.append({"role": role, "href": href, "reason": reason})
    return rows


def reason_contradiction(row: dict[str, str], status_ok: bool | None, status: str) -> str | None:
    reason = row["reason"].lower()
    href = row["href"]
    role = row["role"]
    if not href:
        return None

    claims_broken_link = any(
        marker in reason
        for marker in [
            "returned 403",
            "return 403",
            "blocked",
            "inaccessible",
            "no working direct link",
            "no alternative direct url worked",
            "unverifiable",
            "posting removed",
            "confirmed closed",
            "expired",
        ]
    )
    if claims_broken_link and status_ok:
        return f"{role}: reason says link is blocked/closed/unverifiable, but validator found live link: `{status}` — {href}"

    claims_403 = "403" in reason
    if claims_403 and "403" not in status:
        return f"{role}: reason says 403, but validator did not observe 403: `{status}` — {href}"

    claims_closed = any(marker in reason for marker in ["closed", "expired", "removed"])
    if claims_closed and status_ok:
        return f"{role}: reason says closed/expired/removed, but validator found live link: `{status}` — {href}"

    return None


def weekday_date_failures(html: str, today: dt.date) -> list[str]:
    failures = []
    expected = today.strftime("%A, %b %-d %Y")
    if expected not in html:
        failures.append(f"Missing expected date string: {expected}")

    for bad in BAD_DATE_STRINGS:
        if bad in html:
            failures.append(f"Incorrect weekday/date combination found: {bad}")

    pattern = re.compile(
        r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
        r"(\d{1,2}),?\s+(\d{4})\b"
    )
    for match in pattern.finditer(html):
        weekday, month, day, year = match.groups()
        date_value = dt.datetime.strptime(f"{month} {int(day)} {year}", "%b %d %Y").date()
        actual = date_value.strftime("%A")
        if weekday != actual:
            failures.append(f"Date string has wrong weekday: {match.group(0)} should be {actual}")
    return failures


def check_html(name: str, html: str, today: dt.date, minimum_size: int = 10000) -> tuple[list[str], list[str]]:
    failures = []
    passes = []

    if len(html) >= minimum_size:
        passes.append(f"{name}: HTML size is {len(html)} bytes")
    else:
        failures.append(f"{name}: HTML too small ({len(html)} bytes)")

    for required in ['id="tab-content-fulltime"', 'id="tab-content-fractional"', 'id="tab-content-all"']:
        if required in html:
            passes.append(f"{name}: found `{required}`")
        else:
            failures.append(f"{name}: missing `{required}`")

    found_placeholders = [token for token in PLACEHOLDERS if token in html]
    if found_placeholders:
        failures.append(f"{name}: unreplaced placeholders present: {', '.join(found_placeholders)}")
    else:
        passes.append(f"{name}: no configured placeholders found")

    date_failures = weekday_date_failures(html, today)
    if date_failures:
        failures.extend(f"{name}: {failure}" for failure in date_failures)
    else:
        passes.append(f"{name}: weekday/date strings are calendar-correct")

    return failures, passes


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def sentence_list(items: list[str], limit: int = 3) -> str:
    if not items:
        return "None."
    shown = items[:limit]
    suffix = "" if len(items) <= limit else f" Plus {len(items) - limit} more."
    return " ".join(shown) + suffix


def main() -> int:
    now = dt.datetime.now(PT)
    today = now.date()
    today_iso = today.isoformat()
    REPORT_DIR.mkdir(exist_ok=True)
    report_path = REPORT_DIR / f"{today_iso}.md"

    fetch_notes: list[str] = []

    public_html, public_status, public_error = fetch_url(PUBLIC_URL)
    fetch_notes.append(f"Public GitHub Pages: status={public_status or 'ERROR'} {public_error}".strip())

    failures: list[str] = []
    passes: list[str] = []
    date_case_failures: list[str] = []
    date_case_passes: list[str] = []

    html_failures, html_passes = check_html("Live GitHub Pages", public_html, today)
    failures.extend(html_failures)
    passes.extend(html_passes)
    date_failures = weekday_date_failures(public_html, today)
    if date_failures:
        date_case_failures.extend(f"Live GitHub Pages: {failure}" for failure in date_failures)
    else:
        date_case_passes.append("Live GitHub Pages: weekday/date strings are calendar-correct")

    seen_urls: set[str] = set()
    link_status_cache: dict[str, tuple[bool, str]] = {}
    link_results: list[str] = []
    link_case_failures: list[str] = []
    link_case_passes: list[str] = []
    tab_link_results: list[str] = []
    links_by_tab = tab_job_links(public_html)
    found_tab_labels = set(links_by_tab)
    for label, tab_id in LINK_VALIDATION_TAB_IDS:
        if label not in found_tab_labels:
            failures.append(f"Public GitHub Pages: missing `{tab_id}` section for {label}")
            link_case_failures.append(f"{label}: missing `{tab_id}` section")
            continue

        tab_links = links_by_tab[label]
        if not tab_links:
            failures.append(f"Public GitHub Pages: no job posting links found in {label} tab")
            link_case_failures.append(f"{label}: no job posting links found")
            continue

        passes.append(f"Public GitHub Pages: found {len(tab_links)} job posting links in {label} tab")
        tab_link_results.append(f"{label}: {len(tab_links)} job posting links checked")

        for link in tab_links:
            url = link["href"]
            tab_key = f"{label}|{url}"
            if tab_key in seen_urls:
                continue
            seen_urls.add(tab_key)
            ok, status = link_status_cache.setdefault(url, link_status(url))
            link_text = link.get("text", "").strip() or "Job link"
            result_line = f"{label} — {link_text}: `{status}` — {url}"
            link_results.append(result_line)
            if ok:
                passes.append(f"{label} link OK: {url}")
                link_case_passes.append(result_line)
            else:
                failures.append(f"{label} link failed: {url} ({status})")
                link_case_failures.append(result_line)

    unique_checked_urls = {line.rsplit(" — ", 1)[-1] for line in link_results}
    if not unique_checked_urls:
        failures.append("Public GitHub Pages: no job posting links found across Full-Time Roles or Fractional & Advisory tabs")
        link_case_failures.append("No job posting links found across Full-Time Roles or Fractional & Advisory")

    # Backward-compatible summary for included Apply buttons.
    public_apply_links = apply_links(public_html)
    if public_apply_links:
        passes.append(f"Public GitHub Pages: found {len(public_apply_links)} included Apply links")
    else:
        passes.append("Public GitHub Pages: no explicit Apply-button links found; tab-level job links were still checked")

    reason_results: list[str] = []
    reason_case_failures: list[str] = []
    reason_case_passes: list[str] = []
    reason_rows = all_evaluated_reason_rows(public_html)
    if not reason_rows:
        reason_case_failures.append("No All Evaluated rows with reason/status text were found")
    for row in reason_rows:
        href = row["href"]
        if not href:
            reason_case_passes.append(f"{row['role']}: no direct row link to verify; reason recorded as `{row['reason']}`")
            continue
        ok, observed = link_status_cache.setdefault(href, link_status(href))
        contradiction = reason_contradiction(row, ok, observed)
        result_line = f"{row['role']}: reason=`{row['reason']}`; observed=`{observed}`; url={href}"
        reason_results.append(result_line)
        if contradiction:
            reason_case_failures.append(contradiction)
            failures.append(f"All Evaluated reason mismatch: {contradiction}")
        else:
            reason_case_passes.append(result_line)

    status = "FAIL" if failures else "PASS"
    date_case_status = "FAIL" if date_case_failures else "PASS"
    link_case_status = "FAIL" if not unique_checked_urls or link_case_failures else "PASS"
    reason_case_status = "FAIL" if reason_case_failures else "PASS"
    date_case_actual = (
        f"{len(date_case_failures)} live-page date check(s) failed; "
        f"{len(date_case_passes)} live-page date check(s) passed."
    )
    date_case_why = (
        "This test is marked FAIL because the live page has a missing or incorrect expected date string."
        if date_case_failures
        else "This test is marked PASS because the live page contains the expected date string and every visible weekday/date pair is calendar-correct."
    )
    link_case_failures_for_report = list(link_case_failures)
    if not unique_checked_urls:
        link_case_failures_for_report.append("No job posting links found on the public page")
    link_case_actual = (
        f"{len(unique_checked_urls)} unique job posting URL(s) checked across tabs; "
        f"{len(link_case_failures_for_report)} failure(s); "
        f"{len(link_case_passes)} pass(es)."
    )
    link_case_why = (
        "This test is marked FAIL because at least one job posting link is broken, blocked, not job-specific, or points to an error/closed-job page."
        if link_case_failures_for_report
        else "This test is marked PASS because every checked job posting link in the Full-Time Roles and Fractional & Advisory tabs resolved to a live direct company or ATS page."
    )
    reason_case_actual = (
        f"{len(reason_rows)} All Evaluated reason row(s) inspected; "
        f"{len(reason_case_failures)} contradiction(s); "
        f"{len(reason_case_passes)} non-contradicting row(s)."
    )
    reason_case_why = (
        "This test is marked FAIL because at least one All Evaluated row's reason contradicts the observed link behavior."
        if reason_case_failures
        else "This test is marked PASS because no All Evaluated reason contradicted the observed link behavior."
    )
    title = f"Job Alerts Test Report - {today_iso}"
    generated = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    report = f"""---
title: {title}
created: {today_iso}
status: active
tags: [job-search, automation, testing, daily-test-report, codex]
area:
---

# {title}

Generated: {generated}

Overall result: **{status}**

## Scope

Automated daily smoke test for [[test-plan]], focused on the recurring P0 regressions:

- Calendar-correct page date and weekday.
- Live, direct, non-broken Apply links.

Source under test: `{PUBLIC_URL}`

## Specific Regression Test Cases

### TC-P0-DATE-001: Weekday/date must be calendar-correct

Result: **{date_case_status}**

Expected:

- Today's page date must render as `{today.strftime("%A, %b %-d %Y")}`.
- The weekday must be computed from the calendar date, not inferred or copied from an example.
- The known bad regression strings must never appear: `{", ".join(BAD_DATE_STRINGS)}`.

Actual Summary:

{date_case_actual}

Why this is **{date_case_status}**:

{date_case_why}

Failure Details:

{markdown_list(date_case_failures)}

Passing Details:

{markdown_list(date_case_passes)}

### TC-P0-LINK-001: Job links in Full-Time Roles and Fractional & Advisory must be valid and not broken

Result: **{link_case_status}**

Expected:

- Every job posting link in Full-Time Roles and Fractional & Advisory must resolve through redirects to a direct company or ATS page.
- All Evaluated links are excluded from this test and are covered by `TC-P0-REASON-001` when the reason/status text makes a link-status claim.
- `404`, `410`, `403`, `5xx`, timeout, DNS/TLS failure, expired posting, and aggregator links are failures.
- `Could not verify` is not acceptable for an included card.

Actual Summary:

{link_case_actual}

Why this is **{link_case_status}**:

{link_case_why}

Failure Details:

{markdown_list(link_case_failures_for_report)}

Passing Details:

{markdown_list(link_case_passes)}

### TC-P0-REASON-001: All Evaluated discard/status reasons must match observed link behavior

Result: **{reason_case_status}**

Expected:

- If the All Evaluated reason says a link returned `403`, was blocked, was closed, or had no working direct URL, the validator should observe the same kind of failure.
- A row is a failure if its reason says the link is blocked/closed/unverifiable but the live link validates successfully.
- This check currently verifies link-status claims in the reason text; location, level, compensation, and policy-fit claims may still require separate semantic checks.

Actual Summary:

{reason_case_actual}

Why this is **{reason_case_status}**:

{reason_case_why}

Failure Details:

{markdown_list(reason_case_failures)}

Passing Details:

{markdown_list(reason_case_passes)}

## Fetch Results

{markdown_list(fetch_notes)}

## Failures

{markdown_list(failures)}

## Passing Checks

{markdown_list(passes)}

## Job Posting Link Results

{markdown_list(link_results)}

## All Evaluated Reason Results

{markdown_list(reason_results)}

## Tab Link Coverage

{markdown_list(tab_link_results)}

## Next Actions

{"- Fix blocking failures before relying on the daily alert." if failures else "- No blocking failures found by this smoke test."}
"""
    report_path.write_text(report)
    print(f"Report written to: {report_path.relative_to(REPO_ROOT)}")
    print(f"Overall result: {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
