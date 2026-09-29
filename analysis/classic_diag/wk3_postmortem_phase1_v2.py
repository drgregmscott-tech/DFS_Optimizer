"""Phase 1 v2 -- corrected Steps 2-5 for the Wk1-3 postmortem (WK3_ROOT_CAUSE_FINDINGS.md).

Reuses Step 1 parsing (SLATES, norm, parse_lineup, load_our_model) from
wk3_postmortem_phase1.py. What v2 adds / fixes:

  Step 2  drivers AND killers per slate (cap 5 early/afternoon, 10 main),
          stack-pairing split (X with vs without natural partner P),
          snowflake test (same player, other slate variants of the same week).
  Step 3  literal four-way taxonomy on the flagged list (drivers + killers).
  Step 4  per-player root-cause tag for every flag + whether gmscott81's
          submitted entries rostered the player; QB/DST ownership spot-check.
  Step 5  bias check (our_own_pct - field%) vs FPTS, stratified by salary tier.

usage: python analysis/classic_diag/wk3_postmortem_phase1_v2.py
Outputs: analysis/classic_diag/wk3_postmortem_v2_*.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wk3_postmortem_phase1 import SLATES, norm, parse_lineup, load_our_model  # noqa: E402

OUT = HERE
MIN_FIELD_N = 20
MIN_FIELD_PCT = 0.05          # eligibility floor for driver/killer ranking
CHALK = 0.15                  # "heavily weighted" threshold, field and ours
Z_STRONG = 1.0                # strong projection within position
Z_WEAK = 0.5                  # below this = we did not like the player
ME = "gmscott81"
WEEK_OF = lambda lab: lab.split("_")[0]  # noqa: E731
IS_MAIN = lambda lab: "main" in lab      # noqa: E731


# ---------------------------------------------------------------- Step 1 reuse
def load_entries(f, cash_pct):
    """One row per entry (dedupe EntryId), cash flag, player-key set, mine flag."""
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    fpts = tab.drop_duplicates("k").set_index("k")["FPTS"].to_dict()
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).drop_duplicates("EntryId")
    e = e.sort_values("Points", ascending=False).reset_index(drop=True)
    N = len(e)
    cash_n = int(np.floor(N * cash_pct))
    e["cash"] = e.index < cash_n
    e["mine"] = e.EntryName.astype(str).str.contains(ME, na=False)
    e["keys"] = [frozenset(norm(nm) for _, nm in parse_lineup(L)) for L in e.Lineup]
    return e, fpts, N, cash_n


def player_table(e, fpts, N):
    base = e.cash.mean()
    cnt, csh, mine = {}, {}, {}
    for keys, c, m in zip(e["keys"], e.cash, e.mine):
        for k in keys:
            cnt[k] = cnt.get(k, 0) + 1
            if c:
                csh[k] = csh.get(k, 0) + 1
            if m:
                mine[k] = mine.get(k, 0) + 1
    tot_cash = int(e.cash.sum())
    rows = []
    for k, n in cnt.items():
        c = csh.get(k, 0)
        wo_n = N - n
        rows.append(dict(k=k, field_n=n, field_pct=n / N, cash_rate=c / n,
                         cash_rate_without=(tot_cash - c) / wo_n if wo_n else np.nan,
                         lift=c / n - base, fpts=fpts.get(k, np.nan),
                         my_entries=mine.get(k, 0)))
    P = pd.DataFrame(rows)
    P["lift_z"] = P.lift / np.sqrt(base * (1 - base) / P.field_n)
    return P, base


def attach_model(P, our):
    cols = dict(our_pos="position", team="team", salary="salary", our_proj="final_projection",
                our_own_pct="estimated_ownership_pct", chalk_score="chalk_score",
                injury_status="injury_status")
    for c, src in cols.items():
        P[c] = P.k.map(our[src]) if our is not None and src in our.columns else np.nan
    P["ffc_listed"] = (P.k.map(our["ffc_own_pct"]).notna() if our is not None and "ffc_own_pct" in our.columns
                       else np.nan)
    # projection z within position, over players the field actually used (>=1%)
    rel = P[(P.field_pct >= 0.01) & P.our_proj.notna()]
    stats = rel.groupby("our_pos").our_proj.agg(["mean", "std"])
    P["proj_z_pos"] = (P.our_proj - P.our_pos.map(stats["mean"])) / P.our_pos.map(stats["std"]).replace(0, np.nan)
    P["proj_rank_pos"] = P.groupby("our_pos").our_proj.rank(ascending=False, method="min")
    return P


# ---------------------------------------------------------------- Step 2
def pick_flags(P, lab):
    cap = 10 if IS_MAIN(lab) else 5
    el = P[(P.field_n >= MIN_FIELD_N) & (P.field_pct >= MIN_FIELD_PCT)]
    d = el[el.lift > 0].nlargest(cap, "lift").assign(dir="driver")
    k = el[el.lift < 0].nsmallest(cap, "lift").assign(dir="killer")
    return pd.concat([d, k])


def stack_pair(e, P, base, row):
    """Split X's entries by presence of natural partner P (same team)."""
    pos, team = row.our_pos, row.team
    if pd.isna(team) or pos not in ("QB", "WR", "TE", "RB"):
        return dict(partner=None, pair_note="n/a (DST or no team)")
    mates = P[(P.team == team) & (P.k != row.k)]
    cand = mates[mates.our_pos.isin(["WR", "TE"])] if pos == "QB" else mates[mates.our_pos == "QB"]
    if cand.empty:
        return dict(partner=None, pair_note="no partner in field")
    p = cand.sort_values("field_pct", ascending=False).iloc[0]
    has_x = e["keys"].map(lambda s: row.k in s)
    has_p = e["keys"].map(lambda s: p.k in s)
    w, wo = e[has_x & has_p], e[has_x & ~has_p]
    out = dict(partner=p.k, partner_field_pct=p.field_pct,
               n_with=len(w), n_without=len(wo),
               lift_with=w.cash.mean() - base if len(w) else np.nan,
               lift_without=wo.cash.mean() - base if len(wo) else np.nan)
    lw, lo = out["lift_with"], out["lift_without"]
    s = np.sign(row.lift)
    if len(wo) < MIN_FIELD_N or len(w) < MIN_FIELD_N:
        out["pair_note"] = "thin subset (<20)"
    elif np.sign(lo) == s and abs(lo) >= 0.5 * abs(row.lift):
        out["pair_note"] = "standalone"
    elif np.sign(lw) == s and (np.sign(lo) != s or abs(lo) < 0.5 * abs(row.lift)):
        out["pair_note"] = "pairing-driven"
    else:
        out["pair_note"] = "mixed"
    return out


