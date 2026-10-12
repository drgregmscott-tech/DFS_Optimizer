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
 * Cron Trigger of its own. It only relays. ALL cadences (not just the
 * near-lock window) are configured on cron-job.org (a free external cron
 * service) hitting this Worker's URL -- see setup steps below. Keeping the
 * schedule entirely on cron-job.org's UI means it's one place to adjust as
 * lock times shift week to week, no redeploy needed for a schedule change.
 *
 * WK3 postmortem §1 (2026-09-28) -- GitHub's native `schedule:` trigger in
 * refresh_data.yml, previously used for the COARSE cadences (light Vegas
 * refresh Tue-Sun, full-pipeline scheduled refresh 6x/week), was confirmed
 * unreliable beyond the "a few minutes late" caveat above: on 2026-09-27
 * its Sunday 15:05/16:05/17:05Z slots didn't fire at all -- the workflow's
 * only `schedule` runs that day landed at 18:57Z and 19:43Z, hours outside
 * every defined cron hour. The near-lock cadence below (cron-job.org ->
 * this Worker) was NOT affected -- it's an independent, already-reliable
 * path. Rather than trust GitHub's native trigger for anything, ALL three
 * cadences now go through this same cron-job.org -> Worker ->
 * repository_dispatch relay, distinguished by the `kind` query param (see
 * `fetch` below). refresh_data.yml no longer has a `schedule:` block at
 * all.
 *
 * A first attempt at this fix (2026-09-28) tried moving the coarse
 * cadences onto Cloudflare's own Cron Triggers instead of cron-job.org.
 * Abandoned before shipping: Cloudflare's Workers Free plan caps a whole
 * ACCOUNT (not just this Worker) at 5 cron triggers total, already spoken
 * for by other things on this account, and one of the 7 needed cron
 * strings ("5 15,16,17 * * 0", a 3-value comma list) was independently
 * rejected by Cloudflare's own cron parser as invalid syntax. Not worth
 * fighting either limit when cron-job.org already works and has no
 * per-job cap on its free tier -- simpler to extend the mechanism already
 * proven reliable than adopt a second one with its own new constraints.
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
 * 4. At https://cron-job.org (free account), create jobs, each a GET
 *    request to:
 *      https://<your-worker-name>.<your-subdomain>.workers.dev/?token=<the same random string as WORKER_AUTH_TOKEN>&kind=<kind>
 *
 *    REVISED 2026-10-12 (WK5 postmortem item 5) -- the near-lock cadence
 *    and the `kind=full` cadence are BOTH now replaced by one simplified,
 *    never-needs-weekly-editing job:
 *      - kind=espn_diff -- run this EVERY 10 MINUTES, EVERY DAY, ALL DAY,
 *        no time-of-day restriction needed. scripts/espn_diff_probe.py
 *        decides in code (via x_monitor_windows.compute_window(), reading
 *        data/current_slate.json) whether a given tick is inside a real
 *        pre-lock window (105 min before each lock through lock) and
 *        no-ops with zero network calls otherwise -- so this one job
 *        safely covers every week's lock times automatically, with no
 *        cron-job.org edits needed when lock times shift or DST changes.
 *        Inside a window, the script itself also decides whether THIS
 *        tick needs a full refresh (two fixed ~75-/~60-minutes-to-lock
 *        anchors, which re-pull Vegas lines -- chosen to land just after
 *        the ~90-minute official inactive report) or just a free
 *        injury-only check (every other in-window tick, escalating to a
 *        Vegas-free `scheduled_injury_refresh` only on a real detected
 *        status change for a game that hasn't kicked off yet). Inside 60
 *        minutes of lock there is deliberately no MORE automatic Vegas
 *        pull -- a real need that close to lock is a manual
 *        `gh api .../dispatches -f event_type=near_lock_refresh` call
 *        (X_INJURY_FEED_RUNBOOK.md step 4), not another automatic one.
 *        This is why the OLD `(no kind)` near-lock job and the OLD
 *        `kind=full` job (Thu/Sat/Sun/Mon scheduled full refreshes) are
 *        no longer needed -- DELETE
 *        both from cron-job.org; they're now redundant with what this one
 *        job's own per-tick logic already guarantees, and removing them
 *        is the main fix for the real finding here: one real Sunday
 *        (2026-10-11) burned ~70 of a free-tier 500-credit/month Odds API
 *        budget on Vegas pulls this one job's new logic no longer needs.
 *        See scripts/espn_diff_probe.py's docstring for the full reasoning.
 *      - kind=vegas  -- UNCHANGED, keep as-is. Light Vegas-only refresh:
 *        Tue-Fri 1x/day (~noon ET), Sat 2x/day (~11am + 5pm ET), Sun hourly
 *        (~11am-1pm ET). Cheap (a handful of Odds API credits/week) and
 *        not part of this fix.
 *      - kind=injury -- UNCHANGED, keep as-is. Saturday ~10am/1pm/4pm ET,
 *        no Vegas pull. Covers the Thu-night-to-Saturday and
 *        Saturday-to-Sunday gaps, which are outside any pre-lock window
 *        and so NOT covered by the espn_diff job above -- still needed.
 *
 * That's the whole setup -- after the one-time cron-job.org cleanup above
 * (delete the old near-lock and `kind=full` jobs, replace with a single
 * always-on `kind=espn_diff` job every 10 min), no further cron-job.org
 * edits are needed week to week, ever -- lock times, DST, and slate mix
 * are all handled in code now.
 * ---------------------------------------------------------------------
 */

async function dispatchGithubEvent(env, event_type) {
  const dispatchUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`;
  return fetch(dispatchUrl, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
      "User-Agent": "dfs-optimizer-scheduled-refresh-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type,
      client_payload: {
        fired_at_utc: new Date().toISOString(),
        source: "cloudflare_worker/scheduled_refresh.js",
      },
    }),
  });
}

// WK3 postmortem §1 -- maps the `kind` query param (cron-job.org's own
// per-job setting, not anything this file's code decides) to the
// repository_dispatch event_type refresh_data.yml's "Determine which
// cadence fired this run" step reads. Keep these three strings in sync
// with that step's case statement if either changes.
const KIND_TO_EVENT_TYPE = {
  vegas: "scheduled_vegas_refresh",
  full: "scheduled_full_refresh",
  injury: "scheduled_injury_refresh",
  espn_diff: "scheduled_espn_diff_probe",
};
const DEFAULT_EVENT_TYPE = "near_lock_refresh"; // no `kind` param = old behavior, unchanged

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

    const kindParam = url.searchParams.get("kind");
    if (kindParam && !(kindParam in KIND_TO_EVENT_TYPE)) {
      return new Response(
        `Unrecognized kind "${kindParam}" -- expected "vegas", "full", "injury", "espn_diff", or omit for near-lock.`,
        { status: 400 }
      );
    }
    const event_type = kindParam ? KIND_TO_EVENT_TYPE[kindParam] : DEFAULT_EVENT_TYPE;

    const ghResponse = await dispatchGithubEvent(env, event_type);

    // GitHub's dispatches endpoint returns 204 No Content on success, with
    // no body -- don't try to parse JSON out of that.
    if (ghResponse.status === 204) {
      return new Response(
        `OK -- dispatched ${event_type} at ${new Date().toISOString()}`,
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
