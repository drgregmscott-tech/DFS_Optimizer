"""Cache the real 2026 wk1-2 DK classic ownership frame with production
features (fit_ownership_model.load_training_frame) plus the history-only extras.
Writes analysis/ownership_fc_refit/cache_2026.parquet (our own data, not FC)."""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import fit_ownership_model as fom  # noqa: E402

df = fom.load_training_frame("dk")
pos = df["position"]
df["vegas_pts"] = pd.to_numeric(df["implied_total"], errors="coerce")
df["sal_rank"] = df.groupby(["slate_id", "position"])["salary"].rank(ascending=False, method="min")
df["val"] = df["final_projection"] / (df["salary"] / 1000.0)
df["val_rank"] = df.groupby(["slate_id", "position"])["val"].rank(ascending=False, method="min")
df["proj_rank"] = df.groupby(["slate_id", "position"])["final_projection"].rank(ascending=False, method="min")
df["n_pos"] = df.groupby(["slate_id", "position"])["player_id"].transform("size")
keep = [c for c in df.columns if df[c].dtype != object or c in
        ("player_id", "player_name", "position", "position_group", "slate_id", "team")]
df[keep].to_parquet(REPO / "analysis/ownership_fc_refit/cache_2026.parquet")
print(df.groupby("slate_id").agg(n=("own", "size"), s=("own", "sum")))
