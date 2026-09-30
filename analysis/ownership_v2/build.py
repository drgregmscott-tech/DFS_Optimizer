"""Build ownership-v2 frames.

history (FC-derived -> git-ignored): data/fc_history/derived/ownership_v2/hist.parquet
  86 FC single-entry DK main slates 2021-25. Targets: fc_own_proj (FC pre-lock 'Own', 2021-23), own (realized SE).
  Pool = players with our regenerated projection > 0 and not inactive (same pool as fc_own_features_ourproj,
  i.e. the 'played' proxy for pre-lock OUT news -- slightly optimistic for late scratches).
2026 (ours, no FC): data/fc_history/derived/ownership_v2/y2026.parquet from analysis/ownership_refit_wk3/frame.parquet
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import R, Ctx, build_features, load_stats  # noqa: E402

DER = R / "data/fc_history/derived"
OUT = DER / "ownership_v2"; OUT.mkdir(exist_ok=True)


def opp_code(s):
    return s.astype(str).str.replace(r"^(@|vs)\s*", "", regex=True).str.strip()


def hist():
    M = pd.read_parquet(DER / "model_vs_fc/frame.parquet")
    M = M[M.season <= 2025].copy()
    F = pd.read_parquet(DER / "fc_own_features_ourproj.parquet")
    F = F[F.season <= 2025][["season", "week", "player_id", "l_exp", "l_est", "final_projection"]]
    M = M.merge(F, on=["season", "week", "player_id"], how="left")
    d = pd.DataFrame({
        "slate_id": "h" + M.season.astype(str) + "_" + M.week.astype(str).str.zfill(2),
        "season": M.season, "week": M.week, "player_id": M.player_id, "player": M.player,
        "pos": M.pos, "team": M.team, "opp": opp_code(M.opp), "salary": M.salary.astype(float),
        "proj": M.final_projection.fillna(0.0), "sigma": M.sigma, "team_total": M.implied_total,
        "game_total": M.over_under, "in_pool": M.final_projection.fillna(0) > 0,
        "l_exp": M.l_exp, "l_est": M.l_est,
        "own": M.own, "fc_own": M.fc_own_proj, "fc_proj": M.fc, "pdepth": M.pdepth, "act": M.act,
        "ours_own_model": M.ours_own_model})
    # 2026-09-30 fix (analysis/wrte_chalk_root_cause): the frame covers every game of the week (~15), but the labels
    # come from the main-slate contest (~11 games). ~25% of the old pool were off-slate teams (own exactly 0, FC Own 0),
    # which taught v2 to spread mass (chalk under-sized). Pool = teams on the contest slate. The contest game list is
    # public pre-lock (DK salary file); history has no saved game list, so a team is on the slate iff its skill players
    # drew any realized ownership (agrees with the nflverse Sunday-main schedule on 1904/1943 team-weeks; the exceptions
    # are Saturday/holiday slates the schedule rule gets wrong).
    sk = d[d.pos != "DST"].groupby(["slate_id", "team"]).own.sum()
    on = set(sk[sk > 0].index)
    d["in_pool"] = d.in_pool & pd.Series([(s, t) in on for s, t in zip(d.slate_id, d.team)], index=d.index)
    m = pd.read_csv(DER / "fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
    m = m[(m.contest == "single_entry") & (m.slate_kind == "classic") & m.player_id.notna()]
    prior_salary = m[["season", "week", "player_id", "salary"]].drop_duplicates(["season", "week", "player_id"])
    lag_own = m[["season", "week", "player_id", "own_pct"]].rename(columns={"own_pct": "own"}) \
        .drop_duplicates(["season", "week", "player_id"])
    return d, prior_salary, lag_own


def y2026():
    f = pd.read_parquet(R / "analysis/ownership_refit_wk3/frame.parquet")
    d = pd.DataFrame({
        "slate_id": f.slate_id, "season": 2026, "week": f.week.astype(int), "player_id": f.player_id,
        "player": f.player_name, "pos": f.position, "team": f.team, "opp": f.opponent,
        "salary": f.salary.astype(float), "proj": f.final_projection, "sigma": f.sigma,
        "team_total": f.implied_total, "game_total": f.over_under, "in_pool": f.final_projection > 0,
        "l_exp": f.l_exp, "l_est": f.l_est, "own": f.own, "est_live": f.est_live,
        "dk_avg_ppg": f.dk_avg_ppg, "ffc_own_pct": f.ffc_own_pct, "pub_val": f.pub_val,
        "l_ffc": f.l_ffc, "ffc_listed": f.ffc_listed, "top1sal": f.top1sal, "cv_live": f.cv,
        "dart": f.dart, "lo_proj": f.lo_proj, "sal": f.sal, "position_group": f.position_group})
    prior_salary = d[["season", "week", "player_id", "salary"]].drop_duplicates(["season", "week", "player_id"])
    lg = pd.read_csv(R / "data/ownership_actual_log.csv", dtype={"player_id": str})
    lg = lg[(lg.slate_format == "classic") & lg.slate_id.str.contains("_main_")]
    lg["week"] = lg.slate_id.str.extract(r"wk(\d+)")[0].astype(int)
    lag_own = lg.groupby(["season", "week", "player_id"]).actual_ownership_pct.mean().rename("own").reset_index()
    live_log = lg.groupby(["slate_id", "player_id"]).estimated_ownership_pct_at_lock.first()
    return d, prior_salary, lag_own, live_log


def main():
    stats = load_stats()
    h, ps, lo = hist()
    H = build_features(h, Ctx(stats, ps, lo))
    H.to_parquet(OUT / "hist.parquet")
    print("hist", H.shape, H.slate_id.nunique(), "pool", H.in_pool.sum())
    d, ps2, lo2, live_log = y2026()
    Y = build_features(d, Ctx(stats, ps2, lo2))
    lg = pd.read_csv(R / "data/ownership_actual_log.csv", dtype={"player_id": str})
    ll = lg.groupby(["slate_id", "player_id"]).estimated_ownership_pct_at_lock.first()
    Y["live_log"] = [ll.get((a, b), np.nan) for a, b in zip(Y.slate_id, Y.player_id)]
    Y.to_parquet(OUT / "y2026.parquet")
    print("2026", Y.shape, Y.slate_id.nunique())
    # sanity: reconstructed DK avg vs DK's displayed avg (2026)
    ok = Y.dk_avg_ppg.notna() & (Y.pos != "DST")
    print("corr reconstructed dkavg vs DK lobby AvgPPG:", np.corrcoef(Y.dkavg[ok], Y.dk_avg_ppg[ok])[0, 1],
          "pubv vs pub_val:", np.corrcoef(Y.pubv[ok], Y.pub_val[ok])[0, 1])
    print(H[["pressure", "vacated", "my_share", "sal_chg", "l_lag_own", "prev_ppg", "dkavg", "last_dk"]].describe().T)


if __name__ == "__main__":
    main()
