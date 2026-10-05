"""Weekly construction-rule review (standing post-slate cadence; WK4_POSTMORTEM_CHECKLIST item 2).

Grades every live rule in CLASSIC_RULES.md / SHOWDOWN_RULES.md against the real DK contest exports in
data/contest_results/ for one week (or several), using the same motion as the existing checks:
  - field-wide RAW lift: cash rate (top 25%, same line as replay_validation.CASH_PCT) and top-1% rate of
    lineups with the feature, minus the contest's base rate, in percentage points;
  - field-wide CONTROLLED lift: per-contest linear-probability fit, cash ~ z(our projection sum) +
    z(sum log realized own) + every rule indicator at once (same idea as the FC study's section-5 OLS);
  - sign check against the rule's expected direction, per contest;
  - the owner's own entries (EntryName contains gmscott81), feature by feature;
  - classic only, optional (--replay N): optimizer on/off replay with the CURRENT se3max_pool --cl-* weights,
    N paired 5%-randomized seeds per slate, graded against every real field for that slate
    (logic reused from analysis/classic_shape_weights/replay_cl_arm.py).
  - showdown: DST/K FLEX+CPT modeled vs real ownership (checklist item 8's recurring-underestimate check).

Usage (from repo root):
  python scripts/grade_construction_week.py --week 5               # field grading, ~5-10 min (MME file is the slow part)
  python scripts/grade_construction_week.py --week 5 --replay 20   # + optimizer on/off replay (~30-60 min)
  python scripts/grade_construction_week.py --week 1-5             # pooled season-to-date context
  python scripts/grade_construction_week.py --week 5 --replay 20 --candidate three_plus_punt_penalty=0
                                                                   # + a third replay arm with overridden --cl-* weights
Writes CSVs + report.txt to analysis/weekly_construction_review/out/wk<N>/ (gitignored scratch). Needs the week's
data/contest_results/dk_*_full.csv exports, data/salaries_dk_<slate>.csv and output/final_projections_dk_<slate>.csv.
Run AFTER item-1 grading (same post-slate session). Read the per-contest sign columns first; a rule that flips sign
for 2+ straight weeks is the trigger for a controlled history re-fit (see analysis/wk4_construction_review/).

Caveats printed with the report: one week is 4-6 contests -- this is a DRIFT check against the 410-contest classic /
142-contest showdown evidence base, not a re-derivation. Lineups inside one contest are heavily duplicated, so a
per-contest standard error overstates certainty; read the per-contest sign agreement first.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CR = ROOT / "data" / "contest_results"
CASH_PCT = 0.25
CL_TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")
SD_TOK = re.compile(r"\b(CPT|FLEX)\s+")
FN = re.compile(r"dk_(classic|showdown)_wk(\d+)_(.+?)_(\d{2}[A-Za-z]{3}\d{4})(?:_(mme|se3max))?_full\.csv$")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 500)

# Expected direction from the rule docs: +1 = should help, -1 = should hurt, 0 = documented as no effect.
CL_RULES = {  # indicator -> (expected sign, rule text)
    "dst_band": (+1, "R1 DST $2.8-3.1k (bonus 0.8)"),
    "dst_exp": (-1, "R1 DST $3.6k+ (penalty 2.0)"),
    "zero_punt": (-1, "R2 0 punts (penalty 1.5)"),
    "three_punt": (-1, "R2 3+ punts (penalty 0.5, was 2.5)"),
    "flex_wr_hi": (+1, "R3 FLEX-slot WR $6.3k+ vs TE (bonus 3.0)"),
    "flex_wr_mid": (-1, "R3 FLEX-slot WR $4.9-6.3k vs TE (penalty 1.3)"),
    "flex_wr_lo": (0, "R3 FLEX-slot WR <$4.9k vs TE (no rule)"),
    "flex_rb": (0, "R3 FLEX-slot RB vs TE (dead, 0)"),
    "dst_vs_own": (-1, "R4 DST facing own skill player (hard)"),
}
# The optimizer can't see DK's FLEX slot; it tags the 4th WR as whichever WR maximizes the term (see
# add_classic_shape_terms docstring). So for a 4-WR lineup it fires the bonus if ANY WR is $6.3k+. Lineup-level
# version of the same indicators, graded separately (opt_* columns).
CL_OPT = {
    "opt_wr_hi": (+1, "R3 as the optimizer applies it: 4 WR & any WR $6.3k+ (+3.0)"),
    "opt_wr_mid": (-1, "R3 as the optimizer applies it: 4 WR, all four $4.9-6.3k (-1.3)"),
}
SD_RULES = {
    "wrte_cpt_noqb": (-1, "R13 WR/TE CPT without own QB in FLEX (hard)"),
    "cheap_tier": (-1, "R12 any FLEX $600-1000 (penalty 1.0 SE / 2.0 GPP, per player)"),
    "stack_over3": (0, "4+ FLEX on CPT's team, beyond heavy (stack-cap penalty 0 since 2026-10-05; history +1.3)"),
    "qb_cpt_rbte": (+1, "R11 QB CPT with own RB/TE in FLEX (bonus 0.75 SE / 1.5 GPP)"),
    "heavy_cpt": (-1, "R7 CPT-heavy = 3+ FLEX on CPT team (flat 1.25 SE / 0.5 GPP)"),
    "cpt_k": (-1, "R3 K captain (penalty 1.0 / 1.5)"),
    "cpt_dst": (-1, "R3 DST captain (hard-excluded)"),
    "has_dst": (0, "R6 any DST rostered (Weak; solver's exclude_skill_vs_opp_dst blocks it)"),
    "two_k": (0, "R5 two kickers (Weak)"),
}


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(s.split())


def parse(s, tok):
    p = tok.split(" " + str(s).strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def weeks_arg(w):
    if "-" in str(w):
        a, b = str(w).split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in str(w).split(",")]


def discover(weeks):
    out = []
    for f in sorted(CR.glob("dk_*_full.csv")):
        m = FN.match(f.name)
        if not m or int(m.group(2)) not in weeks:
            continue
        fmt, wk, slate, date, ctype = m.groups()
        sid = f"dk_{fmt}_wk{wk}_{slate}_{date}"
        out.append(dict(fmt=fmt, week=int(wk), slate=slate, sid=sid, ctype=ctype or "", path=f,
                        label=f"wk{wk}_{slate}" + (f"_{ctype}" if ctype else "")))
    return out


def load_contest(path):
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    own = df[["Player", "Roster Position", "%Drafted"]].dropna(subset=["Player"]).copy()
    own["k"] = own.Player.map(norm)
    own["own"] = own["%Drafted"].astype(str).str.rstrip("%").astype(float)
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy()
    e["Rank"] = e.Rank.astype(int)
    N = len(e)
    e["cash"] = (e.Rank <= CASH_PCT * N).astype(float)
    e["top1"] = (e.Rank <= max(1, int(0.01 * N))).astype(float)
    e["top10"] = (e.Rank <= max(1, int(0.10 * N))).astype(float)
    e["mine"] = e.EntryName.astype(str).str.contains("gmscott81", na=False)
    return e, own


def salary_info(sid, showdown):
    s = pd.read_csv(ROOT / "data" / f"salaries_dk_{sid}.csv")
    if showdown:
        s = s[s["Roster Position"] != "CPT"]
    s["k"] = s.Name.map(norm)
    gi = s["Game Info"].astype(str).str.split(" ").str[0].str.split("@")
    s["opp"] = [g[1] if len(g) == 2 and t == g[0] else (g[0] if len(g) == 2 else "") for g, t in zip(gi, s.TeamAbbrev)]
    return s.drop_duplicates("k").set_index("k")[["Position", "Salary", "TeamAbbrev", "opp"]]


def proj_info(sid, showdown):
    f = ROOT / "output" / f"final_projections_dk_{sid}.csv"
    if not f.exists():
        return None
    p = pd.read_csv(f)
    if showdown:
        p = p[p.roster_role == "FLEX"]
    p["k"] = p.player_name.map(norm)
    return p.drop_duplicates("k").set_index("k")


# ---------------------------------------------------------------- classic
def classic_features(c):
    e, own = load_contest(c["path"])
    info = salary_info(c["sid"], False)
    pj = proj_info(c["sid"], False)
    own_map = own.groupby("k").own.sum().to_dict()
    rows, miss = [], 0
    for r in e.itertuples():
        L = [(slot, norm(n)) for slot, n in parse(r.Lineup, CL_TOK)]
        if len(L) != 9 or any(k not in info.index for _, k in L):
            miss += 1
            continue
        pos = {k: info.Position[k] for _, k in L}
        sal = {k: info.Salary[k] for _, k in L}
        dst = [k for s, k in L if s == "DST"][0]
        flex = [k for s, k in L if s == "FLEX"][0]
        skill = [k for _, k in L if k != dst]
        punts = sum(sal[k] <= 4000 for k in skill)
        wr_sal = [sal[k] for k in skill if pos[k] == "WR"]
        fp, fs = pos[flex], sal[flex]
        d = dict(rank=r.Rank, pts=r.Points, cash=r.cash, top1=r.top1, mine=r.mine,
                 dst_sal=sal[dst], punts=punts, flex_pos=fp, flex_sal=fs,
                 dst_band=int(2800 <= sal[dst] <= 3100), dst_exp=int(sal[dst] >= 3600),
                 zero_punt=int(punts == 0), three_punt=int(punts >= 3),
                 flex_rb=int(fp == "RB"), flex_wr_hi=int(fp == "WR" and fs >= 6300),
                 flex_wr_mid=int(fp == "WR" and 4900 <= fs < 6300), flex_wr_lo=int(fp == "WR" and fs < 4900),
                 dst_vs_own=int(any(info.TeamAbbrev[k] == info.opp[dst] for k in skill)),
                 n_wr=len(wr_sal))
        d["opt_wr_hi"] = int(len(wr_sal) == 4 and max(wr_sal) >= 6300)
        d["opt_wr_mid"] = int(len(wr_sal) == 4 and max(wr_sal) < 6300 and min(wr_sal) >= 4900)
        d["proj"] = sum(pj.final_projection.get(k, np.nan) for _, k in L) if pj is not None else np.nan
        d["logown"] = sum(np.log(own_map.get(k, 0.0) + 0.1) for _, k in L)
        rows.append(d)
    d = pd.DataFrame(rows)
    d["dst_b"] = pd.cut(d.dst_sal, [0, 2800, 3200, 3600, 1e9], labels=["<2.8k", "2.8-3.1k", "3.2-3.5k", "3.6k+"], right=False).astype(str)
    d["punt_b"] = np.where(d.punts >= 3, "3+", d.punts.astype(str))
    d["flex_b"] = np.select([d.flex_rb == 1, d.flex_wr_hi == 1, d.flex_wr_mid == 1, d.flex_wr_lo == 1],
                            ["RB", "WR 6.3k+", "WR 4.9-6.3k", "WR <4.9k"], "TE")
    return d, miss, len(e)


def z(s):
    s = s.astype(float)
    return (s - s.mean()) / s.std() if s.std() > 0 else s * 0


def controlled(d, feats, y="cash"):
    """Per-contest LPM: y ~ z(proj) + z(logown) + all rule indicators. Returns coef (pts) per feature."""
    s = d.dropna(subset=["proj"])
    cols = [f for f in feats if s[f].sum() >= 30 and (1 - s[f]).sum() >= 30]
    X = np.column_stack([np.ones(len(s)), z(s.proj), z(s.logown)] + [s[f].astype(float) for f in cols])
    b, *_ = np.linalg.lstsq(X, s[y].astype(float).values, rcond=None)
    res = s[y].values - X @ b
    sig2 = res @ res / max(1, len(s) - X.shape[1])
    se = np.sqrt(np.diag(sig2 * np.linalg.pinv(X.T @ X)))
    return {f: (100 * b[3 + i], 100 * se[3 + i]) for i, f in enumerate(cols)}


def raw_lift(d, f, y="cash"):
    if d[f].sum() < 30:
        return np.nan, d[f].mean()
    return 100 * (d.loc[d[f] == 1, y].mean() - d[y].mean()), d[f].mean()


def level_table(d, col, label):
    base_c, base_t = d.cash.mean(), d.top1.mean()
    g = d.groupby(col).agg(n=("cash", "size"), cash=("cash", "mean"), top1=("top1", "mean"))
    g["share%"] = 100 * g.n / len(d)
    g["cash_lift"] = 100 * (g.cash - base_c)
    g["top1_lift"] = 100 * (g.top1 - base_t)
    g["contest"] = label
    return g.reset_index().rename(columns={col: "level"})[["contest", "level", "n", "share%", "cash_lift", "top1_lift"]]


def grade_rules(per, rules, kind):
    """per: list of (label, dataframe). Returns rule x contest table + summary."""
    rows = []
    for lab, d in per:
        # Slot-based FLEX dummies and the optimizer's lineup-level (opt_*) version overlap, so they get separate fits.
        base = [f for f in rules if not f.startswith("opt_")]
        ctl = controlled(d, base)
        opt = [f for f in rules if f.startswith("opt_")]
        if opt:
            ctl.update({k: v for k, v in controlled(d, [f for f in base if not f.startswith("flex_")] + opt).items()
                        if k.startswith("opt_")})
        for f, (sgn, txt) in rules.items():
            rl, sh = raw_lift(d, f)
            t1, _ = raw_lift(d, f, "top1")
            cb, cse = ctl.get(f, (np.nan, np.nan))
            mine = d.loc[d.mine, f].mean() if d.mine.any() else np.nan
            rows.append(dict(contest=lab, rule=f, expect=sgn, share=100 * sh, raw_cash=rl, raw_top1=t1,
                             ctl_cash=cb, ctl_se=cse, mine_share=100 * mine if mine == mine else np.nan))
    T = pd.DataFrame(rows)

    def agree(x, sgn):
        x = x.dropna()
        if sgn == 0 or not len(x):
            return f"{len(x)} graded"
        return f"{int((np.sign(x) == sgn).sum())}/{len(x)}"

    S = []
    for f, (sgn, txt) in rules.items():
        t = T[T.rule == f]
        S.append(dict(rule=txt, expect={1: "+", -1: "-", 0: "0"}[sgn], field_share=t.share.mean(),
                      raw_cash=t.raw_cash.mean(), raw_sign=agree(t.raw_cash, sgn),
                      ctl_cash=t.ctl_cash.mean(), ctl_sign=agree(t.ctl_cash, sgn),
                      raw_top1=t.raw_top1.mean(), mine_share=t.mine_share.mean()))
    return T, pd.DataFrame(S)


# ---------------------------------------------------------------- showdown
def showdown_features(c):
    e, own = load_contest(c["path"])
    info = salary_info(c["sid"], True)
    pj = proj_info(c["sid"], True)
    own_cpt = own[own["Roster Position"] == "CPT"].groupby("k").own.sum().to_dict()
    own_flex = own[own["Roster Position"] != "CPT"].groupby("k").own.sum().to_dict()
    rows, miss = [], 0
    for r in e.itertuples():
        L = [(slot, norm(n)) for slot, n in parse(r.Lineup, SD_TOK)]
        if len(L) != 6 or any(k not in info.index for _, k in L):
            miss += 1
            continue
        cpt = [k for s, k in L if s == "CPT"][0]
        fl = [k for s, k in L if s == "FLEX"]
        ct, cp = info.TeamAbbrev[cpt], info.Position[cpt]
        same = [k for k in fl if info.TeamAbbrev[k] == ct]
        fpos = [info.Position[k] for k in fl]
        same_pos = [info.Position[k] for k in same]
        allpos = [cp] + fpos
        d = dict(rank=r.Rank, pts=r.Points, cash=r.cash, top1=r.top1, top10=r.top10, mine=r.mine,
                 cpt_pos=cp, same_flex=len(same),
                 wrte_cpt_noqb=int(cp in ("WR", "TE") and "QB" not in same_pos),
                 cheap_tier=int(any(600 <= info.Salary[k] <= 1000 for k in fl)),
                 n_cheap=sum(600 <= info.Salary[k] <= 1000 for k in fl),
                 punt500=int(any(info.Salary[k] <= 500 for k in fl)),
                 stack_over3=int(len(same) >= 4),
                 qb_cpt_rbte=int(cp == "QB" and any(p in ("RB", "TE") for p in same_pos)),
                 heavy_cpt=int(len(same) >= 3), cpt_k=int(cp == "K"), cpt_dst=int(cp == "DST"),
                 has_dst=int("DST" in allpos), two_k=int(allpos.count("K") >= 2))
        d["split"] = f"{max(len(same) + 1, 6 - len(same) - 1)}-{min(len(same) + 1, 5 - len(same))}"
        if pj is not None:
            d["proj"] = 1.5 * pj.final_projection.get(cpt, np.nan) + sum(pj.final_projection.get(k, np.nan) for k in fl)
        else:
            d["proj"] = np.nan
        d["logown"] = np.log(own_cpt.get(cpt, 0) + 0.1) + sum(np.log(own_flex.get(k, 0) + 0.1) for k in fl)
        rows.append(d)
    return pd.DataFrame(rows), miss, len(e)


def sd_dst_k_own(c):
    """Modeled vs real ownership for DST/K rows (checklist item 8)."""
    _, own = load_contest(c["path"])
    p = ROOT / "output" / f"final_projections_dk_{c['sid']}.csv"
    if not p.exists():
        return pd.DataFrame()
    P = pd.read_csv(p)
    P = P[P.position.isin(["DST", "K"])].copy()
    P["k"] = P.player_name.map(norm)
    own["role"] = np.where(own["Roster Position"] == "CPT", "CPT", "FLEX")
    real = own.groupby(["k", "role"]).own.sum()
    P["real_own"] = [real.get((k, r), 0.0) for k, r in zip(P.k, P.roster_role)]
    P["slate"] = c["label"]
    return P[["slate", "player_name", "position", "roster_role", "salary", "estimated_ownership_pct", "real_own"]]


# ---------------------------------------------------------------- classic replay (optimizer on vs off)
def replay(classic, n_seeds, out, candidate=None):
    sys.path.insert(0, str(ROOT / "scripts"))
    import optimizer  # noqa: E402
    presets = json.loads((ROOT / "data" / "optimizer_presets.json").read_text())
    pr = presets["se3max_pool"]
    CL = {k[3:].replace("-", "_"): float(v) for k, v in pr.items() if isinstance(k, str) and k.startswith("cl-")}
    fixed_counts, flex_count = optimizer.parse_roster_requirements(optimizer.SITE_CONFIGS["dk"]["roster_slots"])

    def solve(pool, cl, proj):
        sp = {"WR", "TE"}
        cands, _, _ = optimizer.resolve_stack_candidates(pool, "qb", sp, None, None, None,
                                                         optimizer.DEFAULT_STACK_CANDIDATE_POOL,
                                                         diversify_requested="off", bring_back=True)
        best = None
        for cnd in cands[:5]:
            try:
                sel = optimizer.solve_lineup(pool, optimizer.SITE_CONFIGS["dk"]["salary_cap"], fixed_counts, flex_count,
                                             stack_mode="qb", stack_size=2, stack_positions=sp, bring_back=True,
                                             target_team=cnd["target_team"], flex_positions={"RB", "WR", "TE"},
                                             optimization_projection=proj, **cl)
            except Exception:
                continue
            score = proj.reindex(sel.player_id).sum() + optimizer.classic_shape_adjustment(sel, fixed_counts, **cl)
            if best is None or score > best[0]:
                best = (score, sel)
        return best[1]

    fields = {}
    for c in classic:
        e, own = load_contest(c["path"])
        f = own.drop_duplicates("k")
        df = pd.read_csv(c["path"], encoding="utf-8-sig", low_memory=False, usecols=["Player", "FPTS"]).dropna()
        df["k"] = df.Player.map(norm)
        fields.setdefault(c["sid"], []).append((c["label"], df.drop_duplicates("k").set_index("k").FPTS.to_dict(),
                                                 e.Points.to_numpy(float)))
    rr = []
    for sid, flist in fields.items():
        pool = optimizer.load_final_projections("dk", sid)
        pool = pool[pool.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
        for seed in range(n_seeds):
            proj = optimizer.randomize_projections(pool, 5, np.random.default_rng(seed))
            arms = [("off", {}), ("on", CL)] + ([("cand", {**CL, **candidate})] if candidate else [])
            for arm, cl in arms:
                sel = solve(pool, cl, proj)
                pos, sal = sel.position, sel.salary
                wr = sal[pos == "WR"]
                shape = dict(dst=int(sal[pos.isin(["DST", "DEF"])].iloc[0]),
                             punts=int(((~pos.isin(["DST", "DEF"])) & (sal <= 4000)).sum()),
                             flex=("RB" if (pos == "RB").sum() > 2 else "WR" if len(wr) > 3 else "TE"),
                             wr4_hi=int(len(wr) > 3 and wr.max() >= 6300),
                             proj=float(sel.final_projection.sum()))
                ks = sel.player_name.map(norm)
                for lab, fpts, real in flist:
                    pts = sum(fpts.get(k, 0.0) for k in ks)
                    rank = int((real > pts).sum()) + 1
                    pct = 1 - (rank - 1) / len(real)
                    rr.append(dict(slate=lab, seed=seed, arm=arm, pts=pts, pct=pct, cash=int(pct >= 1 - CASH_PCT), **shape))
    R = pd.DataFrame(rr)
    R.to_csv(out / "replay_arms.csv", index=False)
    W = R.pivot_table(index=["slate", "seed"], columns="arm", values=["pct", "cash", "pts", "proj"])
    d = W["pct"]["on"] - W["pct"]["off"]
    per = d.groupby(level=0).mean()
    lines = [f"weights (se3max_pool): {CL}",
             f"pairs={len(W)}  slates={per.size}  cash off={W['cash']['off'].mean():.3f} on={W['cash']['on'].mean():.3f}  "
             f"pct off={W['pct']['off'].mean():.3f} on={W['pct']['on'].mean():.3f}  paired diff {d.mean():+.3f} "
             f"(slate-level SE {per.std() / np.sqrt(per.size):.3f}; slates up {int((per > 0).sum())}/{per.size})  "
             f"real pts off={W['pts']['off'].mean():.1f} on={W['pts']['on'].mean():.1f}  "
             f"proj off={W['proj']['off'].mean():.1f} on={W['proj']['on'].mean():.1f}",
             "per-slate paired pct diff: " + ", ".join(f"{k} {v:+.3f}" for k, v in per.round(3).items())]
    if candidate:
        dc = W["pct"]["cand"] - W["pct"]["on"]
        pc = dc.groupby(level=0).mean()
        lines.append(f"candidate {candidate} vs current: cash {W['cash']['cand'].mean():.3f} vs {W['cash']['on'].mean():.3f}; "
                     f"pct paired diff {dc.mean():+.3f} (slate SE {pc.std() / np.sqrt(pc.size):.3f}; slates up {int((pc > 0).sum())}/{pc.size}, "
                     f"identical {int((dc == 0).sum())}/{len(dc)} pairs); proj {W['proj']['cand'].mean():.1f}")
    shp = R.drop_duplicates(["slate", "seed", "arm"]).groupby("arm").agg(
        dst_band=("dst", lambda s: s.between(2800, 3100).mean()), dst_exp=("dst", lambda s: (s >= 3600).mean()),
        zero_punt=("punts", lambda s: (s == 0).mean()), three_punt=("punts", lambda s: (s >= 3).mean()),
        flex_rb=("flex", lambda s: (s == "RB").mean()), flex_wr=("flex", lambda s: (s == "WR").mean()),
        flex_te=("flex", lambda s: (s == "TE").mean()), wr4_hi=("wr4_hi", "mean"))
    lines.append(shp.round(3).to_string())
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True, help="week number, '1-4' range, or '3,4' list")
    ap.add_argument("--replay", type=int, default=0, help="classic on/off optimizer replay seeds per slate (0 = skip)")
    ap.add_argument("--skip-showdown", action="store_true")
    ap.add_argument("--skip-classic", action="store_true")
    ap.add_argument("--candidate", default="", help="extra replay arm: current weights overridden, e.g. dst_expensive_penalty=0.4")
    ap.add_argument("--out", default=None, help="output folder (default out/wk<week>)")
    a = ap.parse_args()
    weeks = weeks_arg(a.week)
    out = Path(a.out) if a.out else ROOT / "analysis" / "weekly_construction_review" / "out" / f"wk{a.week}"
    out.mkdir(parents=True, exist_ok=True)
    C = discover(weeks)
    rep = [f"# Construction-rule review, week(s) {a.week}. Cash = top {int(CASH_PCT * 100)}% by rank; lifts in pct pts.",
           "raw = feature rate minus contest base rate; ctl = per-contest LPM coefficient controlling our projection + "
           "realized ownership + all other rule indicators; sign = contests where the effect matches the rule's direction.",
           "This is a drift check against the large evidence base, not a re-derivation."]

    if not a.skip_classic:
        cls = [c for c in C if c["fmt"] == "classic"]
        per, levels = [], []
        for c in cls:
            d, miss, N = classic_features(c)
            d.to_csv(out / f"lineups_{c['label']}.csv.gz", index=False, compression="gzip")
            rep.append(f"classic {c['label']}: {len(d)}/{N} lineups mapped ({miss} unmapped), proj coverage "
                       f"{d.proj.notna().mean():.0%}, my entries {int(d.mine.sum())}")
            per.append((c["label"], d))
            for col in ("dst_b", "punt_b", "flex_b"):
                levels.append(level_table(d, col, c["label"]).assign(feature=col))
        if per:
            T, S = grade_rules(per, {**CL_RULES, **CL_OPT}, "classic")
            T.to_csv(out / "classic_rule_by_contest.csv", index=False)
            S.to_csv(out / "classic_rule_summary.csv", index=False)
            Lv = pd.concat(levels)
            Lv.to_csv(out / "classic_levels.csv", index=False)
            pooled = Lv.groupby(["feature", "level"]).agg(share=("share%", "mean"), cash_lift=("cash_lift", "mean"),
                                                           top1_lift=("top1_lift", "mean"),
                                                           cash_up=("cash_lift", lambda s: f"{int((s > 0).sum())}/{len(s)}"))
            rep += ["\n## CLASSIC rule summary (mean over contests)", S.round(2).to_string(index=False),
                    "\n## CLASSIC level table (mean over contests; cash_up = contests with positive lift)",
                    pooled.round(2).to_string(),
                    "\n## CLASSIC rule x contest", T.round(2).to_string(index=False)]
            if a.replay:
                rep += [f"\n## CLASSIC optimizer replay, {a.replay} paired seeds/slate, current se3max_pool --cl-* on vs off",
                        replay(cls, a.replay, out, {k: float(v) for k, v in (x.split("=") for x in a.candidate.split(",") if x)} or None)]

    if not a.skip_showdown:
        sds = [c for c in C if c["fmt"] == "showdown"]
        per, own_rows = [], []
        for c in sds:
            d, miss, N = showdown_features(c)
            d.to_csv(out / f"lineups_{c['label']}.csv.gz", index=False, compression="gzip")
            rep.append(f"showdown {c['label']}: {len(d)}/{N} lineups mapped ({miss} unmapped), proj coverage "
                       f"{d.proj.notna().mean():.0%}, my entries {int(d.mine.sum())}")
            per.append((c["label"], d))
            own_rows.append(sd_dst_k_own(c))
        if per:
            T, S = grade_rules(per, SD_RULES, "showdown")
            T.to_csv(out / "showdown_rule_by_contest.csv", index=False)
            S.to_csv(out / "showdown_rule_summary.csv", index=False)
            lv = []
            for lab, d in per:
                for col in ("cpt_pos", "split", "same_flex"):
                    lv.append(level_table(d, col, lab).assign(feature=col))
            Lv = pd.concat(lv)
            Lv.to_csv(out / "showdown_levels.csv", index=False)
            O = pd.concat(own_rows) if own_rows else pd.DataFrame()
            O.to_csv(out / "showdown_dst_k_ownership.csv", index=False)
            rep += ["\n## SHOWDOWN rule summary (mean over slates)", S.round(2).to_string(index=False),
                    "\n## SHOWDOWN levels by slate", Lv.round(2).to_string(index=False),
                    "\n## SHOWDOWN rule x slate", T.round(2).to_string(index=False),
                    "\n## SHOWDOWN DST/K modeled vs real ownership (checklist item 8)", O.round(1).to_string(index=False)]

    txt = "\n".join(rep)
    (out / "report.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
