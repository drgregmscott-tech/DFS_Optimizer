"""Step H driver: run scripts/build_projections_statline.py UNCHANGED, optionally with the
floor-share exclusion fix monkeypatched in, and capture audit snapshots.

usage (from repo root):
  python analysis/proj_h/h_build.py <tag> <fix:0|1> -- <normal build_projections_statline.py args>

Env (optional): H_THRESH (default 4200), H_GUARD (e.g. "RB:1,WR:3,TE:1"; players whose
depth_rank <= guard[pos] are never excluded; default "RB:1,WR:3,TE:1").

The fix: inside apply_volume_prior(), zero-history (no usage row at all) RB/WR/TE priced
<= H_THRESH and not depth-chart-guarded get price_share = 0 BEFORE the Session 14.0b team-sum
normalisation, so (a) they contribute no mu to reconciliation's raw_sum and (b) the
reconciliation target (team_pred x historical pool share, which floor players never fed)
is unchanged -> scale = target/raw_sum renormalises the real contributors UP.
Writes into analysis/proj_h/builds/<tag>/ : final csv copy, reconcile csv copy,
pre/post reconcile pool snapshots, and the excluded-player list.
"""
import os
import runpy
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(REPO)

import statline_model  # noqa: E402
import volume_prior  # noqa: E402

tag, fix = sys.argv[1], sys.argv[2] == "1"
assert sys.argv[3] == "--"
build_args = sys.argv[4:]
slate_id = build_args[build_args.index("--slate-id") + 1]
OUT = Path(__file__).resolve().parent / "builds" / tag
OUT.mkdir(parents=True, exist_ok=True)
THRESH = float(os.environ.get("H_THRESH", 4200))
GUARD = {k: int(v) for k, v in (x.split(":") for x in os.environ.get("H_GUARD", "RB:1,WR:3,TE:1").split(","))}

_orig_avp = statline_model.apply_volume_prior
_orig_rec = statline_model.reconcile_team_shares
_orig_sfs = volume_prior.share_from_salary


def floor_mask(pool, depth_chart):
    # NB: the build's own `_no_usage_history` flag is False for every row in these backtest
    # builds (games_played is already filled upstream), so "zero history" = 0 games in the
    # lookback window (these rows also have hist_team NaN).
    nohist = pd.to_numeric(pool.get("games_played"), errors="coerce").fillna(0).eq(0)
    sal = pd.to_numeric(pool["salary"], errors="coerce")
    pos = pool["position"].astype(str)
    m = pos.isin(list(GUARD)) & nohist & (sal <= THRESH)
    rank = pd.Series(np.nan, index=pool.index)
    if depth_chart is not None and not depth_chart.empty:
        dc = depth_chart.drop_duplicates("player_id").set_index("player_id")["depth_rank"]
        rank = pool["player_id"].astype(str).map(dc)
    guarded = m & rank.notna() & (rank <= pos.map(GUARD))
    return m & ~guarded, m & guarded, rank


def avp(pool, artifact, team_vol, *a, **kw):
    excl, guarded, rank = floor_mask(pool, kw.get("depth_chart"))
    pool.assign(depth_rank_h=rank, excluded=excl, guarded=guarded)[excl | guarded][
        ["player_id", "player_name", "team", "position", "salary", "depth_rank_h", "excluded", "guarded"]
    ].to_csv(OUT / "floor_players.csv", index=False)
    if not fix:
        return _orig_avp(pool, artifact, team_vol, *a, **kw)
    ex_idx = set(pool.index[excl])

    def sfs(art, pos, comp, salary):
        s = _orig_sfs(art, pos, comp, salary)
        s = pd.Series(np.asarray(s, float), index=salary.index)
        s[s.index.isin(ex_idx)] = 0.0
        return s.to_numpy()

    volume_prior.share_from_salary = sfs
    try:
        out = _orig_avp(pool, artifact, team_vol, *a, **kw)
    finally:
        volume_prior.share_from_salary = _orig_sfs
    print(f"[H] floor-share fix: excluded {int(excl.sum())} zero-history floor player(s), "
          f"guarded {int(guarded.sum())}", file=sys.stderr)
    return out


def rec(pool, team_vol, *a, **kw):
    keep = [c for c in ["player_id", "player_name", "team", "hist_team", "position", "salary", "games_played",
                        "_no_usage_history", "rush_mu", "recv_mu", "pass_mu", "rush_price_share",
                        "recv_price_share", "volume_prior_weight", "absent_player_factor"] if c in pool.columns]
    pool[keep].to_csv(OUT / "pool_pre_reconcile.csv", index=False)
    team_vol.to_csv(OUT / "team_vol.csv", index=False)
    p2, rep = _orig_rec(pool, team_vol, *a, **kw)
    p2[keep].to_csv(OUT / "pool_post_reconcile.csv", index=False)
    return p2, rep


statline_model.apply_volume_prior = avp
statline_model.reconcile_team_shares = rec

sys.argv = ["build_projections_statline.py"] + build_args
runpy.run_path(str(REPO / "scripts" / "build_projections_statline.py"), run_name="__main__")

site = build_args[build_args.index("--site") + 1]
for src in (REPO / "output" / f"final_projections_{site}_{slate_id}.csv",
            REPO / "output" / f"statline_reconcile_{site}_{slate_id}.csv"):
    if src.exists():
        shutil.copy2(src, OUT / src.name)
print(f"[H] copied outputs to {OUT}", file=sys.stderr)
