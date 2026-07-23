/**
 * optimizer_api.js
 * =================
 *
 * Session 7.2b -- UI-Optimizer Integration (real-solver dispatch path).
 *
 * WHY THIS EXISTS: the frontend (Session 7.1) is a static, client-only page
 * with no server of its own and no stored credentials -- it can never hold
 * a GitHub token (a private repo's raw files are not publicly fetchable,
 * and a token embedded in shipped JS would be world-readable). This Worker
 * is the credentialed middle layer: it holds the SAME `GH_DISPATCH_TOKEN`
 * secret Session 5.2's scheduled_refresh.js already uses, and does two
 * things with it that a static page cannot do on its own:
 *
 *   1. DISPATCH -- fire a `repository_dispatch` event (type
 *      `run_optimizer_request`) carrying the UI's current controls
 *      (site/week/exposure/uniqueness/stacking/lock/exclude) as
 *      `client_payload`, which run_optimizer_dispatch.yml picks up and
 *      runs through the real, already-validated `optimizer.py`. Returns a
 *      `request_id` immediately -- this endpoint does NOT wait for the
 *      Action to finish (GitHub Actions cold start + solve is commonly
 *      30-90+ seconds, see this session's architecture discussion).
 *
 *   2. POLL -- given a `request_id`, use the GitHub Contents API
 *      (authenticated, works against a private repo) to check whether
 *      `output/ui_requests/{request_id}.csv` (success) or
 *      `output/ui_requests/{request_id}.error.txt` (optimizer.py raised)
 *      exists yet, and return its content directly -- so the frontend never
 *      needs its own GitHub credentials to read the private repo's result.
 *
 * This is a SEPARATE Worker from scheduled_refresh.js on purpose (own
 * subfolder, own wrangler.toml) -- that Worker's own header describes
 * itself as "a thin, fast, reliable relay" that "does NOT run any Python,
 * touch the repo's data, or have a Cron Trigger of its own." This Worker's
 * job (reading private repo contents back out, not just firing a dispatch)
 * is a genuinely different responsibility -- keeping them separate means
 * neither file's scope drifts from what its own header claims.
 *
 * ---------------------------------------------------------------------
 * ONE-TIME SETUP (mirrors scheduled_refresh.js's own setup steps):
 *
 * 1. Deploy this Worker (from this directory, via Wrangler):
 *      npx wrangler deploy optimizer_api.js
 *    Or paste into the Cloudflare dashboard -> Workers & Pages -> Create
 *    -> Worker -> Edit code. Name it, e.g. "dfs-optimizer-api".
 *
 * 2. Reuse the SAME GitHub PAT from Session 5.2's scheduled_refresh.js
 *    setup (it already has "Contents: Read and write" on this repo, which
 *    is everything this Worker needs -- no new PAT/scopes required) as a
 *    secret on THIS Worker too (secrets do not share across Workers, even
 *    same account):
 *      npx wrangler secret put GH_DISPATCH_TOKEN     (same PAT value)
 *      npx wrangler secret put WORKER_AUTH_TOKEN      (can reuse the same
 *                                                       random string as
 *                                                       scheduled_refresh.js
 *                                                       or generate a new
 *                                                       one -- either is
 *                                                       fine, they're
 *                                                       independent Workers)
 *    And two plain (non-secret) environment variables (already set in this
 *    directory's wrangler.toml, no action needed unless the repo moves):
 *      GITHUB_OWNER = drgregmscott-tech
 *      GITHUB_REPO  = DFS_Optimizer
 *
 * 3. Note the deployed URL (e.g. https://dfs-optimizer-api.<subdomain>.
 *    workers.dev) -- Session 7.2c's frontend JS calls this directly.
 *
 * That's the whole setup -- no cron-job.org needed here (unlike
 * scheduled_refresh.js), every call is triggered live by a UI action.
 * ---------------------------------------------------------------------
 *
 * API
 * ---
 * GET /?action=dispatch&token=<WORKER_AUTH_TOKEN>&site=dk&week=10
 *     [&mode=single|multi&n_lineups=&max_exposure=&uniqueness=
 *      &randomization_pct=&seed=&stack_mode=&stack_size=&stack_positions=
 *      &bring_back=true&stack_team=&stack_game=&game_stack_min_players=
 *      &mini_stack_type=&stack_candidate_pool=&stack_diversify=
 *      &lock=id1,id2&exclude=id3,id4]
 *   -> 200 { "request_id": "<uuid>" }
 *   Every param besides token/site/week is OPTIONAL and passed through
 *   unchanged to run_optimizer_dispatch.yml, which itself only sets a CLI
 *   flag when the field is present (decision, see that file) -- this
 *   Worker never invents a default on the UI's behalf.
 *
 * GET /?action=poll&token=<WORKER_AUTH_TOKEN>&request_id=<uuid>
 *   -> 200 { "status": "complete", "csv": "<raw csv text>" }
 *   -> 200 { "status": "error", "message": "<text>" }
 *   -> 200 { "status": "pending" }   (neither file exists yet -- keep polling)
 */