def snowflake(flags, allP):
    """Same player, other slate variants of the same week."""
    recs = []
    for _, r in flags.iterrows():
        wk = WEEK_OF(r.slate)
        others = [s for s in allP if WEEK_OF(s) == wk and s != r.slate]
        cut_same, cut_opp, cut_absent, var_same, var_opp = [], [], [], [], []
        for s in others:
            same_games = IS_MAIN(s) and IS_MAIN(r.slate)  # se3max vs mme: same games, different contest
            q = allP[s][(allP[s].k == r.k) & (allP[s].field_n >= MIN_FIELD_N)]
            if q.empty:
                if not same_games:
                    cut_absent.append(s)
                continue
            lift = q.lift.iloc[0]
            flagged_there = ((flags.slate == s) & (flags.k == r.k) & (flags.dir == r.dir)).any()
            tag = f"{s.split('_', 1)[1]}:{lift:+.3f}{'*' if flagged_there else ''}"
            same_sign = np.sign(lift) == np.sign(r.lift)
            (var_same if same_games and same_sign else var_opp if same_games else
             cut_same if same_sign else cut_opp).append(tag)
        if cut_same and not cut_opp:
            verdict = "holds across game-set cuts"
        elif cut_opp and not cut_same:
            verdict = "reverses across cuts"
        elif cut_same and cut_opp:
            verdict = "mixed"
        else:
            verdict = "single cut only (contest-variant echo only)" if (var_same or var_opp) else "single cut only"
        recs.append(dict(snow_cut_same=";".join(cut_same), snow_cut_opp=";".join(cut_opp),
                         snow_variant_same=";".join(var_same), snow_variant_opp=";".join(var_opp),
                         snow_verdict=verdict))
    return pd.DataFrame(recs, index=flags.index)


