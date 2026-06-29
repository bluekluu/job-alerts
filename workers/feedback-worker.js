const ALLOWED_ORIGINS = new Set([
  "https://bluekluu.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);

const VALID_TYPES = new Set([
  "Bug",
  "Incorrect job result",
  "Broken link",
  "Missing role",
  "Criteria suggestion",
]);

function corsHeaders(origin) {
  const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : "https://bluekluu.github.io";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function jsonResponse(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(origin),
    },
  });
}

function clean(value, maxLength) {
  return String(value || "").trim().slice(0, maxLength);
}

function labelsFor(type) {
  const labels = ["bug", "user-feedback", "needs-codex-fix"];
  if (type === "Broken link") labels.push("link-validation");
  if (type === "Incorrect job result") labels.push("scoring-or-filtering");
  if (type === "Missing role") labels.push("source-coverage");
  if (type === "Criteria suggestion") labels.push("criteria");
  return labels;
}

function issueBody(payload) {
  const context = payload.context || {};
  return [
    "## Feedback",
    "",
    payload.details,
    "",
    "## Submitted From",
    "",
    `- Type: ${payload.type}`,
    `- Page: ${payload.page || context.url || "Not provided"}`,
    `- Active tab: ${context.activeTab || "Not captured"}`,
    `- Alert date: ${context.alertDate || "Not captured"}`,
    `- Contact: ${payload.contact || "Not provided"}`,
    "",
    "## Browser Context",
    "",
    "```json",
    JSON.stringify(context, null, 2),
    "```",
  ].join("\n");
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (request.method !== "POST") {
      return jsonResponse({ error: "Method not allowed." }, 405, origin);
    }

    if (!env.GITHUB_TOKEN) {
      return jsonResponse({ error: "Feedback service is missing GITHUB_TOKEN." }, 500, origin);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({ error: "Request body must be JSON." }, 400, origin);
    }

    const type = clean(payload.type, 80);
    const summary = clean(payload.summary, 120);
    const details = clean(payload.details, 3000);
    const page = clean(payload.page, 240);
    const contact = clean(payload.contact, 120);
    const context = typeof payload.context === "object" && payload.context ? payload.context : {};

    if (!VALID_TYPES.has(type)) {
      return jsonResponse({ error: "Feedback type is invalid." }, 400, origin);
    }
    if (summary.length < 4 || details.length < 10) {
      return jsonResponse({ error: "Summary and details are required." }, 400, origin);
    }

    const issue = {
      title: `[Feedback] ${summary}`,
      body: issueBody({ type, details, page, contact, context }),
      labels: labelsFor(type),
    };

    const response = await fetch("https://api.github.com/repos/bluekluu/job-alerts/issues", {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "job-alerts-feedback-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify(issue),
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      return jsonResponse(
        { error: result.message || "GitHub issue creation failed." },
        response.status,
        origin,
      );
    }

    return jsonResponse(
      { number: result.number, html_url: result.html_url },
      201,
      origin,
    );
  },
};
