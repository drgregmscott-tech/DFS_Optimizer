"""Parse FC Lineup Study SHOWDOWN contest files into one per-entry feature table.

Input : data/fc_history/lineup_study/*_SHOWDOWN_{SE,big}_*.json.gz   (FC subscription data, gitignored)
Output: data/fc_history/lineup_study/_sd_entries_cache.parquet      (per-entry, gitignored raw-data folder; never commit)
        data/fc_history/derived/showdown/ls_qa.csv                   (per-contest QA, aggregate only)

Schema facts (verified by inspection 2026-09-28, not assumed):
- rows = [rank, entry_id, user, points, cash_amt(cents), player_ids]; player_ids[0] is CPT, [1:] FLEX
  (roster_order = CPT,FLEX x5). CPT slot confirmed below by least-squares: points = 1.5*CPT + sum(FLEX).
- players{id: PlayerId, PlayerName, Team, Salary(FLEX price), SitePos, FC_proj, fantasy_points, cnt, own ...}.
  Some ids carry only {cnt, own} (no metadata), and '<id>_CPTN' keys exist on some slates. We do NOT use
  FC's own%; realized CPT / FLEX rostership is computed directly from the rows (it is the real field).
- players.fantasy_points is wrong on some slates (2022wk12 SE etc.), so player actual scores are re-solved from
  the entry Points by least squares. Missing salaries are recovered from the $50k cap bound.
- cash_amt is all-zero on 2025wk15-17, so payouts are rebuilt from payouts.ranges with tie-splitting and checked
  against cash_amt where present.
"""
import glob, gzip, json, os, re, sys
from collections import Counter, defaultdict
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "data", "fc_history", "lineup_study")
OUT_CACHE = os.path.join(SRC, "_sd_entries_cache.parquet")
OUT_DIR = os.path.join(ROOT, "data", "fc_history", "derived", "showdown")
CAP = 50000


def load(f):
    d = json.load(gzip.open(f))
    return d.get("data", d) if "rows" not in d else d


def global_meta(files):
    meta = {}
    for f in files:
        d = load(f)
        for k, p in d["players"].items():
            if "PlayerId" in p and k not in meta:
                meta[k] = {"pos": p.get("SitePos"), "team": p.get("Team"), "name": p.get("PlayerName")}
    return meta


def rebuild_payouts(ranks, payouts, places_paid):
    rng = {int(k): v for k, v in payouts["ranges"].items()}
    last = int(payouts.get("last_paid_rank") or places_paid)
    starts = sorted(rng)
    prize = np.zeros(len(ranks) + 2)
    for i, s in enumerate(starts):
        e = (starts[i + 1] - 1) if i + 1 < len(starts) else last
        prize[s:min(e, len(ranks)) + 1] = rng[s]
    cnt = Counter(ranks)
    out = {}
    for r, c in cnt.items():
        out[r] = prize[r:r + c].sum() / c if r < len(prize) else 0.0
    return np.array([out[r] for r in ranks])


def solve_scores(lineups, pts, ids):
    """Least-squares player scores from entry points, CPT at 1.5x. Returns dict, max residual."""
    idx = {p: i for i, p in enumerate(ids)}
    uniq = {}
    for lu, p in zip(lineups, pts):
        uniq.setdefault(tuple(lu), p)
    keys = list(uniq)
    if len(keys) > 30000:
        rs = np.random.RandomState(0)
        keys = [keys[i] for i in rs.choice(len(keys), 30000, replace=False)]
    A = np.zeros((len(keys), len(ids)))
    for r, lu in enumerate(keys):
        A[r, idx[lu[0]]] += 1.5
        for p in lu[1:]:
            A[r, idx[p]] += 1.0
    b = np.array([uniq[k] for k in keys])
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = np.abs(A @ x - b)
    return {p: x[i] for p, i in idx.items()}, float(np.percentile(res, 99)), float(res.max())


def cap_bound_salary(lineups, sal):
    """Upper bound on unknown FLEX salaries from the $50k cap (lineups with exactly one unknown)."""
    bound = defaultdict(lambda: 10 ** 9)
    for lu in lineups:
        unk = [(j, p) for j, p in enumerate(lu) if sal.get(p) is None]
        if len(unk) != 1:
            continue
        j, p = unk[0]
        known = sum(sal[q] * (1.5 if k == 0 else 1.0) for k, q in enumerate(lu) if k != j)
        mult = 1.5 if j == 0 else 1.0
        bound[p] = min(bound[p], (CAP - known) / mult)
    return {p: int(np.floor(v / 100.0 + 1e-6) * 100) for p, v in bound.items() if v < 10 ** 8}