# ---------------------------------------------------------------- Step 3 / 4
def four_way(r):
    field_on = r.field_pct >= CHALK
    we_on = (pd.notna(r.our_own_pct) and r.our_own_pct >= CHALK * 100) or \
            (pd.notna(r.proj_z_pos) and r.proj_z_pos >= Z_STRONG)
    if r.dir == "driver":
        return {(True, False): "field hit / we missed", (False, True): "we hit / field missed",
                (False, False): "both missed", (True, True): "both hit"}[(field_on, we_on)]
    return {(True, False): "field trapped / we avoided", (False, True): "we trapped / field avoided",
            (False, False): "neither heavy (minor-owned killer)", (True, True): "both trapped"}[(field_on, we_on)]


def root_cause(r):
    rostered = r.my_entries > 0
    if pd.isna(r.our_proj):
        return "no signal (not in our pool)"
    z = r.proj_z_pos
    if r.dir == "driver":
        if z >= Z_STRONG:
            return "good signal followed" if rostered else "good signal ignored/overridden"
        if z >= 0:
            return "no signal (neutral projection)"
        return "bad signal (projection below pos mean)"
    if z >= Z_STRONG:
        return "bad signal (projected strong, busted)"
    if z < Z_WEAK:
        return "good signal ignored/overridden" if rostered else "good signal followed"
    return "no signal (neutral projection)"


def own_tag(r):
    if pd.isna(r.our_own_pct):
        return "own: n/a"
    gap = r.our_own_pct - 100 * r.field_pct
    return "own: under >=10pt" if gap <= -10 else "own: over >=10pt" if gap >= 10 else "own: within 10pt"


# ---------------------------------------------------------------- Step 5
def salary_band(pos, sal):
    if pd.isna(sal):
        return np.nan
    edges = {"QB": [5500, 6500, 7500], "RB": [5000, 6500, 8000], "WR": [4500, 6000, 7500],
             "TE": [3500, 4500, 6000], "DST": [2800, 3200, 3600]}.get(pos)
    if edges is None:
        return np.nan
    names = ["1_low", "2_mid-low", "3_mid-high", "4_high"]
    return names[int(np.searchsorted(edges, sal, side="right"))]


