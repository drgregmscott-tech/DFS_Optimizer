"""
dst_model.py
=============

Session 10.4 -- the DST projection engine. Consumes `data/dst_model.json`
(written by `fit_dst_model.py`) and produces a per-defense mean AND sigma by
Monte-Carlo simulation.

Deliberately separate from the fitter, the same split Session 10.2 made
between `salary_anchor.py` and `fit_salary_anchor.py`: the production path
never imports the fitting machinery.

What this replaces
------------------
`build_projections.py`'s decision #5: `AvgPointsPerGame * (league_avg_implied
/ opponent_implied)`, `matchup_factor` pinned at 1.0, and Session 10.3a's
unconditional `sigma = 3.25 + 0.39 * projection`. That model cannot see a
single defensive component, and it reads a step function at a point estimate.

Numbered decisions (continuing fit_dst_model.py's numbering):

 12. MONTE CARLO, FOR THE SAME REASON SESSION 10.3a USED IT, ONLY MORE SO.
     The points-allowed brackets are a step function with 3-point steps.
     Measured over 3,952 real team-weeks: integrating the bracket table over
     the fitted negative binomial returns a mean of 0.433 against a realized
     0.479, while looking the bracket up at the point estimate returns 0.181.
     The point estimate is biased low by 0.30 points on EVERY defense,
     compresses the spread across defenses by 19% (SD 0.860 -> 0.696), and
     ranks worse against realized outcomes (Spearman 0.369 -> 0.336).

     For skill positions the equivalent error was worth about 2 points on the
     players near a bonus threshold. Here it is a systematic bias on every
     single defense in the pool plus a compression of exactly the ordering
     the optimizer selects on. This is the card's central premise and it
     measures out.

 13. A LATENT "DEFENSIVE DOMINANCE" FACTOR, BECAUSE INDEPENDENT DRAWS ARE
     MEASURABLY TOO NARROW. A defense that holds an offense down also tends
     to sack and intercept it -- these are not independent events, they are
     the same afternoon. Measured on real team-weeks:

         corr(points-allowed residual, takeaways)   -0.267
         corr(points-allowed residual, sacks)       -0.290
         corr(bracket points, all other components) +0.301

     Drawing every component independently gives a total DST sigma of 5.138
     against a realized 5.782 -- an 11% understatement, and understating
     sigma is the one direction that actively misleads Session 10.5's
     `sum(mean) - lambda*sigma` objective, since it would make defenses look
     falsely safe.

     Fixed the same way Session 10.3a fixed the yards/TD correlation: one
     standard normal per simulated game-week scales the points-allowed mean
     down and the component rates up together. Its strength is CALIBRATED
     against the measured +0.301, not guessed -- see `calibrate_latent()`.

 14. SIGMA IS NOW CONDITIONAL, WHICH IS THE WHOLE REASON THIS CARD BLOCKS
     SESSION 10.5. Session 10.3a shipped `3.25 + 0.39 * projection` flagged
     `dst_measured_unconditional_session_10_4_pending`. That was measured
     honestly but it is a function of the projection alone, so two defenses
     with the same mean got the same sigma no matter who they played. Here
     sigma falls out of the same simulation as the mean, conditioned on the
     opponent's implied total, so a defense facing a 17-point team and one
     facing a 27-point team no longer share a variance. `sigma_source`
     becomes `dst_simulated_session_10_4`.

 15. EARLY-SEASON AND WEEK 1 ARE HANDLED BY PRIOR-SEASON CARRYOVER, NOT BY
     GIVING UP. Every team rate is shrunk twice: the previous season's team
     rate is itself shrunk toward the league mean, and that becomes the prior
     the current season-to-date rate updates. At week 1 the season-to-date
     sample is empty and the projection is the carried-over prior, which is a
     real number rather than a zero.

     This makes DST buildable in week 1, which the legacy model also managed
     (via the salary file's `AvgPointsPerGame`, which in a real week-1 export
     carries last season's average) but which the stat-line engine's skill
     positions still cannot do until Session 10.3b. Noted because it is a
     free side benefit, not a claim that week 1 is now solved.

 16. FAIL LOUD ON A MISSING OPPONENT, ZERO ON A BYE. A defense with no row in
     `vegas_implied_totals_{week}.csv` has no game that week; its projection
     is forced to 0.0 and its sigma to 0.0, matching `build_projections.py`'s
     decision #5 bye handling and decision #4b's philosophy exactly. A
     defense that HAS a game but whose opponent's team stats cannot be found
     is a different thing entirely -- that is a data error, and it raises
     rather than silently falling back to a league-average defense.

 17. THE PROJECTION IS CLIPPED AT BOTH ENDS, AND THE CLIPS ARE NOT ARBITRARY.
     Points allowed is clipped to [3, 45] before drawing: the fitted linear
     model is only supported over the observed implied-total range, and an
     extrapolated mean outside that band would be read through a bracket
     table that is very sensitive at the edges. 3 and 45 bracket the real
     observed range with room to spare.

 18. NO SALARY ANCHOR, SAME REASONING AS `build_projections_statline.py`'s
     decision #4. Session 10.2 measured the points-level blend neutral and
     explained why. A DST's price carries the same information as its
     opponent's implied total, only noisier.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring_rules  # noqa: E402
from ingest_salaries import BASE_TEAM_ABBREV_MAP  # noqa: E402


def canonical_team(s):
    """Decision #12 (see fit_dst_model.py). `games.parquet` uses era-correct
    team codes, `team_stats_*.parquet` and `weekly_stats_*.parquet` use the
    current franchise code retroactively. Every join in this file crosses
    that boundary, so every one of them normalises first.

    Reuses ingest_salaries.py's BASE_TEAM_ABBREV_MAP rather than declaring a
    second mapping. Site overrides are deliberately not applied -- this is
    nflverse-to-nflverse reconciliation, not a site export.
    """
    return (pd.Series(s, dtype="object").astype(str).str.strip().str.upper()
            .map(lambda t: BASE_TEAM_ABBREV_MAP.get(t, t)))

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODEL_PATH = DATA_DIR / "dst_model.json"

SUPPORTED_SCHEMA = 1
DEFAULT_SIMS = 20000
DEFAULT_SEED = 20104

# Decision #17.
PA_MEAN_BOUNDS = (3.0, 45.0)
DROPBACK_BOUNDS = (15.0, 60.0)
SACK_RATE_BOUNDS = (0.01, 0.16)
INT_RATE_BOUNDS = (0.002, 0.070)


# ---------------------------------------------------------------------------
# Model artifact
# ---------------------------------------------------------------------------

def load_model(path: Path = MODEL_PATH) -> dict:
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Fit it first:\n"
            f"  python3 scripts/fit_dst_model.py\n"
            f"(Session 10.4. The DST model is not shipped pre-fitted -- the "
            f"fit window is a deliberate choice, see that script's decision "
            f"#11.)"
        )
    model = json.loads(path.read_text())
    version = model.get("schema_version")
    if version != SUPPORTED_SCHEMA:
        raise SystemExit(
            f"{path.name} has schema_version {version}, this code supports "
            f"{SUPPORTED_SCHEMA}. Refit with the current fit_dst_model.py "
            f"rather than reading a stale artifact -- a silently-mismatched "
            f"model would project plausible-looking wrong numbers."
        )
    return model


# ---------------------------------------------------------------------------
# Feature assembly (decision #15)
# ---------------------------------------------------------------------------

def _shrink(total, count, prior_rate, k):
    """Empirical-Bayes rate: (observed + k*prior) / (count + k)."""
    total = np.asarray(total, dtype=float)
    count = np.asarray(count, dtype=float)
    return (total + k * np.asarray(prior_rate, dtype=float)) / (count + k)


def load_team_stats(season: int) -> pd.DataFrame:
    path = DATA_DIR / f"team_stats_{season}.parquet"
    if not path.exists():
        raise SystemExit(
            f"{path.name} not found -- the DST model needs nflverse team-week "
            f"stats. Run:\n"
            f"  python3 scripts/ingest_historical.py --season {season}\n"
            f"(Session 10.4 added the team-stats pull to that script.)\n\n"
            f"NOTE FOR THE AUTOMATED REFRESH: since Session 10.4 the "
            f"distributional DST is the DEFAULT, so this file is now a "
            f"required input to every projection build -- including the "
            f"GitHub Actions refresh, which must pull the CURRENT season's "
            f"team stats each week or the DST model runs on prior-season "
            f"carryover alone. If you need a build to succeed right now "
            f"without it, pass --dst-model legacy explicitly; that is a "
            f"deliberate downgrade, not a fallback this code will take on "
            f"your behalf."
        )
    df = pd.read_parquet(path)
    df = df[df["season_type"] == "REG"].copy()
    df["team"] = canonical_team(df["team"])
    df["opponent_team"] = canonical_team(df["opponent_team"])
    return df


def _season_totals(team_stats: pd.DataFrame, upto_week: int | None) -> pd.DataFrame:
    """Aggregate a season's team-weeks. `upto_week` is EXCLUSIVE -- passing
    the target week gives strictly-prior data and no lookahead."""
    df = team_stats if upto_week is None else team_stats[team_stats["week"] < upto_week]
    if df.empty:
        return pd.DataFrame(columns=["team", "games"])

    # Defense's own side.
    own = df.groupby("team", as_index=False).agg(
        games=("week", "count"),
        sacks=("def_sacks", "sum"),
        ints=("def_interceptions", "sum"),
        fum=("fumble_recovery_opp", "sum"),
    )
    # Volume faced: the opponent's dropbacks in those same games.
    faced = df[["season", "week", "team", "opponent_team"]].merge(
        df[["season", "week", "team", "attempts", "sacks_suffered", "carries",
            "passing_interceptions", "fumbles_lost_total"]].rename(
                columns={"team": "opponent_team"}),
        on=["season", "week", "opponent_team"], how="left")
    faced["dropbacks"] = (pd.to_numeric(faced["attempts"], errors="coerce").fillna(0.0)
                          + pd.to_numeric(faced["sacks_suffered"], errors="coerce").fillna(0.0))
    faced_agg = faced.groupby("team", as_index=False).agg(
        dropbacks_faced=("dropbacks", "sum"))
    own = own.merge(faced_agg, on="team", how="left")

    # Offense's own side (used when this team is somebody else's opponent).
    off = df.groupby("team", as_index=False).agg(
        off_games=("week", "count"),
        sacks_allowed=("sacks_suffered", "sum"),
        pass_att=("attempts", "sum"),
        ints_thrown=("passing_interceptions", "sum"),
        fumbles_lost=("fumbles_lost_total", "sum"),
    )
    off["off_dropbacks"] = off["pass_att"] + off["sacks_allowed"]
    return own.merge(off, on="team", how="outer")


def build_features(season: int, week: int, teams, vegas: pd.DataFrame,
                   model: dict, games: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assemble one feature row per defense in `teams`.

    `vegas` is `vegas_implied_totals_{week}.csv` as build_projections.py
    loads it (columns: team, opponent, implied_total, over_under). A team
    absent from it has no game -- decision #16.
    """
    # Decision #12 -- normalise the caller's team codes before anything
    # joins on them. The vegas file comes from a site-normalised source and
    # `teams` from the salary file, both of which can carry a legacy code.
    vegas = vegas.copy()
    vegas["team"] = canonical_team(vegas["team"]).to_numpy()
    vegas["opponent"] = canonical_team(vegas["opponent"]).to_numpy()
    teams = list(canonical_team(list(teams)))
    if games is not None and not games.empty:
        games = games.copy()
        games["home_team"] = canonical_team(games["home_team"]).to_numpy()
        games["away_team"] = canonical_team(games["away_team"]).to_numpy()

    lg = model["league_means"]
    shrink = model["shrink_games"]

    cur = _season_totals(load_team_stats(season), upto_week=week)
    try:
        prev = _season_totals(load_team_stats(season - 1), upto_week=None)
    except SystemExit:
        prev = pd.DataFrame(columns=cur.columns)

    lg_sack_rate = lg["sacks"] / lg["dropbacks"]
    lg_int_rate = model["int_rate"]["league_int_rate"]
    lg_fum = model["fumble_recovery"]["league_rate_per_game"]

    # Decision #15: the rate table must cover EVERY team in the universe, not
    # just those with rows in the current season-to-date frame -- otherwise
    # week 1 (empty by construction) produces an empty table and decision
    # #16's guard fires on what is actually the carryover case working as
    # designed. Found by running week 1, not by reading the code.
    # The universe must include every team REFERENCED, not just every team
    # being projected: a defense's opponent needs rates even when that
    # opponent is not itself in the pool (a different slate, or an actuals
    # file that spells a relocated team the old way). Missing this made week 1
    # trip decision #16's guard on what was really a lookup gap.
    universe = sorted(
        set(map(str, teams))
        | set(vegas["team"].astype(str)) | set(vegas["opponent"].dropna().astype(str))
        | (set(cur["team"].astype(str)) if not cur.empty else set())
        | (set(prev["team"].astype(str)) if not prev.empty else set()))

    def rates(frame, prior=None):
        """Return per-team shrunk rates; `prior` supplies the prior means.

        Reindexed onto `universe`, so a team with no rows yet gets zeros for
        its observed totals and therefore falls back cleanly to the prior.
        """
        frame = frame.copy() if not frame.empty else pd.DataFrame({"team": []})
        frame["team"] = frame["team"].astype(str) if len(frame) else frame.get("team")
        f = (pd.DataFrame({"team": universe})
             .merge(frame, on="team", how="left"))
        # A week-1 call has an EMPTY season-to-date frame by construction
        # (decision #15), so every one of these columns can be absent. Create
        # them at 0.0 rather than letting `.get()` hand back a scalar NaN --
        # that failure was silent enough to reach a traceback three layers
        # down rather than here.
        for c in ("games", "sacks", "ints", "fum", "dropbacks_faced",
                  "off_games", "sacks_allowed", "pass_att", "ints_thrown",
                  "off_dropbacks", "fumbles_lost"):
            if c not in f.columns:
                f[c] = 0.0
            f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0)
        p = prior if prior is not None else {}
        out = pd.DataFrame({"team": f["team"]})
        out["own_sack_rate"] = _shrink(
            f["sacks"], f["dropbacks_faced"],
            p.get("own_sack_rate", lg_sack_rate), shrink["sack_rate"] * lg["dropbacks"])
        out["own_int_rate"] = _shrink(
            f["ints"], f["dropbacks_faced"],
            p.get("own_int_rate", lg_int_rate), shrink["int_rate"] * lg["dropbacks"])
        out["own_fum_rate"] = _shrink(
            f["fum"], f["games"], p.get("own_fum_rate", lg_fum), shrink["fumble_rate"])
        out["opp_sack_allowed_rate"] = _shrink(
            f["sacks_allowed"], f["off_dropbacks"],
            p.get("opp_sack_allowed_rate", lg_sack_rate),
            shrink["sack_rate"] * lg["dropbacks"])
        out["opp_dropbacks"] = _shrink(
            f["off_dropbacks"], f["off_games"],
            p.get("opp_dropbacks", lg["dropbacks"]), shrink["dropbacks"])
        return out

    prev_rates = rates(prev)
    prior_map = {c: prev_rates.set_index("team")[c] for c in prev_rates.columns if c != "team"}

    cur_rates = rates(cur)
    # Second shrink: current season-to-date updates the carried-over prior.
    prev_idx = prev_rates.set_index("team")
    for c in [c for c in cur_rates.columns if c != "team"]:
        carried = cur_rates["team"].map(prev_idx[c]) if not prev_idx.empty else np.nan
        default = {"own_sack_rate": lg_sack_rate, "own_int_rate": lg_int_rate,
                   "own_fum_rate": lg_fum, "opp_sack_allowed_rate": lg_sack_rate,
                   "opp_dropbacks": lg["dropbacks"]}[c]
        cur_rates[c + "_prior"] = pd.to_numeric(carried, errors="coerce").fillna(default)

    cur_idx = cur.set_index("team") if not cur.empty else pd.DataFrame()
    games_played = (pd.Series(list(teams)).map(cur_idx["games"]).fillna(0.0)
                    if "games" in cur_idx.columns else pd.Series(0.0, index=range(len(list(teams)))))

    rate_idx = cur_rates.set_index("team")
    rows = []
    vg = vegas.drop_duplicates(subset=["team"]).set_index("team")
    for team in teams:
        has_game = team in vg.index
        opp = vg.at[team, "opponent"] if has_game else None
        opp_implied = float(vg.at[opp, "implied_total"]) if (has_game and opp in vg.index) else np.nan
        rec = {"team": team, "has_game": bool(has_game and not np.isnan(opp_implied)),
               "opponent": opp, "opp_implied": opp_implied,
               "own_implied": float(vg.at[team, "implied_total"]) if has_game else 0.0,
               "over_under": float(vg.at[team, "over_under"]) if (has_game and "over_under" in vg.columns) else 0.0}
        for c in ("own_sack_rate", "own_int_rate", "own_fum_rate"):
            rec[c] = float(rate_idx.at[team, c]) if team in rate_idx.index else np.nan
        for c in ("opp_sack_allowed_rate", "opp_dropbacks"):
            if opp is not None and opp in rate_idx.index:
                rec[c] = float(rate_idx.at[opp, c])
            else:
                rec[c] = np.nan
        rec["own_epa_prior"] = 0.0   # see build_dst_features_epa below
        rows.append(rec)
    feat = pd.DataFrame(rows)

    # Decision #16: a team WITH a game whose opponent has no stats at all is
    # a data error, not a bye.
    broken = feat[feat["has_game"] & feat["opp_sack_allowed_rate"].isna()]
    if not broken.empty:
        raise SystemExit(
            f"dst_model: {len(broken)} defense(s) have a game this week but "
            f"no team stats could be found for their opponent: "
            f"{broken[['team', 'opponent']].to_dict('records')[:5]}\n"
            f"That is a data problem (team abbreviation mismatch between the "
            f"vegas file and team_stats_{season}.parquet), not a bye. Not "
            f"falling back to a league-average defense -- that would project "
            f"a plausible number from broken inputs."
        )

    feat["games_played"] = games_played.to_numpy() if len(games_played) == len(feat) else 0.0
    feat = _attach_epa_and_wind(feat, season, week, games, model)
    feat = _attach_opponent_qb(feat, season, week, games, model)
    return feat


