"""Construction-detail pass on the 142 real DK Showdown lineup-study contests (follow-up to lineup_study_analysis.py).

Reads the per-entry player-id cache from lineup_study_ids_build.py and writes aggregate-only tables:
  derived/showdown/ls_cd_<question>.csv and ls_cd_out.txt
Questions:
  Q1 partner   : CPT position x primary same-team partner position (highest-salary same-team FLEX; also by ownership)
  Q2 stack     : CPT position x number of FLEX on the CPT's team (0-4)
  Q3 punts     : FLEX price tiers <=$500 / $600-1000 / $1.1-2k / $2.1-4k (non-DST FLEX-5), counts per tier + cheapest tier
  Q4 split side: 4-2 / 5-1 by which side the CPT is on, and whether the heavy side is the favourite
  Q5 templates : coarse shape string per lineup; the most common top-1% shape per CPT position and its concentration
Metrics (within contest, then equal weight per contest; 90% bootstrap CIs over contests), same as lineup_study_analysis.py:
  cash lift (pts vs contest cash rate), capped return (payout capped at contest 99.9th pct / contest mean), top-1% lift,
  and SHARES of each level among the field, among cashers and among top-1% entries (conditional on the CPT position
  where the question is conditional). Lift metrics need >= 30 entries in a contest; shares are always computed.
"""
import os
import numpy as np
import pandas as pd

ROOT = os.environ.get("DFS_ROOT", r"C:\Users\gmsco\Desktop\DFS_Optimizer")
LS = os.path.join(ROOT, "data", "fc_history", "lineup_study")
OUT = os.path.join(ROOT, "data", "fc_history", "derived", "showdown")
RS = np.random.RandomState(7)
MIN_N = 30
LINES = []


def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LINES.append(s)


def boot(v, B=2000):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    if len(v) < 3:
        return np.nan, np.nan
    s = v[RS.randint(0, len(v), (B, len(v)))].mean(1)
    return np.percentile(s, 5), np.percentile(s, 95)


def tier(s):
    return np.select([s <= 500, s <= 1000, s <= 2000, s <= 4000], ["<=500", "600-1k", "1.1-2k", "2.1-4k"], ">4k")


