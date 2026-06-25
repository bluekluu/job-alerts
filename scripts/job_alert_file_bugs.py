#!/usr/bin/env python3
"""File GitHub issues from the latest Job Alerts test report.

Default mode is a dry run. Use --apply to create or update GitHub issues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports"
REPO = "bluekluu/job-alerts"
PUBLIC_URL = "https://bluekluu.github.io/job-alerts/"


@dataclass(frozen=True)
class Finding:
    testcase_id: str
    testcase_title: str
    severity: str
    area: str
    evidence: str
    report_path: Path

    @property
    def fingerprint(self) -> str:
        normalized = re.sub(r"\s+", " ", f"{self.testcase_id} {self.evidence}").strip().lower()
        return hashlib.sha1(normalized.encode()).hexdigest()[:16]

    @property
    def title(self) -> str:
        summary = summarize_evidence(self.evidence)
        return truncate(f"[{self.severity.upper()}] {summary}", 120)

    @property
    def labels(self) -> list[str]:
        return ["bug", "codex-filed", "needs-codex-fix", self.severity, self.area]


def run_gh(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def latest_report() -> Path:
    reports = sorted(REPORT_DIR.glob("*.md"))
    if not reports:
        raise FileNotFoundError(f"No test reports found in {REPORT_DIR}")
    return reports[-1]


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        _, _, rest = text.partition("\n---\n")
        return rest
    return text


def parse_bullets(block: str) -> list[str]:
    bullets = []
    for line in block.splitlines():
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if item and item.lower() != "none":
            bullets.append(item)
    return bullets


def parse_findings(report_path: Path) -> list[Finding]:
    text = strip_frontmatter(report_path.read_text())
    findings: list[Finding] = []
    section_pattern = re.compile(
        r"^###\s+(TC-[A-Z0-9-]+):\s+(.+?)\n\n"
        r"Result:\s+\*\*(FAIL|PASS)\*\*"
        r"(?P<body>.*?)(?=^###\s+TC-|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    failure_pattern = re.compile(
        r"Failure Details:\n\n(?P<failures>.*?)(?=\n\nPassing Details:|\n\n## |\Z)",
        re.DOTALL,
    )

    for match in section_pattern.finditer(text):
        result = match.group(3)
        if result != "FAIL":
            continue
        testcase_id = match.group(1)
        testcase_title = match.group(2).strip()
        failure_match = failure_pattern.search(match.group("body"))
        if not failure_match:
            continue
        for evidence in parse_bullets(failure_match.group("failures")):
            findings.append(
                Finding(
                    testcase_id=testcase_id,
                    testcase_title=testcase_title,
                    severity=severity_for(testcase_id, evidence),
                    area=area_for(testcase_id, testcase_title, evidence),
                    evidence=evidence,
                    report_path=report_path,
                )
            )
    return findings


def severity_for(testcase_id: str, evidence: str) -> str:
    if "P0" in testcase_id:
        return "p0"
    if "P1" in testcase_id:
        return "p1"
    if any(marker in evidence.lower() for marker in ["404", "403", "broken", "wrong weekday"]):
        return "p1"
    return "p2"


def area_for(testcase_id: str, title: str, evidence: str) -> str:
    combined = f"{testcase_id} {title} {evidence}".lower()
    if "date" in combined or "weekday" in combined:
        return "area:date"
    if "link" in combined or "url" in combined or "http" in combined:
        return "area:links"
    if "filter" in combined or "location" in combined or "score" in combined:
        return "area:filters"
    if "publish" in combined or "archive" in combined:
        return "area:publishing"
    return "area:template"


def summarize_evidence(evidence: str) -> str:
    lower = evidence.lower()
    if " — " in evidence:
        prefix = evidence.split(" — ", 1)[0]
        if "full-time roles" in lower or "fractional & advisory" in lower:
            url = trailing_url(evidence)
            if url:
                parsed = urlparse(url)
                path = parsed.path.strip("/") or parsed.netloc
                target = f"{parsed.netloc}/{path}" if path != parsed.netloc else parsed.netloc
                return f"Job Alerts broken included link: {prefix} - {target}"
            return f"Job Alerts broken included link: {prefix}"
    if "reason says" in lower:
        subject = evidence.split(": reason says", 1)[0]
        return f"Job Alerts reason mismatch: {subject}"
    if "date" in lower or "weekday" in lower:
        return "Job Alerts date rendering is incorrect"
    return f"Job Alerts validation failure: {evidence}"


def trailing_url(value: str) -> str:
    match = re.search(r"https?://\S+\s*$", value)
    return match.group(0) if match else ""


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def issue_body(finding: Finding) -> str:
    report_rel = finding.report_path.relative_to(REPO_ROOT)
    return f"""<!-- job-alert-bug:{finding.fingerprint} -->

