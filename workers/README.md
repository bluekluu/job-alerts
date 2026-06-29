# Feedback Worker

The live JobAlerts page is hosted on GitHub Pages, so browser JavaScript cannot safely create GitHub Issues directly. This Cloudflare Worker receives public feedback form submissions and creates issues server-side with a GitHub token stored as a Worker secret.

Required Worker secret:

```bash
wrangler secret put GITHUB_TOKEN
```

The token only needs access to create issues in `bluekluu/job-alerts`.

Generate the site with the Worker URL:

```bash
JOB_ALERT_FEEDBACK_ENDPOINT="https://<worker-name>.<account>.workers.dev" python3 scripts/job_alert_generate.py
```

Then validate, commit, and push the generated page.
