"""
build_projections_statline.py
==============================

Session 10.3a -- the PARALLEL projection engine.

Same job as build_projections.py (Session 2.4): produce
`output/final_projections_{site}_{week}.csv` for a site/season/week. Different
internals: instead of blending points averages, it projects a STAT LINE, then
converts it to that site's points via `scoring_rules.py`, Monte-Carlo'd so the
mean is right despite DK's step-function bonuses and so a per-player sigma
falls out of the same pass.

It EXISTS ALONGSIDE build_projections.py, which is untouched. Per the ROADMAP
card: "Built as a NEW parallel component that co-exists with the current
build_projections.py until the harness says it wins."

Numbered decisions:

  1. SAME OUTPUT FILENAME AND A SUPERSET OF THE SAME SCHEMA. It writes the
     identical path build_projections.py writes, with every legacy column
     present and meaning the same thing, plus new columns appended. That is
     what lets `optimizer.py`, `ownership_heuristic.py`, the frontend and the
     harness all consume it with ZERO changes -- the engines are swapped by
     choosing which script to run, not by teaching everything downstream
     about a second format. The legacy engine's own schema is not touched,
     so Session 2.4's contract is intact (this project's schema-stability
     principle).

     Legacy columns kept, with honest mappings:
       season_avg     -- the stat-line mean with the market factor removed
                         (i.e. the pure usage projection). Not a season
                         average; it is the closest honest analogue and the
                         column is documented here rather than left to be
                         guessed at.
       recent_form    -- same value. There is no second recency scheme in
                         this engine to distinguish it from, and fabricating
                         a fake split would be worse than repeating the real
                         number. Same reasoning build_projections.py's
                         decision #5a already applied to defenses.
       matchup_factor,
       vegas_factor   -- passed through unchanged from Sessions 2.2/2.3, so
                         they still mean what they always meant. Their
                         product is what decision #10 of statline_model.py
                         applies to the efficiency rates.
     New columns appended: sigma, statline_p10, statline_p90, and proj_*
     mean stat-line columns (audit trail -- the whole point of a stat-line
     model is that you can see WHY a projection is what it is).

  2. DST IS REUSED VERBATIM FROM build_projections.py. Session 10.4 owns the
     DST rebuild; re-implementing it here would create a second copy to keep
     in sync and would confound 10.3's measurement with a DST change. The
     import is direct, so a 10.4 fix lands in both engines at once.

     SESSION 10.4 UPDATE: that prediction held. `build_dst_projections()`
     grew a `model=` argument and both engines picked it up with no
     duplicated logic -- this engine just forwards its own `--dst-model`
     flag. Default stays `legacy` here too, so an existing stat-line run is
     unchanged unless the flag is passed.

  3. DST SIGMA IS A MEASURED PLACEHOLDER (SUPERSEDED WHEN
     --dst-model distributional IS PASSED -- Session 10.4 now returns a real
     simulated sigma conditioned on the opponent's implied total, and
     `sigma_source` becomes `dst_simulated_session_10_4`. The constants below
     remain in force for the legacy DST path, which is still the default.) -- not NaN, not zero, and not a
     guess. A defense has no stat-line model until Session 10.4, but a NaN
     here is not an option: Session 10.5's objective
     (`sum(mean) - lambda*sigma`) has to do something with a defense on every
     single lineup, and NaN would either crash it or silently become zero --
     which would assert that a DST has no variance, the least true statement
     available about a DST.

     So it is measured directly, this session, from real data: team-week
     defensive scoring reconstructed over 3,952 real team-weeks (2014-2021)
     by aggregating def_sacks / def_interceptions / fumble_recovery_opp /
     def_safeties / def_tds / special_teams_tds from nflverse weekly stats
     and applying each site's points-allowed brackets to the real final
     scores from nflverse games.csv. Result: mean 6.36, SD 5.78.

     The measurement also CORRECTED the first implementation of this. The
     obvious move -- scale sigma proportionally to the projection -- is
     wrong. Sorting teams into strength quartiles, mean DST scoring rises
     5.24 -> 7.56 (a factor of 1.44) while its SD rises only 5.30 -> 6.21 (a
     factor of 1.17). A good defense is not proportionally more volatile. The
     fitted relationship is therefore affine and mostly flat:
         sigma ~= 3.25 + 0.39 * projection
     which is what ships. Still labelled a placeholder in `sigma_source`,
     because it is an UNCONDITIONAL spread -- Session 10.4's job is to
     condition it on the opponent's implied total, which is the whole reason
     that card exists.

     Known approximations, stated rather than buried: blocked kicks and
     2-point return conversions are not in the reconstruction (nflverse
     weekly stats carry no team-level column for them), and return TDs are
     attributed via players' `special_teams_tds`. Both are small and both
     bias the measured SD slightly LOW, i.e. conservatively.

  4. NO SALARY ANCHOR HERE. Session 10.2 measured the anchor as neutral at
     the points level and explained why (a monotone-in-salary term is nearly
     redundant with the salary cap the ILP already enforces). Its one real
     use, cold start, belongs on the stat-line INPUTS -- Session 10.3b. So
     this engine takes no anchor flags at all rather than offering a knob
     that is known not to work here.

  5. WEEK 1 IS STILL NOT BUILDABLE, and says so. statline_model.py's
     decision #5 keeps projections_baseline.py's lookahead guard, so week 1
     has no prior usage and every projection is 0. Reported explicitly
     instead of emitting a file full of zeros that looks like a bug.

  6. A PLAYER WITH NO USAGE HISTORY GETS 0.0, not a drop -- identical to
     build_projections.py's decision #3, so the two engines' pools differ
     only where the projection genuinely differs, never because one engine
     silently kept or dropped a player the other did not.

  8. THE RECONCILIATION AUDIT TRAIL is written to
     `output/statline_reconcile_{site}_{week}.csv` every run: one row per
     team/component pair with the share used, which basis produced it
     (exclusive / recent / full_season), the raw pool sum, the target and the
     applied scale. Reconciliation adjusts real volume on roughly 80 pairs a
     week and none of it was previously visible after the fact.

  7. THE CONFIRMED-NO-GAME ZERO-OUT IS PRESERVED EXACTLY (build_projections'
     decisions #4a/#4b): team drift is auto-corrected from real data for an
     already-played week, and a player with no real row that week is forced
     to 0.0 rather than neutrally-factored. Reusing the legacy loaders means
     this behaviour is shared code, not a parallel reimplementation that
     could drift.

  9. SESSION 10.3b -- THE VOLUME PRIOR IS OPT-IN AND OFF BY DEFAULT.
     `--volume-prior` turns on price-as-a-cold-start-prior, the
     Vegas-anchored team volume, and the role-change participation override
     together, because they are not separable: cold start needs a team
     volume that is not this season's history (there isn't one in week 1),
     and the role flag needs the price share the cold start already
     computes. Session 10.3b's card listed them as independent bullets;
     probe C measured that they are not. See volume_prior.py decisions
     #1-#8 for the evidence behind each.

     OFF BY DEFAULT, unlike Session 10.4's DST model, and deliberately so:
     10.4 shipped on a measured DST-slot improvement, whereas this card
     ships on a CAPABILITY gate (week 1 becomes buildable, role changes are
     repaired before reconciliation) with no accuracy claim. A component
     that has not been shown to help should not be silently on. Flip the
     default only when a measurement supports it.

     `--volume-prior-floor` (default 0.0) is the mid-season asymptotic
     weight. 0.0 means the prior is a cold-start mechanism ONLY, which is
     what probe A's evidence supports and what the user confirmed: price
     never beat history at any games-played level, so a standing mid-season
     blend is not something to switch on by accident.

Usage:
  python3 scripts/build_projections_statline.py --site dk --season 2021 \
      --week 10 --slate-id rotoguru_2021_wk10
  python3 scripts/build_projections_statline.py --site dk --season 2021 \
      --week 1 --slate-id rotoguru_2021_wk1 --volume-prior
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring_rules  # noqa: E402
import statline_model  # noqa: E402
import sigma_recalibration
import volume_prior  # noqa: E402
from ingest_salaries import SITE_CONFIGS  # noqa: E402
# Decisions #2 and #7: reuse, never re-implement.
# Session 14.0 additions: CAPTAIN_ROLES, is_showdown_slate,
# apply_captain_multiplier, add_showdown_ownership_columns, and
# _build_kicker_projections -- this engine had none of Phase 13's
# Showdown/Single-Game support or Session 13.1's kicker model wired in.
# Reused directly from build_projections.py for the same reason DST
# already was: one implementation, not a second copy that can drift.
from build_projections import (  # noqa: E402
    CAPTAIN_ROLES,
    NO_GAME_SENTINEL,
    POSITIONS,
    add_ownership_columns,
    add_showdown_ownership_columns,
    apply_captain_multiplier,
    build_dst_projections,
    build_opponent_map,
    build_opponent_map_from_salaries,
    build_vegas_factors,
    is_showdown_slate,
    load_matchup_factors,
    load_real_team_for_week,
    load_salaries,
    load_schedule,
    load_vegas_implied_totals,
    _build_kicker_projections,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# Decision #3 -- MEASURED, not assumed: 3,952 real team-weeks, 2014-2021.
# sigma ~= intercept + slope * projection. The slope is well below
# proportional (0.39, not 1.0) because a better defense is barely more
# volatile than a worse one -- see decision #3 for the quartile evidence.
# DK and FD share these values because their defensive scoring components and
# points-allowed brackets are the same; kept per-site so Session 10.4 can
# diverge them without touching any call site.
DST_SIGMA_INTERCEPT = {"dk": 3.25, "fd": 3.25}
DST_SIGMA_SLOPE = {"dk": 0.39, "fd": 0.39}
# Floor/ceiling: the affine fit is only supported over the observed
# projection range, and no real DST has near-zero week-to-week spread.
DST_SIGMA_BOUNDS = (3.0, 9.0)

PROJ_STAT_COLUMNS = [
    "proj_pass_att", "proj_pass_yd", "proj_pass_td", "proj_rush_att",
    "proj_rush_yd", "proj_rush_td", "proj_targets", "proj_rec",
    "proj_rec_yd", "proj_rec_td",
]

LEGACY_COLUMNS = [
    "player_id", "player_name", "position", "team", "salary", "site_player_id",
    "season_avg", "recent_form", "matchup_factor", "vegas_factor",
    "final_projection", "opponent", "implied_total", "over_under",
]


def build_statline_projections(site: str, season: int, week: int, slate_id: str,
                               n_sims: int = statline_model.DEFAULT_SIMS,
                               seed: int = statline_model.DEFAULT_SEED,
                               reconcile_threshold: float = statline_model.RECONCILE_FAIL_THRESHOLD,
                               dst_model_mode: str = "distributional",
                               use_volume_prior: bool = False,
                               prior_floor: float = None,
                               prior_k: float = None,
                               role_change: bool = True,
                               sigma_recal: bool = False,
                               vegas_slate_id: str = None,
                               ) -> pd.DataFrame:
    """`vegas_slate_id` (Session 14.0 -- this engine never had Session
    13.5-pause's fix at all): defaults to `slate_id`. See
    build_projections.py's build_final_projections() docstring for the
    full reasoning; identical convention, kept so a caller passing
    --vegas-slate-id doesn't need to know which engine is running.
    """
    variance = statline_model.load_variance()
    prior_art = volume_prior.load_prior(site) if use_volume_prior else None
    if prior_art is not None:
        print(f"Volume prior ON -- {volume_prior.describe(prior_art)}; "
              f"mid-season floor {prior_floor if prior_floor is not None else volume_prior.DEFAULT_WEIGHT_FLOOR}, "
              f"k {prior_k if prior_k is not None else volume_prior.DEFAULT_COLD_START_K}, "
              f"role-change {'on' if role_change else 'OFF'}.")
    matchup = load_matchup_factors(site, season, week)
    # Session 14.0 FIX: was load_vegas_implied_totals(week) -- crashed on
    # any real slate, since Session 13.5-pause keyed that function's vegas
    # file by slate_id, not week. Same default convention as the legacy
    # engine: falls back to slate_id when vegas_slate_id isn't given.
    vegas = load_vegas_implied_totals(vegas_slate_id if vegas_slate_id else slate_id)
    salaries = load_salaries(site, slate_id)
    schedule = load_schedule(season)

    opponent_map = build_opponent_map(schedule, week)

    # Session 14.0: Showdown/Single-Game support, ported from
    # build_projections.py's build_final_projections() (Session 13.3).
    # Same reasoning as there -- run the whole pipeline on FLEX-priced rows
    # only, derive CPT/MVP rows afterward via apply_captain_multiplier()
    # rather than double-running the pipeline. This engine previously had
    # no Showdown handling at all. Must happen BEFORE the opponent-map
    # fallback below, which needs build_salaries.
    showdown = is_showdown_slate(salaries)
    if showdown:
        build_salaries = salaries[salaries["roster_role"] == "FLEX"].copy()
        captain_salaries = salaries[salaries["roster_role"].isin(CAPTAIN_ROLES)].copy()
        if build_salaries.empty or captain_salaries.empty:
            raise SystemExit(
                f"{slate_id}: slate_format='showdown' but roster_role values "
                f"don't split into FLEX + {sorted(CAPTAIN_ROLES)} as expected "
                f"(Session 13.2 ingest contract). roster_role values present: "
                f"{sorted(salaries['roster_role'].dropna().unique())}."
            )
        print(f"Showdown slate detected (Session 14.0, stat-line engine): "
              f"{len(build_salaries)} FLEX row(s), {len(captain_salaries)} "
              f"captain-equivalent row(s).")
    else:
        build_salaries = salaries
        captain_salaries = None

    # Session 14.0 FIX (found via a real run, not caught in the original
    # audit): decision #9 from build_projections.py -- if the schedule has
    # no entries for any slate team (true for EVERY slate right now, since
    # DFS_Weekly_Process.md's --week 23 sentinel exists specifically to
    # guarantee that), fall back to inferring matchups from the salary
    # file's own Game Info column. This engine had no fallback at all,
    # meaning vegas_factor silently went neutral 1.0 for everyone AND the
    # Vegas-anchored team volume in apply_volume_prior() below had no real
    # per-team implied_total to anchor to -- which is what actually tripped
    # the share-reconciliation fail-loud on the real Week 1 slate that
    # surfaced this gap.
    slate_teams = set(build_salaries["normalized_team"].dropna().unique())
    schedule_covered = slate_teams & set(opponent_map.keys())
    if not schedule_covered:
        print(
            f"NOTE: schedule has no week-{week} games for slate teams -- "
            f"falling back to vegas over_under pairing (decision #9, Madden Sim path).",
            file=sys.stderr,
        )
        opponent_map = build_opponent_map_from_salaries(build_salaries)
        if opponent_map:
            games_found = sorted(set(
                tuple(sorted([k, opponent_map[k]])) for k in opponent_map
            ))
            print(f"  Inferred {len(games_found)} game(s) from salary file: {games_found}", file=sys.stderr)
        else:
            print("  WARNING: could not infer any opponent pairs from salary file. "
                  "All skill players will get opponent=BYE_OR_UNKNOWN.", file=sys.stderr)

    vegas_factors = build_vegas_factors(vegas, opponent_map)

    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    players = build_salaries[build_salaries["position_upper"].isin(POSITIONS)].copy()
    players = players[players["player_id"].notna()]
    players = players.rename(columns={"normalized_team": "team",
                                      "position_upper": "position"})
    players = players[["player_id", "name", "position", "team", "salary", site_id_col]] \
        .rename(columns={"name": "player_name", site_id_col: "site_player_id"})

    # Decision #7: identical team-drift handling to the legacy engine.
    week_was_played, real_team_this_week = load_real_team_for_week(season, week)
    players["no_real_game_this_week"] = False
    if week_was_played:
        corrected = players["player_id"].map(real_team_this_week)
        played = corrected.notna()
        players.loc[played, "team"] = corrected[played]
        players["no_real_game_this_week"] = ~played
        print(f"{int((~played).sum())} player(s) had no real game in week {week} "
              f"-- final_projection forced to 0.0 (build_projections decision #4b).")

    # --- usage + reconciliation -------------------------------------------
    usage = statline_model.build_usage(season, week, variance)
    if usage.empty and prior_art is None:
        print(f"WARNING: no usage history at all before week {week} "
              f"(decision #5 -- week 1 is not buildable by this engine "
              f"without --volume-prior).", file=sys.stderr)
    elif usage.empty:
        print(f"No usage history before week {week}: building from the price "
              f"prior alone (statline_model decision #14).")

    df = players.merge(usage.drop(columns=["position", "hist_team"], errors="ignore"),
                       on="player_id", how="left")
    n_no_history = int(df["games_played"].isna().sum()) if "games_played" in df else len(df)
    if "games_played" in df:
        df["games_played"] = df["games_played"].fillna(0).astype(int)

    if prior_art is not None:
        # Decision #17. Must run BEFORE the rates are used for anything --
        # a cold-start player's volume is worthless multiplied by a NaN rate.
        df = statline_model.fill_cold_start_rates(df, variance)

    df["opponent"] = df["team"].map(opponent_map)
    df.loc[df["no_real_game_this_week"], "opponent"] = None

    matchup_lookup = matchup.set_index(["team", "position"])["matchup_factor"]
    df["matchup_factor"] = df.apply(
        lambda r: matchup_lookup.get((r["opponent"], r["position"])), axis=1)
    df["matchup_factor"] = df["matchup_factor"].fillna(1.0)

    merge_cols = ["team", "vegas_factor", "implied_total"]
    if "over_under" in vegas_factors.columns:
        merge_cols.append("over_under")
    df = df.merge(vegas_factors[merge_cols], on="team", how="left")
    for c in ("vegas_factor", "implied_total", "over_under"):
        if c in df.columns:
            df.loc[df["no_real_game_this_week"], c] = None
    df["vegas_factor"] = df["vegas_factor"].fillna(1.0)

    # Decision #10 of statline_model: the market factor scales efficiency.
    df["market_factor"] = df["matchup_factor"] * df["vegas_factor"]

    # Share reconciliation (statline_model decision #7) -- mandatory per the
    # ROADMAP, because an incoherent QB/receiver pair corrupts stacking.
    team_vol = statline_model.team_volume_history(season, week)

    if prior_art is not None:
        # Team-level spread. build_vegas_factors() drops it (it only ever
        # needed implied_total), but the fitted team-volume specification
        # requires BOTH terms -- volume_prior.py decision #7 -- so it is
        # taken from the raw vegas frame here rather than by widening a
        # Session 2.3 contract that nothing else uses.
        vg = vegas.copy()
        vg["expected_opponent"] = vg["team"].map(opponent_map)
        vg = vg[vg["opponent"] == vg["expected_opponent"]].drop_duplicates("team")
        if "spread" not in vg.columns:
            vg["spread"] = 0.0
        vg = vg.set_index("team")[["implied_total", "spread"]]

        pool_teams = sorted(df.loc[~df["no_real_game_this_week"], "team"]
                            .dropna().astype(str).unique().tolist())
        team_vol = statline_model.vegas_anchored_team_volume(
            team_vol, vg, prior_art, teams=pool_teams)

        for c in ("participation", "games_played"):
            if c not in df.columns:
                df[c] = 0.0
        df = statline_model.apply_volume_prior(
            df, prior_art, team_vol, weight_floor=prior_floor, k=prior_k,
            role_change=role_change)
        n_flag = int(df["role_change_flag"].sum())
        n_cold = int((df["games_played"] <= 1).sum())
        print(f"Volume prior applied: {n_flag} role-change flag(s), "
              f"{n_cold} player(s) at 0-1 games of history "
              f"(mean price weight {df['volume_prior_weight'].mean():.3f}).")

    recon_pool = df[~df["no_real_game_this_week"]].copy()
    if not recon_pool.empty and not team_vol.empty:
        recon_pool, recon_report = statline_model.reconcile_team_shares(
            recon_pool, team_vol, reconcile_threshold)
        for col in ("recv_mu", "rush_mu", "pass_mu"):
            if col in recon_pool.columns:
                df.loc[recon_pool.index, col] = recon_pool[col]
        if len(recon_report):
            worst = recon_report.reindex(
                recon_report["scale"].sub(1.0).abs().sort_values(ascending=False).index).head(3)
            print(f"Share reconciliation: {len(recon_report)} team/component pair(s) "
                  f"rescaled; largest "
                  f"{', '.join(f'{r.team}/{r.component} {r.scale:.2f}x' for r in worst.itertuples())}.")
            # Decision #8: reconciliation moves real volume on ~80 team/component
            # pairs a week, and until now none of it was inspectable after the
            # fact. Written every run so a surprising projection can be traced
            # to the rescale that produced it.
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            recon_report.sort_values(
                "scale", key=lambda c: (c - 1.0).abs(), ascending=False
            # Session 14.0 FIX: was named by {week}, same collision class as
            # the main output filename bug -- see that fix's comment.
            ).to_csv(OUTPUT_DIR / f"statline_reconcile_{site}_{slate_id}.csv", index=False)

    # --- simulate ----------------------------------------------------------
    # Belt-and-suspenders with statline_model._num(): a player with no usage
    # history merges in as NaN across every usage column, and NaN is truthy in
    # Python so the idiomatic `x or 0.0` does not catch it. Guarded in the draw
    # path AND here, the same two-place pattern Session 10.1's bug #2 ($0
    # salary -> NaN value) settled on.
    usage_cols = [c for c in df.columns
                  if c.endswith(("_mu", "_mu_raw", "_yd_rate", "_td_rate",
                                 "_hist_vol", "_price_share", "_price_volume"))
                  or c in ("catch_rate", "int_rate", "participation",
                           "participation_effective", "market_factor")]
    for c in usage_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    sim_input = df[~df["no_real_game_this_week"]].copy()
    sim = statline_model.simulate(sim_input, site, variance, n_sims=n_sims, seed=seed)

    df = df.merge(sim, on="player_id", how="left")
    # Decision #6: no history -> 0.0, never dropped.
    for c in ["statline_mean", "statline_sigma", "statline_p10", "statline_p90"] + PROJ_STAT_COLUMNS:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    df["final_projection"] = df["statline_mean"].clip(lower=0.0)
    df["sigma"] = df["statline_sigma"].clip(lower=0.0)
    df["sigma_source"] = "statline_mc"

    # Decision #1: honest legacy-column mappings.
    safe_factor = df["market_factor"].replace(0, np.nan)
    df["season_avg"] = (df["final_projection"] / safe_factor).fillna(0.0).round(4)
    df["recent_form"] = df["season_avg"]

    # Decision #7: confirmed-no-game rows are zeroed outright.
    no_game = df["no_real_game_this_week"]
    df.loc[no_game, ["final_projection", "sigma", "statline_p10", "statline_p90"]] = 0.0
    df.loc[no_game, "sigma_source"] = "no_game"

    if "over_under" not in df.columns:
        df["over_under"] = None
    df["opponent"] = df["opponent"].fillna(NO_GAME_SENTINEL)
    df["implied_total"] = df["implied_total"].fillna(0.0)
    df["over_under"] = df["over_under"].fillna(0.0)

    skill_out = df[LEGACY_COLUMNS + ["sigma", "sigma_source", "statline_p10",
                                     "statline_p90"] + PROJ_STAT_COLUMNS]

    # --- DST (decisions #2, #3; Session 10.4) ------------------------------
    # Session 14.0 FIX: was build_dst_projections(salaries, ...). Now takes
    # build_salaries, matching build_projections.py's own
    # build_final_projections() call exactly -- keeps this engine's Showdown
    # handling consistent with the skill pool above, which already uses
    # build_salaries.
    dst_out = build_dst_projections(build_salaries, vegas, site, model=dst_model_mode,
                                    season=season, week=week)
    if "sigma" in dst_out.columns:
        # Session 10.4's distributional path returns a real simulated sigma,
        # conditioned on the opponent's implied total. This is the column
        # Session 10.5's objective actually wants; the placeholder below
        # existed only because this did not exist yet.
        dst_out = dst_out.drop(columns=[c for c in ("dst_p10", "dst_p90")
                                        if c in dst_out.columns])
        dst_out = dst_out.assign(
            sigma=dst_out["sigma"].fillna(0.0).round(4),
            sigma_source=np.where(dst_out["final_projection"] > 0,
                                  "dst_simulated_session_10_4", "no_game"),
            statline_p10=0.0,
            statline_p90=0.0,
        )
    else:
        dst_sigma = (DST_SIGMA_INTERCEPT[site]
                     + DST_SIGMA_SLOPE[site] * dst_out["final_projection"]
                     ).clip(*DST_SIGMA_BOUNDS)
        dst_out = dst_out.assign(
            sigma=dst_sigma.where(dst_out["final_projection"] > 0, 0.0).round(4),
            sigma_source=np.where(dst_out["final_projection"] > 0,
                                  "dst_measured_unconditional_session_10_4_pending",
                                  "no_game"),
            statline_p10=0.0,
            statline_p90=0.0,
        )
    for c in PROJ_STAT_COLUMNS:
        dst_out[c] = 0.0
    dst_out = dst_out[skill_out.columns]

    # --- Kicker (Session 13.1 -- this engine never had it wired in at all)
    # Only produces rows for a Showdown/Single-Game pool (classic DK/FD carry
    # no K slot at all, same as build_projections.py's own
    # _build_kicker_projections() docstring notes), but must be built
    # unconditionally -- a classic slate just gets an empty, correctly-
    # columned frame back, same behavior as the legacy engine.
    kicker_out = _build_kicker_projections(build_salaries, site, opponent_map)
    if len(kicker_out):
        # kicker_out's schema is LEGACY_COLUMNS + sigma/dst_p10/dst_p90 (the
        # legacy engine's naming) -- reconcile onto this engine's own
        # sigma_source/statline_p10/statline_p90/PROJ_STAT_COLUMNS schema
        # rather than teaching _build_kicker_projections() a second output
        # shape.
        kicker_out = kicker_out.rename(
            columns={"dst_p10": "statline_p10", "dst_p90": "statline_p90"})
        kicker_out["sigma_source"] = np.where(
            kicker_out["final_projection"] > 0,
            "kicker_session_13_1", "no_game")
        for c in PROJ_STAT_COLUMNS:
            kicker_out[c] = 0.0
    kicker_out = kicker_out[skill_out.columns] if len(kicker_out) else \
        pd.DataFrame(columns=skill_out.columns)

    out = pd.concat([skill_out, dst_out, kicker_out], ignore_index=True)

    # Session 10.4b (decision #12 of this file) -- sigma dispersion
    # recalibration. OFF by default, so an existing stat-line run is
    # byte-for-byte unchanged. Applied AFTER the skill+DST concat because the
    # artifact is fit per position across the whole pool, and BEFORE the
    # ownership columns purely for readability -- ownership derives from
    # final_projection and is untouched by sigma either way.
    #
    # Why this exists: probe_sigma_quality.py's probe B3 measured the
    # engine's per-player sigma to be correctly RANKED (Spearman +0.31 to
    # +0.45) but massively OVER-DISPERSED (realized/projected ratio falling
    # ~2.1-2.7 -> ~0.58-0.69 across sigma quintiles at every position). The
    # LEVEL was already right, which is why Session 10.3a's capability gate
    # passed and this went unnoticed. Session 10.5's objective squares sigma,
    # and because the distortion is non-linear while lambda is a scalar, no
    # lambda can undo it. See sigma_recalibration.py's module docstring.
    if sigma_recal:
        out = sigma_recalibration.apply_recalibration(out, site)

    # Session 14.0: derive CPT/MVP rows from the FLEX-priced projections
    # just built (same pattern as build_projections.py's Session 13.3),
    # and route to the Showdown-aware ownership grouping. This engine
    # previously had neither.
    if showdown:
        out["roster_role"] = "FLEX"
        captain_out = apply_captain_multiplier(out, captain_salaries, site)
        out = pd.concat([out, captain_out], ignore_index=True)
        out["slate_format"] = "showdown"
        out = add_showdown_ownership_columns(out, site)
    else:
        out = add_ownership_columns(out, site)
        out["roster_role"] = None
        out["slate_format"] = "classic"
        out["ownership_available"] = True

    out = out.sort_values("final_projection", ascending=False).reset_index(drop=True)

    print(f"{n_no_history} player(s) had no usage history before week {week} "
          f"(0.0 projection, decision #6).")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Session 10.3a stat-line projection engine (parallel to build_projections.py).")
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", required=True)
    parser.add_argument("--vegas-slate-id", default=None,
                        help="Which vegas_implied_totals_{X}.csv to read, if "
                             "it's NOT the same as --slate-id. Defaults to "
                             "--slate-id (Session 14.0 -- same convention as "
                             "the legacy engine).")
    parser.add_argument("--statline-sims", type=int, default=statline_model.DEFAULT_SIMS,
                        help="Monte-Carlo draws per player (decision #1).")
    parser.add_argument("--statline-seed", type=int, default=statline_model.DEFAULT_SEED,
                        help="Seed for this engine's OWN Generator. Never touches "
                             "the global numpy RNG (statline_model decision #2).")
    # Session 10.4 -- forwarded straight to build_dst_projections(). Default
    # legacy, so an existing stat-line run is unchanged.
    parser.add_argument("--dst-model", choices=["legacy", "distributional"],
                        default="distributional",
                        help="DST projection model (Session 10.4, DEFAULT "
                             "since that session). 'distributional' also "
                             "replaces the placeholder DST sigma with a real "
                             "simulated one, which is what Session 10.5's "
                             "objective needs. 'legacy' restores the "
                             "pre-10.4 DST and its unconditional sigma.")
    # Session 10.3b (decision #9). One flag turns on all three mechanisms,
    # because probe C measured that they are not separable.
    parser.add_argument("--volume-prior", action="store_true",
                        help="Enable the Session 10.3b volume prior: price as "
                             "a cold-start prior on volume, Vegas-anchored "
                             "team volume, and the role-change participation "
                             "override. OFF by default -- this card ships on "
                             "a capability gate, not a measured improvement.")
    parser.add_argument("--volume-prior-floor", type=float, default=None,
                        help="Mid-season asymptotic weight on the price side "
                             f"(default {volume_prior.DEFAULT_WEIGHT_FLOOR} = "
                             "cold start only; probe A measured price losing "
                             "to history at every games-played level, so "
                             "raising this is not a free win).")
    parser.add_argument("--volume-prior-k", type=float, default=None,
                        help="Half-weight point of the cold-start schedule "
                             f"(default {volume_prior.DEFAULT_COLD_START_K}, "
                             "ARBITRARY and unfit -- first retuning target).")
    parser.add_argument("--no-role-change", action="store_true",
                        help="Disable the participation override only, "
                             "keeping cold start and Vegas team volume. For "
                             "attributing a result to one mechanism.")
    # Session 10.4b. OFF by default: this session ships the correction, and
    # the default is flipped only once the probe re-run confirms probe B3's
    # ratio column flattens. "Never silently change existing behavior."
    parser.add_argument("--sigma-recalibration", action="store_true",
                        help="Apply the Session 10.4b per-position sigma "
                             "dispersion correction from "
                             "data/sigma_recalibration.json. OFF by default. "
                             "Corrects a measured over-dispersion that no "
                             "single lambda in Session 10.5's objective could "
                             "undo, because the distortion is non-linear in "
                             "sigma. Fails loud if the artifact is missing or "
                             "was fit for a different site.")
    parser.add_argument("--reconcile-threshold", type=float,
                        default=statline_model.RECONCILE_FAIL_THRESHOLD,
                        help="Max proportional share-reconciliation rescale before "
                             "hard error (statline_model decision #7).")
    args = parser.parse_args()

    result = build_statline_projections(
        args.site, args.season, args.week, args.slate_id,
        n_sims=args.statline_sims, seed=args.statline_seed,
        reconcile_threshold=args.reconcile_threshold,
        dst_model_mode=args.dst_model,
        use_volume_prior=args.volume_prior,
        prior_floor=args.volume_prior_floor,
        prior_k=args.volume_prior_k,
        role_change=not args.no_role_change,
        sigma_recal=args.sigma_recalibration,
        vegas_slate_id=args.vegas_slate_id)

    def _clean_site_id(value):
        if pd.isna(value):
            return None
        s = str(value).strip()
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        return s
    result["site_player_id"] = result["site_player_id"].map(_clean_site_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Session 14.0 FIX: was named by {week}, not {slate_id} -- the exact bug
    # Session 2.4 already fixed in the legacy engine. Two slates sharing a
    # week (Madden Sim, Showdown/classic same week, etc.) would silently
    # overwrite each other's output.
    out_path = OUTPUT_DIR / f"final_projections_{args.site}_{args.slate_id}.csv"
    result.to_csv(out_path, index=False)

    n_null = result[LEGACY_COLUMNS].isna().any(axis=1).sum()
    n_neg = int((result["final_projection"] < 0).sum())
    n_nonzero = int((result["final_projection"] > 0).sum())
    n_sigma_zero = int(((result["final_projection"] > 0) & (result["sigma"] <= 0)).sum())
    print(f"Wrote {len(result)} players to {out_path}")
    print(f"  Sigma recalibration (10.4b): "
          f"{'ON' if args.sigma_recalibration else 'OFF'}")
    print(f"  Nulls in any legacy column: {n_null} (should be 0)")
    print(f"  Negative final_projection: {n_neg} (should be 0)")
    print(f"  Players with a positive projection: {n_nonzero}")
    print(f"  Positive projection but zero sigma: {n_sigma_zero} (should be 0 -- "
          f"a real projection with no variance would break Session 10.5's objective)")
    if n_nonzero == 0:
        print("  NOTE: every projection is 0.0 -- expected for week 1 "
              "WITHOUT --volume-prior (decision #5). With the prior on, or "
              "for any other week, this is a real problem.")