def features(e, p):
    """e: entries of one contest; p: player table of that contest indexed by pid."""
    ids = [e[f"p{j}"].values for j in range(6)]
    # a few contests carry 1-3 players whose FC/global-meta team is stale (traded / other game): treat as unknown
    main2 = p.team.value_counts().index[:2]
    p = p.assign(team=p.team.where(p.team.isin(main2)))
    pos = [p.pos.reindex(x).fillna("?").values for x in ids]
    tm = [p.team.reindex(x).fillna("?").values for x in ids]
    sal = [p.sal.reindex(x).values.astype(float) for x in ids]
    own = [p.flex_own.reindex(x).values for x in ids]
    fav = p.fav.dropna().iat[0] if p.fav.notna().any() else None
    n = len(e)
    F = pd.DataFrame(index=range(n))
    F["cpt_pos"] = pos[0]
    same = np.column_stack([tm[j] == tm[0] for j in range(1, 6)])
    stack = same.sum(1)
    F["stack"] = stack.astype(str)
    fpos = np.column_stack(pos[1:]); fsal = np.column_stack(sal[1:]); fown = np.column_stack(own[1:])
    # primary partner: highest-salary same-team FLEX (ties -> higher ownership); and highest-owned same-team FLEX
    key_s = np.where(same, fsal + fown / 1000.0, -1e9); key_o = np.where(same, fown, -1e9)
    ps = fpos[np.arange(n), key_s.argmax(1)]; po = fpos[np.arange(n), key_o.argmax(1)]
    F["partner_sal"] = np.where(stack > 0, ps, "none"); F["partner_own"] = np.where(stack > 0, po, "none")
    # same-team receiver presence (for QB CPT) and own-QB (for skill CPT)
    has = lambda P: (same & np.isin(fpos, P)).any(1)
    F["same_passcatcher"] = has(["WR", "TE"]); F["same_qb"] = has(["QB"])
    opp = ~same & (np.column_stack(tm[1:]) != "?")
    F["opp_qb"] = (opp & (fpos == "QB")).any(1)
    F["bringback"] = (opp & np.isin(fpos, ["QB", "RB", "WR", "TE"])).sum(1)
    # splits by side
    unknown = np.column_stack(tm) == "?"
    cnt_c = 1 + stack
    split = np.maximum(cnt_c, 6 - cnt_c)
    F["split"] = np.where(unknown.any(1), "?", np.char.add(np.char.add(split.astype(str), "-"), (6 - split).astype(str)))
    side = np.where(cnt_c > 3, "CPT heavy", np.where(cnt_c < 3, "CPT light", "even"))
    cpt_fav = (tm[0] == fav) if fav else np.full(n, False)
    heavy_is_fav = np.where(cnt_c > 3, cpt_fav, ~cpt_fav) if fav else np.full(n, np.nan)
    F["split_side"] = np.where(F.split.isin(["4-2", "5-1"]), F.split + " " + side, "other")
    F["split_fav"] = np.where(F.split.isin(["4-2", "5-1"]) & bool(fav),
                              F.split + np.where(heavy_is_fav == True, " heavy=fav", " heavy=dog"), "other")  # noqa: E712
    F["split_side_fav"] = np.where(F.split.isin(["4-2", "5-1"]) & bool(fav),
                                   F.split_side + np.where(heavy_is_fav == True, " fav", " dog"), "other")  # noqa: E712
    # punt tiers, FLEX-5 non-DST, FLEX price
    nd = fpos != "DST"
    ok = np.isfinite(fsal).all(1)
    t = tier(np.nan_to_num(fsal, nan=99999))
    for lab in ["<=500", "600-1k", "1.1-2k", "2.1-4k"]:
        c = ((t == lab) & nd).sum(1)
        F["n_" + lab] = np.where(ok, np.minimum(c, 2).astype(str), "nan")
        F.loc[F["n_" + lab] == "2", "n_" + lab] = "2+"
    cheap = np.where(nd, np.nan_to_num(fsal, nan=99999), 99999).min(1)
    F["cheapest"] = np.where(ok, tier(cheap), "nan")
    punts4 = ((fsal <= 4000) & nd).sum(1)
    F["punt_mix"] = np.where(ok, np.char.add(np.char.add(((t == "<=500") & nd).sum(1).astype(str), "min+"),
                                             (((fsal > 500) & (fsal <= 2000)) & nd).sum(1).astype(str)), "nan")
    F["punt_mix"] = np.where(ok, np.char.add(F.punt_mix.values.astype(str),
                                             np.char.add("val+", (((fsal > 2000) & (fsal <= 4000)) & nd).sum(1).astype(str))), "nan")
    # Q5 coarse template
    pb = np.where(punts4 >= 2, "2+punt", np.where(punts4 == 1, "1punt", "0punt"))
    kd = np.where((fpos == "K").any(1) & (fpos == "DST").any(1), "K+D", np.where((fpos == "K").any(1), "K",
                  np.where((fpos == "DST").any(1), "D", "noKD")))
    F["template"] = (F.cpt_pos + "|" + F.partner_sal + "|" + (cnt_c).astype(str) + "-" + (6 - cnt_c).astype(str) + "|" + pb + "|" + kd)
    # outcomes
    cap = e.payout_c.quantile(0.999); pc = np.minimum(e.payout_c.values, cap)
    F["cashed"] = (e.payout_c.values > 0).astype(float)
    F["ret_cap"] = pc / pc.mean()
    F["top1"] = (e["rank"].values <= max(1, np.floor(0.01 * n))).astype(float)
    F["top01"] = (e["rank"].values <= max(1, np.floor(0.001 * n))).astype(float)
    return F


def agg(F, feat, cond=None):
    """Per-contest rows: lift metrics vs the contest, and shares within the cond group among field/cashers/top1."""
    rows = []
    base_c, base_t = F.cashed.mean(), F.top1.mean()
    groups = [("all", F)] if cond is None else list(F.groupby(cond))
    for cv, G in groups:
        nG, nGc, nGt = len(G), G.cashed.sum(), G.top1.sum()
        for lv, e in G.groupby(feat):
            r = {"cond": cv, "level": lv, "n": len(e), "sh_field": len(e) / nG,
                 "sh_cash": e.cashed.sum() / nGc if nGc else np.nan, "sh_top1": e.top1.sum() / nGt if nGt else np.nan,
                 "n_top1": e.top1.sum()}
            if len(e) >= MIN_N:
                r.update(cash_lift=100 * (e.cashed.mean() - base_c), ret_cap=e.ret_cap.mean(), top1_lift=100 * (e.top1.mean() - base_t))
            rows.append(r)
    return rows


QUESTIONS = {  # name: (feature, cond)
    "cpt_pos": ("cpt_pos", None),
    "partner_sal": ("partner_sal", "cpt_pos"), "partner_own": ("partner_own", "cpt_pos"),
    "stack_by_cpt": ("stack", "cpt_pos"),
    "qb_recv": ("same_passcatcher", "cpt_pos"), "own_qb": ("same_qb", "cpt_pos"), "opp_qb": ("opp_qb", "cpt_pos"),
    "bringback": ("bringback", "cpt_pos"),
    "n_<=500": ("n_<=500", None), "n_600-1k": ("n_600-1k", None), "n_1.1-2k": ("n_1.1-2k", None), "n_2.1-4k": ("n_2.1-4k", None),
    "cheapest": ("cheapest", None), "punt_mix": ("punt_mix", None),
    "split_side": ("split_side", None), "split_fav": ("split_fav", None), "split_side_fav": ("split_side_fav", None),
    "split_side_by_cpt": ("split_side", "cpt_pos"),
    "template": ("template", "cpt_pos"),
}