const POLL_PENDING_RETRY_HINT_MS = 4000; // suggested to the client, not enforced server-side

function auth(request, env) {
  const url = new URL(request.url);
  const suppliedToken = url.searchParams.get("token");
  return env.WORKER_AUTH_TOKEN && suppliedToken === env.WORKER_AUTH_TOKEN;
}

function corsHeaders() {
  // The frontend is a public static page calling this Worker cross-origin.
  // Auth is the shared-secret token param (same pattern as
  // scheduled_refresh.js), not CORS restriction -- CORS here only affects
  // which *browsers* will let JS read the response, not who can call the
  // endpoint at all (that's true of any public Worker URL regardless of
  // this header).
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
  };
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

async function handleDispatch(url, env) {
  const site = url.searchParams.get("site");
  const week = url.searchParams.get("week");
  if (!site || !week) {
    return json({ error: "site and week are required." }, 400);
  }
  if (!env.GH_DISPATCH_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json(
      { error: "Worker is missing required secrets/env vars (GH_DISPATCH_TOKEN, GITHUB_OWNER, GITHUB_REPO) -- see this file's setup header." },
      500,
    );
  }

  const request_id = crypto.randomUUID();

  // Pass through every recognized param as-is; omit anything not supplied
  // so run_optimizer_dispatch.yml's own per-field defaulting (mirroring
  // optimizer.py's own CLI defaults) applies unchanged.
  const passthroughKeys = [
    "mode", "n_lineups", "max_exposure", "uniqueness", "randomization_pct",
    "seed", "stack_mode", "stack_size", "stack_positions", "bring_back",
    "stack_team", "stack_game", "game_stack_min_players", "mini_stack_type",
    "stack_candidate_pool", "stack_diversify", "lock", "exclude",
  ];
  const client_payload = { request_id, site, week };
  for (const key of passthroughKeys) {
    const v = url.searchParams.get(key);
    if (v !== null && v !== "") client_payload[key] = v;
  }

  const dispatchUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`;
  const ghResponse = await fetch(dispatchUrl, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
      "User-Agent": "dfs-optimizer-api-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: "run_optimizer_request",
      client_payload,
    }),
  });

  if (ghResponse.status !== 204) {
    const errorBody = await ghResponse.text();
    return json({ error: `GitHub dispatch failed (status ${ghResponse.status}): ${errorBody}` }, 502);
  }

  return json({ request_id, poll_retry_hint_ms: POLL_PENDING_RETRY_HINT_MS });
}

async function fetchRepoFile(env, path) {
  const contentsUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${path}`;
  const res = await fetch(contentsUrl, {
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
      "User-Agent": "dfs-optimizer-api-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`GitHub contents API failed for ${path} (status ${res.status}): ${await res.text()}`);
  }
  const data = await res.json();
  // Contents API returns base64 with embedded newlines -- atob() alone
  // chokes on those, so strip whitespace first.
  const decoded = atob(data.content.replace(/\s/g, ""));
  return decoded;
}

async function handlePoll(url, env) {
  const request_id = url.searchParams.get("request_id");
  if (!request_id) {
    return json({ error: "request_id is required." }, 400);
  }
  if (!/^[a-zA-Z0-9-]+$/.test(request_id)) {
    // request_id always comes from crypto.randomUUID() on our own dispatch
    // path -- reject anything else outright rather than building a GitHub
    // API path out of unvalidated input.
    return json({ error: "invalid request_id format." }, 400);
  }

  try {
    const errorText = await fetchRepoFile(env, `output/ui_requests/${request_id}.error.txt`);
    if (errorText !== null) {
      return json({ status: "error", message: errorText.trim() });
    }
    const csv = await fetchRepoFile(env, `output/ui_requests/${request_id}.csv`);
    if (csv !== null) {
      return json({ status: "complete", csv });
    }
    return json({ status: "pending", poll_retry_hint_ms: POLL_PENDING_RETRY_HINT_MS });
  } catch (err) {
    return json({ error: `Poll failed: ${err.message}` }, 502);
  }
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }
    if (request.method !== "GET") {
      return json({ error: "Method not allowed -- use GET." }, 405);
    }
    if (!auth(request, env)) {
      return json({ error: "Unauthorized." }, 401);
    }

    const url = new URL(request.url);
    const action = url.searchParams.get("action");
    if (action === "dispatch") return handleDispatch(url, env);
    if (action === "poll") return handlePoll(url, env);
    return json({ error: "action must be 'dispatch' or 'poll'." }, 400);
  },
};
