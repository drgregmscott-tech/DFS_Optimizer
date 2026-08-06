"""
probe_reconcile_gap.py
=======================

Session 14.0 diagnostic -- throwaway probe, not a permanent script.

Traces the two candidate explanations for the widespread rush/recv
reconciliation failure on a real slate: either the TARGET (team-predicted
volume x pool_share) is coming out too low, or the pool's raw_sum is
genuinely too high. Prints the actual numbers behind both sides for a
short list of (team, component) pairs, plus a per-player breakdown of
what's feeding raw_sum, so we can see which one it is instead of guessing.

Usage:
  python scripts/probe_reconcile_gap.py --site dk --season 2025 --week 23 \
      --slate-id dk_classic_wk1 --vegas-slate-id dk_classic_wk1 \
      --team GB --component rush
  python scripts/probe_reconcile_gap.py --site dk --season 2025 --week 23 \
      --slate-id dk_classic_wk1 --vegas-slate-id dk_classic_wk1 \
      --team CAR --component rush
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statline_model
import volume_prior
from ingest_salaries import SITE_CONFIGS
from build_projections import (
    POSITIONS,
    build_opponent_map,
    build_opponent_map_from_salaries,
    build_vegas_factors,
    load_real_team_for_week,
    load_salaries,
    load_schedule,
    load_vegas_implied_totals,
)

_TEAM_PRED_COL = {"pass": "team_attempts", "rush": "team_carries", "recv": "team_targets"}
_HIST_COL = {"pass": "hist_attempts", "rush": "hist_carries", "recv": "hist_targets"}
_RECENT_COL = {"pass": "recent_attempts", "rush": "recent_carries", "recv": "recent_targets"}
_MU_COL = {"pass": "pass_mu", "rush": "rush_mu", "recv": "recv_mu"}
_VOL_STAT = {"pass": "attempts", "rush": "carries", "recv": "targets"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--site", required=True, choices=["dk", "fd"])
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--slate-id", required=True)
    p.add_argument("--vegas-slate-id", default=None)
    p.add_argument("--team", required=True, help="e.g. GB")
    p.add_argument("--component", required=True, choices=["pass", "rush", "recv"])
    args = p.parse_args()

    site, season, week, slate_id = args.site, args.season, args.week, args.slate_id
    vegas_slate_id = args.vegas_slate_id or slate_id
    comp = args.component
    team = args.team

    variance = statline_model.load_variance()
    prior_art = volume_prior.load_prior(site)

    vegas = load_vegas_implied_totals(vegas_slate_id)
    salaries = load_salaries(site, slate_id)
    schedule = load_schedule(season)

    opponent_map = build_opponent_map(schedule, week)
    slate_teams = set(salaries["normalized_team"].dropna().unique())
    if not (slate_teams & set(opponent_map.keys())):
        opponent_map = build_opponent_map_from_salaries(salaries)
    vegas_factors = build_vegas_factors(vegas, opponent_map)

    print(f"=== Opponent / Vegas resolution for {team} ===")
    print(f"opponent_map[{team}] = {opponent_map.get(team)}")
    vf_row = vegas_factors[vegas_factors["team"] == team]
    print(f"vegas_factors row for {team}:\n{vf_row.to_string(index=False)}\n")

    # --- team_volume_history: the raw real-history side --------------------
    team_vol = statline_model.team_volume_history(season, week)
    tv_row = team_vol[team_vol["team"] == team]
    print(f"=== team_volume_history() raw row for {team} ===")
    print(tv_row.to_string(index=False))
    print()

    # --- vegas-anchored prediction: the TARGET side -------------------------
    vg = vegas.copy()
    vg["expected_opponent"] = vg["team"].map(opponent_map)
    vg = vg[vg["opponent"] == vg["expected_opponent"]].drop_duplicates("team")
    if "spread" not in vg.columns:
        vg["spread"] = 0.0
    vg_row = vg[vg["team"] == team]
    print(f"=== Raw vegas row used for team-volume prediction, {team} ===")
    print(vg_row.to_string(index=False))
    print()

    vg_indexed = vg.set_index("team")[["implied_total", "spread"]]
    pool_teams = sorted(slate_teams)
    team_vol_anchored = statline_model.vegas_anchored_team_volume(
        team_vol, vg_indexed, prior_art, teams=pool_teams)
    tva_row = team_vol_anchored[team_vol_anchored["team"] == team]
    print(f"=== vegas_anchored_team_volume() output for {team} (this IS the target basis) ===")
    print(tva_row.to_string(index=False))
    pred_col = _TEAM_PRED_COL[comp]
    hist_col_full = f"{pred_col}_history"
    if pred_col in tva_row.columns:
        print(f"\n>>> {comp} team_pred used for target = "
              f"{tva_row[pred_col].iloc[0] if len(tva_row) else 'MISSING'}")
    if hist_col_full in tva_row.columns:
        print(f">>> {comp} raw pre-anchor history value (team_volume_history's own number) = "
              f"{tva_row[hist_col_full].iloc[0] if len(tva_row) else 'MISSING'}")
    print()

    # --- player-level pool: the raw_sum side --------------------------------
    usage = statline_model.build_usage(season, week, variance)
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    players = salaries[salaries["position_upper"].isin(POSITIONS)].copy()
    players = players[players["player_id"].notna()]
    players = players.rename(columns={"normalized_team": "team", "position_upper": "position"})
    players = players[["player_id", "name", "position", "team", "salary", site_id_col]].rename(
        columns={"name": "player_name", site_id_col: "site_player_id"})
    week_was_played, real_team_this_week = load_real_team_for_week(season, week)
    players["no_real_game_this_week"] = False
    if week_was_played:
        corrected = players["player_id"].map(real_team_this_week)
        played = corrected.notna()
        players.loc[played, "team"] = corrected[played]
        players["no_real_game_this_week"] = ~played

    df = players.merge(usage.drop(columns=["position", "hist_team"], errors="ignore"),
                       on="player_id", how="left")
    df["games_played"] = pd.to_numeric(df.get("games_played"), errors="coerce").fillna(0).astype(int)
    df = statline_model.fill_cold_start_rates(df, variance)

    df = statline_model.apply_volume_prior(df, prior_art, team_vol_anchored,
                                           role_change=True)

    team_players = df[(df["team"] == team) & (df["position"].isin(POSITIONS))].copy()
    mu_col = _MU_COL[comp]
    show_cols = ["player_name", "position", "salary", "games_played",
                 "participation", "participation_effective",
                 f"{comp}_price_share", f"{comp}_price_volume",
                 "volume_prior_weight", mu_col]
    show_cols = [c for c in show_cols if c in team_players.columns]
    team_players = team_players.sort_values(mu_col, ascending=False)
    print(f"=== Per-player breakdown, {team} {comp} (post volume-prior blend) ===")
    print(team_players[show_cols].to_string(index=False))
    print(f"\n>>> RAW POOL SUM ({comp}_mu across these players) = "
          f"{team_players[mu_col].sum():.2f}")


if __name__ == "__main__":
    main()
