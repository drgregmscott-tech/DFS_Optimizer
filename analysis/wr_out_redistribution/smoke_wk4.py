"""Wk4 main smoke test of apply_wr_replacement on the live pool (no live file touched).
(1) live status (latest output/player_status_4_*.csv + manual overrides): who fires, and Nico Collins (QUESTIONABLE)
must NOT trigger. (2) synthetic: an in-memory copy of the status with a real WR1 set OUT."""
import sys
from pathlib import Path
import pandas as pd
CODE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE / "scripts"))
import statline_model as sm
pool = pd.read_csv(CODE / "output/final_projections_dk_dk_classic_wk4_main_04Oct2026.csv", dtype={"player_id": str})
pool = pool[pool.position.isin(["RB", "WR", "TE"])].copy()
st = sm.load_injury_status(4)
st["player_id"] = st.player_id.astype(str)
print("live OUT/DOUBTFUL on slate teams:")
od = st[st.status.str.upper().isin(["OUT", "DOUBTFUL"]) & st.team.isin(pool.team.unique())]
print(od.merge(pool[["player_id", "player_name"]], on="player_id", how="left")[["player_name", "team", "position", "status"]].to_string(index=False))
nico = pool[pool.player_name.str.contains("Nico Collins")]
print("\nNico Collins status:", st[st.player_id.isin(nico.player_id)].status.tolist())
r = sm.apply_wr_replacement(pool, 2026, 4, st)
hit = r[r.wrw_wr_delta_pts > 0]
print("\n(1) LIVE fires:", len(hit))
print(hit[["player_name", "team", "position", "salary", "final_projection", "wrw_wr_delta_pts", "wrw_wr_vacated_tgt"]].round(2).to_string(index=False))
print("HOU rows touched:", int((r.team.eq("HOU") & (r.wrw_wr_delta_pts > 0)).sum()))

ag, tvr = sm._wrw_trailing_usage(2026, 4, sorted(pool.team.unique()), {"trail_team_games": 8, "trail_player_apps": 4, "team_vol_games": 4})
for who in sys.argv[1:] or ["Nico Collins", "Puka Nacua"]:
    row = pool[pool.player_name == who].iloc[0]
    syn = pd.concat([st[st.player_id != row.player_id],
                     pd.DataFrame([{"player_id": row.player_id, "team": row.team, "position": "WR", "status": "OUT"}])])
    r2 = sm.apply_wr_replacement(pool, 2026, 4, syn)
    a = ag.loc[row.team].copy(); a.index = a.index.astype(str)
    t = pool[pool.team == row.team].merge(a[["sh_tgt", "last_g"]], left_on="player_id", right_index=True, how="left") \
        .merge(r2[["player_id", "wrw_wr_delta_pts"]], on="player_id")
    print(f"\n(2) SYNTHETIC {who} OUT ({row.team}); team trailing targets {tvr.loc[row.team, 'ttgt']:.1f}, "
          f"his trailing tgt share {a.loc[row.player_id, 'sh_tgt']:.3f}, played last team game: {a.loc[row.player_id, 'last_g'] == tvr.loc[row.team, 'last_g']}")
    print(t[t.position.isin(["WR", "TE", "RB"])].sort_values(["position", "sh_tgt"], ascending=[False, False])
          [["player_name", "position", "salary", "sh_tgt", "final_projection", "wrw_wr_delta_pts"]].round(3).head(14).to_string(index=False))
    print("other teams touched:", int(((r2.team != row.team) & (r2.wrw_wr_delta_pts != r.wrw_wr_delta_pts)).sum()))
