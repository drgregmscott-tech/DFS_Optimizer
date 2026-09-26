"""Build leak-free ownership-model features for every FC history slate.

Reads data/fc_history/derived/fc_master_mapped.csv (git-ignored subscription
data) and writes data/fc_history/derived/fc_own_features_<contest>.parquet
(also git-ignored -- NEVER commit either; the repo is public).

Per slate, FC's own pre-lock projection (fc_proj) stands in for our
final_projection and FC's stdv for sigma. Everything else is recomputed with
the production code (heuristic, optimizer exposure, om.build_features), so
the base features mean the same thing they do at runtime. pub_val and FFC
ownership do not exist historically (pub_val column is left 0 / absent).

Extra history-only candidates (all pre-lock): vegas_pts (team implied total),
sal_rank (salary rank within pos), val_rank (fc_proj/$ rank within pos),
proj_rank (projection rank within pos), n_pos (pool size at pos).

    python analysis/ownership_fc_refit/build_fc_features.py [--contest single_entry]
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import ownership_model as om  # noqa: E402
import build_projections as bp  # noqa: E402

SRC = REPO / "data/fc_history/derived/fc_master_mapped.csv"


def slate_frame(g: pd.DataFrame) -> pd.DataFrame:
    g = g[g["pos"].isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    # unmapped rows get a synthetic id so they stay in the pool
    pid = g["player_id"].astype(object)
    synth = "fc_" + g["name_key"].astype(str) + "_" + g["team"].astype(str)
    g["player_id"] = pid.where(pid.notna(), synth)
    g = g.drop_duplicates("player_id")
    df = pd.DataFrame({
        "player_id": g["player_id"].values,
        "player_name": g["player"].values,
        "position": g["pos"].values,
        "team": g["team"].values,
        "salary": pd.to_numeric(g["salary"], errors="coerce").values,
        "final_projection": pd.to_numeric(g["fc_proj"], errors="coerce").fillna(0).values,
        "sigma": pd.to_numeric(g["stdv"], errors="coerce").fillna(0).values,
        "vegas_pts": pd.to_numeric(g["vegas_pts"], errors="coerce").values,
        "own": pd.to_numeric(g["own_pct"], errors="coerce").fillna(0).values,
        "opp": g["opp"].astype(str).str.replace("@", "").str.strip().values,
    })
    team_tot = df.groupby("team")["vegas_pts"].median()
    df["implied_total"] = df["vegas_pts"]
    df["over_under"] = df["vegas_pts"] + df["opp"].map(team_tot)
    df["over_under"] = df["over_under"].fillna(df["over_under"].median())
    df["implied_total"] = df["implied_total"].fillna(df["implied_total"].median())
    df = df.rename(columns={"opp": "opponent"})
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contest", default="single_entry")
    args = ap.parse_args()
    d = pd.read_csv(SRC, dtype={"player_id": str})
    d = d[(d["contest"] == args.contest) & (d["slate_kind"] == "classic")]
    frames = []
    t0 = time.time()
    for sf, g in d.groupby("source_file"):
        df = slate_frame(g)
        own_total_all = df["own"].sum()
        df = bp.add_ownership_columns(df, "dk", layered=False)
        df = df[df["final_projection"] > 0].copy()
        df["position_group"] = df["position"]
        exposure = om.optimizer_exposure(df, "dk")
        feats = om.build_features(df, exposure)
        feats = feats.drop(columns=["pub_val", "ffc_listed", "l_ffc"])
        df = pd.concat([df, feats], axis=1)
        pos = df["position"]
        df["sal_rank"] = df.groupby(pos)["salary"].rank(ascending=False, method="min")
        df["val"] = df["final_projection"] / (df["salary"] / 1000.0)
        df["val_rank"] = df.groupby(pos)["val"].rank(ascending=False, method="min")
        df["proj_rank"] = df.groupby(pos)["final_projection"].rank(ascending=False, method="min")
        df["n_pos"] = df.groupby(pos)["player_id"].transform("size")
        df["season"] = int(g["season"].iloc[0])
        df["week"] = int(g["week"].iloc[0])
        df["slate_id"] = sf
        df["own_total_all"] = own_total_all
        frames.append(df)
        print(f"{sf}: {len(df)} players (own kept {df['own'].sum():.0f}/{own_total_all:.0f}) "
              f"{time.time() - t0:.0f}s", flush=True)
    out = pd.concat(frames, ignore_index=True)
    path = REPO / f"data/fc_history/derived/fc_own_features_{args.contest}.parquet"
    out.to_parquet(path)
    print(f"Wrote {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