## Observed

{finding.evidence}

## Expected

The daily Job Alerts page should satisfy `{finding.testcase_id}: {finding.testcase_title}`.

## Reproduction

1. Open {PUBLIC_URL}
2. Run the smoke test:

```bash
python3 scripts/job_alert_test_report.py
```

3. Inspect `{report_rel}`.

## Source Report

- Report: `{report_rel}`
- Test case: `{finding.testcase_id}`
- Filed by: Codex QA
- Fingerprint: `{finding.fingerprint}`

## Fix Guidance

Make the smallest change that fixes the underlying generation, validation, or publishing behavior. Prefer preventing the bad card/status from being generated over patching only the rendered HTML after publication.
"""


def existing_codex_issues() -> dict[str, dict[str, object]]:
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            REPO,
            "--label",
            "codex-filed",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,body,url",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    issues = {}
    for issue in json.loads(result.stdout or "[]"):
        body = issue.get("body") or ""
        match = re.search(r"job-alert-bug:([a-f0-9]{16})", body)
        if match:
            issues[match.group(1)] = issue
    return issues


def write_temp_body(body: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", delete=False, suffix=".md")
    with handle:
        handle.write(body)
    return Path(handle.name)


def create_issue(finding: Finding, body: str) -> str:
    body_path = write_temp_body(body)
    try:
        result = run_gh(
            [
                "issue",
                "create",
                "--repo",
                REPO,
                "--title",
                finding.title,
                "--body-file",
                str(body_path),
                "--label",
                ",".join(finding.labels),
            ]
        )
    finally:
        body_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def comment_existing(issue_number: int, finding: Finding) -> None:
    today = dt.date.today().isoformat()
    body = f"""Codex QA observed this failure again on {today}.

Latest evidence:

{finding.evidence}

Fingerprint: `{finding.fingerprint}`
"""
    result = run_gh(
        ["issue", "comment", str(issue_number), "--repo", REPO, "--body", body]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def ensure_gh_available() -> None:
    result = run_gh(["auth", "status"])
    if result.returncode != 0:
        raise RuntimeError("GitHub CLI is not authenticated. Run `gh auth login` first.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None, help="Path to a specific test report")
    parser.add_argument("--apply", action="store_true", help="Create/comment on GitHub issues")
    parser.add_argument("--mention-claude", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--comment-existing", action="store_true", help="Comment when an open duplicate already exists")
    args = parser.parse_args()

    report_path = args.report or latest_report()
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()

    findings = parse_findings(report_path)
    if not findings:
        print(f"No failing test-case findings found in {report_path.relative_to(REPO_ROOT)}")
        return 0

    print(f"Report: {report_path.relative_to(REPO_ROOT)}")
    print(f"Findings: {len(findings)}")

    if not args.apply:
        for finding in findings:
            print(f"DRY RUN create/update: {finding.title}")
            print(f"  labels: {', '.join(finding.labels)}")
            print(f"  fingerprint: {finding.fingerprint}")
        print("\nDry run only. Re-run with --apply to create or update GitHub issues.")
        return 0

    ensure_gh_available()
    existing = existing_codex_issues()
    created = 0
    updated = 0
    skipped = 0

    for finding in findings:
        existing_issue = existing.get(finding.fingerprint)
        if existing_issue:
            number = int(existing_issue["number"])
            if args.comment_existing:
                comment_existing(number, finding)
                updated += 1
                print(f"Updated existing issue #{number}: {existing_issue['title']}")
            else:
                skipped += 1
                print(f"Skipped existing issue #{number}: {existing_issue['title']}")
            continue

        url = create_issue(finding, issue_body(finding))
        created += 1
        print(f"Created: {url}")

    print(f"Done. created={created} updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
