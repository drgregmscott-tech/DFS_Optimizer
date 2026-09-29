"""WK3 postmortem parking-lot item 2: re-run the classic lineup-study ownership headline (§4) and the player-level
"ownership predicts points beyond FC proj + salary" test (§6) with OUR PRE-LOCK MODELED ownership in place of
realized ownership, on the SAME contests. Sibling of analysis/showdown_history/lineup_study_modeled_own.py.

Modeled-ownership sources (FC-history main slates only, one per (season, week); gitignored, FC-derived):
  v2  data/fc_history/derived/ourproj/proj_<yr>_wk<n>.csv  estimated_ownership_pct: production projection replay
      (run_ourproj.py, leak-patched statline engine) + production layered ownership model (current artifact, written
      2026-09-26 after the 2026-09-23 refit), pub_val = 0 (no DK lobby average in history). NO inactive handling:
      players ruled OUT before lock keep a projection/ownership -> pessimistic vs live.
  v1  data/fc_history/derived/fc_own_features_ourproj.parquet features, re-scored here with the production artifact
      (om.predict, pub_val = 0). Its pool zeroes every skill player with no nflverse weekly_stats row that week
      ("played" proxy) -> uses POST-GAME info (also zeroes active players who recorded no stats) -> optimistic/leaky.
  Truth for a live pre-lock model sits between v1 and v2 on inactives; both are reported, the verdict must hold on both.
  fcpo FC's own pre-lock proj_own from the lineup-study player dict, where populated (checked, reported).
  bXX  blends w*realized + (1-w)*v2 at the player level ("how good must a pre-lock source be" ceiling curve).

Matching: lineup-study player (name, team) -> gsis via the v2 pool of that (season, week) (DST by team). Contest
coverage = share of realized ownership mass (sum over rostered players of realized %) that maps. Unmapped players get a
floor (default 0.5%; sensitivity 0 / 2%). Entries are rebuilt from the raw JSON in the same order as
lineup_study_build.py and aligned to its entries cache (points/rank verified).

Method = lineup_study_analysis.py headline/slopes (within-contest quintiles among quality lineups, equal weight per
contest, 90% contest bootstrap CIs, season signs).

Env: DFS_ROOT (repo root with scripts/ and data/), FC_LS_DIR (raw lineup study), CL_DER (derived/classic cache dir,
default <DFS_ROOT>/data/fc_history/derived/classic), NPROC.
Outputs (aggregate only): analysis/classic_history/out/cl_modown_*.csv, cl_modown_out.txt
"""
import glob, gzip, json, os, re, sys, warnings
from multiprocessing import Pool
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.environ.get("DFS_ROOT", os.path.dirname(os.path.dirname(HERE)))
SRC = os.environ.get("FC_LS_DIR", os.path.join(R, "data", "fc_history", "lineup_study"))
DER = os.environ.get("CL_DER", os.path.join(R, "data", "fc_history", "derived", "classic"))
FCD = os.path.join(R, "data", "fc_history", "derived")
OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(R, "scripts"))
import lineup_study_analysis as A  # noqa: E402

FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}
FLOOR = float(os.environ.get("FLOOR", "0.5"))
BLENDS = (0.05, 0.1, 0.15, 0.25, 0.5)
SEASONS = (2022, 2023, 2024, 2025)
LINES = []


def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LINES.append(s)


def nk(s):
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))


def tfix(t):
    return FIX.get(t, t)