def main():
    pd.set_option("display.width", 250)
    allP, allE, flag_parts, bases = {}, {}, [], {}
    for lab, (f, sid, cash_pct) in SLATES.items():
        e, fpts, N, cash_n = load_entries(f, cash_pct)
        P, base = player_table(e, fpts, N)
        P = attach_model(P, load_our_model(sid))
        P["slate"] = lab
        allP[lab], allE[lab], bases[lab] = P, e, base
        mine_n = int(e.mine.sum())
        print(f"{lab}: {N} entries, cash top {cash_n}, base {base:.3f}, {ME} entries={mine_n}")
        fl = pick_flags(P, lab)
        pair = pd.DataFrame([stack_pair(e, P, base, r) for _, r in fl.iterrows()], index=fl.index)
        flag_parts.append(pd.concat([fl, pair], axis=1))
    F = pd.concat(flag_parts, ignore_index=True)
    F = pd.concat([F, snowflake(F, allP)], axis=1)
    F["four_way"] = F.apply(four_way, axis=1)
    F["root_cause"] = F.apply(root_cause, axis=1)
    F["own_tag"] = F.apply(own_tag, axis=1)
    F["rostered_by_me"] = F.my_entries > 0
    F["own_mech"] = np.where(F.slate.str.startswith("wk3"), "layered+FFC", "heuristic softmax")
    A = pd.concat(allP.values(), ignore_index=True)
    A.to_csv(OUT / "wk3_postmortem_v2_players.csv", index=False)
    F.to_csv(OUT / "wk3_postmortem_v2_flags.csv", index=False)
    # collapse to unique week-player-direction (what the findings doc tables show)
    F["week"] = F.slate.map(WEEK_OF)
    U = F.groupby(["week", "dir", "k"]).agg(
        pos=("our_pos", "first"), salary=("salary", "first"),
        slates=("slate", lambda s: ",".join(x.split("_", 1)[1] for x in s)),
        field_min=("field_pct", "min"), field_max=("field_pct", "max"),
        lift_min=("lift", "min"), lift_max=("lift", "max"), our_own_max=("our_own_pct", "max"),
        proj_z_mean=("proj_z_pos", "mean"), my_entries=("my_entries", lambda x: "/".join(str(int(v)) for v in x)),
        four_way=("four_way", lambda x: x.mode()[0]), root_cause=("root_cause", lambda x: "; ".join(sorted(set(x)))),
        own_tag=("own_tag", lambda x: "; ".join(sorted(set(x)))),
        pair_note=("pair_note", lambda x: "; ".join(sorted(set(str(v) for v in x))))).reset_index()
    U.to_csv(OUT / "wk3_postmortem_v2_flags_unique.csv", index=False)

    show = ["slate", "dir", "k", "our_pos", "salary", "field_pct", "lift", "lift_z", "fpts", "our_own_pct",
            "proj_z_pos", "my_entries"]
    print("\n==== STEP 2: drivers / killers per slate ====")
    for lab in SLATES:
        g = F[F.slate == lab]
        print(f"\n--- {lab} (base cash {bases[lab]:.3f}) ---")
        print(g[show[1:]].round(3).to_string(index=False))

    print("\n==== STEP 2b: stack-pairing split ====")
    pc = ["slate", "dir", "k", "our_pos", "lift", "partner", "n_with", "lift_with", "n_without",
          "lift_without", "pair_note"]
    print(F[pc].round(3).to_string(index=False))
    print(F.groupby(["dir", "pair_note"]).size().unstack(fill_value=0))

    print("\n==== STEP 2c: snowflake ====")
    sc = ["slate", "dir", "k", "lift", "snow_cut_same", "snow_cut_opp", "snow_variant_same", "snow_variant_opp",
          "snow_verdict"]
    print(F[sc].round(3).to_string(index=False))
    print(F.groupby(["dir", "snow_verdict"]).size().unstack(fill_value=0))

    print("\n==== STEP 3: four-way ====")
    print(F.groupby(["dir", "four_way"]).size())
    print("killer field_pct distribution:", F[F.dir == "killer"].field_pct.describe().round(3).to_dict())

    print("\n==== STEP 4: root cause ====")
    rc = ["slate", "dir", "k", "our_pos", "field_pct", "lift", "our_own_pct", "proj_z_pos", "proj_rank_pos",
          "my_entries", "injury_status", "ffc_listed", "four_way", "root_cause", "own_tag"]
    print(F[rc].round(3).to_string(index=False))
    print(F.groupby(["dir", "root_cause"]).size())
    print(pd.crosstab(F.root_cause, F.own_tag))
    ign = F[F.root_cause == "good signal ignored/overridden"]
    print(f"\nsignal-there-lineup-didn't-use: {len(ign)} player-slate rows, "
          f"{ign.k.nunique()} unique players:\n", ign[["slate", "dir", "k", "proj_z_pos", "my_entries"]].to_string(index=False))
    # wk3 FFC-listing cliff
    w3 = F[F.slate.str.startswith("wk3") & (F.own_tag == "own: under >=10pt")]
    print("\nwk3 flags under-owned >=10pt, ffc_listed:\n", w3[["slate", "k", "ffc_listed", "our_own_pct", "field_pct"]])

    print("\n==== STEP 4b: ownership calibration by position (all field players, field_pct>=10%) ====")
    A["gap"] = A.our_own_pct - 100 * A.field_pct
    A["mech"] = np.where(A.slate.str.startswith("wk3"), "wk3 layered+FFC", "wk1-2 heuristic")
    top = A[(A.field_pct >= 0.10) & A.our_own_pct.notna()]
    print(top.groupby(["mech", "our_pos"]).agg(n=("gap", "size"), mean_gap=("gap", "mean"),
                                              mean_field=("field_pct", lambda x: 100 * x.mean()),
                                              mean_ours=("our_own_pct", "mean")).round(1))
    for lab in ["wk1_main", "wk2_main_se3max", "wk3_main_se3max", "wk3_early"]:
        for pos in ["QB", "DST"]:
            g = A[(A.slate == lab) & (A.our_pos == pos) & (A.field_pct >= 0.03)].sort_values("field_pct", ascending=False)
            print(f"\n{lab} {pos}:")
            print(g[["k", "salary", "chalk_score", "our_own_pct", "field_pct", "our_proj", "fpts"]].head(8)
                  .assign(field_pct=lambda d: (100 * d.field_pct).round(1)).round(1).to_string(index=False))

    print("\n==== STEP 5: bias check stratified by salary ====")
    B = A[A.our_own_pct.notna() & A.fpts.notna() & A.our_pos.notna()].copy()
    B["band"] = [salary_band(p, s) for p, s in zip(B.our_pos, B.salary)]
    print(f"overall corr(gap,fpts) n={len(B)}: {B.gap.corr(B.fpts):.3f}")

    def strat(df, label):
        # within-position fpts z so bands with different scoring scales pool fairly
        df = df.copy()
        df["fpts_z"] = df.groupby(["slate", "our_pos"]).fpts.transform(lambda x: (x - x.mean()) / (x.std() or 1))
        rel = df[df.field_pct >= 0.02]
        out = rel.groupby("band").apply(lambda g: pd.Series(dict(
            n=len(g), corr_gap_fpts=g.gap.corr(g.fpts), corr_gap_fptsz=g.gap.corr(g.fpts_z),
            mean_gap=g.gap.mean(), mean_field=100 * g.field_pct.mean())), include_groups=False).round(3)
        print(f"\n{label} (field_pct>=2%):\n{out}")

    strat(B, "ALL positions")
    strat(B[B.our_pos.isin(["WR", "TE"])], "WR+TE")
    strat(B[B.our_pos == "WR"], "WR")
    strat(B[B.our_pos == "TE"], "TE")
    strat(B[B.our_pos.isin(["QB", "RB", "DST"])], "QB+RB+DST")
    strat(B[B.mech == "wk1-2 heuristic"], "ALL, wk1-2 only")
    strat(B[B.mech == "wk3 layered+FFC"], "ALL, wk3 only")

    # robustness: within-position salary quartiles (per slate), all rows with field_pct>=2%
    B["q"] = B.groupby(["slate", "our_pos"]).salary.transform(
        lambda s: pd.qcut(s.rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"]))
    for lab, sub in [("ALL", B), ("WR+TE", B[B.our_pos.isin(["WR", "TE"])])]:
        r = sub[sub.field_pct >= 0.02]
        print(f"\n{lab} by within-position salary quartile (per slate, full pool), field_pct>=2%:")
        print(r.groupby("q", observed=True).apply(lambda g: pd.Series(dict(
            n=len(g), corr_gap_fpts=g.gap.corr(g.fpts), mean_gap=g.gap.mean(),
            mean_field=100 * g.field_pct.mean())), include_groups=False).round(3))
    print("\nper-position corr(gap,fpts), all rows:",
          B.groupby("our_pos").apply(lambda g: round(g.gap.corr(g.fpts), 3), include_groups=False).to_dict())

    print("\n==== STEP 4c: rigor checks ====")
    # (a) base rate: how often did we roster ANY strong-projection (z>=1, field>=5%) player?
    S = A[(A.proj_z_pos >= Z_STRONG) & (A.field_pct >= MIN_FIELD_PCT) & (A.field_n >= MIN_FIELD_N)].copy()
    S["rostered"] = S.my_entries > 0
    S = S.merge(F[["slate", "k", "dir"]], on=["slate", "k"], how="left")
    S["dir"] = S["dir"].fillna("unflagged")
    print("strong-projection players (z>=1, field>=5%): rostered rate by flag status")
    print(S.groupby("dir").rostered.agg(["size", "mean"]).round(3))
    print("same, se3max/single-entry slates only:")
    print(S[~S.slate.str.contains("mme")].groupby("dir").rostered.agg(["size", "mean"]).round(3))
    # (b) chalk ownership error dispersion by mechanism
    top["abs"] = top.gap.abs()
    print("\nchalk (field>=10%) |gap| MAE by mechanism/pos:")
    print(top.groupby(["mech", "our_pos"]).abs.mean().round(1).unstack())
    # (c) wk3 FFC-listing cliff
    w3 = A[A.slate.str.startswith("wk3") & (A.field_pct >= 0.10) & A.our_own_pct.notna()]
    print("\nwk3 chalk (field>=10%) by FFC listing:")
    print(w3.groupby("ffc_listed").agg(n=("gap", "size"), mean_gap=("gap", "mean"),
                                        mae=("gap", lambda x: x.abs().mean()),
                                        mean_field=("field_pct", lambda x: 100 * x.mean())).round(1))
    print(w3[w3.ffc_listed == False][["slate", "k", "our_pos", "our_own_pct", "field_pct"]]  # noqa: E712
          .assign(field_pct=lambda d: (100 * d.field_pct).round(1)).round(1).to_string(index=False))


if __name__ == "__main__":
    main()
