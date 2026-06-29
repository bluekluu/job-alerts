# Feedback Worker

The live JobAlerts page is hosted on GitHub Pages, so browser JavaScript cannot safely create GitHub Issues directly. This Cloudflare Worker receives public feedback form submissions and creates issues server-side with a GitHub token stored as a Worker secret.

Production Worker:

```text
https://job-alerts-feedback.bluekluu.workers.dev
```

Required Worker secret:

```bash
npx wrangler secret put GITHUB_TOKEN --name job-alerts-feedback
```

The token only needs access to create issues in `bluekluu/job-alerts`.

Generate the site with the Worker URL:

```bash
JOB_ALERT_FEEDBACK_ENDPOINT="https://job-alerts-feedback.bluekluu.workers.dev" python3 scripts/job_alert_generate.py
```

The `Daily Generate` and `Criteria Update` workflows set `JOB_ALERT_FEEDBACK_ENDPOINT` so scheduled regenerations keep the live feedback form wired to this Worker.

To redeploy Worker code:

```bash
npx wrangler deploy
```

Do not commit `.wrangler/`; it contains local Cloudflare account cache data and is ignored.
