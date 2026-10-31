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
   - **B / D1**: filter by a salary floor (~$4500 RB/WR/TE, ~$5000 QB, DST
     excluded) applied to `QUESTIONABLE`/`DOUBTFUL` players (B) or the
     active pool (D1). On the live Wk8 file this trimmed `QUESTIONABLE`
     from 23 down to 13 real names (Amon-Ra St. Brown, Lamar Jackson,
     Rashee Rice, etc.) by dropping scrubs the floor isn't rosterable
     anyway.

Feeds: **P** = projection track (production inputs), **O** = ownership
track (field-perception inputs), **P+O** = both.

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
losing/gaining role?"

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
that kind of script?"

## H. Weather (Feeds: P via pass volume/scoring environment)
_Relevance: open/discovery, run once per outdoor game on the slate — no name filter needed._

H1. "Is there a notable weather forecast (wind, rain, snow, extreme cold)
for [GAME] at [STADIUM] this week that could affect the passing game or
kicking game?"

---

## Open design questions (not yet decided)

- ~~How placeholders get filled automatically~~ — decided above: open
  templates get a relevance qualifier instead of a name list; name-supplying
  templates filter by `own_vac_bump` (C) or a salary floor (B/D1).
- Cadence: once per week (e.g. Tue/Wed) vs. a closer-to-lock re-check for
  B/C given status changes right up to kickoff.
- Which API/tool actually runs these (Claude API web_search tool vs.
  Gemini API search grounding) — tracked separately, not blocking this
  question set.
- How an answer gets scored/diffed automatically against our own columns
  (`participation_effective`, `own_vacated`, `wrw_vacated`,
  `estimated_ownership_pct`, `chalk_score`) vs. just flagged for manual
  review.
