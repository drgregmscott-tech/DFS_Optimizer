"""
backtest_harness.py
===================

Session 10.1 -- Lineup-Level Backtest Harness.

The measurement scaffold the whole projection redesign (Phase 10) is built
to be judged against. It answers the only question that matters for this
project: given a historical week, what lineup would our ACTUAL pipeline have
built, and how would it have finished?

It is deliberately built BEFORE any projection change, so a rewrite can be
told apart from a regression. Without a measured baseline, "did the new
projection help?" is unanswerable.

WHAT IT DOES, per (site, season, week):

  1. Derive a REAL vegas_implied_totals_{week}.csv from nflverse historical
     lines (see decision #1 -- this closed the Vegas blocker).
  2. Run the REAL projection component scripts (projections_baseline,
     projections_matchup) and build_projections.py against the matched
     RotoGuru salary file -- the actual pipeline, not a reimplementation.
  3. Filter to the Sunday MAIN SLATE (decision #2 -- the bootstrap left the
     full-week pool unfiltered on purpose; the harness owns this).
  4. Run the REAL optimizer (solve_lineup, imported in-process) to build the
     lineup(s).
  5. Score them against rotoguru_actuals_{site}_{season}.csv (the scoring
     truth).
  6. Report percentile vs a synthetic ownership-weighted field, as median-
     AND max-percentile SEPARATELY (decision #3).

Numbered decisions:

  1. REAL VEGAS FROM nflverse, NOT SYNTHETIC. The blocker the ROADMAP flagged
     ("no real historical vegas lines available") turned out to be wrong for
     the BACKTEST case: nflverse's games.csv
     (github.com/nflverse/nfldata/master/data/games.csv) carries real
     historical spread_line and total_line going back decades. The harness
     derives implied totals from those using the EXACT formula vegas_odds.py
     documents: team_implied = total/2 - team_spread/2, where team_spread is
     signed (negative = favorite). Verified: implied totals sum back to the
     game total for every row (vegas_odds.py's own built-in sanity check),
     and nflverse's spread_line is signed positive = HOME favored (TB -10 vs
     DAL in 2021 wk1 -> home implied 31.25, matching their real 31 points).
     This does NOT change the live-production gap -- The Odds API still can't
     retroactively supply lines for a live run; this real-history source is
     available for backtesting specifically.

     The emitted file matches vegas_odds.py's column contract exactly
     (team, opponent, commence_time, spread, over_under, implied_total), so
     build_projections.py reads it with zero changes.

  2. SUNDAY MAIN SLATE FILTER. RotoGuru's salary pool is the full-week
     Thurs-Mon slate (its own disclaimer). A DK/FD Classic "main slate" is
     the Sunday games only (roughly 1pm + 4pm ET kickoffs; excludes the
     Thu game, the Sun/Mon night games, and any London 9:30am game). The
     bootstrap deliberately left this unfiltered and handed it here. The
     filter uses games.csv's `gameday` (a date) and `gametime`: keep games
     whose gameday is the Sunday of that week and whose kickoff is NOT a
     primetime slot. This is an APPROXIMATION -- the exact main-slate
     membership a site published that week isn't archived anywhere we have
     -- and it's flagged as such rather than presented as exact. It is far
     closer to reality than the full-week pool, which is the point.

  3. METRIC = PERCENTILE VS SYNTHETIC FIELD, MEDIAN AND MAX SEPARATELY.
     NOT percent-of-hindsight-optimal: that denominator is a single noisy
     extremum (one $3k WR catching 3 TDs swings it 30+ pts for reasons
     unrelated to our process), its scale is uninformative (realistic
     lineups live in a compressed 50-90% band), and it rewards ceiling-
     chasing, which is explicitly NOT this user's strategy.

     Instead: generate a large field of legal lineups sampled PROPORTIONAL
     to Session 4.1's estimated_ownership_pct (chalk-concentrated, far more
     realistic than uniform -- a uniform field would flatter us), score the
     whole field on actuals, and report where our lineup(s) fall as a
     percentile.

     For a portfolio (n>1 lineups) the object is the DISTRIBUTION of the
     lineups' percentiles: report MEDIAN percentile (floor / cash-rate
     proxy) and MAX percentile (upside / tournament proxy) SEPARATELY, never
     blended -- because lambda in the future objective trades between them,
     and that tradeoff curve is the entire point. At n=1 they collapse to
     one number, correct for single-entry.

     HONEST LIMITATION, stated in output: the field's realism inherits
     estimated_ownership_pct's known unfitness (Session 4.1's heuristic, not
     real ownership -- the circularity Sessions 9.3/9.4 eventually fix). The
     percentile is "vs a plausible synthetic field", not "vs a real
     contest". The harness says so rather than implying more.

  4. CALLS THE REAL CODE, IN-PROCESS WHERE POSSIBLE. solve_lineup and the
     projection builders are imported and called directly, not
     reimplemented -- the project's own hard-won lesson (DST losing
     site_player_id, bring-back auto-select failing, team-drift) is that
     only real runs through the real functions catch the real bugs. Static
     re-implementation in a harness would defeat the harness's purpose.
     build_projections.py is driven via its file-based interface (it reads
     several intermediate CSVs), so the harness writes those inputs and
     invokes it as a subprocess; the optimizer's solve_lineup is called
     directly in-process.

  5. FAIL LOUD, PER-WEEK ISOLATION. A week that can't be built (missing
     input, projection error, infeasible solve) is recorded as an ERROR
     with its reason and the run CONTINUES -- one bad week doesn't abort a
     multi-week backtest -- but the error is surfaced prominently in the
     summary, never silently skipped. Same philosophy as
     batch_match_rotoguru.py.

  6. BOOTSTRAP, NOT VALIDATION SET. RotoGuru tops out at 2021; the project's
     current-state weekly_stats is 2025. They don't overlap, so this harness
     CANNOT measure whether the CURRENT projection system is good NOW. Its
     jobs: prove these mechanics, and produce the baseline distribution that
     every later Phase 10 change is measured against. The output says so.

  8. SESSION 10.2 -- SALARY-ANCHOR MEASUREMENT ARM. `--salary-anchor-weight`
     (and the cold-start variants) are passed straight through to
     build_projections.py, which is where the anchor is actually applied.
     The harness deliberately does NOT implement the blend itself -- same
     decision #4 reasoning as everything else here: measuring a
     reimplementation would measure the reimplementation.

     Two consequences worth stating:

     (a) WEEK 1 BECOMES BACKTESTABLE when the anchor can carry the
         cold start. The week-1 skip below exists because a usage-based
         model has zero prior weeks to build from, so every projection is
         0/NaN and the pool empties. A salary anchor has no such
         dependency -- price exists before kickoff. So week 1 is skipped
         only when the anchor is off, or when it is on at a flat weight
         below 1.0 (which would still leave a mostly-zero pool). With
         `--salary-anchor-cold-start`, week 1 runs. That is not a
         convenience: it is the cleanest available evidence for or against
         the ROADMAP's cold-start design claim, on a week where the usage
         model contributes literally nothing.

     (b) EVERY RESULT LINE AND THE SUMMARY STATE THE ANCHOR CONFIG. A
         percentile with no record of which arm produced it is worthless
         for a before/after comparison, and this file is the before/after
         comparison.

  9. SESSION 10.2 -- THE FIELD IS PINNED TO THE ANCHOR-OFF POOL BY DEFAULT.
     Found by running Session 10.2's first real comparison, not by review.

     Turning the anchor on rescues zero-history players from a 0.0 model
     projection into a positive one, so they pass this harness's
     `final_projection > 0` pool filter. The pool grew ~35% (226 -> 312
     players in 2021 wk2). Decision #3 samples the synthetic FIELD from that
     same pool -- so the field grew too, got more diluted, and scored lower.
     Measured across 2021: the field's median score fell in 15 of 17 weeks,
     mean -1.41 pts, t = -4.3.

     That was by a wide margin the strongest effect in the whole comparison.
     Every apparent percentile "gain" (max-pctile +1.4, t = +1.8; median-
     pctile +1.9, t = +1.0) was weaker than the movement in the yardstick
     being measured against, and the arm's RAW score -- in real fantasy
     points, immune to the field -- moved +0.4 pts/week at w=0.25, i.e. not
     at all. The improvement was substantially an artifact.

     So `--field-pool baseline` (the default) runs the projection pipeline a
     SECOND time per week with the anchor off, purely to construct the
     field, and pins every arm to that one yardstick. Costs one extra
     build_projections call per week and only when the anchor is on; the
     anchor-OFF arm is untouched, so Session 10.1's published baseline
     (72.8 / 94.7) still reproduces exactly. `--field-pool arm` restores the
     old behaviour for comparison.

     Raw median/best lineup scores are now printed per week and in the
     summary alongside the percentiles, for the same reason: they are in
     arm-independent units, so they are the check on whether a percentile
     move is real.

Usage:
    python3 scripts/backtest_harness.py --site dk --season 2021 --week 10
    python3 scripts/backtest_harness.py --site dk --season 2021 --week 1 2 3
    python3 scripts/backtest_harness.py --site dk --season 2019 --all-weeks
    python3 scripts/backtest_harness.py --site dk --season 2021 --week 10 \
        --num-lineups 20 --field-size 5000
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
from ingest_salaries import SITE_CONFIGS, normalize_team  # noqa: E402
import optimizer as opt  # noqa: E402  -- solve_lineup, parse_roster_requirements, called in-process

# nflverse historical game lines -- the decision #1 source. Cached locally
# after first fetch so a multi-week run hits the network once.
GAMES_CSV_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
GAMES_CACHE = DATA_DIR / "nflverse_games.csv"

# Set by --debug; when on, one week's lineup is dumped player-by-player with
# projected vs actual points, plus the field distribution, to explain a
# surprising percentile rather than leaving it a bare number.
DEBUG = False


def _debug_dump(site, season, week, lineup, actuals_wk, pool, field_scores,
                our_score, label="lineup"):
    """Player-by-player dump. Session 10.2: anchor-aware -- when the pool
    carries the decision #8 audit columns, every line shows what the anchor
    actually did to that player (pre-anchor model value, the fitted anchor,
    the weight applied, the resulting delta), and players who exist in the
    pool ONLY because the anchor rescued them from a 0.0 model projection
    are tagged RESCUED.

    That tag is the point of the whole dump. The riskiest way for the anchor
    to look good is for its gains to come from newly-rescued zero-history
    players -- those are the least-informed projections in the pool, so a
    win there is as likely to be luck as skill, and it would not generalize.
    A win that comes from RE-RANKING players the model already knew about is
    a different and far more trustworthy thing. Reading those apart requires
    seeing which is which, per player, on a real week.
    """
    pts = actuals_wk.set_index("gid")["actual_points"]
    anchored = "final_projection_pre_anchor" in pool.columns
    lut = pool.set_index("site_player_id") if "site_player_id" in pool.columns else None

    print(f"\n===== DEBUG: {site} {season} wk{week} — our {label} =====")
    if anchored:
        print(f"  {'':3s} {'player':22s} {'pre':>6s} {'anch':>6s} {'w':>5s} "
              f"{'post':>6s} {'actual':>7s}  flags")
    total_proj = total_act = 0.0
    n_zero_actual = 0
    n_rescued = 0
    rescued_actual = 0.0
    for r in lineup.itertuples():
        sid = str(getattr(r, "site_player_id", ""))
        name = getattr(r, "player_name", getattr(r, "name", "?"))
        posn = getattr(r, "position", "?")
        # optimizer's assign_roster_slots emits the column as 'projection'
        # (renamed from final_projection); fall back for either name.
        proj = float(getattr(r, "projection",
                             getattr(r, "final_projection", float("nan"))))
        act = float(pts.get(sid, float("nan")))
        joined = "OK" if sid in pts.index else "NO-JOIN(->0)"
        act_used = act if sid in pts.index else 0.0
        total_proj += proj if proj == proj else 0.0
        total_act += act_used
        if act_used == 0.0:
            n_zero_actual += 1

        if anchored and lut is not None and sid in lut.index:
            row = lut.loc[sid]
            pre = float(row["final_projection_pre_anchor"])
            anc = float(row["salary_anchor"])
            w = float(row["anchor_weight_used"])
            flags = []
            if pre == 0.0 and proj > 0.0:
                flags.append("RESCUED")
                n_rescued += 1
                rescued_actual += act_used
            if w == 0.0:
                flags.append("no-anchor")
            print(f"  {posn:3s} {str(name)[:22]:22s} {pre:6.2f} {anc:6.2f} "
                  f"{w:5.2f} {proj:6.2f} {act_used:7.2f}  "
                  f"{joined if joined != 'OK' else ''}{' '.join(flags)}")
        else:
            print(f"  {posn:3s} {str(name)[:22]:22s} id={sid:6s} "
                  f"proj={proj:6.2f}  actual={act_used:6.2f}  join={joined}")

    print(f"  -- lineup projected total: {total_proj:.2f}   "
          f"actual total: {total_act:.2f}   (harness scored: {our_score:.2f})")
    print(f"  -- players with 0 actual points: {n_zero_actual}/9 "
          f"(several NO-JOINs would signal a scoring bug)")
    if anchored:
        share = (rescued_actual / total_act * 100.0) if total_act else 0.0
        print(f"  -- ANCHOR-RESCUED players in this lineup: {n_rescued}/9, "
              f"contributing {rescued_actual:.1f} of {total_act:.1f} actual "
              f"pts ({share:.0f}%).")
        print(f"     A high share here means the arm's result rests on "
              f"zero-history players, NOT on better ranking of known ones.")
    fs = np.asarray(field_scores)
    print(f"  -- field: n={len(fs)}, min={fs.min():.1f}, "
          f"p25={np.percentile(fs,25):.1f}, median={np.median(fs):.1f}, "
          f"p75={np.percentile(fs,75):.1f}, max={fs.max():.1f}")
    print(f"  -- our score {our_score:.1f} vs field median {np.median(fs):.1f}: "
          f"{'BELOW' if our_score < np.median(fs) else 'above'} median")
    print("=" * 52 + "\n")


# ---------------------------------------------------------------------------
# Decision #7: bridge the combined-vs-per-season schedule layout mismatch
# ---------------------------------------------------------------------------

def ensure_per_season_schedule(season: int) -> None:
    """build_projections.py's load_schedule() reads schedules_{season}.parquet
    (per-season). But ingest_historical.py, when given multiple seasons,
    wrote ONE combined schedules_2014_..._2021.parquet -- while the 2025 file
    is per-season. (Flagged in Session 10.0's log as the layout wrinkle the
    harness must own.) Rather than touch the validated production script for
    a backtest-only concern, the harness materializes the per-season file the
    pipeline expects, from whichever schedule source is present:

      1. schedules_{season}.parquet already exists -> nothing to do.
      2. A combined schedules_*.parquet containing this season -> slice it.
      3. Neither -> fall back to nflverse games.csv (already fetched for
         vegas), which carries season/week/home_team/away_team.

    Idempotent; only writes if the per-season file is missing.
    """
    per_season = DATA_DIR / f"schedules_{season}.parquet"
    if per_season.exists():
        return

    # 2. Look for any combined schedules file that contains this season.
    for cand in sorted(DATA_DIR.glob("schedules_*.parquet")):
        try:
            df = pd.read_parquet(cand)
        except Exception:
            continue
        if "season" in df.columns and season in set(df["season"].unique()):
            sub = df[df["season"] == season].copy()
            if len(sub):
                sub.to_parquet(per_season, index=False)
                return

    # 3. Fall back to games.csv.
    games = load_games()
    sub = games[games["season"] == season][
        ["season", "week", "home_team", "away_team", "gameday", "game_type"]
    ].copy() if "game_type" in games.columns else games[games["season"] == season][
        ["season", "week", "home_team", "away_team", "gameday"]
    ].copy()
    if sub.empty:
        raise RuntimeError(
            f"Cannot materialize schedules_{season}.parquet -- no per-season "
            f"file, no combined file containing {season}, and games.csv has no "
            f"{season} rows."
        )
    sub.to_parquet(per_season, index=False)


# ---------------------------------------------------------------------------
# Decision #1: real vegas_implied_totals from nflverse historical lines
# ---------------------------------------------------------------------------

def load_games(force_refresh: bool = False) -> pd.DataFrame:
    if GAMES_CACHE.exists() and not force_refresh:
        return pd.read_csv(GAMES_CACHE)
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(GAMES_CSV_URL, GAMES_CACHE)
    return pd.read_csv(GAMES_CACHE)


def build_vegas_file(games: pd.DataFrame, site: str, season: int, week: int) -> Path:
    """Derive a real vegas_implied_totals_{week}.csv for the target week,
    matching vegas_odds.py's exact column contract (decision #1)."""
    wk = games[(games["season"] == season) & (games["week"] == week)].copy()
    if wk.empty:
        raise RuntimeError(f"No games in nflverse games.csv for {season} wk{week}.")

    rows = []
    for g in wk.itertuples():
        total = getattr(g, "total_line", None)
        spread = getattr(g, "spread_line", None)  # positive = HOME favored
        if pd.isna(total) or pd.isna(spread):
            # A game with no posted line can't contribute implied totals;
            # skip it (its players fall back to neutral vegas_factor
            # downstream, same as build_projections handles a missing team).
            continue
        home, away = g.home_team, g.away_team
        home_spread = -float(spread)   # home favored -> negative team_spread
        away_spread = float(spread)
        home_it = float(total) / 2 - home_spread / 2
        away_it = float(total) / 2 - away_spread / 2
        commence = getattr(g, "gameday", "")
        rows.append({"team": normalize_team(home, site), "opponent": normalize_team(away, site),
                     "commence_time": commence, "spread": home_spread,
                     "over_under": float(total), "implied_total": round(home_it, 2)})
        rows.append({"team": normalize_team(away, site), "opponent": normalize_team(home, site),
                     "commence_time": commence, "spread": away_spread,
                     "over_under": float(total), "implied_total": round(away_it, 2)})

    if not rows:
        raise RuntimeError(f"No games with posted lines for {season} wk{week}.")

    out = pd.DataFrame(rows)
    # Sanity check vegas_odds.py documents: each game's two implied totals
    # sum back to that game's total. Fail loud if the derivation is wrong.
    for ou, grp in out.groupby("over_under"):
        for opp, pair in grp.groupby("commence_time"):
            if len(pair) >= 2:
                s = pair["implied_total"].sum()
                # pairs share over_under; allow small float noise
                if abs(s % ou) > 0.05 and abs((s % ou) - ou) > 0.05:
                    pass  # multiple games can share a total; per-pair check below is the real one
    # Per-game exact check: group by the (team,opponent) unordered pair.
    seen = {}
    for r in rows:
        key = frozenset((r["team"], r["opponent"]))
        seen.setdefault(key, []).append(r["implied_total"])
    for key, its in seen.items():
        if len(its) == 2:
            game_total = out[out["team"] == list(key)[0]]["over_under"].iloc[0]
            if abs(sum(its) - game_total) > 0.05:
                raise RuntimeError(
                    f"Implied-total derivation wrong for {key}: "
                    f"{its} sums to {sum(its)}, expected {game_total}."
                )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"vegas_implied_totals_{week}.csv"
    out.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Decision #2: Sunday main-slate membership
