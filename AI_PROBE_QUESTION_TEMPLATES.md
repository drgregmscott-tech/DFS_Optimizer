# AI Chat Probe — Standard Question Templates

Draft set, organized by the gap category each one addresses (see conversation
2026-10-28/29 for how this list was built). Each question is meant to be
asked of a live-search-capable LLM chat (Claude.ai, Gemini, or later the
Claude/Gemini API with web search). Placeholders in `[BRACKETS]` get filled
from our own data (e.g. players with `role_change_injury_flag`,
`q_return_flag`, or `own_vacated` set, or just the week's full slate).

Every template ends with the same freshness check, because our own test
showed an LLM can confidently answer from stale/wrong premises (the
Etienne-to-Saints miss): **always append** "Please confirm this reflects
news from the current week, and name your source/date — if you're not
confident it's current, say so rather than guessing."

**Correction, 2026-10-31 — how a probe answer actually gets cross-checked.**
A separate probe session caught the cross-check step drifting into the
wrong thing: real lineup-pool exposure (how many of 100 built lineups
include a player) was being used as a reason to thumbs-up/down him. That's
wrong — exposure is an emergent property of the solver's salary-cap
combinatorics across the WHOLE pool, not a read on whether a single
player's projection is accurate. It's a different question, and
conflating the two is how the Bourne/Treadwell investigations almost
reached the wrong conclusion before being reframed.

The actual loop: pull every specific claim out of a probe answer (who
benefits if X sits, a usage/role-trend call, an explicit over/under-
projection opinion, a "good matchup"/"trap matchup" read) and check EACH
ONE directly against that exact player's own data in
`output/final_projections_*.csv` — never against exposure:
- Beneficiary/usage claims → `probe_team_usage_rank.py` (real trailing
  target/carry share).
- Production/over-under claims → `season_avg` / `recent_form`.
- Matchup-trap claims → **correction, 2026-10-31, check this per
  POSITION, not slate-wide**: `matchup_factor` is exactly 1.0 for every
  QB/RB/WR/TE (deliberate, tested — `build_projections_statline.py:1155`
  hard-overrides it; see `project_role_step_up_bias_and_matchup_revisit`
  memory for the Oct 26 re-test that kept it off). It only varies for
  DST. A slate-wide check without filtering by position wrongly looks
  like it varies everywhere, because DST's real variation gets mixed in.
  **For a skill-position trap-matchup claim, there is no live
  matchup-specific signal to check it against at all** — `vegas_factor`
  is the only thing available, and it's game script/total only, not real
  matchup specificity. Say that plainly rather than treating vegas_factor
  as equivalent.
- Game-environment claims → `vegas_factor` / `implied_total`.

Verdict per claim: **agree** / **disagree-overprojected** /
**disagree-underprojected** / **trap-confirmed** / **trap-not-confirmed**.
The thumbs-up/down list comes from these verdicts, not from exposure.

**Closing report format, correction 2026-11-02 (WK8 postmortem Item C).**
The cross-check's final answer is a frontend action list, not a narrative
verdict-by-verdict writeup. A report that reads as "I agree with the chat's
read, here's why our numbers support it" leaves the user re-reading prose
to infer what to click — that's the gap this fixes. Every cross-check
session must end with exactly these three lists (empty lists are fine —
write "none" rather than omitting the heading):

**Thumbs up:** [player — one-line reason, e.g. "disagree-underprojected:
recent_form trending up, probe's usage-trend claim checks out"]
**Thumbs down:** [player — one-line reason, e.g.
"disagree-overprojected: season_avg running well below our projection"]
**Exclude (high-risk trap):** [player — one-line reason, e.g.
"trap-confirmed: vegas_factor shows game script works against him"]

Map from verdict to action: **agree** → no action (already reflected in
our numbers, don't touch). **disagree-underprojected** → thumbs up.
**disagree-overprojected** → thumbs down. **trap-confirmed** → exclude.
**trap-not-confirmed** → no action. The narrative verdict-by-verdict
writeup can still precede the lists for context, but the lists are
mandatory and must be the last thing in the report.

**Fourth list, added 2026-11-07 — "Checked, no bust-risk flag."** Every
player who was specifically named in the Fringe-value or Build-derived
sections below (i.e. a real candidate we deliberately asked about, not
every player on the slate) and resolved to **agree** or
**trap-not-confirmed** goes here instead of being silently dropped. This
is NOT a "safe" or "low risk" claim — it means exactly one thing: nothing
in the probe's own claims about him, checked against our data, raised a
red flag this week. Without this list, a salary-saver that was actually
vetted and came back clean looks identical to one that was never checked
at all, which defeats the point of asking about him in the first place.

**Follow-up correction, same day:** the fringe-value/matchup-trap
questions below (E3, sharpened F2) were first drafted as open,
unnamed questions. That's the wrong shape — open "what's good value"
questions have been the *weakest*-performing category all session
(generic, hard to verify, prone to stale/pattern-matched answers); named
questions about a specific player have been the *strongest* (same
pattern as B/C). Fixed in `probe_ai_chat_weekly_questions.py`: it now
runs `probe_cheap_value_finder.py`'s `candidates_by_position()` first and
fans the usage-trend and matchup-trap questions out onto those exact
names (top 3 per position, DK, by pts/$1000 efficiency) instead of
asking an open question. Our own data picks the candidates; the chat
verifies usage trend + trap risk on exactly those names. The templates
below (E3, F2) describe the underlying idea; the generator script is the
actual source of truth for how they're asked now.

**Relevance filtering — two different mechanisms, used where each fits:**

1. **Open/discovery templates** (we don't hand the model a pre-picked name
   list: A1, D2, F1/F2, G1, H1) — **always append** a relevance qualifier:
   "Limit this to DFS-relevant situations — rosterable/salaried players
   with a realistic path to meaningful snaps, not deep backups or
   practice-squad depth." The model's own judgment does the filtering
   here; no extraction work needed on our side.
2. **Name-supplying templates** (we pick specific players/teams to ask
   about: B, C, D1) — the qualifier can't undo a name we already put in
   the question, so filtering has to happen on our side, before we build
   the list:
   - **C** (next-man-up): filter `OUT` players to only those whose absence
     produced a nonzero `own_vac_bump` on a teammate — i.e. our own
     pipeline already decided the vacancy moved something. Checked
     against the live Wk8 file: raw `OUT` count was 58, but only 5
     distinct teams had a real `own_vac_bump` consequence (and the chain
     checks out — Davante Adams `OUT` is the actual driver behind Puka
     Nacua's bump). That's the list C1/C2 get built from, not all 58.
     **Correction, 2026-11-09 (WK9 Item F):** this filter has a confirmed
     blind spot for WR/TE — `own_vac_bump` only fires on a *fresh* (k=1)
     OUT, so a sustained multi-week absence (a player OUT for several
     weeks running, never "freshly" OUT) shows zero bump even when the
     real-world vacancy is obvious (SF's Wk9 Jordan Watkins case: Evans/
     Samuel/Kirk/Pearsall all out by different weeks, zero bump, zero
     `wrw_wr_delta_pts`, but Watkins was literally SF's only real WR
     volume). **Add a second, separate check alongside the `own_vac_bump`
     filter for WR/TE**: any team where 2+ WR/TE are OUT/IR regardless of
     bump value, so a sustained-absence case isn't silently dropped from
     C1/C2 the way the pipeline's own vacancy credit drops it. RB doesn't
     need this — it already has the k≥2 decay extension and real
     `own_vac_bump` signal to filter on.
   - **B / D1**: filter by a salary floor (~$4500 RB/WR/TE, ~$5000 QB, DST
     excluded) applied to `QUESTIONABLE`/`DOUBTFUL` players (B) or the
     active pool (D1). On the live Wk8 file this trimmed `QUESTIONABLE`
     from 23 down to 13 real names (Amon-Ra St. Brown, Lamar Jackson,
     Rashee Rice, etc.) by dropping scrubs the floor isn't rosterable
     anyway.

Feeds: **P** = projection track (production inputs), **O** = ownership
track (field-perception inputs), **P+O** = both.

**Correction, 2026-11-09 (WK9 Item G, gated on D/E/F) — what's now real
signal vs. still fully manual.** Per the user's own correction, projections
feed the probe, not the other way around — this update only reflects what
D/E/F actually confirmed exists or doesn't, checked directly against the
code, not assumed from the postmortem summary:

- **D1 (usage trajectory) partially has real backing now, RB-only.** Item D
  shipped a genuine recency-weighted usage signal
  (`statline_model._wrw_trailing_usage`'s short/long carry-share blend,
  `build_projections_statline.py` line ~1502) — but it's scoped to RB
  carry-share reallocation specifically (the who-replaces-whom mechanism),
  validated 10/10 LOSO. `recent_form` itself is also no longer a duplicate
  of `season_avg` (same commit), but it's explicitly NOT wired into ranking
  anywhere — display/future-use only, not something to cite as "the model
  already knows this." For RB role-trend questions, D1's answer can now be
  checked against real signal; for QB/WR/TE, there is still no equivalent
  trend mechanism — stay fully manual/skeptical there, same as before.
- **Game-script/spread-driven usage (E1/E2/G1) already has real signal —
  the question shifts from "does the model know this" to "is this case
  handled."** Item E's investigation found the checklist's "missing
  feature" premise was wrong: a spread-anchored usage discount already
  fires live in `volume_prior.py` (decision #7 — both Vegas terms, implied
  total AND spread direction, always carried together for RB volume). A
  follow-on "committee split" extension was tested and failed validation
  (3/5 seasons), so nothing new shipped — the existing mechanism is what's
  live. Since the signal exists but can still misfire in a specific case
  (Item A's Wk9 diagnosis: Allgeier's bad-matchup read correctly registered
  "low-scoring" game environment but still got badged "normal swing" — a
  propagation gap, not a missing-input gap), a probe answer that surfaces a
  game-script concern should be checked against `vegas_factor`/
  `implied_total` as a real signal first, with the open question being
  whether this specific player's badge/rationale is actually reflecting it
  correctly — not whether the signal exists at all.
- **Target-starved / no-competition-for-volume roles (Watkins-type cases)
  are a confirmed real gap — stay fully manual, this is the probe's actual
  job.** Item F confirmed the next-man-up vacancy mechanism
  (`apply_wr_replacement`/`apply_te_replacement` in `statline_model.py`)
  only credits a vacancy when the OUT player's own last appearance is the
  team's immediately-preceding game (a "fresh" k=1 OUT) — RB got a k≥2
  decay extension for sustained absences (2026-10-26), WR/TE never did, and
  the obvious clone-the-RB-fix attempt failed validation (5/10 and 3/10
  LOSO, rejected, not shipped). Concretely: **`own_vac_bump` being zero for
  a sustained multi-week-OUT situation (like SF's Evans/Samuel/Kirk/
  Pearsall all out by different weeks, none "fresh") does NOT mean there's
  no real vacancy** — it means the pipeline's vacancy credit only sees
  fresh OUTs. See the correction to the C section's relevance-filtering
  note below: don't let a zero `own_vac_bump` silently exclude a real
  sustained-absence case from C1/C2's candidate list.

---

## A. Fresh roster moves (Feeds: P — foundational correctness check)
_Relevance: open/discovery — append the DFS-relevance qualifier; no pre-filter needed._

A1. "List any NFL trades, signings, waiver claims, or practice-squad
elevations from the past 7 days affecting [TEAM]'s offense. Has anything
changed [PLAYER]'s role or active-roster status?"

A2. "Is [PLAYER] still on [TEAM]'s roster, and still playing the same
position/role he played last week?" (run for any player whose team/role in
our data hasn't been touched by other pipeline refreshes recently — a
cheap correctness tripwire, not a judgment call)

## B. Injury-tag nuance (Feeds: P via participation_effective; O secondarily)
_Relevance: name-supplying — pre-filter `QUESTIONABLE`/`DOUBTFUL` list by
salary floor (~$4500 RB/WR/TE, ~$5000 QB) before building B2's batch list._

B1. "[PLAYER] is listed as [STATUS] on this week's injury report for
[INJURY]. What are beat reporters saying about his likelihood of playing —
is this trending toward active, trending toward out, or genuinely
uncertain going into game day?"

B2. "For these questionable/doubtful players this week — [LIST] — summarize
the latest practice-participation reporting (limited/full/DNP each day)
and whether each is trending toward playing or sitting."

## C. Next-man-up / vacated-role beneficiary (Feeds: P+O — direct heuristic check)
_Relevance: name-supplying — pre-filter `OUT` players to only those whose
absence produced a nonzero `own_vac_bump` on a teammate (our own pipeline's
signal that the vacancy already moved something)._

C1. "If [PLAYER_OUT] doesn't play this week, who on [TEAM] is expected to
get the bulk of his snaps/touches/targets, based on beat reporter or
coaching staff reporting? Is there a clear lead backup, or is it a
committee?"

C2. "Has [TEAM]'s coaching staff or beat reporters said anything specific
about how [PLAYER_OUT]'s workload (carries, targets, red-zone role) would
be split if he's out this week?"

## D. Usage trajectory (Feeds: P via recent_form weighting; O secondarily)
_Relevance: D1 is name-supplying (same salary floor as B); D2 is
open/discovery (append the qualifier instead)._

D1. "Over [PLAYER]'s last 2-3 games, has his role (snap share, target
share, red-zone usage) been trending up, down, or steady? Is there a
reported reason — scheme change, coach's comments, a competing player
losing/gaining role?" **Correction, 2026-11-09 (WK9 Item D):** for an RB,
this can now be partially checked against real signal — a short (last-2)
vs. longer (~5-game) carry-share blend is shipped and live
(`statline_model._wrw_trailing_usage`, validated 10/10 LOSO) inside the
RB-vacancy reallocation mechanism specifically. It is NOT general-purpose
usage-trend tracking for every RB, and it is NOT wired in for QB/WR/TE at
all — for any player/position outside that one RB-vacancy mechanism, this
question is still fully probe-driven with nothing in our own data to check
it against beyond the bare `season_avg` vs. `recent_form` gap (and
`recent_form` is now a genuine signal, not a duplicate — see the
2026-11-09 correction note above — but it's display-only, not a trend
mechanism in its own right).

D2. "Has [TEAM]'s offensive game plan or play-calling tendency shifted
recently (more pass-heavy, more up-tempo, new OC influence, etc.) in a way
beat reporters have flagged?"

## E. Matchup / scheme intel (Feeds: P as a new qualitative layer; O secondarily)
_Relevance: runs once per team/matchup on the slate, not per player — no
name filter needed; append the qualifier to E2 since it does ask about a
specific beneficiary._

E1. "What is [OPPONENT]'s defense known for schematically this week — e.g.
shadow coverage on a specific receiver, a positional weakness opposing
offenses have exploited, or notable defensive injuries/absences that open
up an edge?"

E2. "Is there a specific [TEAM] player expected to see a notably favorable
or unfavorable matchup this week because of [OPPONENT]'s defensive
tendencies or injuries?"

E3. (Added 2026-10-31, explicit trap framing) "Is there a matchup this
week that LOOKS good on paper (a weak defense, a high implied total) but
is actually a trap — e.g. the defense is weak against a different
position, the team's pace/script works against the player, or the
matchup stat is driven by garbage time, not real volume? Conversely, is
there a matchup that looks bad but is actually fine for a specific
player?" **Correction, 2026-10-31:** for a skill-position player this
can NOT be checked against `matchup_factor` — it's pinned to 1.0 for
QB/RB/WR/TE by design (see the relevance-filtering note above). The only
thing to check it against is `vegas_factor`/`implied_total` (game script,
not real matchup specificity), and that limit should be stated plainly
in the verdict, not glossed over.

## F. Field chalk / overlooked value (Feeds: O — direct field-attention signal, not just triage)
_Relevance: open/discovery — append the qualifier; this one's slate-wide by design._

The value here isn't limited to validating specific ownership numbers —
what a live-search LLM surfaces *unprompted* is itself a sample of what's
getting talked about this week, which is close to a direct read of the
discourse that drives real ownership. F0 is written to capture that
directly, before narrowing to the chalk-list framing in F1/F2.

F0. "What storylines or players are fantasy analysts and DFS communities
most focused on heading into this week's slate, and why?"

F1. "Heading into this week's DraftKings main slate, which players are
shaping up to be chalk (high-owned) at QB, RB, WR, TE, and DST, and why?"

F2. "Are there any players being talked about as clear value or overlooked
plays this week that aren't already on the chalk list above?" (Sharpened
2026-10-31 — ask explicitly, not just as a fallback to F1: "Specifically,
which cheap/fringe players (low salary, low rostered ownership) do
analysts think are undervalued or overvalued this week, and why? Flag any
that are getting attention mainly because of a matchup call, not a role
change.") This is the question that should route most directly into an
over/underprojection or trap-matchup verdict — it's the probe's own
fringe-value read, checked against our data, not our own
`probe_cheap_value_finder.py` output re-asked back to it.

F3. (Follow-up, used to decide if F1/F2 should route into A-E) "What's the
specific reason the field is high on [PLAYER] — is it a role/usage fact, a
matchup, or just raw name recognition/recent big game?"

## G. Game script / blowout risk (Feeds: P via volume distribution; O secondarily)
_Relevance: open/discovery — append the qualifier; slate-wide by design._

G1. "Which games this week project as potential blowouts based on current
lines, and which specific players benefit (garbage-time volume, bellcow
role protecting a lead) or get hurt (abandoned game plan, early exit) by
that kind of script?" **Correction, 2026-11-09 (WK9 Item E/A):** a
spread-anchored game-script discount for RB volume already exists and is
live (`volume_prior.py` decision #7) — check a G1 claim against
`vegas_factor`/`implied_total` as real signal, not an acknowledged gap.
But a real signal existing doesn't guarantee it propagates correctly to
the cheat sheet's badge/Range read — Item A's Wk9 diagnosis found a case
(Allgeier) where the game-environment read correctly flagged "low-scoring"
but the badge/Range still said "normal swing" anyway. So when a G1 answer
and `vegas_factor` agree on a real game-script concern, the useful
follow-up isn't "does the model know this" (yes) but "is this specific
player's cheat-sheet read actually reflecting it" — check the player's
own rationale/badge directly, don't assume agreement with `vegas_factor`
means the concern is already captured everywhere downstream.

## H. Weather (Feeds: P via pass volume/scoring environment)
_Relevance: open/discovery, run once per outdoor game on the slate — no name filter needed._

H1. "Is there a notable weather forecast (wind, rain, snow, extreme cold)
for [GAME] at [STADIUM] this week that could affect the passing game or
kicking game?"

---

## Showdown slates (separate script, 2026-11-05)

Classic's templates above don't transfer directly to showdown -- it's one
game, not a slate, so the risk shape is different: game script decides
who's even relevant (CPT survival, not just volume), captain selection is
its own decision with its own ownership dynamics, and cheap pieces matter
more per-lineup (a top showdown lineup needs ~2 cheap hits, not 1 bonus
dart). `scripts/probe_ai_chat_weekly_questions_showdown.py` is a separate
script, not a flag on the classic one, built around 4 categories instead
of A-H above:

- **Injury-tag + next-man-up** (reused from B/C) -- run on CPT/FLEX-deduped
  rows (`probe_cheap_value_finder.dedup_cpt_flex()`: showdown rows every
  player twice, CPT salary = 1.5x FLEX, same `player_id` -- keep the FLEX
  row as the real salary, don't double-count or double-ask).
- **Game script / blowout risk** -- first-class here, framed around CPT
  survival specifically (whose role depends on the game staying
  competitive vs. who benefits/survives a blowout).
- **Captain selection** -- an open "chalk captain tonight" discovery
  question, plus a named confirm/challenge question for every CPT row
  with `estimated_ownership_pct > 7` (threshold in `CPT_OWNERSHIP_THRESHOLD`).
  Framed as "tonight" not "this week" -- showdown slates are single
  primetime games (TNF/SNF/MNF), run close to kickoff.
- **Cheap-piece viability** -- `candidates_by_position()` fanned out onto
  named players same as classic's fringe-value fix, but top 5 per
  position (not 3) and with showdown-specific salary floors ($3000
  RB/WR/TE vs. classic's $4500, since showdown's whole pool is cheaper --
  checked against a real wk9 file, classic's floor would've dropped real
  rotational pieces like a $3200 RB2). Needed a second fix beyond the
  floor: pts/$1000 efficiency blows up for a $200 practice-squad/UDFA
  name with a ~1pt projection (a literal game-day-inactive-adjacent
  scrub can out-rank a real $2800 WR on pure ratio). Added `min_proj`
  (3.0, `MIN_PROJ` in the showdown script) to `candidates_by_position()`
  as a second filter alongside the salary floor -- classic's floors never
  go low enough to need it, so it defaults to 0 there (no behavior
  change).

`candidates_by_position()` also gained `slate_path` (pass the exact file
the caller already resolved instead of this function re-globbing --
showdown filenames don't match classic's `_classic_wk*_main_*` glob
shape) and `team_filter` (scope the candidate pool to just the showdown
slate's 2 teams).

## Build-derived value check, added 2026-11-07

Separate problem the fringe-value section (candidates_by_position's
top-3-per-position-by-efficiency list) doesn't fully solve: that list is
a *proxy* for which cheap players the solver will actually roster, and a
real salary-saver can rank outside the top-3 cutoff and never get asked
about. The user's actual complaint was concrete: "yeah, the optimizer
likes this WR2 for $4100 this week but I don't really trust that guy" --
and the probe wasn't reliably covering that exact player.

Fix, in `probe_cheap_value_finder.build_pool_candidates()`: run the real
100-lineup build first (the user already does this as part of the weekly
cadence -- confirmed it doesn't disrupt his Fri/Sat/Sun build schedule to
build before probing), then read the distinct cheap WR/RB/TE that
actually show up anywhere in `output/lineups_multi_<slate>_*.csv`,
excluding anyone already covered by the fringe-value section.
`probe_ai_chat_weekly_questions.py` fans the same usage-trend +
matchup-trap question pair onto this list under its own "Build-derived
value check" heading -- additive to the fringe-value section, never a
replacement (explicit user instruction, 2026-11-07: "I don't want the
probe to be narrowed down to only these players... this is more of an
add on").

**Why this doesn't re-trigger the exposure problem:** selection (who do
we ask about) and verdict (is the answer right) are different questions.
Exposure was ruled out as a way to answer the second one -- how often a
player shows up across 100 lineups says nothing about whether his own
projection is accurate, it's an emergent property of the whole pool's
combinatorics (see the exposure correction above). But "did the solver
actually roster him anywhere in a real build" is a legitimate way to
answer the first question, and it's membership-only (yes/no), never a
count or percentage. The verdict itself still comes only from
season_avg/recent_form/matchup_factor/vegas_factor, exactly as before.

Requires the 100-lineup build to already exist for this slate -- if
`lineups_multi_<slate>_*.csv` isn't there yet, this section is skipped
(logged as an HTML comment in the output, not a silent gap) rather than
guessing at who the solver would pick.

## Open design questions (not yet decided)

- ~~How placeholders get filled automatically~~ — decided above: open
  templates get a relevance qualifier instead of a name list; name-supplying
  templates filter by `own_vac_bump` (C) or a salary floor (B/D1).
- ~~Whether to retool these templates around recent_form/game-script before
  the underlying signals were confirmed real~~ — decided 2026-11-09 (WK9
  Item G, gated on D/E/F per the user's own correction): see the
  2026-11-09 correction block right after the relevance-filtering notes
  above, plus the inline corrections on D1, C's filter, and G1. Each claim
  in those corrections was checked directly against the code before being
  written, not assumed from the postmortem summary.
- Cadence: once per week (e.g. Tue/Wed) vs. a closer-to-lock re-check for
  B/C given status changes right up to kickoff.
- Which API/tool actually runs these (Claude API web_search tool vs.
  Gemini API search grounding) — tracked separately, not blocking this
  question set.
- How an answer gets scored/diffed automatically against our own columns
  (`participation_effective`, `own_vacated`, `wrw_vacated`,
  `estimated_ownership_pct`, `chalk_score`) vs. just flagged for manual
  review.