# ------------------------------------------------------------------ modeled pools
def build_pools():
    import ownership_model as om
    from ownership_heuristic import compute_position_slot_budgets
    art = om.load_artifact("dk"); bud = compute_position_slot_budgets("dk")
    F = pd.read_parquet(os.path.join(FCD, "fc_own_features_ourproj.parquet"))
    v1 = []
    for sid, g in F.groupby("slate_id"):
        g = g.copy(); g["pub_val"] = 0.0
        g["v1"] = om.predict(g, g[art["features"]], art, bud).values
        v1.append(g[["season", "week", "player_id", "v1", "own"]])
    V1 = pd.concat(v1).rename(columns={"own": "fc_main_own"})
    pools = {}
    for f in glob.glob(os.path.join(FCD, "ourproj", "proj_*_wk*.csv")):
        m = re.search(r"proj_(\d{4})_wk(\d+)\.csv", f); s, w = int(m.group(1)), int(m.group(2))
        p = pd.read_csv(f, dtype={"player_id": str})
        p = p.drop_duplicates("player_id")
        p["team"] = p.team.map(tfix); p["k"] = p.player_name.map(nk)
        p = p.merge(V1[(V1.season == s) & (V1.week == w)][["player_id", "v1", "fc_main_own"]], on="player_id", how="left")
        p["v1"] = p["v1"].fillna(0.0)       # in the pool but dropped by the played / zero-projection filter -> model 0
        pools[(s, w)] = p[["player_id", "position", "team", "k", "final_projection", "estimated_ownership_pct",
                           "estimated_ownership_pct_heuristic", "v1", "fc_main_own"]].rename(columns={"estimated_ownership_pct": "v2",
                                                                                                    "estimated_ownership_pct_heuristic": "heur"})
    return pools


def load_raw(f):
    d = json.load(gzip.open(f))
    return d.get("data", d) if "rows" not in d else d


# ------------------------------------------------------------------ per contest
def z(v):
    v = np.asarray(v, float); s = v.std()
    return (v - v.mean()) / s if s > 0 else v * 0


