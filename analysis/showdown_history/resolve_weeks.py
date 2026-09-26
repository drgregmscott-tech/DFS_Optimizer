"""Step 1 of the ourproj replay: resolve each FC showdown slate -> (season, week, game_id), verified three ways:
home team (FC Opp '@'/'vs'), closing total/spread vs nflverse, and FC actual scores vs nflverse weekly PPR points.
Output (gitignored): data/fc_history/derived/showdown/slate_weeks_resolved.csv. Embeds no FC data."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]; OUT = R / "data/fc_history/derived/showdown"
FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}
def nk(s): return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))
P = pd.read_parquet(OUT / "players.parquet")
G = pd.read_csv(R / "data/nflverse_games.csv")
G = G[G.game_type == "REG"]
WS = {y: pd.read_parquet(R / f"data/weekly_stats_{y}.parquet") for y in (2023, 2024, 2025)}
rows = []
for s, g in P.groupby("slate"):
    yr = int(s[:4]); teams = sorted({FIX.get(t, t) for t in g.Team})
    # home team: players whose Opp starts with 'vs'
    home = g[g.Opp.astype(str).str.startswith("vs")].Team.map(lambda t: FIX.get(t, t)).unique()
    home = home[0] if len(home) == 1 else None
    tv = g.groupby("Team").tv.first(); tv.index = [FIX.get(t, t) for t in tv.index]
    c = G[(G.season == yr) & (((G.home_team == teams[0]) & (G.away_team == teams[1])) | ((G.home_team == teams[1]) & (G.away_team == teams[0])))]
    best = []
    for _, r in c.iterrows():
        fc_spread = tv[r.home_team] - tv[r.away_team]           # home implied margin
        ws = WS[yr]; ws = ws[(ws.week == r.week) & ws.team.isin(teams)]
        m = g[~g.pos.isin(["DST"])].assign(k=g.Player.map(nk)).merge(ws.assign(k=ws.player_display_name.map(nk)), on="k")
        corr = np.corrcoef(m.act, m.fantasy_points_ppr)[0, 1] if len(m) > 3 else np.nan
        mad = float(np.median(np.abs(m.act - m.fantasy_points_ppr))) if len(m) else np.nan
        best.append(dict(slate=s, season=yr, week=int(r.week), game_id=r.game_id, home=r.home_team, away=r.away_team,
                         fc_home=home, home_ok=(home == r.home_team) if home else np.nan,
                         d_total=round(tv.sum() - r.total_line, 2), d_spread=round(fc_spread - r.spread_line, 2),
                         n_match=len(m), act_corr=round(corr, 3), act_medabs=mad, n_cand=len(c), gameday=r.gameday, weekday=r.weekday))
    b = pd.DataFrame(best)
    b["score"] = b.act_corr.fillna(0) * 10 - b.d_total.abs() - b.d_spread.abs() + b.home_ok.fillna(0).astype(float) * 2
    b = b.sort_values("score", ascending=False)
    ch = b.iloc[0].to_dict()
    ch["runner_up_corr"] = b.act_corr.iloc[1] if len(b) > 1 else np.nan
    ch["runner_up_week"] = b.week.iloc[1] if len(b) > 1 else np.nan
    # verified = FC home team matches, median |FC act - nflverse PPR| ~0 (exact stat match), and any rematch candidate
    # matches clearly worse (corr gap > 0.1). corr < 1 is driven by K/DST-free DK bonuses (300yd/100yd +3), not mismatch.
    ch["verified"] = bool(ch["home_ok"] is True and ch["act_medabs"] <= 0.5 and
                          (len(b) == 1 or ch["act_corr"] - b.act_corr.iloc[1] > 0.1))
    rows.append(ch)
res = pd.DataFrame(rows).drop(columns="score")
assert res.slate.is_unique and len(res) == 49
res.to_csv(OUT / "slate_weeks_resolved.csv", index=False)
pd.set_option("display.width", 250); print(res.to_string(index=False))
print("verified:", res.verified.sum(), "/", len(res), " multi-candidate:", (res.n_cand > 1).sum())
