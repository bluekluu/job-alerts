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

## Codex Issue Fixer

Issues labeled `needs-codex-fix` are eligible for `.github/workflows/codex-issue-fixer.yml`.

The workflow:

1. Reads the issue.
2. Runs `openai/codex-action@v1` on a branch named `codex/issue-<number>`.
3. Validates static contracts and scripts.
4. Opens or updates a pull request with `Fixes #<number>` when code changes are made.
5. Comments back on the issue.

Required repository secret:

```text
OPENAI_API_KEY
```

The fixer does not push directly to `main` and does not auto-close issues. Issues close when the linked PR is merged.