def _attach_opponent_qb(feat: pd.DataFrame, season: int, week: int,
                        games: pd.DataFrame | None, model: dict) -> pd.DataFrame:
    """Decision #8 -- the opponent's starting QB's career interception rate,
    shrunk toward the league mean, plus a rookie flag.

    Two sources, in order, because the backtest and the live path genuinely
    differ:

      1. `games.parquet`'s `home_qb_id`/`away_qb_id` for the target week.
         Populated for a completed game, which is the backtest case. This is
         the announced starter, so using it is not hindsight about the game's
         outcome -- but it IS unavailable before kickoff for a future week.
      2. The opponent's leading passer in their most recent PRIOR game. This
         is the live path, and it is also the honest fallback whenever the
         announced starter is not yet known.

    If neither resolves, the league mean is used and the rookie flag is
    False. That is a real degradation rather than an error: a defense with an
    unknown opposing quarterback still has to be projected, and the league
    rate is the correct thing to fall back to. The `qb_source` column records
    which path each row took so a run can be audited.
    """
    it_m = model["int_rate"]
    lg_rate = it_m["league_int_rate"]
    k = it_m["qb_shrink_attempts"]

    # Career-to-date passing, strictly before this week.
    frames = []
    for s in (season - 1, season):
        path = DATA_DIR / f"weekly_stats_{s}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        feat["qb_int_rate"] = lg_rate
        feat["opp_qb_is_rookie"] = False
        feat["qb_source"] = "league_mean_no_history"
        return feat

    sp = pd.concat(frames, ignore_index=True)
    sp = sp[sp["season_type"] == "REG"].copy()
    sp["team"] = canonical_team(sp["team"])
    for c in ("attempts", "passing_interceptions"):
        sp[c] = pd.to_numeric(sp[c], errors="coerce").fillna(0.0)
    prior = sp[(sp["season"] < season) | ((sp["season"] == season) & (sp["week"] < week))]
    passers = prior[prior["attempts"] > 0]

    career = passers.groupby("player_id").agg(
        att=("attempts", "sum"), ints=("passing_interceptions", "sum"),
        first_season=("season", "min"))
    career["rate"] = (career["ints"] + k * lg_rate) / (career["att"] + k)
    career["is_rookie"] = (career["first_season"] == season)

    # Source 1: the announced starter from the schedule.
    starter = {}
    if games is not None and not games.empty:
        wk = games[(games["season"] == season) & (games["week"] == week)]
        for g in wk.itertuples():
            starter[g.home_team] = getattr(g, "home_qb_id", None)
            starter[g.away_team] = getattr(g, "away_qb_id", None)

    # Source 2: each team's leading passer in their most recent prior game.
    recent = passers.sort_values(["season", "week"])
    last_game = recent.groupby("team")[["season", "week"]].max()
    lead = {}
    for team, row in last_game.iterrows():
        g = recent[(recent["team"] == team) & (recent["season"] == row["season"])
                   & (recent["week"] == row["week"])]
        if not g.empty:
            lead[team] = g.loc[g["attempts"].idxmax(), "player_id"]

    rates, rookies, sources = [], [], []
    for row in feat.itertuples():
        opp = row.opponent
        qb_id, source = None, "league_mean_unknown_qb"
        if opp is not None:
            cand = starter.get(opp)
            if cand is not None and not pd.isna(cand) and cand in career.index:
                qb_id, source = cand, "announced_starter"
            else:
                cand = lead.get(opp)
                if cand is not None and cand in career.index:
                    qb_id, source = cand, "last_game_leading_passer"
        if qb_id is None:
            rates.append(lg_rate); rookies.append(False); sources.append(source)
        else:
            rates.append(float(career.at[qb_id, "rate"]))
            rookies.append(bool(career.at[qb_id, "is_rookie"]))
            sources.append(source)
    feat["qb_int_rate"] = rates
    feat["opp_qb_is_rookie"] = rookies
    feat["qb_source"] = sources
    return feat