def ols(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def contest(args):
    f, pool, badproj = args
    base = os.path.basename(f)[:-8]
    ep = os.path.join(DER, "entries", base + ".parquet")
    if not os.path.exists(ep) or pool is None:
        return {"file": base, "status": "no_cache_or_pool"}
    d = load_raw(f); P = d["players"]
    R0 = [r for r in d["rows"] if len(r[5]) == 9]
    ids = sorted({str(i) for r in R0 for i in r[5]}); idx = {p: i for i, p in enumerate(ids)}
    M = np.array([[idx[str(i)] for i in r[5]] for r in R0], dtype=np.int32)
    E = pd.read_parquet(ep)
    if len(E) != len(M) or not np.allclose(E["points"].values, np.array([float(r[3]) for r in R0]), atol=0.02):
        return {"file": base, "status": "misaligned"}
    del d, R0
    n = len(M); npl = len(ids)
    cnt = np.bincount(M.ravel(), minlength=npl); rost = cnt / n * 100
    # map players to the main-slate pool
    pk = pool.set_index(["k", "team"]); pk = pk[~pk.index.duplicated()]
    kuniq = pool.drop_duplicates("k", keep=False).set_index("k")
    dst = pool[pool.position == "DST"].drop_duplicates("team").set_index("team")
    cols = ["v1", "v2", "heur", "final_projection", "fc_main_own"]
    val = np.full((npl, len(cols)), np.nan); gs = np.empty(npl, object)
    pos = np.empty(npl, object); team = np.empty(npl, object)
    fcpo = np.full(npl, np.nan); fp = np.full(npl, np.nan); proj = np.full(npl, np.nan); sal = np.full(npl, np.nan)
    for p, i in idx.items():
        q = P.get(p, {})
        pos[i] = q.get("SitePos"); team[i] = tfix(q.get("Team"))
        for k_, arr in (("proj_own", fcpo), ("fantasy_points", fp), ("FC_proj", proj), ("Salary", sal)):
            try:
                if q.get(k_) not in (None, ""):
                    arr[i] = float(q[k_])
            except (TypeError, ValueError):
                pass
        row = None
        if pos[i] == "DST":
            row = dst.loc[team[i]] if team[i] in dst.index else None
        elif q.get("PlayerName"):
            k = nk(q["PlayerName"])
            if (k, team[i]) in pk.index:
                row = pk.loc[(k, team[i])]
            elif k in kuniq.index:
                row = kuniq.loc[k]
        if row is not None:
            val[i] = row[cols].values.astype(float); gs[i] = row["player_id"]
    mapped = ~np.isnan(val[:, 1])
    cov = rost[mapped].sum() / rost.sum()
    fcpo_cov = rost[~np.isnan(fcpo)].sum() / rost.sum()
    meta = {"contest": E["contest"].iat[0], "season": int(E["season"].iat[0]), "ctype": E["ctype"].iat[0],
            "type": E["type"].iat[0], "slate": E["slate"].iat[0], "file": base}
    info = {**meta, "status": "ok", "n": n, "cov_mass": cov, "cov_players": mapped.mean(),
            "cov_players_ge1": mapped[rost >= 1].mean(), "fcpo_cov_mass": fcpo_cov, "unmapped_top_own": float(np.max(rost[~mapped], initial=0))}
    # player-level table (returned; not written)
    pl = pd.DataFrame({"pid": ids, "gsis": gs, "pos": pos, "team": team, "own": rost, "v1": val[:, 0], "v2": val[:, 1],
                       "heur": val[:, 2], "ourproj": val[:, 3], "fc_main_own": val[:, 4], "fcpo": fcpo, "fp": fp,
                       "proj": proj, "sal": sal})
    for k_, v in meta.items():
        pl[k_] = v
    pl["n_entries"] = n
    # modeled QB rank (within the main pool, v2 and v1)
    qbpool = pool[pool.position == "QB"]
    top_qb = {s: qbpool.sort_values(s, ascending=False).player_id.iat[0] for s in ("v1", "v2")}
    real_qb1 = ids[max((i for i in range(npl) if pos[i] == "QB"), key=lambda i: rost[i])]
    info["qb1_real_gsis"] = gs[idx[real_qb1]]
    for s in ("v1", "v2"):
        info[f"qb1_agree_{s}"] = float(gs[idx[real_qb1]] == top_qb[s])
    if cov < 0.9:
        return {**info, "pl": pl}
    if os.environ.get("OURPROJ_CTRL"):
        return {**info, "ctrl": ourproj_ctrl(E, M, rost, val, mapped, meta, base in badproj)}
    # lineup own sums per source
    srcs = {"real": rost}
    for fl, tag in ((FLOOR, ""), (0.0, "_f0"), (2.0, "_f2")):
        for j, s in ((0, "v1"), (1, "v2")):
            if tag and s == "v1":
                continue
            srcs[s + tag] = np.where(mapped, val[:, j], fl)
    srcs["heur"] = np.where(mapped, val[:, 2], FLOOR)
    for w in BLENDS:
        srcs[f"b{int(w*100)}"] = w * rost + (1 - w) * srcs["v2"]
    if fcpo_cov >= 0.95:
        srcs["fcpo"] = np.where(np.isnan(fcpo), FLOOR, fcpo)
    E = E.copy()
    if base in badproj:
        E["proj_sum"] = np.nan
    E["own_real"] = E["own_sum"].values
    qb_idx = M[:, 0]
    heads, slps = [], []
    for s, v in srcs.items():
        E["own_sum"] = v[M].sum(1).astype(np.float32)
        d_ = A.prep(E)
        if s == "real":
            base_d = d_
        m = {**meta, "src": s}
        heads += A.headline(d_, m, "all", d_["cashed"] >= 0)
        heads += A.headline(d_, m, "quality", (d_["left"] <= 500) & (d_["proj_q"] >= 4))
        slps += A.slopes(d_, m)
        # lineup-level corr with realized / FC projection
        for lab, mk in (("all", np.ones(n, bool)), ("quality", ((d_["left"] <= 500) & (d_["proj_q"] >= 4)).values)):
            if mk.sum() < 500:
                continue
            e = d_[mk]
            info[f"lcorr_real_{s}_{lab}"] = np.corrcoef(e["own_sum"], e["own_real"])[0, 1]
            if e["proj_sum"].notna().all() and e["proj_sum"].std() >= 3:
                info[f"lcorr_proj_{s}_{lab}"] = np.corrcoef(e["own_sum"], e["proj_sum"])[0, 1]
    # joint OLS: y ~ realized + modeled + FC proj (per SD), all and quality
    d_ = base_d
    for lab, mk in (("all", np.ones(n, bool)), ("quality", ((d_["left"] <= 500) & (d_["proj_q"] >= 4)).values)):
        e = d_[mk]
        if len(e) < 1000 or e["proj_sum"].isna().any() or e["proj_sum"].std() < 3:
            continue
        for s in ("v1", "v2"):
            ms = srcs[s][M].sum(1)[mk]
            X = np.column_stack([np.ones(len(e)), z(e["own_real"]), z(ms), z(e["proj_sum"])])
            X2 = np.column_stack([np.ones(len(e)), z(ms), z(e["proj_sum"])])
            X3 = np.column_stack([np.ones(len(e)), z(e["own_real"] - np.polyval(np.polyfit(ms, e["own_real"], 1), ms)), z(ms), z(e["proj_sum"])])
            r = {**meta, "subset": lab, "src": s, "n": len(e)}
            for y in ("cashed", "ret_cap", "points"):
                yy = np.nan_to_num(e[y].values.astype(float))
                b = ols(X, yy); r[f"{y}_real"] = b[1]; r[f"{y}_mod"] = b[2]; r[f"{y}_proj"] = b[3]
                r[f"{y}_mod_only"] = ols(X2, yy)[1]
                r[f"{y}_realresid"] = ols(X3, yy)[1]
            slps.append({**r, "joint": True})
    # QB: lineups whose QB is the modeled #1 QB vs realized #1 QB
    qrows = []
    d_ = base_d
    for lab, mk in (("all", np.ones(n, bool)), ("quality", ((d_["left"] <= 500) & (d_["proj_q"] >= 4)).values)):
        e = d_[mk]
        if len(e) < 500:
            continue
        qg = gs[qb_idx[mk]]
        bc, br = e["cashed"].mean(), e["ret_cap"].mean()
        for lvl, sel in (("real_qb1", (e["qb_own_rank"] == 1).values), ("v2_qb1", qg == top_qb["v2"]), ("v1_qb1", qg == top_qb["v1"]),
                         ("v2_qb1_not_real1", (qg == top_qb["v2"]) & (e["qb_own_rank"] != 1).values)):
            if sel.sum() < 30:
                continue
            qrows.append({**meta, "subset": lab, "level": lvl, "n": int(sel.sum()), "share": sel.mean(),
                          "cash_lift": 100 * (e["cashed"].values[sel].mean() - bc), "ret_rel": e["ret_cap"].values[sel].mean() / br})
    return {**info, "pl": pl, "heads": heads, "slopes": slps, "qb": qrows}


def ourproj_ctrl(E, M, rost, val, mapped, meta, bad):
    """Is the modeled-ownership effect just OUR projection's information? Lineup sum of our replayed projection
    (the optimizer's own objective) as an extra control. Unmapped players: our projection 0 (they are not in our pool)."""
    if bad:
        return []
    E = E.copy()
    op = np.where(mapped, np.nan_to_num(val[:, 3]), 0.0)[M].sum(1)
    E["own_real"] = E["own_sum"].values
    d_ = A.prep(E)
    out = []
    for lab, mk in (("all", np.ones(len(E), bool)), ("quality", ((d_["left"] <= 500) & (d_["proj_q"] >= 4)).values)):
        e = d_[mk]
        if len(e) < 1000 or e["proj_sum"].isna().any() or e["proj_sum"].std() < 3:
            continue
        o = op[mk]; ms = np.where(mapped, val[:, 1], FLOOR)[M].sum(1)[mk]
        r = {**meta, "subset": lab, "n": len(e), "corr_ourproj_fcproj": np.corrcoef(o, e["proj_sum"])[0, 1],
             "corr_mod_ourproj": np.corrcoef(ms, o)[0, 1]}
        for y in ("cashed", "ret_cap", "points"):
            yy = np.nan_to_num(e[y].values.astype(float))
            one = np.ones(len(e))
            r[f"{y}_ourproj_fcctrl"] = ols(np.column_stack([one, z(o), z(e["proj_sum"])]), yy)[1]
            b = ols(np.column_stack([one, z(ms), z(e["proj_sum"]), z(o)]), yy)
            r[f"{y}_mod_bothctrl"] = b[1]
            r[f"{y}_real_bothctrl"] = ols(np.column_stack([one, z(e["own_real"]), z(e["proj_sum"]), z(o)]), yy)[1]
        out.append(r)
    return out


def run_ourproj_ctrl(jobs):
    with Pool(int(os.environ.get("NPROC", "10")), maxtasksperchild=8) as pp:
        res = list(pp.imap_unordered(contest, jobs))
    C = pd.DataFrame([x for r in res for x in r.get("ctrl", [])])
    rows = []
    for (sub, ct), g in C.groupby(["subset", "ctype"]):
        for c in [c for c in C.columns if c.startswith(("cashed_", "ret_cap_", "points_", "corr_"))]:
            lo, hi = boot(g[c])
            rows.append({"subset": sub, "ctype": ct, "coef": c, "mean": g[c].mean(), "lo": lo, "hi": hi, "contests": len(g),
                         "seasons_pos": seasons_pos(g, c)})
    T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "cl_modown_ourproj_ctrl.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print(T.round(3).to_string(index=False))


# ------------------------------------------------------------------ summaries
def boot(v):
    return A.boot(v)


def seasons_pos(g, col, thr=0.0):
    by = g.groupby("season")[col].mean().reindex(SEASONS)
    return f"{int((by > thr).sum())}/{int(by.notna().sum())}"


def main():
    Q = pd.read_csv(os.path.join(OUT, "cl_qa.csv"))
    drop = set(Q.loc[(Q["rows_vs_entrants"] < 0.99) | (Q["rows_used"] < 1000), "file"].str[:-8])
    badproj = set(Q.loc[(Q["lineups_with_noproj_player"] > 0.3) | (Q["proj_std_lineup"] < 3), "file"].str[:-8])
    files = sorted(f for f in glob.glob(os.path.join(SRC, "*.json.gz")) if "_SHOWDOWN_" not in f and "_LIST" not in f
                   and os.path.basename(f)[:-8] not in drop)
    log(f"analysed contests (after QA exclusions): {len(files)}; entries cache: {DER}")
    pools = build_pools()
    jobs = []
    for f in files:
        s, w = map(int, re.match(r"(\d{4})wk(\d+)", os.path.basename(f)).groups())
        jobs.append((f, pools.get((s, w)), badproj))
    if os.environ.get("OURPROJ_CTRL"):
        return run_ourproj_ctrl(jobs)
    res = []
    with Pool(int(os.environ.get("NPROC", "10")), maxtasksperchild=8) as pp:
        for i, r in enumerate(pp.imap_unordered(contest, jobs)):
            res.append(r)
            if i % 25 == 0:
                print(i, r.get("file"), r.get("status"), round(r.get("cov_mass", np.nan), 3), flush=True)
    INFO = pd.DataFrame([{k: v for k, v in r.items() if k not in ("pl", "heads", "slopes", "qb")} for r in res])
    PL = pd.concat([r["pl"] for r in res if "pl" in r], ignore_index=True)
    H = pd.DataFrame([h for r in res for h in r.get("heads", [])])
    S = pd.DataFrame([h for r in res for h in r.get("slopes", [])])
    QB = pd.DataFrame([h for r in res for h in r.get("qb", [])])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 50)

    # ---------- coverage
    log("\n=== status ===\n" + INFO.status.value_counts().to_string())
    ok = INFO[INFO.status == "ok"].copy()
    ok["cov_bin"] = pd.cut(ok.cov_mass, [0, 0.5, 0.8, 0.9, 0.95, 0.98, 1.001])
    log("\n=== coverage: share of realized ownership mass mapped to the main-slate modeled pool ===")
    log(ok.pivot_table(index="ctype", columns="cov_bin", values="contest", aggfunc="count").to_string())
    used = ok[ok.cov_mass >= 0.9]
    log(f"\nused (cov >= 0.90): {len(used)} contests; by ctype x season:\n" +
        used.pivot_table(index="ctype", columns="season", values="contest", aggfunc="count").to_string())
    log(f"mass coverage among used: median {used.cov_mass.median():.3f}, p10 {used.cov_mass.quantile(.1):.3f}, min {used.cov_mass.min():.3f}; "
        f"players>=1% mapped {used.cov_players_ge1.mean():.3f}; max unmapped player own median {used.unmapped_top_own.median():.2f}")
    log(f"FC proj_own mass coverage: median {ok.fcpo_cov_mass.median():.3f}; contests >= 0.95: {(ok.fcpo_cov_mass >= .95).sum()}")
    ok[["file", "ctype", "season", "cov_mass", "cov_players_ge1", "fcpo_cov_mass", "unmapped_top_own"]].round(4).to_csv(
        os.path.join(OUT, "cl_modown_coverage.csv"), index=False)
    ucont = set(used.contest)

    # ---------- player-level fidelity (per contest, players with realized >= 0.5% or modeled >= 0.5%)
    rows = []
    for c, g in PL[PL.contest.isin(ucont)].groupby("contest"):
        g = g[g.v2.notna()]
        for s in ("v1", "v2", "heur", "fcpo", "fc_main_own"):
            gg = g[g[s].notna() & ((g.own >= 0.5) | (g[s] >= 0.5))]
            if len(gg) < 20:
                continue
            rows.append({"contest": c, "ctype": g.ctype.iat[0], "season": g.season.iat[0], "src": s, "n_pl": len(gg),
                         "corr": gg[s].corr(gg.own), "spearman": gg[s].rank().corr(gg.own.rank()), "mae": (gg[s] - gg.own).abs().mean()})
    PF = pd.DataFrame(rows)
    log("\n=== player-level modeled vs realized (mean over used contests) ===")
    log(PF.groupby("src")[["corr", "spearman", "mae", "n_pl"]].mean().round(3).to_string())
    log(PF.groupby(["src", "season"])["corr"].mean().unstack().round(3).to_string())

    # ---------- headline
    H = H[H.contest.isin(ucont)]
    HS = []
    for (src, sub, feat, ct, lv), g in H.groupby(["src", "subset", "feature", "ctype", "level"]):
        r = {"src": src, "subset": sub, "feature": feat, "ctype": ct, "level": lv, "contests": g.contest.nunique()}
        for m in ("cash_lift", "ret_rel", "ret_raw_rel"):
            r[m] = g[m].mean(); r[m + "_lo"], r[m + "_hi"] = boot(g[m])
        r["ret_rel_seasons"] = seasons_pos(g, "ret_rel", 1); r["cash_seasons"] = seasons_pos(g, "cash_lift")
        HS.append(r)
    HS = pd.DataFrame(HS)
    # Q5-Q1 gap per contest
    G = []
    for (src, sub, ct), g in H[H.feature == "q"].groupby(["src", "subset", "ctype"]):
        p = g.pivot_table(index=["contest", "season"], columns="level", values=["ret_rel", "cash_lift"])
        if ("ret_rel", "5") not in p or ("ret_rel", "1") not in p:
            continue
        gap = (p[("ret_rel", "5")] - p[("ret_rel", "1")]).dropna(); cg = (p[("cash_lift", "5")] - p[("cash_lift", "1")]).dropna()
        lo, hi = boot(gap.values); clo, chi = boot(cg.values)
        by = gap.groupby(level="season").mean().reindex(SEASONS)
        G.append({"src": src, "subset": sub, "ctype": ct, "contests": len(gap), "gap_ret": gap.mean(), "gap_lo": lo, "gap_hi": hi,
                  "contests_pos": int((gap > 0).sum()), "seasons_pos": f"{int((by > 0).sum())}/{int(by.notna().sum())}",
                  "gap_cash": cg.mean(), "gap_cash_lo": clo, "gap_cash_hi": chi})
    G = pd.DataFrame(G)
    HS.to_csv(os.path.join(OUT, "cl_modown_headline.csv"), index=False); G.to_csv(os.path.join(OUT, "cl_modown_gap.csv"), index=False)
    log("\n=== headline Q1/Q5 (quality subset and all), by source ===")
    hc = ["src", "subset", "ctype", "level", "contests", "cash_lift", "cash_lift_lo", "cash_lift_hi", "ret_rel", "ret_rel_lo", "ret_rel_hi",
          "ret_rel_seasons", "ret_raw_rel"]
    log(HS[(HS.feature == "q") & HS.level.isin(["1", "5"])].sort_values(["subset", "ctype", "src", "level"])[hc].round(3).to_string(index=False))
    log("\n=== Q5-Q1 gap (capped return ratio and cash pts) ===")
    log(G.sort_values(["subset", "ctype", "src"]).round(3).to_string(index=False))

    # ---------- slopes
    S = S[S.contest.isin(ucont)]
    SJ = S[S.get("joint", pd.Series(False, index=S.index)).fillna(False).astype(bool)] if "joint" in S else S.iloc[:0]
    SS = S.drop(SJ.index)
    rows = []
    keep = ["cashed_own_raw", "cashed_own_ctrl", "ret_cap_own_ctrl", "points_own_ctrl", "cashed_proj_ctrl", "corr_own_proj"]
    for (src, sub, ct), g in SS.groupby(["src", "subset", "ctype"]):
        for c in keep:
            lo, hi = boot(g[c])
            rows.append({"src": src, "subset": sub, "ctype": ct, "coef": c, "mean": g[c].mean(), "lo": lo, "hi": hi, "contests": len(g),
                         "pos_contests": int((g[c] > 0).sum()), "seasons_pos": seasons_pos(g, c)})
    SL = pd.DataFrame(rows); SL.to_csv(os.path.join(OUT, "cl_modown_slopes.csv"), index=False)
    log("\n=== per-contest OLS per SD of summed ownership (FC projection control) ===")
    log(SL[SL.coef.isin(["cashed_own_ctrl", "ret_cap_own_ctrl", "points_own_ctrl"])].pivot_table(
        index=["subset", "ctype", "src"], columns="coef", values=["mean", "lo", "hi"]).round(3).to_string())
    rows = []
    for (src, sub, ct), g in SJ.groupby(["src", "subset", "ctype"]):
        for c in [x for x in SJ.columns if any(x.startswith(y + "_") for y in ("cashed", "ret_cap", "points"))]:
            lo, hi = boot(g[c])
            rows.append({"src": src, "subset": sub, "ctype": ct, "coef": c, "mean": g[c].mean(), "lo": lo, "hi": hi, "contests": len(g),
                         "seasons_pos": seasons_pos(g, c)})
    JT = pd.DataFrame(rows); JT.to_csv(os.path.join(OUT, "cl_modown_joint.csv"), index=False)
    log("\n=== joint OLS: y ~ realized + modeled + FC proj; mod_only = modeled + proj; realresid = part of realized not explained by modeled ===")
    log(JT.round(3).to_string(index=False))

    # ---------- lineup-level corr
    lc = [c for c in used.columns if c.startswith("lcorr_")]
    LC = used.groupby("ctype")[lc].mean().T
    LC["ALL"] = used[lc].mean()
    LC.to_csv(os.path.join(OUT, "cl_modown_lineup_corr.csv"))
    log("\n=== lineup-level corr (mean over contests) ===\n" + LC.round(3).to_string())

    # ---------- QB
    log("\n=== #1 QB agreement (realized #1 QB in contest == modeled #1 QB in main pool) ===")
    log(used.groupby("ctype")[["qb1_agree_v1", "qb1_agree_v2"]].mean().round(3).to_string())
    log(f"all used: v1 {used.qb1_agree_v1.mean():.3f}  v2 {used.qb1_agree_v2.mean():.3f}; per season v2: " +
        str(used.groupby("season").qb1_agree_v2.mean().round(3).to_dict()))
    QB = QB[QB.contest.isin(ucont)]
    rows = []
    for (sub, ct, lv), g in QB.groupby(["subset", "ctype", "level"]):
        r = {"subset": sub, "ctype": ct, "level": lv, "contests": len(g), "share": g.share.mean()}
        for m in ("cash_lift", "ret_rel"):
            r[m] = g[m].mean(); r[m + "_lo"], r[m + "_hi"] = boot(g[m])
        r["cash_seasons"] = seasons_pos(g, "cash_lift")
        rows.append(r)
    QT = pd.DataFrame(rows); QT.to_csv(os.path.join(OUT, "cl_modown_qb.csv"), index=False)
    log(QT.round(3).to_string(index=False))

    # ---------- player-level §6 with modeled ownership
    Pq = PL[PL.contest.isin(ucont)].copy()
    big = Pq.groupby("slate")["n_entries"].transform("max") == Pq["n_entries"]
    Pq = Pq[big & (Pq.proj > 0) & Pq.fp.notna() & Pq.sal.notna() & Pq.v2.notna()].drop_duplicates(["slate", "pid"])
    rows = []
    for (sl, p), g in Pq.groupby(["slate", "pos"]):
        g = g[(g.own > 0) & (g.v2 > 0)]
        if len(g) < 8:
            continue
        for s in ("own", "v1", "v2", "joint_v2"):
            gg = g[g.v1 > 0] if s == "v1" else g
            if len(gg) < 8:
                continue
            lr = np.log(gg.own.values)
            cols_ = [np.ones(len(gg)), gg.proj.values, gg.sal.values / 1000]
            if s == "joint_v2":
                X = np.column_stack(cols_ + [z(lr), z(np.log(gg.v2.values))])
                b = ols(X, gg.fp.values); coef, coef2 = b[3], b[4]
            else:
                lv = lr if s == "own" else np.log(gg[s].values)
                b = ols(np.column_stack(cols_ + [z(lv)]), gg.fp.values); coef, coef2 = b[3], np.nan
            rows.append({"slate": sl, "season": int(g.season.iat[0]), "pos": p, "src": s, "coef": coef, "coef_mod_in_joint": coef2, "n": len(gg)})
    C = pd.DataFrame(rows)
    out = []
    for (p, s), g in C.groupby(["pos", "src"]):
        lo, hi = boot(g.coef)
        r = {"pos": p, "src": s, "slates": len(g), "pts_per_sd_logown": g.coef.mean(), "lo": lo, "hi": hi, "seasons_pos": seasons_pos(g, "coef")}
        if s == "joint_v2":
            r["mod_coef_in_joint"] = g.coef_mod_in_joint.mean(); r["mod_lo"], r["mod_hi"] = boot(g.coef_mod_in_joint)
        out.append(r)
    PO = pd.DataFrame(out); PO.to_csv(os.path.join(OUT, "cl_modown_player_coef.csv"), index=False)
    log("\n=== player-level: fp ~ FC proj + salary + z(log ownership), largest contest per slate (own = realized; joint_v2 coef = realized given modeled) ===")
    log(PO.round(3).to_string(index=False))

    # ---------- live lock-time log vs replay, 2026 wk1-2 main
    try:
        L = pd.read_csv(os.path.join(R, "data", "ownership_actual_log.csv"), dtype={"player_id": str})
        L = L[L.slate_id.str.contains("classic") & L.slate_id.str.contains("main")]
        rows = []
        for (wk, sid), g in L.groupby(["week", "slate_id"]):
            p = pools.get((2026, int(wk)))
            m = g.merge(p[["player_id", "v1", "v2", "fc_main_own"]], on="player_id", how="inner")
            m = m[(m.actual_ownership_pct >= 0.5) | (m.estimated_ownership_pct_at_lock >= 0.5)]
            rows.append({"slate": sid, "n": len(m), "live_vs_actual": m.estimated_ownership_pct_at_lock.corr(m.actual_ownership_pct),
                         "v1_vs_actual": m.v1.corr(m.actual_ownership_pct), "v2_vs_actual": m.v2.corr(m.actual_ownership_pct),
                         "fcmain_vs_actual": m.fc_main_own.corr(m.actual_ownership_pct),
                         "live_mae": (m.estimated_ownership_pct_at_lock - m.actual_ownership_pct).abs().mean(),
                         "v2_mae": (m.v2 - m.actual_ownership_pct).abs().mean(), "live_vs_v2": m.estimated_ownership_pct_at_lock.corr(m.v2)})
        LV = pd.DataFrame(rows); LV.to_csv(os.path.join(OUT, "cl_modown_live_check.csv"), index=False)
        log("\n=== live lock-time estimates (ownership_actual_log) vs replay, 2026 main slates ===\n" + LV.round(3).to_string(index=False))
    except Exception as e:  # noqa: BLE001
        log("live check failed:", repr(e))
    with open(os.path.join(OUT, "cl_modown_out.txt"), "w") as fh:
        fh.write("\n".join(LINES))


if __name__ == "__main__":
    main()
