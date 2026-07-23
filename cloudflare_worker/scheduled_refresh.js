/**
 * scheduled_refresh.js
 * =====================
 *
 * Session 5.2 -- Scheduling Infrastructure.
 *
 * WHY THIS EXISTS (see refresh_data.yml's header + SESSION_LOG.md's Session
 * 5.2 entry for the fuller reasoning already discussed with the user):
 * GitHub Actions' own `schedule:` cron is fine for coarse, non-time-critical
 * cadences (every 3 hours, once/day, etc.) but is documented to sometimes
 * fire several minutes late under GitHub-side load. That's not acceptable
 * for the actual near-lock window (last hour before a DK/FD slate locks),
 * where refresh_data.yml's card calls for ~10-minute granularity. This
 * Worker is a thin, fast, reliable relay that turns an external HTTP ping
 * into a GitHub `repository_dispatch` event, which triggers
 * refresh_data.yml's `full_refresh_dispatch` path immediately.
 *
 * This Worker does NOT run any Python, touch the repo's data, or have a
 * Cron Trigger of its own. It only relays. The actual "every ~10 minutes,
 * only during the near-lock window" cadence is configured on cron-job.org
 * (a free external cron service) hitting this Worker's URL -- see setup
 * steps below. Splitting it this way means the tight-window schedule lives
 * in one place (cron-job.org's UI, easy to adjust week to week as lock
 * times shift) rather than being redeployed into this file every time.
 *
 * ---------------------------------------------------------------------
 * ONE-TIME SETUP (all done outside this file -- nothing here needs edits
 * for normal weekly use):
 *
 * 1. Deploy this Worker (from this directory, via Wrangler):
 *      npx wrangler init --from-dot-env=false   (if not already a project)
 *      npx wrangler deploy scheduled_refresh.js
 *    Or paste this file's contents directly into the Cloudflare dashboard
 *    at https://dash.cloudflare.com -> Workers & Pages -> Create -> Worker
 *    -> Edit code. Give it a name, e.g. "dfs-optimizer-scheduler".
 *
 * 2. Create a GitHub Personal Access Token (fine-grained, scoped to just
 *    this repo, "Contents: Read and write" + "Metadata: Read-only" is
 *    enough for repository_dispatch) at
 *    https://github.com/settings/tokens
 *
 * 3. Set three Worker secrets (Cloudflare dashboard -> your Worker ->
 *    Settings -> Variables -> "Encrypt" each one -- or via Wrangler:
 *      npx wrangler secret put GH_DISPATCH_TOKEN     (the PAT from step 2)
 *      npx wrangler secret put WORKER_AUTH_TOKEN      (any random string
 *                                                       you generate --
 *                                                       this is what stops
 *                                                       a random internet
 *                                                       request from
 *                                                       triggering your
 *                                                       pipeline)
 *    And two plain (non-secret) environment variables:
 *      GITHUB_OWNER = drgregmscott-tech
 *      GITHUB_REPO  = DFS_Optimizer
 *
 * 4. At https://cron-job.org (free account), create a job per near-lock
 *    window you want covered (e.g. one for DK's Sunday early-slate lock,
 *    one for FD's if it differs) that sends a GET request every ~10
 *    minutes, ONLY during that window, to:
 *      https://<your-worker-name>.<your-subdomain>.workers.dev/?token=<the same random string as WORKER_AUTH_TOKEN>
 *    cron-job.org supports both a time-of-day range AND day-of-week, so
 *    this can be set to fire only Sun 4:00pm-5:00pm ET (adjust per actual
 *    lock time each week) rather than running all week.
 *
 * That's the whole setup -- after this, the tight cadence is entirely
 * controlled from cron-job.org's UI, no redeploy needed to shift a lock
 * time.
 * ---------------------------------------------------------------------
 */

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "GET") {
      return new Response("Method not allowed -- use GET.", { status: 405 });
    }

    // Auth: a shared-secret query param, checked against the WORKER_AUTH_TOKEN
    // secret. This Worker's URL is otherwise public (Cloudflare Workers don't
    // have a built-in private mode), so this is the only thing stopping an
    // unrelated request from spamming GitHub dispatch events / burning CI
    // minutes.
    const url = new URL(request.url);
    const suppliedToken = url.searchParams.get("token");
    if (!env.WORKER_AUTH_TOKEN || suppliedToken !== env.WORKER_AUTH_TOKEN) {
      return new Response("Unauthorized.", { status: 401 });
    }

    if (!env.GH_DISPATCH_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
      return new Response(
        "Worker is missing required secrets/env vars (GH_DISPATCH_TOKEN, GITHUB_OWNER, GITHUB_REPO) -- see this file's setup header.",
        { status: 500 }
      );
    }

    const dispatchUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`;

    const ghResponse = await fetch(dispatchUrl, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
        "User-Agent": "dfs-optimizer-scheduled-refresh-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        event_type: "near_lock_refresh",
        client_payload: {
          fired_at_utc: new Date().toISOString(),
          source: "cloudflare_worker/scheduled_refresh.js",
        },
      }),
    });

    // GitHub's dispatches endpoint returns 204 No Content on success, with
    // no body -- don't try to parse JSON out of that.
    if (ghResponse.status === 204) {
      return new Response(
        `OK -- dispatched near_lock_refresh at ${new Date().toISOString()}`,
        { status: 200 }
      );
    }

    const errorBody = await ghResponse.text();
    return new Response(
      `GitHub dispatch failed (status ${ghResponse.status}): ${errorBody}`,
      { status: 502 }
    );
  },
};
