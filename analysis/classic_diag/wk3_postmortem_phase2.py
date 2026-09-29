"""Phase 2 -- construction-level diagnostics for the Wk1-3 postmortem (WK3_ROOT_CAUSE_FINDINGS.md).

Reuses Step 1 parsing (SLATES, norm, parse_lineup, load_our_model) from wk3_postmortem_phase1.py,
load_entries from wk3_postmortem_phase1_v2.py, and the Phase 1 players CSV (field %, salary, team).

  Part 1  Chalk baseline: from the top-5 field-owned players per position (QB/RB/WR/TE/DST),
          enumerate every valid DK classic lineup (QB, 2RB, 3WR, TE, FLEX, DST, <= $50,000).
          Report (a) the max-total-ownership lineup, (b) max-ownership with a QB+own-WR/TE stack,
          (c) the distribution of all valid top-5 lineups (cash rate). Score vs real field.
  Part 2  Pool shape: per entry -- QB stack size, bring-back, RB-DST / QB-DST conflicts, salary
          used, studs (>= $7,000 non-DST), punts (<= $4,000 non-DST), total field ownership,
          FLEX position. Compare cashing field vs non-cashing field vs gmscott81 entries.
          Plus: stack rate on the Phase 1 pairing-driven QB+WR1 pairs, field-cashing vs ours.

usage: python analysis/classic_diag/wk3_postmortem_phase2.py
Outputs: analysis/classic_diag/wk3_postmortem_phase2_{chalk,shape,pairs}.csv
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wk3_postmortem_phase1 import SLATES, norm, parse_lineup, load_our_model  # noqa: E402
from wk3_postmortem_phase1_v2 import load_entries  # noqa: E402

CAP = 50000
TOPN = 5
STUD, PUNT = 7000, 4000


def chalk_pool(P):
    pool = {}
    for pos in ["QB", "RB", "WR", "TE", "DST"]:
        g = P[(P.our_pos == pos) & P.salary.notna() & P.fpts.notna()]
        pool[pos] = g.nlargest(TOPN, "field_pct")
    return pool


def enum_lineups(pool):
    """All valid lineups from top-N per position. Returns DataFrame: own, pts, sal, stack, keys."""
    rec = lambda d: list(d[["k", "field_pct", "fpts", "salary", "team"]].itertuples(index=False))  # noqa: E731
    Q, R, W, T, D = (rec(pool[p]) for p in ["QB", "RB", "WR", "TE", "DST"])
    out = []
    for q in Q:
        for d in D:
            for t in T:
                for rr in itertools.combinations(R, 2):
                    for ww in itertools.combinations(W, 3):
                        used = {x.k for x in (*rr, *ww, t)}
                        flex = [x for x in (*R, *W, *T) if x.k not in used]
                        base = (q, d, t, *rr, *ww)
                        for f in flex:
                            L = base + (f,)
                            # dedupe flex/slot permutations: require flex key > same-pos slot keys ordering
                            sal = sum(x.salary for x in L)
                            if sal > CAP:
                                continue
                            ks = frozenset(x.k for x in L)
                            stack = sum(1 for x in (*rr, *ww, t, f) if x.team == q.team and x in (*W, *T))
                            out.append((ks, sum(x.field_pct for x in L), sum(x.fpts for x in L), sal, stack))
    df = pd.DataFrame(out, columns=["keys", "own", "pts", "sal", "stk"]).drop_duplicates("keys")
    return df


def part1(lab, e, P, cash_pct):
    pts_sorted = np.sort(e.Points.values)[::-1]
    N = len(pts_sorted)
    cash_n = int(np.floor(N * cash_pct))
    cash_line = pts_sorted[cash_n - 1]
    rank_of = lambda s: int((pts_sorted > s).sum()) + 1  # noqa: E731
    L = enum_lineups(chalk_pool(P))
    top = L.nlargest(1, "own").iloc[0]
    st = L[L.stk >= 1]
    tops = st.nlargest(1, "own").iloc[0] if len(st) else None
    mine = e[e.mine]
    r = dict(slate=lab, N=N, cash_line=cash_line, n_valid=len(L),
             chalk_pts=top.pts, chalk_own=top.own, chalk_rank=rank_of(top.pts),
             chalk_pctile=rank_of(top.pts) / N, chalk_cash=top.pts >= cash_line,
             chalkstack_pts=tops.pts if tops is not None else np.nan,
             chalkstack_rank=rank_of(tops.pts) if tops is not None else np.nan,
             chalkstack_cash=(tops.pts >= cash_line) if tops is not None else np.nan,
             top5_all_cashrate=(L.pts >= cash_line).mean(), top5_all_median_pts=L.pts.median(),
             top5_all_median_pctile=rank_of(L.pts.median()) / N,
             my_n=len(mine), my_best=mine.Points.max(), my_mean=mine.Points.mean(),
             my_best_rank=rank_of(mine.Points.max()) if len(mine) else np.nan,
             my_mean_pctile=np.mean([rank_of(p) / N for p in mine.Points]) if len(mine) else np.nan,
             my_cashes=int((mine.Points >= cash_line).sum()),
             field_mean=e.Points.mean())
    r["chalk_minus_mybest"] = r["chalk_pts"] - r["my_best"]
    r["chalk_minus_mymean"] = r["chalk_pts"] - r["my_mean"]
    r["chalk_lineup"] = ", ".join(sorted(top["keys"]))
    return r


def entry_shape(e, P, opp):
    team = P.set_index("k").team.to_dict()
    pos = P.set_index("k").our_pos.to_dict()
    sal = P.set_index("k").salary.to_dict()
    own = P.set_index("k").field_pct.to_dict()
    rows = []
    for L, c, m, pts in zip(e.Lineup, e.cash, e.mine, e.Points):
        pl = parse_lineup(L)
        ks = [norm(nm) for _, nm in pl]
        slots = [s for s, _ in pl]
        qbs = [k for k in ks if pos.get(k) == "QB"]
        dst = [k for k in ks if pos.get(k) == "DST"]
        qb = qbs[0] if qbs else None
        qt = team.get(qb)
        stack = sum(1 for k in ks if k != qb and pos.get(k) in ("WR", "TE") and qt and team.get(k) == qt)
        stack_rb = sum(1 for k in ks if k != qb and pos.get(k) in ("WR", "TE", "RB") and qt and team.get(k) == qt)
        ot = opp.get(qt)
        bring = sum(1 for k in ks if pos.get(k) in ("WR", "TE", "RB") and ot and team.get(k) == ot)
        dt = team.get(dst[0]) if dst else None
        dst_vs = sum(1 for k in ks if pos.get(k) != "DST" and dt and team.get(k) == opp.get(dt))
        nd = [k for k in ks if pos.get(k) != "DST"]
        flex_k = ks[slots.index("FLEX")] if "FLEX" in slots else None
        s = [sal.get(k, np.nan) for k in ks]
        rows.append(dict(cash=c, mine=m, pts=pts,
                         stack=stack, stack_any=stack_rb, bringback=bring, dst_vs_own_players=dst_vs,
                         salary=np.nansum(s), sal_known=int(np.sum(~np.isnan(s))),
                         studs=sum(1 for k in nd if sal.get(k, 0) >= STUD),
                         punts=sum(1 for k in nd if 0 < sal.get(k, 99999) <= PUNT),
                         own_sum=100 * sum(own.get(k, 0) for k in ks),
                         flex_pos=pos.get(flex_k), qb_sal=sal.get(qb, np.nan),
                         dst_sal=sal.get(dst[0], np.nan) if dst else np.nan))
    return pd.DataFrame(rows)


def pairs_check(lab, e, P, flags):
    """Phase 1 pairing-driven rows: rate each group rostered X+partner (the stack)."""
    f = flags[(flags.slate == lab) & (flags.pair_note == "pairing-driven")]
    out = []
    for _, r in f.iterrows():
        hx = e["keys"].map(lambda s: r.k in s)
        hp = e["keys"].map(lambda s: r.partner in s)
        both = hx & hp
        grp = {"cash": e.cash & ~e.mine, "noncash": ~e.cash & ~e.mine, "mine": e.mine}
        rec = dict(slate=lab, dir=r.dir, k=r.k, partner=r.partner, lift=r.lift,
                   lift_with=r.lift_with, lift_without=r.lift_without)
        for g, msk in grp.items():
            n = msk.sum()
            rec[f"{g}_n"] = int(n)
            rec[f"{g}_pair_rate"] = both[msk].mean() if n else np.nan
            rec[f"{g}_x_rate"] = hx[msk].mean() if n else np.nan
        out.append(rec)
    return out


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    Pall = pd.read_csv(HERE / "wk3_postmortem_v2_players.csv")
    flags = pd.read_csv(HERE / "wk3_postmortem_v2_flags.csv")
    chalk, shapes, pairs = [], [], []
    for lab, (f, sid, cash_pct) in SLATES.items():
        e, fpts, N, cash_n = load_entries(f, cash_pct)
        P = Pall[Pall.slate == lab].copy()
        our = load_our_model(sid)
        opp = {}
        if our is not None:
            opp = our.dropna(subset=["team", "opponent"]).drop_duplicates("team").set_index("team").opponent.to_dict()
        chalk.append(part1(lab, e, P, cash_pct))
        S = entry_shape(e, P, opp)
        S["slate"] = lab
        shapes.append(S)
        pairs += pairs_check(lab, e, P, flags)
        print(f"{lab}: done ({N} entries, mine {int(e.mine.sum())})")
    C = pd.DataFrame(chalk)
    S = pd.concat(shapes, ignore_index=True)
    PR = pd.DataFrame(pairs)
    C.to_csv(HERE / "wk3_postmortem_phase2_chalk.csv", index=False)
    PR.to_csv(HERE / "wk3_postmortem_phase2_pairs.csv", index=False)

    print("\n==== PART 1: chalk baseline ====")
    cc = ["slate", "N", "cash_line", "n_valid", "chalk_pts", "chalk_own", "chalk_rank", "chalk_pctile", "chalk_cash",
          "chalkstack_pts", "chalkstack_cash", "top5_all_cashrate", "top5_all_median_pts",
          "my_n", "my_best", "my_mean", "my_best_rank", "my_mean_pctile", "my_cashes", "field_mean"]
    print(C[cc].round(3).to_string(index=False))
    for _, r in C.iterrows():
        print(f"  {r.slate}: {r.chalk_lineup}")
    se = C[~C.slate.str.contains("mme")]
    print(f"\nSE slates (9): chalk cashes {int(se.chalk_cash.sum())}/9, chalk+stack cashes "
          f"{int(se.chalkstack_cash.sum())}/9, mine cashes {int((se.my_cashes > 0).sum())}/9; "
          f"chalk beat my entry on {int((se.chalk_pts > se.my_best).sum())}/9; "
          f"mean chalk-mine {se.chalk_minus_mybest.mean():+.1f}; mean top5-universe cash rate {se.top5_all_cashrate.mean():.3f}")
    mm = C[C.slate.str.contains("mme")]
    print(mm[["slate", "chalk_pts", "my_best", "my_mean", "my_cashes", "my_n", "chalk_cash", "top5_all_cashrate"]])

    print("\n==== PART 2: pool shape (cash-field vs noncash-field vs mine) ====")
    S["grp"] = np.where(S.mine, "mine", np.where(S.cash, "field_cash", "field_noncash"))
    S["stack1"] = S["stack"] >= 1
    S["stack2"] = S["stack"] >= 2
    S["naked"] = S.stack_any == 0
    S["bb1"] = S.bringback >= 1
    S["dst_conflict"] = S.dst_vs_own_players >= 1
    S["flex_rb"] = S.flex_pos == "RB"
    S["flex_te"] = S.flex_pos == "TE"
    agg = dict(n=("pts", "size"), stack1=("stack1", "mean"), stack2=("stack2", "mean"), naked=("naked", "mean"),
               bringback=("bb1", "mean"), dst_conflict=("dst_conflict", "mean"), salary=("salary", "mean"),
               studs=("studs", "mean"), punts=("punts", "mean"), own_sum=("own_sum", "mean"),
               flex_rb=("flex_rb", "mean"), flex_te=("flex_te", "mean"), qb_sal=("qb_sal", "mean"),
               dst_sal=("dst_sal", "mean"))
    G = S.groupby(["slate", "grp"]).agg(**agg).round(3)
    G.to_csv(HERE / "wk3_postmortem_phase2_shape.csv")
    print(G.to_string())
    S["is_mme"] = S.slate.str.contains("mme")
    for lbl, sub in [("SE/single-entry slates pooled", S[~S.is_mme]), ("MME slates pooled", S[S.is_mme]),
                     ("all pooled", S)]:
        print(f"\n{lbl}:")
        print(sub.groupby("grp").agg(**agg).round(3).to_string())
    # cash rate by shape bucket in the field (does shape matter at all?)
    F = S[~S.mine]
    print("\nfield cash rate by stack size (all slates pooled, base-rate adjusted per slate):")
    F = F.assign(base=F.groupby("slate").cash.transform("mean"))
    for col in ["stack", "studs", "punts", "bringback"]:
        t = F.groupby(F[col].clip(upper=3)).apply(lambda g: pd.Series(dict(n=len(g), lift=(g.cash - g.base).mean())),
                                                  include_groups=False).round(3)
        print(f"  {col}:\n{t.to_string()}")
    F["sal_left"] = CAP - F.salary
    F["sal_bin"] = pd.cut(F.sal_left, [-1, 0, 200, 500, 1000, 2000, 50000])
    print(F.groupby("sal_bin", observed=True).apply(lambda g: pd.Series(dict(n=len(g), lift=(g.cash - g.base).mean())),
                                                  include_groups=False).round(3))
    M = S[S.mine]
    M["sal_bin"] = pd.cut(CAP - M.salary, [-1, 0, 200, 500, 1000, 2000, 50000])
    print("mine sal_left distribution:", M.sal_bin.value_counts().sort_index().to_dict())
    print("per-slate mine shape rows:")
    print(M[["slate", "pts", "cash", "stack", "bringback", "studs", "punts", "salary", "own_sum", "flex_pos"]]
          .round(1).to_string(index=False))

    print("\n==== PART 2b: Phase 1 pairing-driven stacks: field-cash vs mine ====")
    print(PR.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
