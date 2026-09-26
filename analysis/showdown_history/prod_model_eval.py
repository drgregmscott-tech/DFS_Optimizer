"""Run the PRODUCTION showdown ownership model (scripts/ownership_model_showdown.py, current artifact)
on each FC history slate, feeding FC Proj as final_projection (a proxy: production uses our own projections).
Output: data/fc_history/derived/showdown/prod_own_pred.parquet"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "scripts"))
import ownership_model_showdown as oms
art = json.loads(oms.ARTIFACT.read_text())
df = pd.read_parquet(R / "data/fc_history/derived/showdown/players.parquet")
out = []
for s, g in df.groupby("slate"):
    g = g.reset_index(drop=True); g["player_id"] = [f"p{i}" for i in range(len(g))]
    rows = []
    for role, m in (("CPT", 1.5), ("FLEX", 1.0)):
        t = pd.DataFrame(dict(player_id=g.player_id, roster_role=role, team=g.Team, position=g.pos,
                              salary=g.sal * m, final_projection=g.proj * m, sigma=g.stdv.fillna(0) * m,
                              player_name=g.Player, own=np.where(role == "CPT", g.cpt_own, g.flex_own)))
        rows.append(t)
    pool = pd.concat(rows, ignore_index=True)
    f = oms.build_features(pool); pred = oms.predict(f, art)
    pool["pred"] = pred.values; pool["slate"] = s
    out.append(pool.drop(columns="player_name")); print(s, flush=True)
pd.concat(out).to_parquet(R / "data/fc_history/derived/showdown/prod_own_pred.parquet")
