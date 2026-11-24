# Wk11 AI-probe cross-check (2026-11-22)

Slate file: `output/final_projections_dk_dk_classic_wk11_main_17Nov2026.csv`

## UPDATE 2026-11-22 (after `git pull`): the staleness below was my local checkout, not the pipeline
The automated refresh had already rebuilt the file at 05:39 CT today (origin commit
2090173d); my checkout was 33 commits behind. No rebuild was needed. Walker, Cooper,
Spears are now OUT/IR at 0.0 and Kincaid DOUBTFUL at 0.0. Changes to the verdicts:
- Johnson now 13.8 pts and 56.0% est. ownership, matching the chat's ~55% field. Thumbs
  up is on level only; he is fully field-priced, so no leverage.
- Knox 5.9 -> 7.5: the model now absorbs Kincaid's absence. Thumbs up is weaker; fine
  to leave as checked.
- Wilson (14.0) and Mitchell (9.6) did NOT move after Cooper went OUT, so those two
  remain underprojected. Wilson is the clearest remaining thumbs up.
- Tate is still Questionable at participation 0.6 despite "full Friday", so Ayomanor
  (9.2, 23.9% owned) stays a thumbs down.
- Skattebo 12.9, Worthy 8.6, Dike 7.9 essentially unchanged; verdicts stand.
Everything below was written against the stale local copy; read it with this block first.

## (Original) Headline: our projection file is stale vs. the chat's Fri/Sat news
The file was built Nov 20 04:51 CT from a status pull of Nov 19 evening. Every
designated player in it is still tagged QUESTIONABLE. The chat reports Walker OUT,
Cooper OUT, Kincaid DOUBTFUL, Spears on IR, and several players cleared. Our numbers
still carry Walker at 23.7 pts with participation 1.0, Cooper at 0.6, Kincaid at 1.0.
**Rebuild projections with final statuses before lock.** Most beneficiary verdicts
below follow from this, not from a model flaw.

Build-derived section: no `lineups_multi_*wk11*` pool is in the repo, so the
generator skipped it. The only pool-derived cheap name from your CSV tally that is
not already in the fringe list is Dawson Knox, so he is covered here. Re-run the
generator once the 100-lineup build is saved, for the full list.

Caveat on all "disagree" calls: the chat's news is what is new. I did not
independently verify Walker/Cooper/Kincaid/Spears. Spot-check them before acting.

## Claim-by-claim

Roster moves (Q1): Spears to IR (Pollard leads, Carter change-of-pace), Downs to KC
(slot, Rice outside). Our data: Spears still QUESTIONABLE, 5.5 pts, only 12% carry
share, so his removal moves little. Pollard already has 69% carry share and 16.5 pts.
Agree. Downs already shows 15.2% target share in KC's last 4.

Beneficiaries (Q3), checked with `probe_team_usage_rank.py`:
- **Walker out -> Emmett Johnson**: KC last-4 carry share Walker 70.6% / Johnson 42.0%.
  Johnson projects 11.1 at $6,000 (usage_trend 1.5, vegas 1.26), Walker 23.7. With
  Walker out, Johnson is plainly underprojected. disagree-underprojected. Caveat: chat
  puts him at ~55% field ownership (ours 17.7%), so it is a level call, not leverage.
- **Bowers -> Mayer/Thomas**: Mayer 11.8% target share, 8.4 pts at $4,300. Thomas 3.2%,
  1.2 pts. Agree, no gap.
- **Kincaid doubtful -> Knox**: Kincaid 17.7% share, Knox 9.7% (trend 1.25), 5.9 pts
  at $2,800, vegas 1.34. We still have Kincaid at full participation. Knox
  disagree-underprojected (modest). Hawes is 2.7% share, 3.1 pts, nothing there.
- **Cooper out -> Wilson, Mitchell**: Cooper 26.1% share last 4, we have him 0.6
  participation. Wilson 14.0 pts vs recent_form 21.3, season 16.4; vegas_factor 0.857
  (NYJ implied 19.5) is the drag. Mitchell 9.7 at $4,900. Both
  disagree-underprojected, Wilson more so.