def parse(f, gmeta):
    d = load(f)
    c, P, R = d["contest"], d["players"], d["rows"]
    m = re.match(r"(\d{4})wk(\d+)b?_SHOWDOWN_(SE|big)_(\d+)", os.path.basename(f))
    season, week, ctype, cid = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    R = [r for r in R if len(r[5]) == 6]
    n_all = len(d["rows"])
    lineups = [[str(i) for i in r[5]] for r in R]
    pts = np.array([float(r[3]) for r in R])
    ranks = [int(r[0]) for r in R]
    ids = sorted({p for lu in lineups for p in lu})

    # metadata
    meta = {}
    for p in ids:
        q = P.get(p, {})
        g = gmeta.get(p, {})
        meta[p] = {"pos": q.get("SitePos") or g.get("pos"), "team": q.get("Team") or g.get("team"),
                   "sal": q.get("Salary"), "proj": q.get("FC_proj"), "fp_fc": q.get("fantasy_points")}
    sal = {p: meta[p]["sal"] for p in ids}
    n_sal_missing = sum(v is None for v in sal.values())
    # validate cap-bound method on known players (hide each known salary is too slow; use a sample check below)
    recovered = cap_bound_salary(lineups, sal) if n_sal_missing else {}
    for p, v in recovered.items():
        sal[p] = v
    # check: apply the same bound to known players (their bound must be >= true salary; report equality rate)
    chk_eq = np.nan
    if n_sal_missing:
        known = [p for p in ids if meta[p]["sal"] is not None]
        hits = []
        for p in known[:12]:
            s2 = dict(sal); s2[p] = None
            b = cap_bound_salary([lu for lu in lineups if p in lu][:20000], s2).get(p)
            if b is not None:
                hits.append(b == meta[p]["sal"])
        chk_eq = np.mean(hits) if hits else np.nan

    scores, res99, resmax = solve_scores(lineups, pts, ids)
    # CPT-slot sanity: same solve assuming CPT is slot 1 should fit worse
    alt = [[lu[1], lu[0]] + lu[2:] for lu in lineups[:20000]]
    _, alt99, _ = solve_scores(alt, pts[:20000], ids)

    # realized rostership (the real field)
    n = len(R)
    cpt_cnt = Counter(lu[0] for lu in lineups)
    flex_cnt = Counter(p for lu in lineups for p in lu[1:])
    cpt_own = {p: 100.0 * cpt_cnt[p] / n for p in ids}
    flex_own = {p: 100.0 * flex_cnt[p] / n for p in ids}
    dup = Counter(tuple([lu[0]] + sorted(lu[1:])) for lu in lineups)

    # payouts
    cash_c = np.array([float(r[4]) for r in R])
    rebuilt = rebuild_payouts(ranks, d["payouts"], int(c.get("places_paid")))
    have_cash = cash_c.sum() > 0
    pay = cash_c if have_cash else rebuilt
    agree = float(np.mean(np.abs(cash_c - rebuilt) <= 1.0)) if have_cash else np.nan

    teams = [t for t in d["slate"]["Teams"].split(",")]
    teams = sorted({meta[p]["team"] for p in ids if meta[p]["team"]})
    dsts = {p: sal[p] for p in ids if meta[p]["pos"] == "DST" and sal[p] is not None}
    dst_exp = dst_cheap = None
    if len(dsts) == 2 and len(set(dsts.values())) == 2:
        dst_exp = max(dsts, key=dsts.get); dst_cheap = min(dsts, key=dsts.get)
    # team favourite (from FC game_fav) and top-proj
    fav = None
    for q in P.values():
        if q.get("game_fav"):
            fav = q["game_fav"]; break

    recs = []
    for r, lu, pt, py in zip(R, lineups, pts, pay):
        cpt, flex = lu[0], lu[1:]
        pos = [meta[p]["pos"] for p in lu]
        tm = [meta[p]["team"] for p in lu]
        tc = Counter(tm)
        s = [sal[p] for p in lu]
        sal_ok = all(v is not None for v in s)
        proj = [meta[p]["proj"] for p in lu]
        rec = {
            "rank": int(r[0]), "user": r[2], "points": pt, "payout_c": py,
            "cpt_pos": pos[0], "cpt_team": tm[0],
            "stack_n": sum(1 for t in tm[1:] if t == tm[0]),
            "split": "-".join(map(str, sorted(tc.values(), reverse=True))) if len(tc) <= 2 else "?",
            "n_k": pos.count("K"), "n_dst": pos.count("DST"),
            "dst_exp": int(dst_exp in lu) if dst_exp else np.nan,
            "dst_cheap": int(dst_cheap in lu) if dst_cheap else np.nan,
            "cpt_own": cpt_own[cpt], "flex_own_sum": sum(flex_own[p] for p in flex),
            "own_sum": cpt_own[cpt] + sum(flex_own[p] for p in flex),
            "cpt_own_rank": None,
            "dupes": dup[tuple([cpt] + sorted(flex))],
            "sal_used": (1.5 * s[0] + sum(s[1:])) if sal_ok else np.nan,
            "studs": sum(1 for v, ps in zip(s, pos) if ps != "DST" and v is not None and v >= 7000) if sal_ok else np.nan,
            "punts": sum(1 for v, ps in zip(s, pos) if ps != "DST" and v is not None and v <= 4000) if sal_ok else np.nan,
            "cpt_sal": s[0] if s[0] is not None else np.nan,
            "proj_sum": (1.5 * (proj[0] or 0) + sum((x or 0) for x in proj[1:])) if all(x is not None for x in proj) else np.nan,
            "cpt_fav": int(tm[0] == fav) if fav else np.nan,
            "n_fav": sum(1 for t in tm if t == fav) if fav else np.nan,
        }
        # captain + partner: QB CPT with/without a same-team WR/TE; skill CPT with/without own QB in FLEX
        same = [ps for ps, t in zip(pos[1:], tm[1:]) if t == tm[0]]
        if pos[0] == "QB":
            rec["cpt_pair"] = "QB+recv" if ("WR" in same or "TE" in same) else "QB_no_recv"
        elif pos[0] in ("WR", "TE", "RB"):
            rec["cpt_pair"] = pos[0] + ("+ownQB" if "QB" in same else "_noQB")
        else:
            rec["cpt_pair"] = pos[0]
        rec["n_qb"] = pos.count("QB")
        recs.append(rec)
    df = pd.DataFrame(recs)
    # CPT ownership rank within slate (1 = chalk CPT)
    order = sorted(ids, key=lambda p: -cpt_own[p])
    crank = {p: i + 1 for i, p in enumerate(order)}
    df["cpt_own_rank"] = [crank[lu[0]] for lu in lineups]
    # actual-score-based flags: hindsight CPT etc. use solved scores
    df["cpt_pts"] = [scores[lu[0]] for lu in lineups]
    df["season"], df["week"], df["ctype"], df["contest"] = season, week, ctype, cid
    df["n_entries"] = n
    df["cost_c"] = float(c.get("cost") or 0)
    lr = d.get("list_row") or {}
    qa = {
        "file": os.path.basename(f), "season": season, "week": week, "ctype": ctype, "contest": cid,
        "name": c.get("name"), "max_entries": int(c.get("max_entries")), "total_entrants": int(c.get("total_entrants")),
        "rows": n_all, "rows_used": n, "rows_short": n_all - n, "cost_c": c.get("cost"), "list_cost": lr.get("cost"),
        "places_paid": int(c.get("places_paid")), "paid_rows": int((pay > 0).sum()),
        "cash_amt_present": have_cash, "payout_rebuild_agree": agree,
        "score_resid_p99": res99, "score_resid_max": resmax, "alt_cpt_slot1_resid_p99": alt99,
        "fc_fp_agree": float(np.mean([abs((meta[p]["fp_fc"] or 0) - scores[p]) < 0.05 for p in ids])),
        "n_players": len(ids), "sal_missing": n_sal_missing, "sal_recovered": len(recovered),
        "sal_bound_check_eq": chk_eq, "teams": ",".join(teams), "fav": fav,
        "dst_priced_diff": dst_exp is not None,
        "cpt_own_sum": sum(cpt_own.values()), "flex_own_sum": sum(flex_own.values()),
        "unique_lineups": len(dup), "cap_note": "",
    }
    return df, qa


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*_SHOWDOWN_*.json.gz")))
    gmeta = global_meta(glob.glob(os.path.join(SRC, "*.json.gz"))) if "--fullmeta" in sys.argv else global_meta(files)
    dfs, qas = [], []
    for f in files:
        df, qa = parse(f, gmeta)
        dfs.append(df); qas.append(qa)
        print(qa["file"], qa["rows_used"], "resid99=%.3f alt=%.2f" % (qa["score_resid_p99"], qa["alt_cpt_slot1_resid_p99"]),
              "salmiss", qa["sal_missing"], "rec", qa["sal_recovered"], "eq", qa["sal_bound_check_eq"],
              "payagree", qa["payout_rebuild_agree"], flush=True)
    all_ = pd.concat(dfs, ignore_index=True)
    all_.to_parquet(OUT_CACHE)
    os.makedirs(OUT_DIR, exist_ok=True)
    pd.DataFrame(qas).to_csv(os.path.join(OUT_DIR, "ls_qa.csv"), index=False)
    print("entries", len(all_))


if __name__ == "__main__":
    main()
