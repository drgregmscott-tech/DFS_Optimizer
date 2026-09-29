"""Task: re-run the lineup-study ownership headline test with OUR modeled PRE-LOCK ownership instead of realized ownership.

Chain (reuses the ownership-refit replay machinery, pointed at the lineup-study games instead of the 49 FC-history games):
  --pools    per game: DK showdown salary pool in live ingest schema from the lineup-study player table (same id mapping
             and AvgPointsPerGame proxy as build_pools.py) -> derived/showdown/ls_replay/salaries_sd/, ls_id_map.parquet
  --proj     run_sd_proj.run_slate (production statline engine, showdown path, QB-only depth chart, inactives zeroed)
             -> ls_replay/ourproj_qb/proj_<slate>.csv
  --own      production ownership_model_showdown: build_features (noisy ILP) + predict (CURRENT artifact)
             -> ls_replay/modeled_own.parquet (per slate x lineup-study pid: modeled CPT%, FLEX%)
  --test     headline test (same method as lineup_study_headline.py / lineup_study_analysis.own_slope) with
             own_sum = modeled CPT% + sum modeled FLEX%, plus realized and FC-pre-lock (proj_own) versions on the SAME
             contests -> derived/showdown/ls_modown_headline.csv, ls_modown_slope.csv, ls_modown_out.txt (aggregate only)
Data root: env DFS_ROOT, else the main checkout. All outputs are FC-derived and gitignored.
"""
import argparse, json, os, re, sys, warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
R = Path(os.environ.get("DFS_ROOT", r"C:\Users\gmsco\Desktop\DFS_Optimizer"))
SH = R / "analysis/showdown_history"
sys.path.insert(0, str(SH)); sys.path.insert(0, str(R / "scripts"))
SD = R / "data/fc_history/derived/showdown"
LR = SD / "ls_replay"; SAL = LR / "salaries_sd"
LS = R / "data/fc_history/lineup_study"
FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}
TAG = "qb"


def nk(s): return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))


def slate_name(season, week, teams): return f"LS{season}w{week:02d}_" + "_".join(teams)


def games_table():
    P = pd.read_parquet(LS / "_sd_players.parquet")
    P["tm"] = P.team.map(lambda t: FIX.get(t, t))
    g = P.groupby("contest").agg(season=("season", "first"), week=("week", "first"), ctype=("ctype", "first"),
                                 teams=("tm", lambda s: tuple(sorted(set(s.dropna())))))
    g["slate"] = [slate_name(r.season, r.week, r.teams) for r in g.itertuples()]
    return P, g


