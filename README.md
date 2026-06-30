# job-alerts
Daily job alerts

## Public Feedback

The live GitHub Pages site includes an in-page Feedback form in the hamburger menu. Users do not need to be logged into GitHub.

Submissions post to the Cloudflare Worker at:

```text
https://job-alerts-feedback.bluekluu.workers.dev
```

The Worker creates GitHub Issues in `bluekluu/job-alerts` using a server-side `GITHUB_TOKEN` secret. Do not expose that token in generated HTML, repo files, prompts, or reports.

The daily generation workflow sets:

```text
JOB_ALERT_FEEDBACK_ENDPOINT=https://job-alerts-feedback.bluekluu.workers.dev
```

so regenerated pages keep the form connected. See `workers/README.md` for Worker deployment and secret maintenance.

## Issue Fixing

Issues labeled `needs-codex-fix` are the review queue for manual or locally run Codex work.

There is intentionally no hosted Codex fixer workflow in this repository because hosted Codex Actions require an OpenAI API key. Do not add workflows that require `OPENAI_API_KEY`.

Recommended operating model:

1. Review open issues labeled `needs-codex-fix`.
2. Use Codex manually from the Codex app/CLI/web, or fix directly.
3. Open a PR with `Fixes #<number>`.
4. Merge after validation. GitHub closes the linked issue.