# ---------------------------------------------------------------------------

def sunday_main_slate_teams(games: pd.DataFrame, season: int, week: int) -> set:
    """Return the set of team codes (nflverse form) playing in the Sunday
    main slate: Sunday games excluding primetime (SNF) and any early
    non-1pm/4pm window. Approximation -- see decision #2."""
    wk = games[(games["season"] == season) & (games["week"] == week)].copy()
    wk["gameday"] = pd.to_datetime(wk["gameday"], errors="coerce")
    wk["dow"] = wk["gameday"].dt.dayofweek  # Monday=0 .. Sunday=6
    sunday = wk[wk["dow"] == 6].copy()

    def is_main(t):
        if not isinstance(t, str) or not t:
            return True  # missing gametime -> keep (conservative)
        try:
            hh = int(t.split(":")[0])
        except (ValueError, IndexError):
            return True
        # Keep 1pm + 4pm ET windows (13:00-16:59). Drop SNF (20:xx) and the
        # occasional 9:30am London game (09:xx).
        return 13 <= hh <= 16

    main = sunday[sunday["gametime"].apply(is_main)] if "gametime" in sunday.columns else sunday
    teams = set()
    for g in main.itertuples():
        teams.add(g.home_team)
        teams.add(g.away_team)
    return teams


# ---------------------------------------------------------------------------
# Run the real projection pipeline for one week
# ---------------------------------------------------------------------------

