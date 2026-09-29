"""Parking-lot deep-dive: signal coverage & selection (WK3_ROOT_CAUSE_FINDINGS.md, 2026-09-28).

(a) Killer-side bust base rate: is "35% of killers were z>=1 projections" elevated vs. how
    often z>=1 plays bust in the general eligible population?
(b) What the 35 "no signal" driver rows (0 <= z < 1) have in common vs. other neutral-z players.
(c) Salary-tier / position clustering of misses in gmscott81's actual submitted lineups.

Builds on wk3_postmortem_v2_players.csv / _flags.csv (Phase 1 v2) and the raw contest CSVs.

usage: python analysis/classic_diag/wk3_signal_coverage_deepdive.py
Outputs: analysis/classic_diag/wk3_sigcov_*.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, mannwhitneyu

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wk3_postmortem_phase1 import SLATES, load_our_model  # noqa: E402
from wk3_postmortem_phase1_v2 import load_entries, salary_band  # noqa: E402

OUT = HERE
Z_STRONG = 1.0
BUST_Q = 0.25          # bust = bottom quartile of position outcomes on the slate
EXTRA = ["implied_total", "over_under", "games_played", "participation_effective", "roster_role",
         "sigma", "statline_p90", "season_avg", "recent_form", "matchup_factor", "vegas_factor",
         "proj_targets", "proj_rush_att"]


def fisher(a, b, c, d):
    """2x2 [[a,b],[c,d]] -> (odds ratio, two-sided p)."""
    o, p = fisher_exact([[a, b], [c, d]])
    return o, p


def load_all():
    A = pd.read_csv(HERE / "wk3_postmortem_v2_players.csv")
    F = pd.read_csv(HERE / "wk3_postmortem_v2_flags.csv")
    A["week"] = A.slate.str.split("_").str[0]
    A["band"] = [salary_band(p, s) for p, s in zip(A.our_pos, A.salary)]
    # attach richer model columns + teammate-OUT flag per slate
    parts = []
    for lab, (f, sid, cash) in SLATES.items():
        P = A[A.slate == lab].copy()
        our = load_our_model(sid)
        for c in EXTRA:
            P[c] = P.k.map(our[c]) if our is not None and c in our.columns else np.nan
        if our is not None:
            out_mask = our.injury_status.astype(str).str.upper().isin(["OUT", "IR", "DOUBTFUL"]) \
                & our.position.isin(["QB", "RB", "WR", "TE"])
            outs = our[out_mask]
            # vacated projection proxy: teammate at same position OUT with a real season_avg
            def mate_out(r):
                m = outs[(outs.team == r.team) & (outs.position == r.our_pos) & (outs.index != r.k)]
                return pd.Series(dict(mate_out_same_pos=len(m) > 0,
                                      mate_out_any=((outs.team == r.team) & (outs.index != r.k)).any(),
                                      mate_out_season_avg=m.season_avg.max() if len(m) else 0.0))
            P = pd.concat([P, P.apply(mate_out, axis=1)], axis=1)
        # implied total rank within slate (1 = highest)
        tt = P.drop_duplicates("team")[["team", "implied_total"]].dropna()
        P["itt_rank_pct"] = P.team.map(tt.set_index("team").implied_total.rank(pct=True, ascending=False))
        # outcome percentile within slate x position, over players the field used >= 1%
        rel = P.field_pct >= 0.01
        P["fpts_pct_pos"] = np.nan
        P.loc[rel, "fpts_pct_pos"] = P[rel].groupby("our_pos").fpts.rank(pct=True, method="average")
        parts.append(P)
    A = pd.concat(parts, ignore_index=True)
    A["own_gap"] = A.our_own_pct - 100 * A.field_pct
    A["resid"] = A.fpts - A.our_proj
    A["upside_ratio"] = A.statline_p90 / A.our_proj
    key = ["slate", "k"]
    F["flag"] = F.dir
    A = A.merge(F[key + ["flag", "root_cause", "four_way"]], on=key, how="left")
    return A


# ------------------------------------------------------------------ (a)
def part_a(A):
    E = A[(A.field_n >= 20) & (A.field_pct >= 0.05) & A.proj_z_pos.notna() & A.fpts_pct_pos.notna()].copy()
    E["strong"] = E.proj_z_pos >= Z_STRONG
    E["bust"] = E.fpts_pct_pos <= BUST_Q
    E["bust_half"] = E.fpts <= 0.5 * E.our_proj
    E["killer"] = E.flag == "killer"
    rows = []

    def add(name, df, note=""):
        s, ns = df[df.strong], df[~df.strong]
        for col in ["bust", "bust_half"]:
            a, b = int(s[col].sum()), int((~s[col]).sum())
            c, d = int(ns[col].sum()), int((~ns[col]).sum())
            o, p = fisher(a, b, c, d)
            rows.append(dict(cut=name, bust_def=col, n_strong=len(s), bust_rate_strong=a / max(len(s), 1),
                             n_other=len(ns), bust_rate_other=c / max(len(ns), 1), odds=o, p=p, note=note))

    add("all eligible rows", E)
    U = E.sort_values("slate").drop_duplicates(["week", "k"])  # one row per week-player
    add("unique week-player", U, "first slate variant kept")
    for pos, g in E.groupby("our_pos"):
        add(f"pos={pos}", g)
    for w, g in E.groupby("week"):
        add(f"week={w}", g)

    # the flagged-killer comparison: P(z>=1 | killer) vs P(z>=1 | not killer) in the same eligible pool
    K, NK = E[E.killer], E[~E.killer]
    o, p = fisher(int(K.strong.sum()), int((~K.strong).sum()), int(NK.strong.sum()), int((~NK.strong).sum()))
    # and among real busts only: are strong players over-represented among killers vs other busts?
    B = E[E.bust]
    BK, BN = B[B.killer], B[~B.killer]
    o2, p2 = fisher(int(BK.strong.sum()), int((~BK.strong).sum()), int(BN.strong.sum()), int((~BN.strong).sum()))
    # conditional: of strong players who busted, how many became flagged killers vs other busts
    SB = E[E.strong & E.bust]
    NSB = E[~E.strong & E.bust]
    comp = pd.DataFrame([
        dict(cut="z>=1 share: killers vs rest of eligible pool", n_a=len(K), rate_a=K.strong.mean(),
             n_b=len(NK), rate_b=NK.strong.mean(), odds=o, p=p),
        dict(cut="z>=1 share: killers vs non-killer busts (bottom-quartile)", n_a=len(BK), rate_a=BK.strong.mean(),
             n_b=len(BN), rate_b=BN.strong.mean(), odds=o2, p=p2),
        dict(cut="killer-flag rate: strong busts vs other busts", n_a=len(SB), rate_a=SB.killer.mean(),
             n_b=len(NSB), rate_b=NSB.killer.mean(), odds=np.nan, p=np.nan),
        dict(cut="killer fpts pct-rank within pos (median)", n_a=len(K), rate_a=K.fpts_pct_pos.median(),
             n_b=len(NK), rate_b=NK.fpts_pct_pos.median(), odds=np.nan, p=np.nan),
        dict(cut="killer field% (median)", n_a=len(K), rate_a=K.field_pct.median(),
             n_b=len(NK), rate_b=NK.field_pct.median(), odds=np.nan, p=np.nan),
    ])
    # strong-player field% vs weak (selection effect: strong players are more rostered -> more eligible)
    comp.loc[len(comp)] = dict(cut="field% median: strong vs other", n_a=int(E.strong.sum()),
                               rate_a=E[E.strong].field_pct.median(), n_b=int((~E.strong).sum()),
                               rate_b=E[~E.strong].field_pct.median(), odds=np.nan, p=np.nan)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "wk3_sigcov_a_bust_base_rate.csv", index=False)
    comp.to_csv(OUT / "wk3_sigcov_a_killer_vs_pool.csv", index=False)
    print("\n==== (a) bust base rate, eligible pool (field_n>=20, field%>=5%) ====")
    print(R.round(3).to_string(index=False))
    print(comp.round(3).to_string(index=False))
    # sensitivity to the z cut
    sens = []
    for zc in [0.5, 1.0, 1.5]:
        s = E[E.proj_z_pos >= zc]
        sens.append(dict(z_cut=zc, n=len(s), bust_rate=s.bust.mean(), killer_share_strong=(K.proj_z_pos >= zc).mean(),
                         pool_share_strong=(NK.proj_z_pos >= zc).mean()))
    S = pd.DataFrame(sens)
    S.to_csv(OUT / "wk3_sigcov_a_zcut_sensitivity.csv", index=False)
    print(S.round(3).to_string(index=False))
    return E


# ------------------------------------------------------------------ (b)
def part_b(A, E):
    D = E[(E.flag == "driver") & (E.proj_z_pos >= 0) & (E.proj_z_pos < Z_STRONG)].copy()
    C = E[(E.flag != "driver") & (E.proj_z_pos >= 0) & (E.proj_z_pos < Z_STRONG)].copy()
    allD = E[E.flag == "driver"]
    print(f"\n==== (b) no-signal drivers: n={len(D)} rows (unique week-player {D.drop_duplicates(['week','k']).shape[0]}); "
          f"comparison neutral-z non-drivers n={len(C)} ====")
    feats = ["salary", "field_pct", "our_proj", "proj_z_pos", "own_gap", "implied_total", "itt_rank_pct",
             "games_played", "participation_effective", "sigma", "upside_ratio", "mate_out_season_avg", "resid", "fpts"]
    rows = []
    for c in feats:
        a, b = D[c].dropna(), C[c].dropna()
        p = mannwhitneyu(a, b).pvalue if len(a) > 3 and len(b) > 3 else np.nan
        rows.append(dict(feature=c, driver_median=a.median(), comp_median=b.median(), n_d=len(a), n_c=len(b), mw_p=p))
    for flag in ["mate_out_same_pos", "mate_out_any"]:
        a, b = D[flag].fillna(False).astype(bool), C[flag].fillna(False).astype(bool)
        o, p = fisher(int(a.sum()), int((~a).sum()), int(b.sum()), int((~b).sum()))
        rows.append(dict(feature=flag + " (share)", driver_median=a.mean(), comp_median=b.mean(),
                         n_d=len(a), n_c=len(b), mw_p=p))
    for band in ["1_low", "2_mid-low", "3_mid-high", "4_high"]:
        a, b = D.band == band, C.band == band
        o, p = fisher(int(a.sum()), int((~a).sum()), int(b.sum()), int((~b).sum()))
        rows.append(dict(feature=f"band={band} (share)", driver_median=a.mean(), comp_median=b.mean(),
                         n_d=len(a), n_c=len(b), mw_p=p))
        a2 = allD.band == band
        rows.append(dict(feature=f"band={band} (share, ALL 80 drivers)", driver_median=a2.mean(),
                         comp_median=(E.band == band).mean(), n_d=len(a2), n_c=len(E), mw_p=np.nan))
    for pos in ["QB", "RB", "WR", "TE", "DST"]:
        a, b = D.our_pos == pos, C.our_pos == pos
        o, p = fisher(int(a.sum()), int((~a).sum()), int(b.sum()), int((~b).sum()))
        rows.append(dict(feature=f"pos={pos} (share)", driver_median=a.mean(), comp_median=b.mean(),
                         n_d=len(a), n_c=len(b), mw_p=p))
    rr = D.roster_role.fillna("na").value_counts(normalize=True)
    rc = C.roster_role.fillna("na").value_counts(normalize=True)
    for role in sorted(set(rr.index) | set(rc.index)):
        rows.append(dict(feature=f"roster_role={role} (share)", driver_median=rr.get(role, 0),
                         comp_median=rc.get(role, 0), n_d=len(D), n_c=len(C), mw_p=np.nan))
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "wk3_sigcov_b_nosignal_features.csv", index=False)
    print(R.round(3).to_string(index=False))
    cols = ["slate", "k", "our_pos", "salary", "band", "field_pct", "our_proj", "fpts", "resid", "proj_z_pos",
            "own_gap", "implied_total", "itt_rank_pct", "games_played", "roster_role", "mate_out_same_pos",
            "mate_out_season_avg", "pair_note"] if "pair_note" in D.columns else None
    Fl = pd.read_csv(HERE / "wk3_postmortem_v2_flags.csv")[["slate", "k", "pair_note"]]
    D = D.merge(Fl, on=["slate", "k"], how="left")
    keep = [c for c in ["slate", "k", "our_pos", "salary", "band", "field_pct", "our_proj", "fpts", "resid",
                        "proj_z_pos", "own_gap", "implied_total", "itt_rank_pct", "games_played", "roster_role",
                        "mate_out_same_pos", "mate_out_season_avg", "pair_note", "my_entries"] if c in D.columns]
    D[keep].sort_values(["slate", "our_pos"]).to_csv(OUT / "wk3_sigcov_b_nosignal_drivers.csv", index=False)
    print(D[keep].round(2).to_string(index=False))
    # residual share: how much of the no-signal drivers' outcome was 'projection miss' in points
    print("pair_note:", D.pair_note.value_counts().to_dict())


# ------------------------------------------------------------------ (c)
def part_c(A):
    recs = []
    for lab, (f, sid, cash_pct) in SLATES.items():
        e, fpts, N, cash_n = load_entries(f, cash_pct)
        P = A[A.slate == lab].set_index("k")
        typ = "MME" if "mme" in lab else "SE"
        for grp, sub in [("mine", e[e.mine]), ("cash_field", e[e.cash & ~e.mine]), ("noncash_field", e[~e.cash & ~e.mine])]:
            for keys in sub["keys"]:
                for k in keys:
                    if k not in P.index:
                        continue
                    r = P.loc[k]
                    recs.append(dict(slate=lab, typ=typ, grp=grp, k=k, pos=r.our_pos, band=r.band,
                                     salary=r.salary, fpts=r.fpts, our_proj=r.our_proj,
                                     flag=r.flag if isinstance(r.flag, str) else "",
                                     root_cause=r.root_cause if isinstance(r.root_cause, str) else "",
                                     w=1.0 / len(sub)))  # weight so each group sums to 1 lineup per slate
    S = pd.DataFrame(recs)
    S["resid"] = S.fpts - S.our_proj
    S["pts_per_k"] = S.fpts / (S.salary / 1000)
    S["killer"] = S.flag == "killer"
    S["driver"] = S.flag == "driver"
    S.to_csv(OUT / "wk3_sigcov_c_roster_slots.csv", index=False)

    def summarize(df, by):
        g = df.groupby(by)
        out = pd.DataFrame(dict(
            slots_per_lineup=g.w.sum() / df.slate.nunique(),
            killer_slot_share=g.apply(lambda x: np.average(x.killer, weights=x.w)),
            driver_slot_share=g.apply(lambda x: np.average(x.driver, weights=x.w)),
            mean_resid=g.apply(lambda x: np.average(x.resid.fillna(0), weights=x.w)),
            pts_per_k=g.apply(lambda x: np.average(x.pts_per_k.fillna(0), weights=x.w)),
            n_slots=g.size()))
        return out

    tabs = []
    for typ in ["SE", "MME"]:
        T = S[S.typ == typ]
        for by in ["band", "pos"]:
            t = summarize(T, ["grp", by]).reset_index().rename(columns={by: "level"})
            t.insert(0, "cut", by)
            t.insert(0, "typ", typ)
            tabs.append(t)
    Tab = pd.concat(tabs, ignore_index=True)
    Tab.to_csv(OUT / "wk3_sigcov_c_clustering.csv", index=False)
    print("\n==== (c) roster-slot clustering (weighted per lineup; mine vs cashing field vs non-cashing) ====")
    print(Tab.round(3).to_string(index=False))

    # killer slots I rostered, and flagged drivers I missed that the cashing field used
    mine = S[S.grp == "mine"]
    kil = mine[mine.killer].groupby(["slate", "k", "pos", "band", "salary", "root_cause"]).size().rename("my_slots").reset_index()
    print("\n-- flagged killers in my lineups --")
    print(kil.to_string(index=False))
    kil.to_csv(OUT / "wk3_sigcov_c_my_killers.csv", index=False)
    Dm = A[A.flag == "driver"][["slate", "k", "our_pos", "band", "salary", "field_pct", "my_entries", "root_cause",
                                "proj_z_pos"]].copy()
    Dm["rostered"] = Dm.my_entries > 0
    Dm.to_csv(OUT / "wk3_sigcov_c_driver_coverage.csv", index=False)
    print("\n-- flagged drivers: my coverage by band / pos --")
    for by in ["band", "our_pos"]:
        print(Dm.groupby(by).agg(n=("k", "size"), rostered=("rostered", "sum"), field=("field_pct", "median")).to_string())

    # Fisher: do my killer slots concentrate in a band vs my total slot mix? (SE and MME pooled per slot)
    print("\n-- my killer-slot rate by band vs rest (pooled, unweighted slots) --")
    fr = []
    for key, col in [("band", "band"), ("pos", "pos")]:
        for lvl in mine[col].dropna().unique():
            a = mine[(mine[col] == lvl)]
            b = mine[(mine[col] != lvl)]
            o, p = fisher(int(a.killer.sum()), int((~a.killer).sum()), int(b.killer.sum()), int((~b.killer).sum()))
            # same for cashing field / noncashing comparison: killer rate for this level in noncash field (weighted)
            nc = S[(S.grp == "noncash_field") & (S[col] == lvl)]
            fr.append(dict(cut=key, level=lvl, my_slots=len(a), my_killer_rate=a.killer.mean(),
                           my_killer_rate_rest=b.killer.mean(), p=p,
                           field_killer_rate=np.average(nc.killer, weights=nc.w) if len(nc) else np.nan,
                           my_mean_resid=a.resid.mean()))
    FR = pd.DataFrame(fr).sort_values(["cut", "level"])
    FR.to_csv(OUT / "wk3_sigcov_c_my_killer_rate.csv", index=False)
    print(FR.round(3).to_string(index=False))


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    A = load_all()
    E = part_a(A)
    part_b(A, E)
    part_c(A)


if __name__ == "__main__":
    main()
