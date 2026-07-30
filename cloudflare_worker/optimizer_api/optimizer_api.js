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
 *
 * Session 7.3 additions -- cross-device slate sync (item #2). The
 * frontend's uploaded slate previously lived only in that browser's
 * localStorage, so a slate uploaded on desktop was invisible on phone.
 * These actions store/retrieve it in the private repo instead
 * (same GitHub Contents API `fetchRepoFile` already uses for polling),
 * so any device pointed at the same Worker sees the same slate.
 *
 * Slate rework (slate-mgmt session): the old site+week integer key is
 * replaced by site+slateId (a user-defined string). This allows multiple
 * slates for the same week (main/early/afternoon), preseason slates,
 * Madden Sim slates, and Thanksgiving slates without any naming collision.
 * SlateId format: alphanumeric, hyphens, underscores only (validated).
 * Files live at data/ui_slates/{site}_{slateId}.json -- same folder,
 * same GitHub Contents API pattern, just a different naming convention.
 *
 * POST /?action=save_slate&token=<WORKER_AUTH_TOKEN>&site=dk&slate_id=classic_wk3
 *   body: { "kind": "pool"|"lineup", "filename": "...", "label": "...", "payload": <parsed rows> }
 *   -> 200 { "ok": true }
 *   Writes data/ui_slates/{site}_{slateId}.json (create or update). POST
 *   because a full player pool as a query string risks URL-length limits.
 *
 * GET /?action=load_slate&token=<WORKER_AUTH_TOKEN>&site=dk&slate_id=classic_wk3
 *   -> 200 { "found": true, "kind": ..., "filename": ..., "label": ..., "payload": ..., "savedAt": ... }
 *   -> 200 { "found": false }   (nothing saved yet for this site/slateId)
 *
 * GET /?action=list_slates&token=<WORKER_AUTH_TOKEN>
 *   -> 200 { "slates": [ { "site": "dk", "slateId": "classic_wk3", "label": "DK Classic Wk 3", "savedAt": "..." }, ... ] }
 *   Lists data/ui_slates/ directly -- returns [] if the folder doesn't
 *   exist yet (first-ever save creates it).
 *
 * DELETE /?action=delete_slate&token=<WORKER_AUTH_TOKEN>&site=dk&slate_id=classic_wk3
 *   -> 200 { "ok": true }
 *   -> 200 { "ok": true, "note": "not found" }   (already gone -- idempotent)
 *   Deletes data/ui_slates/{site}_{slateId}.json from the repo. This is
 *   the missing piece that previously made the X button re-appear after
 *   cloud list_slates re-rendered the chip list.
 *
 * GET /?action=ping&token=<WORKER_AUTH_TOKEN>
 *   -> 200 { "ok": true }
 *   Session 7.3 addition -- a deliberately trivial action that makes
 *   NO GitHub API call at all, just confirms two things in isolation:
 *   the Worker is actually deployed and reachable at this URL, and the
 *   supplied token matches. Exists so a "Failed to fetch" in the UI can
 *   be narrowed down to "wrong/undeployed URL" vs. "reachable, but a
 *   GitHub-side problem (bad PAT, wrong owner/repo)" without needing a
 *   full dispatch/save round-trip to find out.
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
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
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
  //
  // NESTED under a single `params` key rather than spread as top-level
  // client_payload properties -- GitHub's repository_dispatch endpoint
  // hard-caps client_payload at 10 top-level properties (discovered via
  // real live testing this session: a request combining stacking + lock +
  // exclude hit "422 No more than 10 properties are allowed" with the
  // flat structure). Nesting keeps client_payload at a fixed 4 top-level
  // keys (request_id, site, week, params) regardless of how many optional
  // fields are set -- run_optimizer_dispatch.yml's arg-builder reads from
  // client_payload.params accordingly.
  const passthroughKeys = [
    "mode", "n_lineups", "max_exposure", "uniqueness", "randomization_pct",
    "seed", "stack_mode", "stack_size", "stack_positions", "bring_back",
    "stack_team", "stack_game", "game_stack_min_players", "mini_stack_type",
    "stack_candidate_pool", "stack_diversify", "lock", "exclude",
    "min_salary_pct", "flex_positions",
    // Session 8 (this session) -- decisions #34/#35.
    "min_projection", "min_total_ownership",
  ];
  const params = {};
  for (const key of passthroughKeys) {
    const v = url.searchParams.get(key);
    if (v !== null && v !== "") params[key] = v;
  }
  const client_payload = { request_id, site, week, params };

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
  // chokes on those, so strip whitespace first. Also UTF-8 safe (matches
  // putRepoFile's UTF-8 safe encode below) -- found via testing that a
  // plain atob() mangles any non-ASCII byte (em-dashes, curly quotes,
  // accented names), even though it happened not to matter for this
  // project's existing plain-ASCII CSV/error.txt content.
  const decoded = decodeURIComponent(escape(atob(data.content.replace(/\s/g, ""))));
  return decoded;
}

