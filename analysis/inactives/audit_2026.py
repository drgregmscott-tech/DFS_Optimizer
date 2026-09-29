"""2026 wk1-3 audit: our last pre-lock status file vs what actually happened. Research only.
Pre-lock = newest output/player_status_{wk}_{UTC ts}.csv stamped before Sunday 17:00Z (1pm ET lock).
Actual inactive: DK actual_fpts == 0 in data/projection_error_log.csv AND (nflverse final report Out/Doubtful, or
roster INA, or no nflverse stat row where stats are complete [wk1-2]). wk3 nflverse stats/rosters incomplete ->
wk3 inactive = actual 0 and not in partial stats (flagged as approximate)."""
import glob, os, re
import pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
H = os.path.join(R, "analysis", "inactives")
out = open(os.path.join(H, "audit_2026_report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")

WEEKS = {1: ("23", "20260913_170000"), 2: ("2", "20260920_170000"), 3: ("3", "20260927_170000")}
log = pd.read_csv(os.path.join(R, "data", "projection_error_log.csv"), dtype={"player_id": str})
log = log[(log.position != "DST") & (log.season == 2026) & (log.slate_format == "classic") & (log.site == "dk")]
log = log.sort_values("final_projection").drop_duplicates(["week", "player_id"], keep="last")
inj = pd.read_parquet(os.path.join(H, "raw", "injuries_2026.parquet"))
inj = inj[inj.position.isin(["QB", "RB", "WR", "TE"])].drop_duplicates(["week", "gsis_id"], keep="last")
ro = pd.read_parquet(os.path.join(R, "data", "weekly_rosters_2026.parquet"), columns=["week", "gsis_id", "status"]).drop_duplicates(["week", "gsis_id"])
st = pd.read_parquet(os.path.join(R, "data", "weekly_stats_2026.parquet"), columns=["player_id", "week"])
played = set(zip(st.week, st.player_id))
allrows = []
for wk, (pre, cut) in WEEKS.items():
    files = sorted(glob.glob(os.path.join(R, "output", f"player_status_{pre}_2026*.csv")))
    ts = [re.search(r"_(\d{8}_\d{6})\.csv$", f).group(1) for f in files]
    pl = [f for f, t in zip(files, ts) if t < cut]
    last = pl[-1]; lt = re.search(r"_(\d{8}_\d{6})\.csv$", last).group(1)
    s = pd.read_csv(last, dtype={"player_id": str})[["player_id", "status"]].rename(columns={"status": "our_status"})
    d = log[log.week == wk].merge(s, on="player_id", how="left")
    d = d.merge(inj[inj.week == wk][["gsis_id", "report_status"]], left_on="player_id", right_on="gsis_id", how="left")
    d = d.merge(ro[ro.week == wk][["gsis_id", "status"]].rename(columns={"status": "roster"}), left_on="player_id", right_on="gsis_id", how="left")
    d["in_stats"] = [(wk, p) in played for p in d.player_id]
    zero = d.actual_fpts.fillna(0) == 0
    if wk <= 2:
        d["inactive"] = zero & (d.report_status.isin(["Out", "Doubtful"]) | (d.roster == "INA") | ~d.in_stats)
    else:
        d["inactive"] = zero & (d.report_status.isin(["Out", "Doubtful"]) | (d.roster == "INA") | ~d.in_stats)
    d["zeroed"] = d.our_status.isin(["OUT", "DOUBTFUL"]) | (d.final_projection == 0)
    P(f"== wk{wk}: pre-lock status file {os.path.basename(last)} (stamped {lt}Z, lock {cut}Z); log rows {len(d)}")
    inact = d[d.inactive]
    P(f"  inactive (actual 0 + evidence): {len(inact)}; zeroed by pipeline: {inact.zeroed.sum()}; left live: {(~inact.zeroed).sum()}")
    live = inact[~inact.zeroed].sort_values("final_projection", ascending=False)
    P(f"  left live & proj>8: {(live.final_projection>8).sum()}; proj>5: {(live.final_projection>5).sum()}; "
      f"sum proj of live inactives: {live.final_projection.sum():.1f}")
    P(live[live.final_projection > 3][["player_name", "position", "final_projection", "our_status", "report_status", "roster"]].head(25).to_string(index=False))
    fz = d[d.zeroed & ~d.inactive & (d.actual_fpts > 0)]
    P(f"  false zero (pipeline zeroed but scored): {len(fz)} {fz[['player_name','actual_fpts','our_status']].values.tolist()[:10]}")
    q = d[d.our_status == "QUESTIONABLE"]
    P(f"  our QUESTIONABLE at lock: {len(q)}; ended inactive {q.inactive.sum()}")
    d["week"] = wk; allrows.append(d)
pd.concat(allrows).to_csv(os.path.join(H, "audit_2026_rows.csv"), index=False)
out.close()