def run_projection_pipeline(site: str, season: int, week: int, slate_id: str,
                            anchor: dict | None = None) -> Path:
    """Drive the REAL component scripts + build_projections.py via their
    file interfaces. Returns the path to final_projections_{site}_{week}.csv.
    Raises RuntimeError with the failing step's stderr on any failure.

    `anchor` (Session 10.2, decision #8) is passed straight through to
    build_projections.py as CLI flags -- the harness never applies the blend
    itself. None / all-zero means the flags are omitted entirely, so the
    command line is byte-identical to the Session 10.1 baseline run."""
    def run(script, extra):
        cmd = [sys.executable, str(SCRIPTS_DIR / script),
               "--site", site, "--season", str(season), "--week", str(week)] + extra
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"{script} failed:\n{(p.stderr or p.stdout).strip()[-1500:]}")

    run("projections_baseline.py", [])
    run("projections_matchup.py", [])
    # build_projections also needs --slate-id; vegas file already written.
    cmd = [sys.executable, str(SCRIPTS_DIR / "build_projections.py"),
           "--site", site, "--season", str(season), "--week", str(week),
           "--slate-id", slate_id]
    if anchor and (anchor["weight"] > 0 or anchor["cold_start"]):
        cmd += ["--salary-anchor-weight", str(anchor["weight"]),
                "--salary-anchor-k", str(anchor["k"])]
        if anchor["cold_start"]:
            cmd += ["--salary-anchor-cold-start"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"build_projections.py failed:\n{(p.stderr or p.stdout).strip()[-1500:]}")

    proj_path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    if not proj_path.exists():
        raise RuntimeError(f"build_projections.py ran but {proj_path.name} was not written.")
    return proj_path


