"""Does the live wk7+ salary-line blend lift backups/depth players into the >5 pt range? (research; no FC data)"""
import json, os
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(R, "data/fc_history/derived")
cfg = json.load(open(os.path.join(D, "projection_v2/early_season_blend_config.json")))
o = pd.read_parquet(os.path.join(D, "qb_depth/dnp_frame.parquet"))
o = o[(o.week >= 7) & ~o.desig.isin(["Out", "Doubtful"]) & o.status.isin(["ACT", "INA"])].copy()
line = {p: v for p, v in cfg["sal_line"].items()}
S = o.salary / 1000 * o.position.map(lambda p: line[p][0]) + o.position.map(lambda p: line[p][1])
g = np.where(o.position == "QB", "QB", "SKILL")
a = np.array([cfg["weeks"]["7+"][k]["a"] for k in g]); w = np.array([cfg["weeks"]["7+"][k]["w"] for k in g])
o["blend"] = (o.final_projection + a + w * (S - o.final_projection)).clip(lower=0)
nsl = o[["season", "week"]].drop_duplicates().shape[0]
for pos in ["QB", "RB", "WR", "TE"]:
    x = o[o.position == pos]
    cross = x[(x.final_projection <= 5) & (x.blend > 5)]
    print(f"{pos}: rows lifted from <=5 to >5 by the wk7+ blend: {len(cross)/nsl:.2f}/slate, zero-snap rate among them {cross.zero_off.mean():.3f}, "
          f"mean pre {cross.final_projection.mean():.1f} -> post {cross.blend.mean():.1f}")
qb = o[(o.position == "QB") & (o.final_projection < 8)]
print(f"QB backups (pre-blend <8): {len(qb)/nsl:.1f}/slate, mean {qb.final_projection.mean():.2f} -> blended {qb.blend.mean():.2f}; share blended >5: {(qb.blend>5).mean():.3f}; zero-snap rate {qb.zero_off.mean():.3f}")