def _attach_epa_and_wind(feat: pd.DataFrame, season: int, week: int,
                         games: pd.DataFrame | None, model: dict) -> pd.DataFrame:
    """Own-defense EPA allowed (prior weeks) and this week's wind."""
    ts = load_team_stats(season)
    prior = ts[ts["week"] < week]
    if not prior.empty:
        epa = prior[["season", "week", "team", "opponent_team"]].merge(
            prior[["season", "week", "team", "passing_epa", "rushing_epa"]].rename(
                columns={"team": "opponent_team"}),
            on=["season", "week", "opponent_team"], how="left")
        epa["allowed"] = (pd.to_numeric(epa["passing_epa"], errors="coerce").fillna(0.0)
                          + pd.to_numeric(epa["rushing_epa"], errors="coerce").fillna(0.0))
        epa_mean = epa.groupby("team")["allowed"].mean()
        feat["own_epa_prior"] = feat["team"].map(epa_mean).fillna(0.0)
    else:
        feat["own_epa_prior"] = 0.0

    # Decision #5 of the fitter -- wind, zero indoors and zero when unknown.
    feat["wind_eff"] = 0.0
    if games is not None and not games.empty:
        wk = games[(games["season"] == season) & (games["week"] == week)]
        wind_by_team, indoor_by_team = {}, {}
        for g in wk.itertuples():
            for t in (g.home_team, g.away_team):
                wind_by_team[t] = getattr(g, "wind", np.nan)
                indoor_by_team[t] = str(getattr(g, "roof", "")) in ("dome", "closed")
        w = pd.to_numeric(feat["team"].map(wind_by_team), errors="coerce").fillna(0.0)
        indoor = feat["team"].map(indoor_by_team).fillna(False).astype(bool)
        feat["wind_eff"] = np.where(indoor, 0.0,
                                    w.clip(0.0, model["wind_clip_mph"]))
    return feat