# ---------------------------------------------------------------------------
# Scoring + synthetic-field percentile (decision #3)
# ---------------------------------------------------------------------------

def load_actuals(site: str, season: int) -> pd.DataFrame:
    path = DATA_DIR / f"rotoguru_actuals_{site}_{season}.csv"
    if not path.exists():
        raise RuntimeError(f"{path.name} not found -- run ingest_rotoguru.py --site {site} --season {season}.")
    a = pd.read_csv(path, dtype={"gid": str})
    return a


def score_lineup(lineup_site_ids: list, actuals_week: pd.DataFrame) -> float:
    """Sum actual_points for a lineup, keyed on RotoGuru gid (== the salary
    file's site_player_id == the projections file's site_player_id)."""
    pts = actuals_week.set_index("gid")["actual_points"]
    total = 0.0
    for sid in lineup_site_ids:
        total += float(pts.get(str(sid), 0.0))
    return total


def build_synthetic_field(pool: pd.DataFrame, site: str, field_size: int,
                          rng: np.random.Generator) -> list:
    """Sample `field_size` legal lineups, drawing players with probability
    proportional to estimated_ownership_pct (decision #3). Returns a list of
    lists-of-site_player_id. Uses a simple ownership-weighted greedy fill per
    roster slot -- NOT the ILP (we want a realistic chalk-shaped field, not
    thousands of optimal lineups)."""
    cfg = SITE_CONFIGS[site]
    fixed_counts, flex_count = opt.parse_roster_requirements(cfg["roster_slots"])
    cap = cfg["salary_cap"]
    flex_positions = opt.FLEX_ELIGIBLE_POSITIONS

    # ownership weights (fallback to uniform if the column is absent/zero)
    own_col = "estimated_ownership_pct" if "estimated_ownership_pct" in pool.columns else None
    by_pos = {pos: pool[pool["position"] == pos] for pos in set(fixed_counts) | flex_positions}

    def weights(df):
        if own_col and df[own_col].sum() > 0:
            w = df[own_col].to_numpy(dtype=float)
            w = np.clip(w, 0.01, None)
            return w / w.sum()
        return np.full(len(df), 1.0 / len(df))

    field = []
    attempts = 0
    max_attempts = field_size * 20
    while len(field) < field_size and attempts < max_attempts:
        attempts += 1
        chosen, chosen_ids, spend, ok = [], set(), 0, True
        # fill fixed slots
        need = dict(fixed_counts)
        for pos, cnt in fixed_counts.items():
            df = by_pos.get(pos)
            if df is None or len(df) < cnt:
                ok = False
                break
            idx = rng.choice(len(df), size=cnt, replace=False, p=weights(df))
            for i in idx:
                r = df.iloc[i]
                chosen.append(r); chosen_ids.add(r["player_id"]); spend += r["salary"]
        if not ok:
            break
        # fill FLEX
        for _ in range(flex_count):
            flex_pool = pool[pool["position"].isin(flex_positions) & ~pool["player_id"].isin(chosen_ids)]
            if flex_pool.empty:
                ok = False; break
            i = rng.choice(len(flex_pool), p=weights(flex_pool))
            r = flex_pool.iloc[i]
            chosen.append(r); chosen_ids.add(r["player_id"]); spend += r["salary"]
        if not ok or spend > cap:
            continue
        field.append([r["site_player_id"] for r in chosen])
    return field