function ghHeaders(env) {
  return {
    "Accept": "application/vnd.github+json",
    "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
    "User-Agent": "dfs-optimizer-api-worker",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

// Session 7.3 -- create-or-update a repo file via the Contents API's
// standard flow: GET first to find the existing sha (required by GitHub
// for an update, omitted entirely for a brand-new file), then PUT.
async function putRepoFile(env, path, contentText, message) {
  const apiUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${path}`;
  let sha;
  const getRes = await fetch(apiUrl, { headers: ghHeaders(env) });
  if (getRes.status === 200) {
    sha = (await getRes.json()).sha;
  } else if (getRes.status !== 404) {
    throw new Error(`GitHub contents API GET failed for ${path} (status ${getRes.status}): ${await getRes.text()}`);
  }
  // UTF-8-safe base64 encode (btoa alone chokes on non-Latin1 chars --
  // player names are ASCII in practice, but this is cheap insurance).
  const b64 = btoa(unescape(encodeURIComponent(contentText)));
  const body = { message, content: b64, branch: "main" };
  if (sha) body.sha = sha;
  const putRes = await fetch(apiUrl, {
    method: "PUT",
    headers: { ...ghHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!putRes.ok) {
    throw new Error(`GitHub contents API PUT failed for ${path} (status ${putRes.status}): ${await putRes.text()}`);
  }
}

async function listRepoDir(env, dirPath) {
  const apiUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${dirPath}`;
  const res = await fetch(apiUrl, { headers: ghHeaders(env) });
  if (res.status === 404) return []; // folder doesn't exist yet -- no slates saved anywhere yet
  if (!res.ok) {
    throw new Error(`GitHub contents API list failed for ${dirPath} (status ${res.status}): ${await res.text()}`);
  }
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

// site and slateId land directly in a GitHub API path -- validate against
// known-safe shapes rather than trusting query-string input verbatim.
// SlateId: alphanumeric, hyphens, underscores, 1-64 chars.
function validSite(site) {
  return site === "dk" || site === "fd";
}
function validSlateId(slateId) {
  return typeof slateId === "string" && /^[a-zA-Z0-9_-]{1,64}$/.test(slateId);
}

async function handleSaveSlate(request, url, env) {
  const site = url.searchParams.get("site");
  const slateId = url.searchParams.get("slate_id");
  if (!validSite(site) || !validSlateId(slateId)) {
    return json({ error: "site must be dk/fd and slate_id must be 1-64 alphanumeric/hyphen/underscore chars." }, 400);
  }
  if (!env.GH_DISPATCH_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Worker is missing required secrets/env vars -- see this file's setup header." }, 500);
  }
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return json({ error: "Request body must be JSON." }, 400);
  }
  if (!body || (body.kind !== "pool" && body.kind !== "lineup") || body.payload === undefined) {
    return json({ error: "Body must include kind ('pool' or 'lineup') and payload." }, 400);
  }
  const record = {
    kind: body.kind,
    filename: body.filename || "",
    label: body.label || slateId,
    week: body.week || "1",
    payload: body.payload,
    savedAt: new Date().toISOString(),
  };
  try {
    await putRepoFile(
      env, `data/ui_slates/${site}_${slateId}.json`, JSON.stringify(record),
      `UI slate save: ${site} ${slateId} [skip ci]`,
    );
  } catch (err) {
    return json({ error: `Save failed: ${err.message}` }, 502);
  }
  return json({ ok: true });
}

async function handleLoadSlate(url, env) {
  const site = url.searchParams.get("site");
  const slateId = url.searchParams.get("slate_id");
  if (!validSite(site) || !validSlateId(slateId)) {
    return json({ error: "site must be dk/fd and slate_id must be 1-64 alphanumeric/hyphen/underscore chars." }, 400);
  }
  try {
    const text = await fetchRepoFile(env, `data/ui_slates/${site}_${slateId}.json`);
    if (text === null) return json({ found: false });
    return json({ found: true, ...JSON.parse(text) });
  } catch (err) {
    return json({ error: `Load failed: ${err.message}` }, 502);
  }
}

async function handleListSlates(env) {
  try {
    const entries = await listRepoDir(env, "data/ui_slates");
    const slates = [];
    for (const entry of entries) {
      if (!entry.name.endsWith(".json")) continue;
      // Parse "{site}_{slateId}.json" -- site is "dk" or "fd" (no underscore),
      // so the first underscore is always the delimiter.
      const base = entry.name.slice(0, -5);
      const sep = base.indexOf("_");
      if (sep === -1) continue;
      const site = base.slice(0, sep);
      const slateId = base.slice(sep + 1);
      if (!validSite(site) || !validSlateId(slateId)) continue;
      // No per-file fetches -- that's N+1 GitHub API calls and causes
      // timeouts on the free Worker plan. label is stored in the frontend's
      // localStorage index for local slates; for cross-device slates the
      // frontend falls back to slateId as the display label.
      slates.push({ site, slateId });
    }
    return json({ slates });
  } catch (err) {
    return json({ error: `List failed: ${err.message}` }, 502);
  }
}

async function handleDeleteSlate(url, env) {
  const site = url.searchParams.get("site");
  const slateId = url.searchParams.get("slate_id");
  if (!validSite(site) || !validSlateId(slateId)) {
    return json({ error: "site must be dk/fd and slate_id must be 1-64 alphanumeric/hyphen/underscore chars." }, 400);
  }
  if (!env.GH_DISPATCH_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Worker is missing required secrets/env vars." }, 500);
  }
  const path = `data/ui_slates/${site}_${slateId}.json`;
  const apiUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${path}`;
  // GET to find the SHA (required by GitHub's DELETE endpoint).
  const getRes = await fetch(apiUrl, { headers: ghHeaders(env) });
  if (getRes.status === 404) {
    return json({ ok: true, note: "not found" }); // idempotent -- already gone
  }
  if (!getRes.ok) {
    return json({ error: `Delete pre-check failed (status ${getRes.status})` }, 502);
  }
  const sha = (await getRes.json()).sha;
  const delRes = await fetch(apiUrl, {
    method: "DELETE",
    headers: { ...ghHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify({
      message: `UI slate delete: ${site} ${slateId} [skip ci]`,
      sha,
      branch: "main",
    }),
  });
  if (!delRes.ok) {
    return json({ error: `Delete failed (status ${delRes.status}): ${await delRes.text()}` }, 502);
  }
  return json({ ok: true });
}

// Presets are stored as a single JSON object at data/ui_presets.json.
// Shape: { presetName: { ctrlNLineups: "10", ... }, ... }
// Shared across all devices that have the same Worker token.

async function handleGetPresets(env) {
  try {
    const text = await fetchRepoFile(env, "data/ui_presets.json");
    if (text === null) return json({ presets: {} });
    return json({ presets: JSON.parse(text) });
  } catch (err) {
    return json({ error: `Get presets failed: ${err.message}` }, 502);
  }
}

async function handleSavePresets(request, env) {
  if (!env.GH_DISPATCH_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Worker is missing required secrets/env vars." }, 500);
  }
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return json({ error: "Request body must be JSON." }, 400);
  }
  if (!body || typeof body.presets !== "object") {
    return json({ error: "Body must include presets object." }, 400);
  }
  try {
    await putRepoFile(
      env, "data/ui_presets.json", JSON.stringify(body.presets, null, 1),
      "UI preset save [skip ci]",
    );
  } catch (err) {
    return json({ error: `Save presets failed: ${err.message}` }, 502);
  }
  return json({ ok: true });
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
      // Preflight for CORS -- browsers send this before DELETE and POST.
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    const url = new URL(request.url);
    const action = url.searchParams.get("action");

    // POST actions carry large payloads in body; DELETE for slate removal.
    const postActions = ["save_slate", "save_presets"];
    const deleteActions = ["delete_slate"];
    const methodOk =
      request.method === "GET" ||
      (request.method === "POST" && postActions.includes(action)) ||
      (request.method === "DELETE" && deleteActions.includes(action));
    if (!methodOk) {
      return json({ error: "Method not allowed." }, 405);
    }
    if (!auth(request, env)) {
      return json({ error: "Unauthorized." }, 401);
    }

    if (action === "dispatch") return handleDispatch(url, env);
    if (action === "poll") return handlePoll(url, env);
    if (action === "save_slate") return handleSaveSlate(request, url, env);
    if (action === "load_slate") return handleLoadSlate(url, env);
    if (action === "list_slates") return handleListSlates(env);
    if (action === "delete_slate") return handleDeleteSlate(url, env);
    if (action === "get_presets") return handleGetPresets(env);
    if (action === "save_presets") return handleSavePresets(request, env);
    if (action === "ping") return json({ ok: true }); // deliberately no GitHub call -- see docstring
    return json({ error: "action must be 'dispatch', 'poll', 'save_slate', 'load_slate', 'list_slates', 'delete_slate', 'get_presets', 'save_presets', or 'ping'." }, 400);
  },
};