- **Mayfield -> Daniels**: replacement QB, not a beneficiary (Daniels 1.3 pts). Mayfield
  is priced at participation 0.75. No action.
- Others (Tuten, Waddle, Tate, Tyson, McConkey, Rodriguez, Meyers, Vaki): chat named no
  beneficiary. All fine in our data; see buckets.

Usage trends (Q7):
- **Ayomanor**: chat says the 94.7% Wk10 snap share came with Tate AND Robinson out;
  Tate back takes it. Ours: 9.2 pts, 5.9 proj targets, +1.1 vacancy credit, and Tate
  at participation 0.6 (so we assume he misses 40% of the time). Chat says full Friday,
  expected. disagree-overprojected. Season avg is 8.9, so the damage is modest, but at
  ~23% owned it is the one to fade. Tate himself: agree.
- **Dike**: same mechanism (+1.65 vacancy credit, 7% target share, 2.2 tgt/g). Chat is
  less sure. Low-confidence disagree-overprojected; recent_form 11.3 argues the other
  way.
- **Worthy**: chat says down (0 catches on 3 targets, Downs arrives). Ours: 8.6 pts is
  above season 6.9 and recent_form 5.8, propped by vegas 1.26; trend 0.84.
  disagree-overprojected.
- **Skattebo**: chat 88% snaps, 18 of 19 RB carries. Ours: 57% last-4 carry share
  (Tracy OUT), 12.8 pts vs recent_form 14.9, season 14.4, held down by vegas 0.89.
  disagree-underprojected on usage. Trap claim (tough JAX run D): no matchup signal
  exists for skill positions; vegas_factor 0.89 is game script only and is already in the number.
- **Hall**: chat "rising from 43% snaps". Ours: 55% carry share, 12.4 pts, trend 0.91.
  43% is still a committee. Agree.
- **Gordon (MIA)**: chat steady/up. Ours: 75% carry share, 23 touches/g, agree on
  usage. But 11.2 pts vs recent 17.1 / season 18.0, because vegas_factor is 0.62
  (MIA implied 14.1, BUF -16.5). This is the usage-up-but-script case, and the model
  already prices the script heavily (possibly too heavily). No action.
- **Kolar**: chat up (41 snaps), questionable concussion, DNP Wed. Ours 6.3 pts at
  $2,700, 14.3% share. Agree on usage; availability is the risk, unknown Thu/Fri.
- **Tremble**: chat rotational with knee question. Ours 12.3% share, trend 1.23, 6.7
  pts. Agree-ish; availability risk.
- **Helm**: chat calls him a low-floor TE2. Ours: he is TEN's TE1 by share (12.8% vs
  Bellinger 8.6%), trend 1.31, 7.5 pts. Classification disagrees; value is fine, TEN
  trailing by 8.5 favors passing.

Matchup traps (Q8): Ayomanor (Porter) and Skattebo only. No matchup-specific signal
exists for any skill position (matchup_factor is pinned to 1.0), so neither can be
confirmed or refuted. The Ayomanor risk is role, not matchup.

Blowouts (Q9): Spreads: BUF -16.5, KC -16.5/-15.5, CHI -11.5, DEN -10, DAL -8.5.
These are already in vegas_factor (MIA 0.62, DAL 1.39, KC 1.26, CHI 1.32).
Not probe-bucketed, but note: **Prescott** 23.7 vs recent_form 18.8 and season 17.0 is
+4.8 above recent_form, all from vegas 1.39. The chat flags 4th-quarter volume loss
in a blowout for him. Mild overprojection risk. He is not in the probe-named list, so
this is a note rather than a verdict. **Javonte Williams** (19.9 vs recent 13.1) and
**Lamb** (21.8 vs recent 16.4) carry the same vegas push but the chat says favorite
RBs benefit, so no flag.