# ---------------------------------------------------------------------------
# Simulation (decisions #12, #13)
# ---------------------------------------------------------------------------

def _nb_draw(rng, mean, dispersion, size):
    """Negative binomial with mean `mean` and var = mean + mean^2/r."""
    mean = np.clip(np.asarray(mean, dtype=float), 1e-6, None)
    r = float(dispersion)
    p = r / (r + mean)
    return rng.negative_binomial(r, p, size=size)


def simulate(features: pd.DataFrame, site: str, model: dict,
             n_sims: int = DEFAULT_SIMS, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Return one row per defense with mean, sigma, percentiles and the mean
    of each simulated component (the audit trail)."""
    rng = np.random.default_rng(seed)
    pa_m, db_m = model["points_allowed"], model["dropbacks"]
    sk_m, it_m = model["sack_rate"], model["int_rate"]
    fum_m, rare = model["fumble_recovery"], model["rare_events"]
    latent = float(model.get("latent_factor", {}).get("strength", 0.0))

    n = len(features)
    out = {k: np.zeros(n) for k in
           ("final_projection", "sigma", "p10", "p90",
            "proj_points_allowed", "proj_sack", "proj_interception",
            "proj_fumble_recovery", "proj_def_td", "proj_st_td",
            "proj_bracket_points")}

    for i, row in enumerate(features.itertuples()):
        if not row.has_game:
            continue  # decision #16 -- bye stays at 0.0 everywhere.

        # --- means -------------------------------------------------------
        mu_pa = (pa_m["intercept"]
                 + pa_m["coefficients"]["opp_implied"] * row.opp_implied
                 + pa_m["coefficients"]["own_epa_prior"] * row.own_epa_prior
                 + pa_m["coefficients"]["wind_eff"] * row.wind_eff)
        mu_pa = float(np.clip(mu_pa, *PA_MEAN_BOUNDS))

        mu_db = (db_m["intercept"]
                 + db_m["coefficients"]["opp_dropbacks_prior"] * row.opp_dropbacks
                 + db_m["coefficients"]["game_total"] * row.over_under
                 + db_m["coefficients"]["abs_spread"] * abs(row.own_implied - row.opp_implied)
                 + db_m["coefficients"]["wind_eff"] * row.wind_eff)
        mu_db = float(np.clip(mu_db, *DROPBACK_BOUNDS))

        sack_rate = (sk_m["intercept"]
                     + sk_m["coefficients"]["opp_sack_rate_prior"] * row.opp_sack_allowed_rate
                     + sk_m["coefficients"]["own_sack_rate_prior"] * row.own_sack_rate
                     + sk_m["coefficients"]["wind_eff"] * row.wind_eff)
        sack_rate = float(np.clip(sack_rate, *SACK_RATE_BOUNDS))

        int_rate = (it_m["intercept"]
                    + it_m["coefficients"]["qb_int_rate_prior"] * getattr(row, "qb_int_rate", it_m["league_int_rate"])
                    + it_m["coefficients"]["own_int_rate_prior"] * row.own_int_rate
                    + it_m["coefficients"]["wind_eff"] * row.wind_eff)
        if getattr(row, "opp_qb_is_rookie", False):
            int_rate *= it_m["rookie_multiplier"]      # decision #8
        int_rate = float(np.clip(int_rate, *INT_RATE_BOUNDS))

        mu_fum = float(fum_m["league_rate_per_game"]
                       + fum_m["opp_weight"] * (row.own_fum_rate - fum_m["league_rate_per_game"]))
        mu_fum = max(mu_fum, 0.05)

        # --- draws (decision #13's latent factor) -------------------------
        bracket, other, comp = _simulate_one(
            mu_pa, mu_db, sack_rate, int_rate, mu_fum,
            model, site, latent, n_sims, rng)
        pts = bracket + other

        out["final_projection"][i] = pts.mean()
        out["sigma"][i] = pts.std(ddof=1)
        out["p10"][i], out["p90"][i] = np.percentile(pts, [10, 90])
        out["proj_points_allowed"][i] = comp["points_allowed"].mean()
        out["proj_sack"][i] = comp["sack"].mean()
        out["proj_interception"][i] = comp["interception"].mean()
        out["proj_fumble_recovery"][i] = comp["fumble_recovery"].mean()
        out["proj_def_td"][i] = comp["def_td"].mean()
        out["proj_st_td"][i] = comp["st_td"].mean()
        out["proj_bracket_points"][i] = bracket.mean()

    res = pd.DataFrame(out)
    res.insert(0, "team", features["team"].to_numpy())

    # Decision #11b of fit_dst_model.py -- linear recalibration, fitted on
    # the fit window. Monotone with a positive slope, so it cannot reorder
    # defenses; it corrects the level and the BETWEEN-DEFENSE spread only.
    #
    # SIGMA IS DELIBERATELY NOT RESCALED, and the first version of this code
    # got that wrong. `actual ~ a + b*proj` with b > 1 says the projections
    # were bunched too tightly ACROSS defenses -- the true conditional means
    # differ more than the raw simulator thought. It says nothing about the
    # predictive spread of one defense's outcome around its own mean, which
    # is what sigma is. They are orthogonal quantities and multiplying sigma
    # by b conflates them.
    #
    # Measured: raw sigma was already calibrated at 0.949 (realized RMSE /
    # mean sigma, 1.00 ideal). Scaling it by b = 1.669 pushed that to 0.565
    # and the sigma range to 9.4-11.2 against a realized RMSE of 5.8 -- i.e.
    # it asserted nearly twice the uncertainty that exists. Caught by
    # measure_dst.py's decision #22 check, which is the entire reason that
    # check is in the harness rather than left as something to eyeball.
    #
    # The percentiles are SHIFTED by the change in the mean for the same
    # reason: they are quantiles of one defense's predictive distribution,
    # so the distribution moves but does not stretch.
    recal = model.get("recalibration")
    if recal:
        a, b = float(recal["intercept"]), float(recal["slope"])
        if b <= 0:
            raise SystemExit(
                f"dst_model: the fitted recalibration slope is {b}, which is "
                f"not positive. Applying it would REVERSE the ranking of every "
                f"defense. Refit -- do not ship this artifact."
            )
        played = res["final_projection"] > 0
        raw = res.loc[played, "final_projection"]
        corrected = (a + b * raw).clip(lower=0.0)
        shift = corrected - raw
        res.loc[played, "final_projection"] = corrected
        res.loc[played, "p10"] = (res.loc[played, "p10"] + shift).clip(lower=0.0)
        res.loc[played, "p90"] = (res.loc[played, "p90"] + shift).clip(lower=0.0)
        # sigma untouched -- see above.
    return res


def _simulate_one(mu_pa, mu_db, sack_rate, int_rate, mu_fum, model, site,
                  latent, n_sims, rng):
    """One defense's draws. Returns (bracket_points, other_points) arrays.

    Factored out of simulate() so calibrate_latent() measures the SAME draw
    scheme production uses, rather than a parallel reimplementation of it.
    """
    pa_m, db_m = model["points_allowed"], model["dropbacks"]
    sk_m, it_m = model["sack_rate"], model["int_rate"]
    fum_m, rare = model["fumble_recovery"], model["rare_events"]

    z = rng.standard_normal(n_sims)
    pa_scale = np.exp(-latent * z)
    ev_scale = np.exp(latent * z)

    pa = _nb_draw(rng, mu_pa * pa_scale, pa_m["nb_dispersion"], n_sims)
    db = _nb_draw(rng, mu_db, db_m["nb_dispersion"], n_sims)
    sacks = _nb_draw(rng, np.clip(sack_rate * db, 1e-6, None) * ev_scale,
                     sk_m["nb_dispersion"], n_sims)
    att = np.clip(db - sacks, 0, None)
    ints = _nb_draw(rng, np.clip(int_rate * att, 1e-6, None) * ev_scale,
                    it_m["nb_dispersion"], n_sims)
    fum = _nb_draw(rng, mu_fum * ev_scale, fum_m["nb_dispersion"], n_sims)
    def_td = rng.poisson(rare["def_td_per_game"] * ev_scale, n_sims)
    st_td = rng.poisson(rare["st_td_per_game"], n_sims)
    safety = rng.poisson(rare["safety_per_game"], n_sims)
    blocked = rng.poisson(rare["blocked_kick_per_game"], n_sims)
    residual = rng.poisson(rare["residual_td_per_game"], n_sims)

    comp = {
        "points_allowed": pa, "sack": sacks, "interception": ints,
        "fumble_recovery": fum, "safety": safety,
        "def_td": def_td + residual, "st_td": st_td,
        "blocked_kick": blocked, "two_pt_return": np.zeros(n_sims),
    }
    bracket = scoring_rules.dst_bracket_points(pa, site)
    total = scoring_rules.score_dst(comp, site)
    return bracket, total - bracket, comp


def calibrate_latent(model: dict, site: str = "dk",
                     target_corr: float = 0.268, n_sims: int = 60000,
                     seed: int = 991) -> float:
    """Decision #13. Find the latent strength reproducing the measured
    WITHIN-GAME correlation between bracket points and the other components.

    The target is the RESIDUAL correlation (+0.268), not the raw
    cross-sectional one (+0.301). The raw figure mixes in between-team
    variation -- good defenses have both better points-allowed and more
    takeaways -- which this simulator reproduces for free through each team's
    own fitted means. Only the leftover within-game co-movement needs a
    latent factor, and calibrating against the raw number would double-count
    the between-team part and inflate every sigma.

    Calibrated at the LEAGUE-MEAN defense, since the factor is one shared
    constant rather than a per-team parameter. Called by fit_dst_model.py,
    never by the production path.
    """
    lg = model["league_means"]
    mu_pa = float(np.clip(
        model["points_allowed"]["intercept"]
        + model["points_allowed"]["coefficients"]["opp_implied"] * lg["opp_implied"],
        *PA_MEAN_BOUNDS))
    mu_db = lg["dropbacks"]
    sack_rate = lg["sacks"] / lg["dropbacks"]
    int_rate = model["int_rate"]["league_int_rate"]
    mu_fum = model["fumble_recovery"]["league_rate_per_game"]

    def realized(strength):
        rng = np.random.default_rng(seed)
        br, oth, _ = _simulate_one(mu_pa, mu_db, sack_rate, int_rate, mu_fum,
                                   model, site, strength, n_sims, rng)
        if br.std() < 1e-9 or oth.std() < 1e-9:
            return 0.0
        return float(np.corrcoef(br, oth)[0, 1])

    if realized(0.60) < target_corr:
        raise SystemExit(
            f"calibrate_latent: even at the maximum strength the simulated "
            f"within-game correlation ({realized(0.60):+.3f}) cannot reach the "
            f"measured target ({target_corr:+.3f}). The draw scheme, not the "
            f"constant, is wrong -- do not widen the bracket and ship it."
        )
    lo, hi = 0.0, 0.60
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if realized(mid) < target_corr:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 5)