def describe_anchor(anchor: dict | None) -> str:
    """One-line, unambiguous label for which arm produced a result
    (Session 10.2, decision #8b). Never abbreviated away -- a percentile
    without its config is not comparable to anything."""
    if not anchor or (anchor["weight"] <= 0 and not anchor["cold_start"]):
        return "anchor OFF (Session 10.1 baseline arm)"
    if anchor["cold_start"]:
        return f"anchor ON cold-start (floor w={anchor['weight']}, k={anchor['k']})"
    return f"anchor ON flat w={anchor['weight']}"


def percentile_of(score: float, field_scores: np.ndarray) -> float:
    if len(field_scores) == 0:
        return float("nan")
    return float((field_scores < score).mean() * 100.0)


# ---------------------------------------------------------------------------
# One week, end to end
# ---------------------------------------------------------------------------

def backtest_week(site: str, season: int, week: int, games: pd.DataFrame,
                  num_lineups: int, field_size: int, rng: np.random.Generator,
                  anchor: dict | None = None,
                  field_pool_mode: str = "baseline") -> dict:
    slate_id = f"rotoguru_{season}_wk{week}"
    salary_path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    if not salary_path.exists():
        return {"site": site, "season": season, "week": week, "status": "ERROR",
                "detail": f"missing {salary_path.name} (run batch_match_rotoguru.py)"}

    # Week 1 is not backtestable with the current projection model: baseline
    # and recent-form are computed from weeks STRICTLY BEFORE the target
    # (projections_baseline.py line ~76, the lookahead guard), so week 1 has
    # zero prior games for every player -> every final_projection is 0/NaN ->
    # an empty pool. This is CORRECT behavior, not a bug: you can't project
    # week 1 from prior-week usage that doesn't exist. It's also exactly the
    # cold-start gap Phase 10's design addresses (at 0 games, a projection
    # should fall back to salary + market signal). Until that ships, week 1
    # is skipped with an explicit reason rather than a confusing
    # "pool too small" error that looks like a data problem.
    # Session 10.2, decision #8a: the anchor is exactly the salary+market
    # fallback that note anticipated. When it is on and able to carry a
    # zero-history player (cold-start schedule, or a flat weight of 1.0),
    # week 1 IS backtestable and is no longer skipped.
    anchor_carries_cold_start = bool(
        anchor and (anchor["cold_start"] or anchor["weight"] >= 1.0)
    )
    if week == 1 and not anchor_carries_cold_start:
        return {"site": site, "season": season, "week": week, "status": "SKIP",
                "detail": "week 1 not backtestable -- no prior-week data for the "
                          "current usage-based model (cold-start gap; run with "
                          "--salary-anchor-cold-start to make it backtestable)"}

    try:
        ensure_per_season_schedule(season)  # decision #7: bridge schedule layout
        build_vegas_file(games, site, season, week)
        proj_path = run_projection_pipeline(site, season, week, slate_id, anchor)
    except RuntimeError as e:
        return {"site": site, "season": season, "week": week, "status": "ERROR", "detail": str(e)}

    # Session 10.2, decision #9: build the FIELD from an anchor-OFF pool, so
    # every arm is scored against one fixed yardstick. See the module
    # docstring -- without this, turning the anchor on enlarges the pool
    # (zero-history players get rescued), which enlarges and WEAKENS the
    # synthetic field sampled from it, which raises our percentile for a
    # reason that has nothing to do with the projection being better.
    # Measured on the first Session 10.2 run: field median fell in 15 of 17
    # weeks (mean -1.41 pts, t=-4.3) -- by far the strongest effect in that
    # whole comparison, and a pure artifact.
    field_proj_path = proj_path
    if field_pool_mode == "baseline" and anchor and (
            anchor["weight"] > 0 or anchor["cold_start"]):
        try:
            field_proj_path = run_projection_pipeline(
                site, season, week, slate_id, None)
            field_proj_path = OUTPUT_DIR / f"final_projections_{site}_{week}_fieldbase.csv"
            pd.read_csv(OUTPUT_DIR / f"final_projections_{site}_{week}.csv",
                        dtype={"player_id": str, "site_player_id": str}
                        ).to_csv(field_proj_path, index=False)
            # Rebuild the ANCHORED file, which the baseline run just clobbered.
            run_projection_pipeline(site, season, week, slate_id, anchor)
        except RuntimeError as e:
            return {"site": site, "season": season, "week": week,
                    "status": "ERROR",
                    "detail": f"field-baseline rebuild failed: {e}"}

    # Decision #2: filter to Sunday main slate, then write the filtered pool
    # back to the final_projections path so the REAL build_multi_lineup
    # (which loads that file itself) operates on exactly the main-slate pool.
    # This exercises the entire real optimizer path -- exposure, uniqueness,
    # stacking, min_projection -- rather than a stripped-down solve.
    proj = pd.read_csv(proj_path, dtype={"player_id": str, "site_player_id": str})
    main_teams = sunday_main_slate_teams(games, season, week)
    main_teams_norm = {normalize_team(t, site) for t in main_teams}
    pool = proj[proj["team"].isin(main_teams_norm)].copy()
    pool = pool[pool["final_projection"] > 0].copy()  # drop byed/zeroed players
    if len(pool) < 20:
        return {"site": site, "season": season, "week": week, "status": "ERROR",
                "detail": f"main-slate pool too small ({len(pool)} players) -- "
                          f"filter or data issue"}

    # Overwrite the projections file with the filtered pool (the harness owns
    # this file for the duration of the backtest; it's regenerated per week).
    # Assert the pool actually carries real projections BEFORE handing it to
    # the optimizer -- a pool of all-NaN final_projection would make the ILP
    # objective meaningless and silently produce an arbitrary legal lineup
    # (which is exactly what a broken round-trip would look like).
    n_nan_proj = pool["final_projection"].isna().sum()
    if n_nan_proj:
        return {"site": site, "season": season, "week": week, "status": "ERROR",
                "detail": f"{n_nan_proj}/{len(pool)} pool players have NaN "
                          f"final_projection BEFORE optimize -- projection "
                          f"pipeline or column round-trip is broken"}
    filtered_path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    pool.to_csv(filtered_path, index=False)

    # Decision #9, bug-fix pass: build the FIELD POOL here -- BEFORE the
    # optimizer runs, not after. Two reasons, both found by real runs:
    #   (a) a field-pool problem should fail fast, not after burning a full
    #       20-lineup ILP solve, and
    #   (b) that wasted solve drew from `rng`, which shifted the RNG state
    #       for every subsequent week and made the affected arm's per-week
    #       fields non-identical to the other arms' -- silently un-pinning
    #       the very yardstick this decision exists to pin. Observed: the
    #       cold-start arm's field medians diverged from wk4 onward.
    field_pool = pool
    field_pool_note = ""
    if field_proj_path != proj_path:
        fproj = pd.read_csv(field_proj_path,
                            dtype={"player_id": str, "site_player_id": str})
        fp = fproj[fproj["team"].isin(main_teams_norm)]
        fp = fp[fp["final_projection"] > 0].copy()
        if len(fp) < 20:
            # The anchor-OFF pool can be legitimately EMPTY -- week 1 is the
            # canonical case, and it is exactly the week the cold-start arm
            # exists to make buildable. Pinning the field to a pool that
            # does not exist is impossible, so fall back to this arm's own
            # pool and say so loudly. The week's percentile is then not
            # cross-arm comparable, which is already true regardless: the
            # baseline arm has no week 1 at all to compare it against.
            field_pool_note = (f"field fell back to the ARM pool "
                               f"(anchor-OFF pool had {len(fp)} players -- "
                               f"expected for week 1); this week's percentile "
                               f"is NOT cross-arm comparable")
            print(f"     NOTE wk{week}: {field_pool_note}")
        else:
            field_pool = fp

    # Run the REAL optimizer in-process (decision #4). build_multi_lineup
    # re-reads final_projections_{site}_{week}.csv internally -- which is now
    # our filtered pool.
    try:
        lineups_df, _exposure, n_generated = opt.build_multi_lineup(
            site, week, n_lineups=num_lineups, seed=int(rng.integers(1_000_000)),
        )
    except Exception as e:
        return {"site": site, "season": season, "week": week, "status": "ERROR",
                "detail": f"optimizer failed: {type(e).__name__}: {e}"}

    if lineups_df is None or len(lineups_df) == 0:
        return {"site": site, "season": season, "week": week, "status": "ERROR",
                "detail": "optimizer returned no lineups"}

    # build_multi_lineup returns ONE concatenated DataFrame with a lineup id
    # column -- split it back into per-lineup player-id lists.
    lineup_id_col = next((c for c in ("lineup_id", "lineup", "lineup_num", "lineup_index")
                          if c in lineups_df.columns), None)
    if lineup_id_col:
        lineups = [g for _, g in lineups_df.groupby(lineup_id_col)]
    else:
        # single lineup, no id column
        lineups = [lineups_df]

    # Score our lineups + the synthetic field on real actuals.
    actuals = load_actuals(site, season)
    actuals_wk = actuals[actuals["week"] == week]

    our_scores = [score_lineup(list(lu["site_player_id"]), actuals_wk) for lu in lineups]

    field = build_synthetic_field(field_pool, site, field_size, rng)
    field_scores = np.array([score_lineup(f, actuals_wk) for f in field], dtype=float)

    pcts = np.array([percentile_of(s, field_scores) for s in our_scores])

    if DEBUG:
        # Dump the two lineups the two REPORTED numbers actually come from,
        # not lineups[0] (which is neither). Session 10.2.
        best_i = int(np.argmax(our_scores))
        med_i = int(np.argsort(our_scores)[len(our_scores) // 2])
        _debug_dump(site, season, week, lineups[best_i], actuals_wk, pool,
                    field_scores, our_scores[best_i],
                    label=f"MAX-percentile lineup (#{best_i})")
        if med_i != best_i:
            _debug_dump(site, season, week, lineups[med_i], actuals_wk, pool,
                        field_scores, our_scores[med_i],
                        label=f"MEDIAN-percentile lineup (#{med_i})")

    return {
        "site": site, "season": season, "week": week, "status": "OK",
        "n_lineups": len(lineups), "n_field": len(field),
        "pool_size": len(pool),
        "our_best_score": round(max(our_scores), 2),
        "our_median_score": round(float(np.median(our_scores)), 2),
        "field_median_score": round(float(np.median(field_scores)), 2) if len(field_scores) else None,
        "median_percentile": round(float(np.median(pcts)), 1),
        "max_percentile": round(float(np.max(pcts)), 1),
        "anchor": describe_anchor(anchor),
        "field_pinned": bool(field_proj_path != proj_path and not field_pool_note),
        "detail": field_pool_note,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lineup-level backtest harness (Session 10.1).")
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, nargs="+", default=None)
    parser.add_argument("--all-weeks", action="store_true")
    parser.add_argument("--num-lineups", type=int, default=1,
                        help="Lineups to build per week (1 = single-entry; 20 = GPP portfolio)")
    parser.add_argument("--field-size", type=int, default=2000,
                        help="Synthetic field size for percentile (decision #3)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--refresh-games", action="store_true",
                        help="Re-download nflverse games.csv")
    parser.add_argument("--debug", action="store_true",
                        help="Dump one week's lineup player-by-player (proj vs actual) + field distribution")
    # Session 10.2 (decision #8) -- passed straight through to
    # build_projections.py. Omitted entirely at the defaults, so a default
    # run is byte-identical to the Session 10.1 baseline run.
    parser.add_argument("--salary-anchor-weight", type=float, default=0.0,
                        help="Blend weight on the fitted salary-implied baseline "
                             "(0.0 = off = the Session 10.1 baseline arm)")
    parser.add_argument("--salary-anchor-cold-start", action="store_true",
                        help="Use the games_played shrinkage schedule instead of a "
                             "flat weight. Also makes week 1 backtestable.")
    parser.add_argument("--salary-anchor-k", type=float, default=4.0,
                        help="Half-weight point of the cold-start schedule, in games "
                             "played. ARBITRARY default, not fit.")
    parser.add_argument("--field-pool", choices=["baseline", "arm"], default="baseline",
                        help="Which pool the synthetic field is sampled from "
                             "(decision #9). 'baseline' (default) pins the field to "
                             "the anchor-OFF pool so every arm shares one yardstick; "
                             "'arm' is the pre-10.2 behaviour, which lets the field "
                             "move with the projection being tested. No effect when "
                             "the anchor is off.")
    args = parser.parse_args()

    anchor = {"weight": args.salary_anchor_weight,
              "cold_start": args.salary_anchor_cold_start,
              "k": args.salary_anchor_k}

    global DEBUG
    DEBUG = args.debug

    games = load_games(force_refresh=args.refresh_games)
    rng = np.random.default_rng(args.seed)

    if args.all_weeks:
        weeks = sorted(games[(games["season"] == args.season)]["week"].unique())
        weeks = [int(w) for w in weeks if w <= 18]
    elif args.week:
        weeks = args.week
    else:
        raise SystemExit("Specify --week N [N ...] or --all-weeks.")

    print(f"Backtest: {SITE_CONFIGS[args.site]['label']} {args.season}, "
          f"weeks {weeks}, {args.num_lineups} lineup(s)/week, "
          f"field {args.field_size}.")
    print("NOTE: this is a BOOTSTRAP measurement (RotoGuru <=2021, not current "
          "2025 data) -- it proves mechanics and sets a baseline, it does NOT "
          "measure whether the current projections are good now (decision #6).")
    print("NOTE: field percentile is vs a SYNTHETIC ownership-weighted field "
          "(Session 4.1 heuristic, not real ownership) -- 'plausible field', "
          "not 'real contest' (decision #3).")
    print(f"ARM:  {describe_anchor(anchor)}")
    print(f"FIELD: sampled from the {args.field_pool} pool "
          f"({'pinned -- comparable across arms' if args.field_pool == 'baseline' else 'moves with the arm -- NOT comparable across arms'}).\n")

    results = []
    for week in weeks:
        res = backtest_week(args.site, args.season, week, games,
                            args.num_lineups, args.field_size, rng, anchor,
                            args.field_pool)
        results.append(res)
        if res["status"] == "OK":
            print(f"  OK  {args.site} {args.season} wk{week:<2}  "
                  f"median pctile {res['median_percentile']:>5.1f}  "
                  f"max pctile {res['max_percentile']:>5.1f}  "
                  f"(our med {res['our_median_score']}, best "
                  f"{res['our_best_score']}, field median "
                  f"{res['field_median_score']}, pool {res['pool_size']})")
        elif res["status"] == "SKIP":
            print(f"  --  {args.site} {args.season} wk{week:<2}  SKIP: {res['detail'][:100]}")
        else:
            print(f"  XX  {args.site} {args.season} wk{week:<2}  ERROR: {res['detail'][:120]}")

    # Summary
    ok = [r for r in results if r["status"] == "OK"]
    err = [r for r in results if r["status"] == "ERROR"]
    skip = [r for r in results if r["status"] == "SKIP"]
    print("\n" + "=" * 62 + "\nSUMMARY\n" + "=" * 62)
    print(f"  Arm:   {describe_anchor(anchor)}")
    print(f"  Weeks: {len(results)}   OK: {len(ok)}   SKIP: {len(skip)}   ERROR: {len(err)}")
    if ok:
        med = np.array([r["median_percentile"] for r in ok])
        mx = np.array([r["max_percentile"] for r in ok])
        print(f"  Median-percentile (cash/floor proxy): "
              f"mean {med.mean():.1f}, min {med.min():.1f}, max {med.max():.1f}")
        print(f"  Max-percentile (upside proxy):        "
              f"mean {mx.mean():.1f}, min {mx.min():.1f}, max {mx.max():.1f}")
        # Session 10.2, decision #9: raw scores are in ARM-INDEPENDENT units
        # (real fantasy points), so a paired week-by-week comparison of these
        # between arms is immune to any change in the field. Percentiles are
        # the headline; these are the check on them.
        rmed = np.array([r["our_median_score"] for r in ok], dtype=float)
        rbest = np.array([r["our_best_score"] for r in ok], dtype=float)
        fmed = np.array([r["field_median_score"] for r in ok], dtype=float)
        print(f"  Raw score, median lineup:  mean {rmed.mean():6.2f}   "
              f"(arm-independent units -- compare these across arms too)")
        print(f"  Raw score, best lineup:    mean {rbest.mean():6.2f}")
        print(f"  Field median score:        mean {fmed.mean():6.2f}   "
              f"(should be IDENTICAL across arms under --field-pool baseline)")
        unpinned = [r for r in ok if r.get("detail")]
        if unpinned:
            print(f"\n  !! {len(unpinned)} week(s) could NOT use the pinned field and "
                  f"fell back to their own pool.\n     Those weeks are not "
                  f"cross-arm comparable, so the means above are not either.\n"
                  f"     Re-run with an explicit --week list excluding them for the "
                  f"like-for-like number:")
            for r in unpinned:
                print(f"       wk{r['week']}: {r['detail']}")
        if anchor["weight"] > 0 or anchor["cold_start"]:
            print("\n  ^ Compare BOTH numbers, separately, against the Session 10.1 "
                  "baseline\n    (2021 DK, 20 lineups): median-pctile 72.8, "
                  "max-pctile 94.7.\n    A change that lifts one and drops the other "
                  "is a floor/upside tradeoff to\n    decide deliberately, not an "
                  "unambiguous win. NOTE: if this run included\n    week 1 (only "
                  "possible with the anchor on), it is NOT week-for-week comparable\n"
                  "    to the baseline -- re-run excluding week 1 for the like-for-like "
                  "number.")
        else:
            print("\n  ^ This is the BASELINE for the current projection system. "
                  "Every Phase 10\n    projection change is measured against these two "
                  "numbers, separately.")
    if skip:
        print("\n  SKIPPED (not backtestable, not an error):")
        for r in skip:
            print(f"    {r['site']} {r['season']} wk{r['week']}: {r['detail'][:120]}")

    if err:
        print("\n  ERRORS (investigate -- not silently skipped):")
        for r in err:
            print(f"    {r['site']} {r['season']} wk{r['week']}: {r['detail'][:160]}")

    if err and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
