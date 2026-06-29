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