# ---------------------------------------------------------------- pools
def pools():
    SAL.mkdir(parents=True, exist_ok=True)
    P, G = games_table()
    M = pd.read_csv(R / "data/fc_history/derived/fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
    M = M[M.player_id.notna() & ~M.player_id.astype(str).str.startswith("DST")]
    M["k"] = M.player.map(nk); M["team"] = M.team.map(lambda t: FIX.get(t, t))
    mm = M.groupby(["season", "k", "team"]).player_id.agg(lambda s: s.mode().iloc[0])
    WS, RO = {}, {}
    maps, plist = [], []
    for slate, cs in G.reset_index().groupby("slate"):
        yr, wk = int(cs.season.iat[0]), int(cs.week.iat[0])
        if yr not in WS:
            WS[yr] = pd.read_parquet(R / f"data/weekly_stats_{yr}.parquet")
            rp = R / f"data/weekly_rosters_{yr}.parquet"
            RO[yr] = pd.read_parquet(rp) if rp.exists() else None
        ws = WS[yr].assign(k=WS[yr].player_display_name.map(nk))
        wsm = ws.groupby(["k", "team"]).player_id.first()
        wsk = ws.groupby("k").player_id.agg(lambda x: x.iloc[0] if x.nunique() == 1 else None)
        ro = None
        if RO[yr] is not None:
            ro = RO[yr].assign(k=RO[yr].full_name.map(nk)).dropna(subset=["gsis_id"]).groupby(["k", "team"]).gsis_id.first()
        # union of players over the contests on this game (SE and big usually share the game); first non-null salary
        g = P[P.contest.isin(cs.contest)].sort_values("sal_known", ascending=False).drop_duplicates("pid")
        g = g[g.pos.notna() & g.tm.notna() & g.sal.notna()].reset_index(drop=True)
        g["k"] = g.name.map(nk)
        ids, tiers = [], []
        for i, r in g.iterrows():
            if r.pos == "DST":
                ids.append(f"DST_{r.tm}"); tiers.append("dst"); continue
            for tier, fn in (("fc_master", lambda: mm.get((yr, r.k, r.tm))), ("wstats_team", lambda: wsm.get((r.k, r.tm))),
                             ("rosters", lambda: ro.get((r.k, r.tm)) if ro is not None else None),
                             ("wstats_name", lambda: wsk.get(r.k))):
                v = fn()
                if isinstance(v, str) and v:
                    ids.append(v); tiers.append(tier); break
            else:
                ids.append(f"UNM_{slate}_{i}"); tiers.append("unmapped")
        g["player_id"] = ids; g["tier"] = tiers
        dup = g.player_id.duplicated(keep=False) & ~g.player_id.str.startswith("UNM")
        for pid, gg in g[dup].groupby("player_id"):
            for j in gg.sort_values("sal", ascending=False).index[1:]:
                g.loc[j, "player_id"] = f"UNM_{slate}_{j}"; g.loc[j, "tier"] = "unmapped_dup"
        prior = ws[ws.week < wk].copy()
        prior["pts"] = np.where(prior.position == "K", 3 * prior.fg_made.fillna(0) + prior.pat_made.fillna(0), prior.fantasy_points_ppr)
        g["avg"] = g.player_id.map(prior.groupby("player_id").pts.mean()).fillna(0.0).round(2)
        rows = []
        for role, mult, off in (("CPT", 1.5, 0), ("FLEX", 1.0, 5000)):
            sal = (g.sal * mult).round().astype(int)
            rows.append(pd.DataFrame({
                "Position": g.pos, "Name": g.name, "ID": [str(800000 + off + i) for i in range(len(g))], "Roster Position": role,
                "Salary": sal, "TeamAbbrev": g.tm, "AvgPointsPerGame": g.avg, "roster_role": role, "name": g.name, "site": "dk",
                "salary": sal, "normalized_name": g.k, "normalized_team": g.tm, "position_upper": g.pos,
                "slate_format": "showdown", "player_id": g.player_id}))
        pd.concat(rows, ignore_index=True).to_csv(SAL / f"salaries_dk_sd_{slate}.csv", index=False)
        g["slate"] = slate
        maps.append(g[["slate", "pid", "name", "tm", "pos", "sal", "player_id", "tier"]])
        plist.append(pd.DataFrame({"slate": slate, "Player": g.name, "Team": g.tm, "act": g.act}))
    A = pd.concat(maps, ignore_index=True); A.to_parquet(LR / "ls_id_map.parquet")
    pd.concat(plist, ignore_index=True).to_parquet(LR / "players.parquet")   # run_sd_proj.inactives (non-2024/25 branch) reads this
    W = G.drop_duplicates("slate")[["slate", "season", "week"]]
    W.to_csv(LR / "slate_weeks.csv", index=False)
    print(A.tier.value_counts().to_string()); print("slates", A.slate.nunique(), "unmapped rows", A.tier.str.startswith("unm").sum())


# ---------------------------------------------------------------- projections
def _run(job):
    import run_sd_proj as rsp
    rsp.SD = LR; rsp.SAL = SAL
    return rsp.run_slate(job)


def proj(workers):
    W = pd.read_csv(LR / "slate_weeks.csv")
    jobs = [(r.slate, int(r.season), int(r.week), TAG, "qb", True, False) for r in W.itertuples()]
    with ProcessPoolExecutor(workers) as ex:
        for s, st, dt in ex.map(_run, jobs):
            print(f"{s}: {st} ({dt}s)", flush=True)


# ---------------------------------------------------------------- modeled ownership
def _own(path):
    import ownership_model_showdown as oms
    art = json.loads(oms.ARTIFACT.read_text(encoding="utf-8"))
    pool = pd.read_csv(path, dtype={"player_id": str})
    f = oms.build_features(pool)
    pool["pred"] = oms.predict(f, art).values
    return pool[["slate", "player_id", "roster_role", "position", "final_projection", "pred"]]


def own(workers):
    import glob
    files = sorted(glob.glob(str(LR / f"ourproj_{TAG}" / "proj_*.csv")))
    with ProcessPoolExecutor(workers) as ex:
        d = pd.concat(list(ex.map(_own, files)), ignore_index=True)
    w = d.pivot_table(index=["slate", "player_id"], columns="roster_role", values="pred", aggfunc="first").reset_index()
    pj = d[d.roster_role == "FLEX"][["slate", "player_id", "final_projection"]].rename(columns={"final_projection": "our_proj"})
    w = w.merge(pj, on=["slate", "player_id"], how="left")
    M = pd.read_parquet(LR / "ls_id_map.parquet")
    o = M.merge(w, on=["slate", "player_id"], how="left").rename(columns={"CPT": "mod_cpt", "FLEX": "mod_flex"})
    o.to_parquet(LR / "modeled_own.parquet")
    print("slates with projections", d.slate.nunique(), "rows", len(o), "missing pred", o.mod_cpt.isna().sum())


# ---------------------------------------------------------------- test
LINES = []


def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LINES.append(s)


def boot(v, B=2000, rs=np.random.RandomState(7)):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    if len(v) < 3:
        return np.nan, np.nan
    s = v[rs.randint(0, len(v), (B, len(v)))].mean(1)
    return np.percentile(s, 5), np.percentile(s, 95)


def test():
    P, G = games_table()
    O = pd.read_parquet(LR / "modeled_own.parquet")
    good = O.groupby("slate").mod_cpt.apply(lambda s: s.notna().mean() > 0.5)
    good = set(good[good].index)
    G = G[G.slate.isin(good)]
    log("contests with modeled ownership:", len(G), G.groupby(["ctype"]).size().to_dict(),
        "by season", G.groupby(["ctype", "season"]).size().to_dict())
    O = O[O.slate.isin(good)].fillna({"mod_cpt": 0.0, "mod_flex": 0.0})   # players absent from our pool: modeled 0
    E = pd.read_parquet(LS / "_sd_entries_ids.parquet")
    E["contest"] = E["contest"].astype(str)
    E = E[E.contest.isin(G.index)]
    P = P[P.contest.isin(G.index)].copy()
    P["slate"] = P.contest.map(G.slate)
    P = P.merge(O[["slate", "pid", "mod_cpt", "mod_flex", "our_proj"]], on=["slate", "pid"], how="left")
    P[["mod_cpt", "mod_flex"]] = P[["mod_cpt", "mod_flex"]].fillna(0.0)
    P["fc_po"] = pd.to_numeric(P.fc_proj_own, errors="coerce")
    # calibration of modeled ownership vs realized, per contest (player level, aggregate)
    cal = []
    for cid, p in P.groupby("contest"):
        cal.append({"contest": cid, "ctype": p.ctype.iat[0],
                    "corr_cpt": np.corrcoef(p.mod_cpt, p.cpt_own)[0, 1], "corr_flex": np.corrcoef(p.mod_flex, p.flex_own)[0, 1],
                    "corr_fcpo_flex": np.corrcoef(p.fc_po.fillna(0), p.flex_own)[0, 1] if p.fc_po.notna().mean() > .5 else np.nan,
                    "mae_flex": (p.mod_flex - p.flex_own).abs().mean()})
    cal = pd.DataFrame(cal)
    log("player-level corr modeled vs realized (mean over contests):", cal.groupby("ctype")[["corr_cpt", "corr_flex", "corr_fcpo_flex", "mae_flex"]].mean().round(3).to_string())
    rows, slopes = [], []
    for cid, e in E.groupby("contest", observed=True):
        p = P[P.contest == cid].set_index("pid")
        n = len(e); ctype = p.ctype.iat[0]; season = int(p.season.iat[0])
        cap = e.payout_c.quantile(0.999); pc = np.minimum(e.payout_c, cap)
        d = pd.DataFrame({"cashed": (e.payout_c > 0).astype(float).values, "ret": (e.payout_c / e.payout_c.mean()).values,
                          "ret_cap": (pc / pc.mean()).values,
                          "top1": (e["rank"] <= max(1, np.floor(0.01 * n))).astype(float).values, "points": e.points.values})
        cols = [e[f"p{j}"].values for j in range(6)]
        def lsum(cpt_col, flex_col):
            c = p[cpt_col]; f = p[flex_col]
            return c.reindex(cols[0]).values + sum(f.reindex(x).values for x in cols[1:])
        d["own_real"] = lsum("cpt_own", "flex_own")
        d["own_mod"] = lsum("mod_cpt", "mod_flex")
        # FC pre-lock projected own is a FLEX-style number per player; use it for all 6 slots (CPT slot x1)
        d["own_fcpo"] = lsum("fc_po", "fc_po") if p.fc_po.notna().mean() > 0.9 else np.nan
        pr = pd.to_numeric(p.fc_proj, errors="coerce")
        d["proj_sum"] = 1.5 * pr.reindex(cols[0]).values + sum(pr.reindex(x).values for x in cols[1:])
        sal = p.sal
        d["left"] = 50000 - (1.5 * sal.reindex(cols[0]).values + sum(sal.reindex(x).values for x in cols[1:]))
        okp = d.proj_sum.notna() & (d.proj_sum > 0)
        proj_ok = okp.mean() >= 0.95 and d.loc[okp, "proj_sum"].std() >= 5
        d["proj_q"] = np.nan
        if proj_ok:
            d.loc[okp, "proj_q"] = pd.qcut(d.loc[okp, "proj_sum"].rank(method="first"), 5, labels=False).values + 1
        for src in ("own_real", "own_mod", "own_fcpo"):
            if d[src].isna().all():
                continue
            # (a) all entries: quintile of summed ownership within contest
            subsets = [("all", np.ones(n, bool))]
            if proj_ok:
                subsets.append(("quality", ((d.left <= 500) & (d.proj_q >= 4)).values))
            for lab, msk in subsets:
                s = d[msk]
                if len(s) < 500 or (lab == "quality" and s.proj_sum.std() < 3):
                    continue
                q = pd.qcut(s[src].rank(method="first"), 5, labels=False) + 1
                bc, br, bt = s.cashed.mean(), s.ret_cap.mean(), s.top1.mean()
                for lv, t in s.groupby(q):
                    if len(t) < 30:
                        continue
                    rows.append({"src": src, "subset": lab, "contest": cid, "ctype": ctype, "season": season, "level": int(lv),
                                 "n": len(t), "cash_lift": 100 * (t.cashed.mean() - bc),
                                 "ret_rel": t.ret_cap.mean() / br if br > 0 else np.nan,
                                 "ret_raw_rel": t.ret.mean() / s.ret.mean() if s.ret.mean() > 0 else np.nan,
                                 "top1_lift": 100 * (t.top1.mean() - bt)})
            # (b) per-contest OLS, standardized own + FC proj (same as lineup_study_analysis.own_slope)
            if proj_ok and n >= 1000:
                s = d[okp]
                z = lambda v: (v - v.mean()) / v.std()
                X = np.column_stack([np.ones(len(s)), z(s[src]), z(s.proj_sum)])
                if np.isfinite(X).all():
                    r = {"src": src, "contest": cid, "ctype": ctype, "season": season, "n": len(s),
                         "corr_own_proj": np.corrcoef(s[src], s.proj_sum)[0, 1],
                         "corr_with_real": np.corrcoef(s[src], s.own_real)[0, 1]}
                    for y in ("cashed", "ret_cap", "top1", "points"):
                        b = np.linalg.lstsq(X, s[y].values.astype(float), rcond=None)[0]
                        r[f"{y}_own_ctrl"] = b[1]
                    slopes.append(r)
        print(cid, flush=True)
    Q = pd.DataFrame(rows); S = pd.DataFrame(slopes)
    out = []
    for (src, sub, ct, lv), g in Q.groupby(["src", "subset", "ctype", "level"]):
        r = {"src": src, "subset": sub, "ctype": ct, "level": lv, "contests": len(g), "entries": int(g.n.sum())}
        for m in ("cash_lift", "ret_rel", "ret_raw_rel", "top1_lift"):
            r[m] = g[m].mean(); r[m + "_lo"], r[m + "_hi"] = boot(g[m])
        for s_ in (2022, 2023, 2024, 2025):
            r[f"ret_rel_{s_}"] = g.loc[g.season == s_, "ret_rel"].mean()
        out.append(r)
    T = pd.DataFrame(out); T.to_csv(SD / "ls_modown_headline.csv", index=False)
    pd.set_option("display.width", 250)
    log("\n=== quintile of summed ownership (1 = least owned) ===")
    log(T[["src", "subset", "ctype", "level", "contests", "cash_lift", "cash_lift_lo", "cash_lift_hi", "ret_rel", "ret_rel_lo", "ret_rel_hi",
           "ret_raw_rel", "ret_raw_rel_lo", "ret_raw_rel_hi", "ret_rel_2022", "ret_rel_2023", "ret_rel_2024", "ret_rel_2025"]].round(3).to_string(index=False))
    # Q5-Q1 gap per contest
    gp = Q.pivot_table(index=["src", "subset", "ctype", "contest", "season"], columns="level", values="ret_rel").reset_index()
    gp["gap"] = gp[5] - gp[1]
    log("\n=== Q5 - Q1 capped-return gap, mean [90% CI], contests positive, by-season means ===")
    gaps = []
    for (src, sub, ct), g in gp.groupby(["src", "subset", "ctype"]):
        v = g.gap.dropna(); lo, hi = boot(v)
        bys = g.groupby("season").gap.mean()
        gaps.append({"src": src, "subset": sub, "ctype": ct, "contests": len(v), "gap": v.mean(), "lo": lo, "hi": hi,
                     "pos": int((v > 0).sum()), **{f"gap_{k}": x for k, x in bys.items()}})
        log(f"{src:9s} {sub:8s} {ct:3s} n={len(v):3d} gap {v.mean():+.3f} [{lo:+.3f},{hi:+.3f}] pos {int((v>0).sum())}/{len(v)}  " +
            " ".join(f"{k}:{x:+.2f}" for k, x in bys.items()))
    pd.DataFrame(gaps).to_csv(SD / "ls_modown_gap.csv", index=False)
    S.to_csv(SD / "ls_modown_slope_by_contest.csv", index=False)
    log("\n=== projection-controlled OLS slope per SD of summed ownership ===")
    for (src, ct), g in S.groupby(["src", "ctype"]):
        for col in ("ret_cap_own_ctrl", "cashed_own_ctrl", "top1_own_ctrl", "points_own_ctrl"):
            lo, hi = boot(g[col]); by = g.groupby("season")[col].mean()
            log(f"{src:9s} {ct:3s} {col:17s} {g[col].mean():+.4f} [{lo:+.4f},{hi:+.4f}] pos {int((g[col]>0).sum())}/{len(g)}  " +
                " ".join(f"{k}:{x:+.3f}" for k, x in by.items()))
        log(f"{src:9s} {ct:3s} lineup corr(own, FC proj) {g.corr_own_proj.mean():.2f}  corr(own, realized own) {g.corr_with_real.mean():.2f}")
    with open(SD / "ls_modown_out.txt", "w") as fh:
        fh.write("\n".join(LINES))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for s in ("pools", "proj", "own", "test"):
        ap.add_argument("--" + s, action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    LR.mkdir(parents=True, exist_ok=True)
    if a.pools: pools()
    if a.proj: proj(a.workers)
    if a.own: own(a.workers)
    if a.test: test()