def summarise(D, name):
    out = []
    for (ct, cv, lv), g in D.groupby(["ctype", "cond", "level"], dropna=False):
        r = {"q": name, "ctype": ct, "cond": cv, "level": lv, "contests": len(g), "entries": int(g.n.sum()),
             "n_top1": int(g.n_top1.sum()), "sh_field": g.sh_field.mean(), "sh_cash": g.sh_cash.mean(), "sh_top1": g.sh_top1.mean()}
        # shares: contests where the level is absent contribute 0 -> use sum/ncontests of that ctype
        for m in ("cash_lift", "ret_cap", "top1_lift"):
            if m in g:
                v = g[m].dropna(); r[m] = v.mean() if len(v) else np.nan; r[m + "_lo"], r[m + "_hi"] = boot(v); r[m + "_n"] = len(v)
        for s in (2022, 2023, 2024, 2025):
            if "cash_lift" in g:
                r[f"cash_{s}"] = g.loc[g.season == s, "cash_lift"].mean()
        out.append(r)
    T = pd.DataFrame(out)
    # re-normalise shares so a level absent in a contest counts as 0 share (denominator = contests having the cond group)
    nct = D.groupby(["ctype", "cond"]).contest.nunique()
    sums = D.groupby(["ctype", "cond", "level"])[["sh_field", "sh_cash", "sh_top1"]].sum()
    for c in ("sh_field", "sh_cash", "sh_top1"):
        T[c] = [sums.loc[(r.ctype, r.cond, r.level), c] / nct.loc[(r.ctype, r.cond)] for r in T.itertuples()]
    return T


def main():
    E = pd.read_parquet(os.path.join(LS, "_sd_entries_ids.parquet"))
    E["contest"] = E.contest.astype(str)
    P = pd.read_parquet(os.path.join(LS, "_sd_players.parquet"))
    P["contest"] = P.contest.astype(str)
    acc = {k: [] for k in QUESTIONS}
    lim = int(os.environ.get("CD_LIMIT", "0"))
    if lim:
        E = E[E.contest.isin(E.contest.unique()[:lim])]
    for cid, e in E.groupby("contest", sort=False):
        p = P[P.contest == cid].set_index("pid")
        F = features(e.reset_index(drop=True), p)
        meta = {"contest": cid, "ctype": p.ctype.iat[0], "season": int(p.season.iat[0])}
        for k, (feat, cond) in QUESTIONS.items():
            for r in agg(F, feat, cond):
                r.update(meta); acc[k].append(r)
        print(cid, len(F), flush=True)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 2000)
    allT = []
    for k, rows in acc.items():
        D = pd.DataFrame(rows)
        T = summarise(D, k)
        if k == "template":   # keep only shapes that matter
            T = T[(T.sh_top1 >= 0.02) | (T.sh_field >= 0.03)]
        T.to_csv(os.path.join(OUT, f"ls_cd_{k.replace('<=', 'le').replace('.', '')}.csv"), index=False)
        allT.append(T)
        cols = ["ctype", "cond", "level", "contests", "n_top1", "sh_field", "sh_cash", "sh_top1", "cash_lift", "cash_lift_lo",
                "cash_lift_hi", "ret_cap", "ret_cap_lo", "ret_cap_hi", "top1_lift", "top1_lift_lo", "top1_lift_hi",
                "cash_2022", "cash_2023", "cash_2024", "cash_2025"]
        log(f"\n=== {k} ===")
        log(T[[c for c in cols if c in T]].round(3).to_string(index=False))
    # Q5 concentration: per ctype x cpt_pos, share of top-1% covered by the top template and #templates to reach 50%
    D = pd.DataFrame(acc["template"])
    log("\n=== template concentration among top-1% (pooled equal-weight shares) ===")
    conc = []
    for (ct, cv), g in D.groupby(["ctype", "cond"]):
        nc = g.contest.nunique()
        s = (g.groupby("level").sh_top1.sum() / nc).sort_values(ascending=False)
        f = (g.groupby("level").sh_field.sum() / nc)
        cz = (g.groupby("level").sh_cash.sum() / nc)
        cum = s.cumsum() / s.sum()
        conc.append({"ctype": ct, "cpt_pos": cv, "contests": nc, "n_templates_top1": int((s > 0).sum()),
                     "top_template": s.index[0], "top_sh_top1": s.iat[0], "top_sh_cash": cz.get(s.index[0]), "top_sh_field": f.get(s.index[0]),
                     "k_for_50pct_top1": int((cum < 0.5).sum() + 1), "second": s.index[1] if len(s) > 1 else None,
                     "second_sh_top1": s.iat[1] if len(s) > 1 else np.nan})
    C = pd.DataFrame(conc); C.to_csv(os.path.join(OUT, "ls_cd_template_concentration.csv"), index=False)
    log(C.round(3).to_string(index=False))
    with open(os.path.join(OUT, "ls_cd_out.txt"), "w") as fh:
        fh.write("\n".join(LINES))


if __name__ == "__main__":
    main()
