"""Step 2a: per-slate DK SHOWDOWN salary pools (CPT + FLEX rows, live ingest schema) from the FC showdown exports,
with gsis player_ids. Writes (gitignored, FC-derived): data/fc_history/derived/showdown/salaries_sd/
salaries_dk_sd_<slate>.csv and mapping report map_report.csv. Embeds no FC data.
Mapping order: fc_master_mapped (name,team,season) -> weekly_stats season (name,team) -> weekly_rosters (name,team)
-> weekly_stats season name-only unique -> unmapped (synthetic id UNM_<slate>_<i>; engine treats as no-history)."""
import re
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]; OUT = R / "data/fc_history/derived/showdown"; SAL = OUT / "salaries_sd"
SAL.mkdir(parents=True, exist_ok=True)
FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}
def nk(s): return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))

P = pd.read_parquet(OUT / "players.parquet")
W = pd.read_csv(OUT / "slate_weeks_resolved.csv").set_index("slate")
M = pd.read_csv(R / "data/fc_history/derived/fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
M = M[M.player_id.notna() & ~M.player_id.astype(str).str.startswith("DST")]
M["k"] = M.player.map(nk); M["team"] = M.team.map(lambda t: FIX.get(t, t))
mm = M.groupby(["season", "k", "team"]).player_id.agg(lambda s: s.mode().iloc[0])
WS = {y: pd.read_parquet(R / f"data/weekly_stats_{y}.parquet") for y in (2023, 2024, 2025)}
RO = {y: pd.read_parquet(R / f"data/weekly_rosters_{y}.parquet") for y in (2024, 2025)}
rep, allmap = [], []
for s, g in P.groupby("slate"):
    yr, wk = int(W.loc[s, "season"]), int(W.loc[s, "week"])
    ws = WS[yr]; ws = ws.assign(k=ws.player_display_name.map(nk))
    wsm = ws.groupby(["k", "team"]).player_id.first()
    wsk = ws.groupby("k").player_id.agg(lambda x: x.iloc[0] if x.nunique() == 1 else None)
    ro = None
    if yr in RO:
        ro = RO[yr].assign(k=RO[yr].full_name.map(nk)).dropna(subset=["gsis_id"]).groupby(["k", "team"]).gsis_id.first()
    g = g.reset_index(drop=True).copy()
    g["team"] = g.Team.map(lambda t: FIX.get(t, t)); g["k"] = g.Player.map(nk)
    ids, tiers = [], []
    for i, r in g.iterrows():
        if r.pos == "DST":
            ids.append(f"DST_{r.team}"); tiers.append("dst"); continue
        for tier, fn in (("fc_master", lambda: mm.get((yr, r.k, r.team))), ("wstats_team", lambda: wsm.get((r.k, r.team))),
                         ("rosters", lambda: ro.get((r.k, r.team)) if ro is not None else None),
                         ("wstats_name", lambda: wsk.get(r.k))):
            v = fn()
            if isinstance(v, str) and v:
                ids.append(v); tiers.append(tier); break
        else:
            ids.append(f"UNM_{s}_{i}"); tiers.append("unmapped")
    g["player_id"] = ids; g["tier"] = tiers
    dup = g.player_id.duplicated(keep=False) & ~g.player_id.str.startswith("UNM")
    if dup.any():  # collisions -> keep higher-salary, mark others unmapped
        for pid, gg in g[dup].groupby("player_id"):
            for j in gg.sort_values("sal", ascending=False).index[1:]:
                g.loc[j, "player_id"] = f"UNM_{s}_{j}"; g.loc[j, "tier"] = "unmapped_dup"
    # pre-lock AvgPointsPerGame proxy: season-to-date mean PPR (K: 3*FG + PAT), weeks < target; kicker starter pick uses it
    prior = ws[ws.week < wk].copy()
    prior["pts"] = np.where(prior.position == "K", 3 * prior.fg_made.fillna(0) + prior.pat_made.fillna(0), prior.fantasy_points_ppr)
    avg = prior.groupby("player_id").pts.mean()
    g["avg"] = g.player_id.map(avg).fillna(0.0).round(2)
    rows = []
    for role, mult, off in (("CPT", 1.5, 0), ("FLEX", 1.0, 5000)):
        sal = (g.sal * mult).round().astype(int)
        rows.append(pd.DataFrame({
            "Position": g.pos, "Name": g.Player, "ID": [str(800000 + off + i) for i in range(len(g))], "Roster Position": role,
            "Salary": sal, "TeamAbbrev": g.team, "AvgPointsPerGame": g.avg, "roster_role": role, "name": g.Player, "site": "dk",
            "salary": sal, "normalized_name": g.k, "normalized_team": g.team, "position_upper": g.pos,
            "slate_format": "showdown", "player_id": g.player_id}))
    pd.concat(rows, ignore_index=True).to_csv(SAL / f"salaries_dk_sd_{s}.csv", index=False)
    g["slate"] = s
    allmap.append(g[["slate", "Player", "team", "pos", "sal", "player_id", "tier", "cpt_own", "flex_own", "proj"]])
A = pd.concat(allmap, ignore_index=True)
A.to_parquet(OUT / "sd_id_map.parquet")
un = A.tier.str.startswith("unmapped")
print(A.tier.value_counts())
print("unmapped rows:", un.sum(), "of", len(A), "| by pos:", A[un].pos.value_counts().to_dict())
print("unmapped: salary<=1000 share %.2f; FC proj==0 share %.2f" % ((A[un].sal <= 1000).mean(), (A[un].proj <= 0).mean()))
print("ownership mass on unmapped: CPT %.2f%% of %.0f, FLEX %.2f%% of %.0f (totals over 49 slates)" % (
    A[un].cpt_own.sum(), A.cpt_own.sum(), A[un].flex_own.sum(), A.flex_own.sum()))
print("max FLEX own among unmapped: %.1f; unmapped with FLEX>=5%%: %d" % (A[un].flex_own.max(), (A[un].flex_own >= 5).sum()))
