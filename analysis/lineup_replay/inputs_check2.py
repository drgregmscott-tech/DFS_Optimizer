"""Same-player-set projection accuracy OLD vs NEW (players with old or new proj > 5, actual known, non-DST)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_2026 as R, common as C
rows = []
for s in R.SLATES:
    fpts, own, _ = R.load_real(s)
    o = R.load_pool("old", s); n = R.load_pool("new", s)
    m = o[["player_id", "player_name", "position", "final_projection", "salary"]].merge(
        n[["player_id", "final_projection"]], on="player_id", suffixes=("_o", "_n"))
    m["act"] = m.player_name.map(C.norm).map(fpts)
    m = m[((m.final_projection_o > 5) | (m.final_projection_n > 5)) & m.act.notna() & (m.position != "DST")]
    for pos, g in [("ALL", m), ("QB", m[m.position == "QB"]), ("SKILL", m[m.position != "QB"])]:
        rows.append(dict(slate=s, pos=pos, n=len(g),
                         mae_old=(g.final_projection_o - g.act).abs().mean(), mae_new=(g.final_projection_n - g.act).abs().mean(),
                         sp_old=g.final_projection_o.corr(g.act, method="spearman"), sp_new=g.final_projection_n.corr(g.act, method="spearman"),
                         top_old=g.nlargest(20, "final_projection_o").act.mean(), top_new=g.nlargest(20, "final_projection_n").act.mean()))
T = pd.DataFrame(rows); T["wk"] = T.slate.str[:3]
pd.set_option("display.width", 200)
print(T[T.pos == "ALL"].round(3).to_string(index=False))
print(T.groupby(["wk", "pos"]).mean(numeric_only=True).round(3).to_string())
T.to_csv(Path(__file__).resolve().parent / "inputs_check.csv", index=False)