## Fringe-value list vs. the chat
`probe_cheap_value_finder.py --week 11` surfaced: WR Ayomanor, Dike, Worthy, Fields,
Bateman; RB Skattebo, Hall, Gordon, Jeanty, Allen; TE Kolar, Tremble, Helm, Otton,
Taylor. The chat covered Ayomanor, Dike, Worthy, Skattebo, Hall, Gordon, Kolar,
Tremble, Helm, which is exactly the nine named in the questions. It surfaced nothing
beyond our list (Tre' Harris $4,000, 35% chalk, is its only extra cheap name; ours has
him at 7.8 pts, 1.7% own, 19.6% share, so we are well below the field on him).

## Frontend action list

**Thumbs up:**
- Emmett Johnson (KC RB): Walker out, 42% carry share and trend 1.5, we project 11.1
  for a lead back. Field chalk, so a level call.
- Garrett Wilson (NYJ WR): Cooper's 26% target share vacated, recent_form 21.3 vs proj 14.0.
- Adonai Mitchell (NYJ WR): same vacated share, 9.7 pts at $4,900 (moderate).
- Dawson Knox (BUF TE): Kincaid doubtful, 5.9 pts at $2,800, target share rising.
- Cam Skattebo (NYG RB): 18 of 19 carries, Tracy out, proj below recent_form.

**Thumbs down:**
- Elic Ayomanor (TEN WR): Tate expected back; Wk10 snap share was a Tate+Robinson-out
  artifact; we still discount Tate at 0.6.
- Xavier Worthy (KC WR): 0 catches on 3 targets, Downs arriving; proj 8.6 is 2.8 above recent_form 5.8.
- Chimere Dike (TEN WR): same mechanism as Ayomanor, low confidence (recent_form
  11.3 cuts the other way). Your call.

**Exclude (high-risk trap):**
- Kenneth Walker III (KC RB): OUT per final report; our file still has him at 23.7.
- Omar Cooper Jr. (NYJ WR): OUT.
- Dalton Kincaid (BUF TE): Doubtful.
- Tyjae Spears (TEN RB): IR.
(All four are availability, not value. Rebuild with final statuses and these drop
out on their own.)

**Checked, no bust-risk flag** (nothing in the chat's claims about him, checked against
our data, raised a flag; this is not a safe claim):
- Brock Bowers (Q, can play without practicing; 12.9 pts at $7,300 already vegas-discounted 0.67)
- Michael Mayer (LV TE; 11.8% share, no gap)
- Bhayshul Tuten (no designation; 15.5 pts, 56% carry share)
- Chris Rodriguez Jr. (not on final report; 6.3 pts, 22% carry share)
- Jaylen Waddle (no designation but concussion clearance pending; own-data note:
  proj 10.4 sits above recent_form 6.4 on vegas 1.12, trend 0.69, so watch him)
- Carnell Tate (Q, full Friday, expected; 11.5 pts)
- Baker Mayfield (Q, conflicting reports; priced at participation 0.75; re-check inactives)
- Jalon Daniels (replacement QB; 1.3 pts, no action)
- Jordyn Tyson (no designation, full Friday; 6.8 pts, 27.7% share)
- Ladd McConkey (Q back, limited all week; 9.5 pts at $5,000)
- Jakobi Meyers (not on final report; 9.8 pts at $4,500, 21% share)
- Sione Vaki (depth, 5.1 pts, not DFS-relevant)
- Breece Hall (rising from 43% snaps; 12.4 pts, below season and recent)
- Ollie Gordon II (usage steady/up; script already priced, vegas 0.62)
- Charlie Kolar (usage up but concussion, DNP Wed; re-check inactives)
- Tommy Tremble (rotational, knee; re-check inactives)
- Gunnar Helm (chat says TE2; our data says TE1 by share, 7.5 pts at $3,300)
- Tony Pollard (Spears IR adds little; 69% carry share already)
- Jonah Coleman, Tre' Harris: chalk names only, not probe-flagged
