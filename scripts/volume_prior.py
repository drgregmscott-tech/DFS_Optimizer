"""
volume_prior.py
===============

Session 10.3b -- price-as-a-volume-prior, cold start, role change, and
Vegas-anchored team volume (the CONSUMER).

Deliberately separate from fit_volume_prior.py, the same split Session 10.2
used for salary_anchor / fit_salary_anchor and Session 10.4 used for
dst_model / fit_dst_model: the production path never imports fitting
machinery, and the artifact's read contract is defined in exactly one place.

Everything here was measured by scripts/probe_statline_priors.py on the real
2014-2021 bootstrap BEFORE any of it was built. Two of Session 10.3b's four
card items changed shape on that evidence and the changes are recorded as
decisions below rather than quietly implemented.

Numbered decisions:

  1. PRICE IS A COLD-START PRIOR ON VOLUME, NOT A MID-SEASON BLEND. The
     default mid-season weight floor is 0.0, user-confirmed.

     Measured (probe A, out-of-sample 2018-21, 36,025 player-week-component
     rows): price-implied share NEVER beats own history at ANY games-played
     level -- pooled MAE 0.0709 price vs 0.0600 history, and history wins in
     every gp bucket. A 50/50 blend lands at 0.0597, i.e. a 0.5% improvement
     on history alone, which is not a component worth carrying mid-season.

     What price DOES have is decorrelated error: residual correlation runs
     0.474-0.597, nowhere near the 0.965 that made Session 10.3a's blend a
     null. So the information is real; it is simply the weaker of the two
     signals, and its non-redundant value is concentrated where history does
     not exist at all. That is cold start, which Session 10.2 already
     measured working on price alone (week 1 2021: structurally unbuildable
     -> median-pctile 57.2 / max-pctile 99.7).

     Consequence: `cold_start_weight()` defaults to floor 0.0, so a player
     with a full history gets essentially no price in his volume, and a
     player with none gets nothing else.

     ONE HONEST CAVEAT ON THAT EVIDENCE. Probe A necessarily excluded 3,905
     rows with no history share -- a true zero-history player has nothing to
     compare against -- so its `gp 0-1` bucket is effectively gp=1, and probe
     A cannot itself speak to true cold start. The cold-start case rests on
     Session 10.2's measured week-1 result, not on probe A.

  2. THE ROADMAP'S ROLE-CHANGE INSTRUCTION IS BACKWARDS FOR THIS PIPELINE,
     AND IS AMENDED RATHER THAN FOLLOWED. Phase 10's design intro says
     "suppress the salary anchor's weight when a role change is flagged -- a
     stale price is exactly the value spot we're trying to beat."

     That presumes the PRICE is the stale signal. On a weekly DFS slate the
     site reprices every player every week with real money behind it, while
     our usage history is by construction weeks old. Measured (probe D,
     out-of-sample, n=36,025): regressing what history MISSES on the
     price-history divergence gives slope +0.4606, t = +95.16, R2 = 0.201.
     Divergence explains a fifth of history's residual. Price sees role
     changes history cannot.

     The three catalogued cases -- the two weeks that ABORTED the first
     Session 10.3a run, plus the week statline_model.py decision #9 already
     names as a known limitation:

         NYJ 2021 wk13 Zach Wilson      realized 1.000  hist 0.115  price 0.937
         SEA 2021 wk13 Russell Wilson   realized 1.000  hist 0.611  price 0.968
         CAR 2021 wk15 Cam Newton       realized 1.000  hist 0.524  price 0.937

     History is off by 0.885 / 0.389 / 0.476; price by 0.063 / 0.032 / 0.063.

  3. THE ROLE-CHANGE FLAG ACTS ON PARTICIPATION, NOT ON THE SHARE
     (user-confirmed, option (b) of two considered).

     Session 10.3b's card states its own problem precisely: "the QB
     projection is substantially a product of reconciliation rather than of
     the volume model." Zach Wilson's failure is not really his share -- it
     is `participation = 0.20` crushing his volume, after which
     reconciliation scales the pool back up and does the work the volume
     model should have done.

     The rejected alternative (option (a)) was to blend the share toward
     price at probe D's 0.46. It was rejected because in the top-divergence
     decile price ALONE is worse than history (MAE 0.237 vs 0.167), so a
     0.46 blend puts Wilson at 0.493 against a realized 1.000 -- half a fix
     that leaves reconciliation still doing the repair. Raising participation
     instead makes the VOLUME MODEL produce the right answer before
     reconciliation is ever consulted, which is what the card asks for.

  4. THE OVERRIDE'S STRENGTH IS FITTED, NOT HAND-TUNED. This one matters,
     because the obvious implementation is two hand-picked thresholds and
     this project flags arbitrary constants for a reason.

     The first draft was `role_strength = clip((rel_div - LO)/(HI - LO))`
     with LO/HI chosen by eye. Both constants were being tuned against the
     three catalogued cases, i.e. fitted to three points and called a rule.
     Replaced with a formulation whose one constant IS probe D's regression
     slope:

         share_target = hist_share + ROLE_SLOPE * (price_share - hist_share)
         part_eff     = clip(part * share_target / hist_share, part, 1.0)

     Participation is scaled by exactly the ratio by which the fitted
     response says the share should move. Checked against the catalogued
     cases: Wilson 0.20 -> 0.86, Newton 0.80 -> 1.00, Russell Wilson
     0.60 -> 0.76. All three substantially repaired, with no constant chosen
     to make them come out that way.

  5. THE OVERRIDE ONLY EVER RAISES PARTICIPATION, NEVER LOWERS IT.
     Participation already handles the backup case correctly -- that is what
     statline_model.py decision #9 built it for, and Cooper Rush is the
     evidence. The gap it cannot close is one-directional: "was hurt, is
     healthy now" looks identical to "is a backup" from behind. So the flag
     is one-directional too. A negative divergence (price below history) is
     left entirely alone rather than treated as a demotion signal, which
     would be a second, unmeasured claim.

  6. PRIOR-SEASON TEAM-VOLUME CARRYOVER IS DROPPED. IT MEASURED WORSE THAN
     USELESS. This is the second card premise that failed.

     Week-1 team volume from the prior season's per-game average (probe C,
     222 week-1 team-seasons):

         pass attempts   league average MAE 6.31 R2 +0.015 | carryover MAE 6.42 R2 -0.065
         carries         league average MAE 5.74 R2 +0.026 | carryover MAE 5.89 R2 -0.046

     NEGATIVE out-of-sample R2 on both channels: carryover is worse than
     simply using the league mean. Week-1 team volume is therefore the league
     mean tilted by that week's line, and the prior season is not consulted.

     DO NOT "FIX" dst_model.py's decision #15 ON THIS FINDING. That carries
     over defensive QUALITY, which persists across a season boundary. This
     is team VOLUME, which is scheme and pace and turns over with
     coordinators and personnel. Different quantity, different answer, and
     Session 10.4's addendum depends on the carryover path working.

  7. VEGAS-ANCHORED TEAM VOLUME SHIPS, WITH THE CARD'S MECHANISM CORRECTED.
     The card says "Vegas-anchored team volume" without saying which Vegas
     number. Measured (probe B, out-of-sample):

         pass attempts   history only R2 0.0652 -> both terms 0.0799
         carries         history only R2 0.0394 -> both terms 0.0667

     The pre-registered hypothesis held: SPREAD drives carries (t = -6.21;
     more negative spread = more favoured = more carries -- favourites run
     out the clock) and the TOTAL drives attempts (t = +4.67).

     BOTH TERMS ARE REQUIRED TOGETHER, which is the mechanical finding that
     would have been easy to get wrong. Alone, each is weak (attempts: total
     t = +1.54, spread t = +1.07); jointly they are +4.67 and +4.53. That is
     suppression, and it is expected rather than surprising, because
     `implied_total = total/2 - spread/2` -- carrying both terms is what
     spans BOTH teams' implied totals rather than one composite of them.
     Never fit or ship one of these without the other.

  8. A SIDE FINDING NOBODY ASKED FOR, RECORDED BECAUSE IT REFRAMES AN
     EXISTING COMPONENT. Team-history volume prediction -- what
     statline_model.py has anchored reconciliation to since Session 10.3a --
     explains 6.5% of pass-attempt variance and 3.9% of carry variance.
     Nearly uninformative.

     That does NOT make reconciliation wrong. Its job is stacking coherence
     (the ROADMAP: "if the QB projection and his stacked receivers' aren't
     derived from the same team pass-volume number, the stack is internally
     incoherent"), not team-volume accuracy. But it does mean reconciliation
     has been normalizing to a number with very little signal in it, and the
     Vegas terms above roughly double that signal. Stated so a future session
     reads reconciliation as what it is.

  9. MISSING ARTIFACT IS A HARD ERROR WITH THE FIX COMMAND. Same reasoning
     as salary_anchor.py decision #2 and statline_model.load_variance(): a
     silent no-op would make a backtest report "the prior didn't help" when
     the truth is that the prior never loaded.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

SCHEMA_VERSION = 1

# Decision #1 -- the ROADMAP card's own starting point, kept so the card's
# stated design is what ships. ARBITRARY, not fit, flagged per this project's
# convention (same status as OWNERSHIP_SOFTMAX_TEMPERATURE, SHRINK_K, and
# Session 10.2's cold-start k, which this deliberately mirrors).
#
# Kept at the card's stated 4.0. Decision #1a's taper, not this constant, is
# what makes the handover complete -- so k now only shapes the curve WITHIN
# the cold-start window rather than setting how long that window is. Both
# constants are FIRST RETUNING TARGETS and neither is fit.
DEFAULT_COLD_START_K = 4.0

# Decision #1a -- THE TAPER, added after the first real run of
# apply_volume_prior() showed the schedule above does NOT mean what
# "cold-start only" was agreed to mean.
#
# `floor + (1-floor)*k/(k+gp)` at floor=0.0, k=4.0 gives w = 0.364 at 7 games
# and w = 0.20 at 16 games. An entrenched starter in the fixture run had his
# volume pulled from 38.0 to 35.2 -- a standing one-third price weight in
# midseason, which is a long way from "cold start only" and points the wrong
# way against probe A's evidence (price LOSES to history at every
# games-played level, including gp 7+: MAE 0.0689 vs 0.0588).
#
# The floor is the ASYMPTOTE, not the mid-season weight, and the decay to it
# is slow. So the schedule is tapered linearly to zero over the first
# COLD_START_MAX_GAMES games:
#
#     w = floor + (1 - floor) * k/(k + gp) * clip((MAX - gp)/MAX, 0, 1)
#
# At floor = 0.0 the prior is then EXACTLY zero from MAX games onward, which
# is what "cold-start only" has to mean to be true. At floor > 0 it still
# asymptotes to the floor, so a future session can turn on a standing
# mid-season blend without this constant fighting it.
#
# The taper is linear rather than another decay curve deliberately: a hard
# cutoff would put a discontinuity in a player's projection at the game he
# crosses it, and a second exponential would be a second unfitted shape.
#
# MAX = 4.0 is ARBITRARY and flagged, but it is not baseless -- probe A's
# bucket table shows history already winning clearly by 2-3 games (MAE 0.0618
# vs price 0.0739), so the handover should be complete around there.
COLD_START_MAX_GAMES = 4.0

# Decision #1 -- mid-season asymptotic weight. 0.0 = price is a cold-start
# mechanism only. USER-CONFIRMED, unlike the constants above.
DEFAULT_WEIGHT_FLOOR = 0.0

# Decision #5 -- below this absolute divergence in share units, no override is
# applied at all, so ordinary week-to-week noise cannot jitter participation.
# ARBITRARY, flagged, not fit.
ROLE_CHANGE_MIN_DIVERGENCE = 0.05

# Decision #4 -- a history share at or below this is treated as "no usable
# history share", so the ratio is never taken against ~0. Such a player is a
# cold-start case and decision #1's schedule already owns him.
ROLE_CHANGE_MIN_HIST_SHARE = 0.02

# Decision #7 -- sane bounds on a predicted team volume, so a wild line or a
# degenerate fit cannot hand reconciliation an absurd target. Observed real
# ranges over 2014-21 sit comfortably inside these. ARBITRARY, flagged.
TEAM_VOLUME_BOUNDS = {"pass": (15.0, 60.0),
                      "rush": (10.0, 45.0),
                      "recv": (15.0, 60.0)}

# component -> the team-level column statline_model.team_volume_history()
# emits for it. Mirrors that function's own naming so the two cannot drift.
TEAM_VOLUME_COLUMN = {"pass": "team_attempts",
                      "rush": "team_carries",
                      "recv": "team_targets"}

# ---------------------------------------------------------------------------
# Session (this change) -- depth-chart usage-share prior. Real-world review
# of the Week 1 2026 slate surfaced a gap the price/role-change machinery
# above doesn't cover: a player's OWN recency-weighted history (build_usage())
# can misrepresent his CURRENT role whenever that history was earned in a
# different context (a different team, a different committee split, a
# different season) than the one he's actually in now -- e.g. a real
# Week 1 2026 case, Kenny Gainwell (TB) projecting a receiving-role share
# on par with his own established-elsewhere history despite Bucky Irving
# (TB) being the real, confirmed lead back this season. Depth chart rank is
# a real, current signal for this that apply_confirmed_starter_override()
# above only checks for the all-or-nothing zero-participation case -- a
# player with plenty of games (so participation is already 1.0) never
# reaches that check at all, no matter how badly his own history
# misrepresents his current-team role.
#
# The user's explicit design requirement: no hardcoded per-position drop-off
# percentages, no manual "is this team a committee" flag, and the
# correction must be able to go BOTH ways (pull an over-credited backup's
# share DOWN, not just an under-credited starter's UP) -- unlike
# role_change_participation() above, which deliberately only ever raises.
# The mechanism here: for every (position, component, depth_rank) group,
# compute the REAL median share-of-team-volume other players at that same
# rank are showing THIS RUN (statline_model.apply_depth_chart_usage_prior())
# -- purely empirical, recomputed fresh every run from real box-score data,
# never a stored assumption -- and blend each player's own share toward
# that peer baseline, with weight fading toward zero as his OWN games_played
# grows (same cold_start_weight() shape used for the price prior below,
# reusing proven machinery rather than inventing new blend math).
#
# All four constants are ARBITRARY STARTING POINTS, flagged per this file's
# own convention (same status as DEFAULT_COLD_START_K, ROLE_CHANGE_MIN_
# DIVERGENCE) -- first retuning targets, not fitted.
DEPTH_RANK_WEIGHT_FLOOR = 0.15   # unlike price's 0.0, this signal is a real
                                 # current-role check (not a competing
                                 # predictor known to lose to history), so it
                                 # keeps a small standing influence even
                                 # mid-season rather than fading to nothing.
DEPTH_RANK_COLD_START_K = 4.0
MIN_GAMES_FOR_BASELINE = 3       # a rank-group median is only built from
                                 # players with at least this many games of
                                 # their own -- excludes noisy single-game
                                 # samples from contaminating the peer baseline.
MIN_BASELINE_SAMPLE = 3          # a (position, component, depth_rank) group
                                 # needs at least this many qualifying rows
                                 # league-wide before its median is trusted at
                                 # all -- too few real examples means no
                                 # correction is applied for that group.
USAGE_PRIOR_RATIO_BOUNDS = (0.5, 1.75)  # safety clamp on how far one run's
                                        # correction can move a player's mu in
                                        # either direction, so a thin/noisy
                                        # rank-group median can't produce an
                                        # extreme swing in one week.

# Session (this change), decision -- real backtesting against actual Week 1
# 2026 DK contest results (5527+ entries, real %Drafted/FPTS) showed the
# flat DEPTH_RANK_WEIGHT_FLOOR above correctly moved Kenny Gainwell's
# (TB RB2) inflated receiving share in the right direction but too weakly
# to flip his final_projection below Bucky Irving's (TB RB1) -- his own
# share (23.3%) was ~3.5x the real league RB2 median. The obvious fix
# ("raise the floor for any big divergence from the peer median") was
# tested against the SAME real data and REJECTED: it also would have
# suppressed Jahmyr Gibbs (DET, a real, legitimate 46-50%-owned workhorse
# whose own share is elite specifically BECAUSE he's a genuine bell-cow,
# not because of stale/cross-context history) toward the peer median just
# as hard, which is exactly backwards -- his real chalk score confirms he
# deserves to stay elite, not get regressed toward average.
#
# The distinguishing signal that separates the two cases: Gainwell's
# situation is a REAL, WITHIN-TEAM inversion -- Irving (his own team's
# confirmed #1 by depth chart) has a LOWER receiving share than Gainwell
# (the #2). Gibbs has no such teammate outshare him on any component --
# nobody on DET's real roster has a bigger rush or recv share than the
# team's real #1. So: only boost the correction's weight when a team-
# relative inversion like this is actually present (see
# apply_depth_chart_usage_prior()'s own inversion-detection logic), never
# from raw distance-from-league-median alone. This is deliberately a
# NARROWER, more specific trigger than "big divergence" -- it fires only
# on the exact real-world pattern (a worse-ranked teammate out-producing a
# better-ranked one) the user described, not on every statistical outlier.
#
# All three constants below are, like every other constant in this
# section, ARBITRARY STARTING POINTS -- first retuning targets once more
# real contest weeks exist to fit them against, not fitted here.
DEPTH_RANK_MAX_WEIGHT_FLOOR = 0.6   # the ceiling this boosted floor can
                                    # reach for a fully-saturated inversion
                                    # -- still leaves 40% weight on the
                                    # player's own real data even at max,
                                    # so a real inversion never gets
                                    # entirely overridden by the peer
                                    # median alone.
DEPTH_RANK_INVERSION_SATURATION = 0.15  # a 15-percentage-point share gap
                                        # between a team's better- and
                                        # worse-ranked player fully
                                        # saturates the boost -- Gainwell/
                                        # Irving's real recv-share gap
                                        # (23.3% vs 9.4%, a 13.9-point gap)
                                        # sits just under this, so it's
                                        # calibrated to treat that exact
                                        # real case as a near-maximal,
                                        # genuine inversion.
DEPTH_RANK_MIN_INVERSION_GAP = 0.02  # below this gap, treat it as ordinary
                                     # week-to-week noise, not a real
                                     # inversion -- same guard-against-
                                     # jitter role ROLE_CHANGE_MIN_
                                     # DIVERGENCE plays for the price prior.

# The component whose share defines a player's ROLE. A QB's role is how much
# of the team's passing he does; a running back's is carries. Receiving is the
# role signal for both pass-catching positions.
PRIMARY_COMPONENT = {"QB": "pass", "RB": "rush", "WR": "recv", "TE": "recv"}

_CACHE = {}


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------

def prior_path(site: str) -> Path:
    return DATA_DIR / f"volume_prior_{site}.json"


def load_prior(site: str, path: Path | None = None) -> dict:
    """Load and memoize the fitted artifact. Decision #9: hard error with the
    exact fix command if it is not there."""
    p = Path(path) if path else prior_path(site)
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    if not p.exists():
        raise SystemExit(
            f"Volume prior requested but {p} does not exist.\n"
            f"Fit it first:\n"
            f"    python3 scripts/fit_volume_prior.py --site {site}\n"
            f"(Not falling back to a no-op prior -- that would report 'the "
            f"prior didn't help' when the prior never ran.)")
    art = json.loads(p.read_text())
    if art.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(
            f"{p.name} has schema_version={art.get('schema_version')}, "
            f"expected {SCHEMA_VERSION}. Refit with the current "
            f"fit_volume_prior.py.")
    if art.get("site") != site:
        raise SystemExit(
            f"{p.name} was fit for site='{art.get('site')}' but is being "
            f"loaded for site='{site}'. Refusing to cross-apply one site's "
            f"price curve to another's salaries -- the two sites price "
            f"differently, which is the whole reason this is fit per site.")
    _CACHE[key] = art
    return art


# ---------------------------------------------------------------------------
# Decision #1 -- price-implied share, and the cold-start schedule
# ---------------------------------------------------------------------------

def share_from_salary(artifact: dict, position: str, component: str,
                      salaries) -> np.ndarray:
    """Vectorized E[share | salary] for one (position, component) pair.

    Flat extrapolation past both ends, identical to salary_anchor.py's
    decision #1 and for the same reason: a curve knows nothing outside the
    salary range it was fit on, and returning NaN would silently drop the
    prior for exactly the players it matters most for.

    An unfitted pair returns zeros rather than raising. Unlike the salary
    anchor -- where an unmapped POSITION means the artifact and the
    projections file are out of sync, which is a real inconsistency worth
    stopping for -- a missing (position, component) here is a legitimate
    thin-data outcome (WR/rush is a genuinely rare component). Zero is the
    honest value: no price information about this player's volume in this
    component.
    """
    sal = pd.to_numeric(pd.Series(salaries), errors="coerce").to_numpy(dtype=float)
    curve = artifact["share_curves"].get(f"{position}|{component}")
    if curve is None:
        return np.zeros(len(sal), dtype=float)
    kx = np.array([k[0] for k in curve["knots"]], dtype=float)
    ky = np.array([k[1] for k in curve["knots"]], dtype=float)
    out = np.interp(sal, kx, ky, left=float(ky[0]), right=float(ky[-1]))
    # A NaN salary carries no market signal; never let it propagate into a
    # volume (the Session 10.1 bug #2 class of failure).
    return np.where(np.isnan(sal), 0.0, out)


def cold_start_weight(games_played, weight_floor: float = DEFAULT_WEIGHT_FLOOR,
                      k: float = DEFAULT_COLD_START_K) -> np.ndarray:
    """Per-player weight on the PRICE side of the volume blend. Decision #1.

        w = floor + (1 - floor) * k/(k + games_played) * taper
        taper = clip((COLD_START_MAX_GAMES - games_played)/COLD_START_MAX_GAMES, 0, 1)

    At games_played = 0 this is 1.0 (pure price -- the only signal that
    exists), reaching exactly `floor` at COLD_START_MAX_GAMES. See decision
    #1a for why the bare ROADMAP schedule needed the taper: without it,
    floor=0 still left a standing one-third price weight at seven games. Identical in
    shape to salary_anchor.effective_weight()'s schedule, deliberately: the
    ROADMAP specifies one cold-start mechanism, and Session 10.2 already
    measured this one working. The difference is only WHAT it is applied to
    -- volume here, points there, which is the correction the amendment to
    Phase 10's design intro requires.
    """
    gp = pd.to_numeric(pd.Series(games_played), errors="coerce") \
           .fillna(0.0).to_numpy(dtype=float)
    if k <= 0:
        raise SystemExit("volume-prior k must be > 0 (it is the half-weight "
                         "point of the cold-start schedule).")
    taper = np.clip((COLD_START_MAX_GAMES - gp) / COLD_START_MAX_GAMES, 0.0, 1.0)
    w = float(weight_floor) + (1.0 - float(weight_floor)) * (k / (k + gp)) * taper
    return np.clip(w, 0.0, 1.0)


def blend_volume(history_volume, price_volume, weight) -> np.ndarray:
    """mu = (1 - w) * history + w * price, clipped at 0."""
    h = pd.to_numeric(pd.Series(history_volume), errors="coerce") \
          .fillna(0.0).to_numpy(dtype=float)
    p = pd.to_numeric(pd.Series(price_volume), errors="coerce") \
          .fillna(0.0).to_numpy(dtype=float)
    w = np.asarray(weight, dtype=float)
    return np.clip((1.0 - w) * h + w * p, 0.0, None)


# ---------------------------------------------------------------------------
# Decisions #6, #7 -- team volume
# ---------------------------------------------------------------------------

def predict_team_volume(artifact: dict, component: str, implied_total,
                        spread, history_volume=None,
                        opp_defense_allowed=None) -> np.ndarray:
    """Predicted team volume for one component.

    `history_volume=None` selects the NO-HISTORY specification, which is the
    week-1 path (decision #6: the prior season is not consulted, because
    carryover measured worse than the league mean). Otherwise the
    with-history specification is used.

    Both specifications always carry BOTH Vegas terms -- see decision #7. A
    caller cannot select one, on purpose.

    Session 15.2b: `opp_defense_allowed` is the upcoming opponent's own
    recency-weighted volume-allowed on this component -- currently only
    ever fitted for rush (fit_volume_prior.py's fit_team_volume()). Column
    assembly is driven by the fitted spec's own `terms` list, not a
    component check here, so this stays correct automatically if another
    component is ever fit with the same term. If the spec WAS fit with it
    and the caller passes None, that is refused rather than silently
    dropping a real fitted coefficient's input -- the same fail-loud
    stance decision #4 in fit_volume_prior.py takes for a thin curve.
    """
    spec_key = "no_history" if history_volume is None else "with_history"
    spec = artifact["team_volume"][component][spec_key]
    terms = spec.get("terms", [])
    it = pd.to_numeric(pd.Series(implied_total), errors="coerce").to_numpy(float)
    sp = pd.to_numeric(pd.Series(spread), errors="coerce").to_numpy(float)
    n = len(it)

    league_mean = float(artifact["team_volume"][component]["league_mean"])
    # A missing line is not an error -- a team on bye, or a game with no
    # posted total, reaches here legitimately. Fall back to the league mean
    # for that team only, which is decision #6's own measured baseline rather
    # than an invented number.
    it_missing = ~np.isfinite(it)
    sp_missing = ~np.isfinite(sp)
    it = np.where(it_missing, np.nan, it)
    sp = np.where(sp_missing, 0.0, sp)

    cols = [np.ones(n)]
    if spec_key == "with_history":
        hv = pd.to_numeric(pd.Series(history_volume), errors="coerce") \
               .fillna(league_mean).to_numpy(float)
        cols.append(hv)
    cols.append(np.where(np.isfinite(it), it, 0.0))
    cols.append(sp)
    if "opp_rush_allowed" in terms:
        if opp_defense_allowed is None:
            raise SystemExit(
                f"volume_prior team_volume[{component}][{spec_key}] was "
                f"fit with opp_rush_allowed but no opp_defense_allowed was "
                f"passed to predict_team_volume() -- refusing to silently "
                f"drop a real fitted term (Session 15.2b).")
        oda = pd.to_numeric(pd.Series(opp_defense_allowed), errors="coerce") \
                .fillna(league_mean).to_numpy(float)
        cols.append(oda)
    X = np.column_stack(cols)
    beta = np.array(spec["beta"], dtype=float)
    if X.shape[1] != len(beta):
        raise SystemExit(
            f"volume_prior team_volume[{component}][{spec_key}] has "
            f"{len(beta)} coefficients but {X.shape[1]} were assembled. The "
            f"artifact and this consumer are out of sync -- refit with the "
            f"current fit_volume_prior.py.")
    pred = X @ beta

    # Where the line was missing the Vegas terms contributed a spurious zero,
    # so fall back rather than ship a number built from a fake total.
    if spec_key == "with_history":
        hv = pd.to_numeric(pd.Series(history_volume), errors="coerce") \
               .fillna(league_mean).to_numpy(float)
        pred = np.where(it_missing, hv, pred)
    else:
        pred = np.where(it_missing, league_mean, pred)

    lo, hi = TEAM_VOLUME_BOUNDS[component]
    return np.clip(pred, lo, hi)


# ---------------------------------------------------------------------------
# Decisions #2-#5 -- the role-change flag
# ---------------------------------------------------------------------------

def role_change_participation(artifact: dict, participation, hist_share,
                             price_share) -> tuple:
    """Decision #3/#4/#5. Returns (effective_participation, role_change_flag).

        share_target = hist + ROLE_SLOPE * (price - hist)
        part_eff     = clip(part * share_target / hist, part, 1.0)

    ROLE_SLOPE is probe D's fitted out-of-sample regression coefficient
    (+0.4606, t = +95.16), stored in the artifact -- not a constant chosen
    here. Raises only, never lowers (decision #5).
    """
    part = pd.to_numeric(pd.Series(participation), errors="coerce") \
             .fillna(0.0).to_numpy(dtype=float)
    hs = pd.to_numeric(pd.Series(hist_share), errors="coerce") \
           .fillna(0.0).to_numpy(dtype=float)
    ps = pd.to_numeric(pd.Series(price_share), errors="coerce") \
           .fillna(0.0).to_numpy(dtype=float)

    slope = float(artifact["role_change"]["slope"])
    div = ps - hs

    eligible = (
        (div > ROLE_CHANGE_MIN_DIVERGENCE)          # decision #5: raises only
        & (hs > ROLE_CHANGE_MIN_HIST_SHARE)         # decision #4: no /~0
        & (part < 1.0)                              # nothing to raise
        & np.isfinite(div)
    )

    share_target = hs + slope * div
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(hs > 0, share_target / hs, 1.0)
    ratio = np.where(np.isfinite(ratio), ratio, 1.0)

    part_eff = np.where(eligible, np.clip(part * ratio, part, 1.0), part)
    return part_eff, eligible


def describe(artifact: dict) -> str:
    """One-line provenance, for run banners and the harness's arm label."""
    rc = artifact.get("role_change", {})
    return (f"volume prior fit {artifact.get('fit_seasons')} "
            f"({len(artifact.get('share_curves', {}))} share curves, "
            f"role slope {rc.get('slope', float('nan')):.4f})")
