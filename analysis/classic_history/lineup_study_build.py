"""Parse FC Lineup Study CLASSIC contest files into per-entry and per-player feature tables.

Input : data/fc_history/lineup_study/*.json.gz, excluding *_SHOWDOWN_* and *_LIST   (FC subscription data; never commit)
        (set FC_LS_DIR to point elsewhere, e.g. the main checkout when running from a worktree)
Output (all gitignored, raw-derived; never commit):
        data/fc_history/derived/classic/entries/<file>.parquet   one row per entry, one file per contest
        data/fc_history/derived/classic/players/<file>.parquet   one row per player per contest (field / cash / top rostership)
Output (aggregate only, committed):
        analysis/classic_history/out/cl_qa.csv                   per-contest QA (no entry- or player-level data)

Schema (verified by inspection 2026-09-29):
- rows = [rank, entry_id, user, points, cash_amt(cents), player_ids]; roster_order QB,RB,RB,WR,WR,WR,TE,FLEX,DST
  (checked on every file below; a file with a different roster_order is skipped and logged).
- players{id: PlayerId, PlayerName, Team, Salary, SitePos, FC_proj, fantasy_points, cnt, own, game, game_total, game_fav,
  game_spread, team_pts, proj_own}. A few ids carry only {cnt, own}; their pos/team/game come from other files of the same
  week (then same season, then any season). Their score is solved from entries with exactly one unknown
  (points - known sum), their salary from the $50k cap bound.
- Checks per file: sum of FC fantasy_points vs entry points (if p99 residual > 0.05, all scores are re-solved by sparse
  least squares); salary > cap lineups (a mis-priced player is repaired from the cap bound); realized vs FC own%;
  cash_amt vs payout table rebuild.
- 2026-10-06: entries also carry lineup-level WR columns (n_wr, wr_sal_min/2nd/3rd/4th/max, n_wr_hp, share_wr_hp,
  wr_min_proj, wr_min_own) for the FLEX-WR lineup-level test (analysis/wk4_construction_review/). Additive only.
"""
import glob, gzip, json, os, re, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.environ.get("FC_LS_DIR", os.path.join(ROOT, "data", "fc_history", "lineup_study"))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic")
OUT_QA = os.path.join(ROOT, "analysis", "classic_history", "out")
CAP = 50000
ORDER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
POSC = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "DST": 4}
ME = "gmscott81"


def load(f):
    d = json.load(gzip.open(f))
    return d.get("data", d) if "rows" not in d else d


def fname_info(f):
    m = re.match(r"(\d{4})wk(\d+)(b?)_(.+)_(\d+)\.json\.gz$", os.path.basename(f))
    season, week, b, typ, cid = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)
    return season, week, b, typ, cid


def group_type(typ, cost_c, max_entries):
    if typ.startswith("SE"):
        return "SE"
    if typ == "3MAX":
        return "3MAX"
    if typ.startswith("20MAX"):
        return "20MAX"
    if typ == "DOUBLEUP":
        return "DU"
    return typ


def pmeta(p):
    g = p.get("game") or ""
    t = p.get("Team")
    opp = None
    if "_" in g and t:
        a, b = g.split("_", 1)
        opp = b if t == a else (a if t == b else None)
    return {"pos": p.get("SitePos"), "team": t, "opp": opp, "name": p.get("PlayerName")}


def rebuild_payouts(ranks, payouts, places_paid):
    rng = {int(k): v for k, v in payouts["ranges"].items()}
    last = int(payouts.get("last_paid_rank") or places_paid)
    starts = sorted(rng)
    top = max(max(ranks) if len(ranks) else 0, last) + 2
    prize = np.zeros(top + 1)
    for i, s in enumerate(starts):
        e = (starts[i + 1] - 1) if i + 1 < len(starts) else last
        prize[s:min(e, top) + 1] = rng[s]
    cnt = Counter(ranks)
    out = {r: prize[r:r + c].sum() / c for r, c in cnt.items()}
    return np.array([out[r] for r in ranks])


def lsq_scores(M, pts, npl):
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import lsqr
    n = len(M)
    A = csr_matrix((np.ones(n * 9), (np.repeat(np.arange(n), 9), M.ravel())), shape=(n, npl))
    x = lsqr(A, pts, atol=1e-10, btol=1e-10, iter_lim=5000)[0]
    return x, np.abs(A @ x - pts)


def parse(f, wmeta, smeta, gmeta):
    season, week, b, typ, cid = fname_info(f)
    d = load(f)
    c, P, R0 = d["contest"], d["players"], d["rows"]
    qa = {"file": os.path.basename(f), "season": season, "week": week, "slate_b": b, "type": typ, "contest": cid,
          "name": c.get("name"), "max_entries": int(c.get("max_entries") or 0), "total_entrants": int(c.get("total_entrants") or 0),
          "cost_c": float(c.get("cost") or 0), "places_paid": int(c.get("places_paid") or 0), "rows": len(R0),
          "roster_order_ok": list(c.get("roster_order") or []) == ORDER}
    qa["ctype"] = group_type(typ, qa["cost_c"], qa["max_entries"])
    if not qa["roster_order_ok"]:
        return None, None, qa
    R = [r for r in R0 if len(r[5]) == 9]
    n = len(R)
    qa["rows_used"] = n
    qa["rows_short"] = len(R0) - n
    qa["rows_vs_entrants"] = len(R0) / max(1, qa["total_entrants"])
    ids = sorted({str(i) for r in R for i in r[5]})
    idx = {p: i for i, p in enumerate(ids)}
    npl = len(ids)
    M = np.array([[idx[str(i)] for i in r[5]] for r in R], dtype=np.int32)
    pts = np.array([float(r[3]) for r in R])
    ranks = np.array([int(r[0]) for r in R])
    is_me = np.array([r[2] == ME for r in R])

    # --- player metadata
    pos = np.full(npl, -1, np.int8); team = np.empty(npl, object); opp = np.empty(npl, object)
    sal = np.full(npl, np.nan); proj = np.full(npl, np.nan); fp = np.full(npl, np.nan)
    fc_own = np.full(npl, np.nan); proj_own = np.full(npl, np.nan); gtot = np.full(npl, np.nan)
    src = Counter()
    for p, i in idx.items():
        q = P.get(p, {})
        if "PlayerId" in q:
            m = pmeta(q); src["file"] += 1
            if q.get("Salary") not in (None, 0, "0", ""):
                sal[i] = float(q["Salary"])
            if q.get("FC_proj") not in (None, ""):
                proj[i] = float(q["FC_proj"])
            if q.get("fantasy_points") not in (None, ""):
                fp[i] = float(q["fantasy_points"])
            if q.get("proj_own") not in (None, ""):
                proj_own[i] = float(q["proj_own"])
            if q.get("game_total") not in (None, ""):
                gtot[i] = float(q["game_total"])
        else:
            m = wmeta.get(p) or smeta.get(p) or gmeta.get(p) or {}
            src["week" if p in wmeta else "season" if p in smeta else "global" if p in gmeta else "none"] += 1
            if p in wmeta and wmeta[p].get("sal"):
                sal[i] = wmeta[p]["sal"]
        if q.get("own") not in (None, ""):
            try:
                fc_own[i] = float(q["own"])
            except ValueError:
                pass
        pos[i] = POSC.get(m.get("pos"), -1); team[i] = m.get("team"); opp[i] = m.get("opp")
    qa.update({"meta_" + k: v for k, v in src.items()})
    qa["n_players"] = npl

    # verify the DST slot really is DST and QB slot QB (roster order sanity)
    qa["slot_qb_is_qb"] = float(np.mean(pos[M[:, 0]] == 0))
    qa["slot_dst_is_dst"] = float(np.mean(pos[M[:, 8]] == 4))
    qa["slot_te_is_te"] = float(np.mean(pos[M[:, 6]] == 3))

    # --- salary: repair / recover from the cap bound
    # position fallback from fixed roster slots (QB/RB/WR/TE/DST slots) when no metadata anywhere
    slotpos = np.array([0, 1, 1, 2, 2, 2, 3, -1, 4])
    for i in np.where(pos < 0)[0]:
        rs, cs = np.where(M == i)
        sp = slotpos[cs]; sp = sp[sp >= 0]
        if len(sp):
            pos[i] = np.bincount(sp).argmax()
    qa["pos_unknown_after_slot"] = int((pos < 0).sum())
    s0 = np.nan_to_num(sal)
    lin_sum = s0[M].sum(1)
    known_all = ~np.isnan(sal)[M].any(1)
    slack = CAP - lin_sum
    # a handful of entries exceed the cap with FC's listed salaries (late swap / repricing); keep them, but do not let
    # them drive the cap bound unless it is widespread
    if np.mean((slack < 0) & known_all) < 0.01:
        slack = np.where((slack < 0) & known_all, np.inf, slack)
    minslack = np.full(npl, np.inf)
    np.minimum.at(minslack, M.ravel(), np.repeat(slack, 9))
    bound = np.floor((s0 + minslack) / 100 + 1e-6) * 100
    qa["sal_missing"] = int(np.isnan(sal).sum())
    qa["lineups_over_cap_raw"] = float(np.mean(lin_sum > CAP))
    known_used = (~np.isnan(sal)) & np.isfinite(minslack)
    over = known_used & (sal > bound)
    qa["sal_overpriced_players"] = int(over.sum())
    qa["sal_overpriced_names"] = ";".join(f"{ids[i]}:{int(sal[i])}->{int(bound[i])}" for i in np.where(over)[0][:6])
    # bound check on known players with >=200 lineups: how often does the bound equal the true salary?
    cnt = np.bincount(M.ravel(), minlength=npl)
    ok = known_used & (cnt >= 200) & ~over
    qa["sal_bound_eq_rate"] = float(np.mean(bound[ok] == sal[ok])) if ok.any() else np.nan
    sal = np.where(over, bound, sal)
    miss = np.isnan(sal) & np.isfinite(minslack)
    sal[miss] = bound[miss]
    qa["sal_recovered"] = int(miss.sum())
    qa["lineups_over_cap_fixed"] = float(np.mean(np.nan_to_num(sal)[M].sum(1) > CAP))

    # --- scores
    unk = np.isnan(fp)
    known_sum = np.nan_to_num(fp)[M].sum(1)
    nunk = unk[M].sum(1)
    full = nunk == 0
    resid = np.abs(known_sum - pts)
    qa["fp_resid_p99"] = float(np.percentile(resid[full], 99)) if full.any() else np.nan
    qa["fp_resid_frac_bad"] = float(np.mean(resid[full] > 0.05)) if full.any() else np.nan
    qa["fp_unknown_players"] = int(unk.sum())
    qa["score_method"] = "fc"
    if full.any() and qa["fp_resid_p99"] > 0.05:
        x, res = lsq_scores(M, pts, npl)
        fp = x; qa["score_method"] = "lsq"; qa["lsq_resid_p99"] = float(np.percentile(res, 99))
    elif unk.any():
        one = nunk == 1
        est = defaultdict(list)
        for r in np.where(one)[0][:200000]:
            j = [p for p in M[r] if unk[p]][0]
            est[j].append(pts[r] - known_sum[r])
        for j, v in est.items():
            fp[j] = float(np.median(v))
        still = np.isnan(fp)
        if still.any():
            x, res = lsq_scores(M, pts, npl)
            fp[still] = x[still]; qa["score_method"] = "fc+lsq_unknown"
        else:
            qa["score_method"] = "fc+single_unknown"
    fin = np.nan_to_num(fp)[M].sum(1)
    qa["score_final_resid_p99"] = float(np.percentile(np.abs(fin - pts), 99))

    # --- payouts
    cash_c = np.array([float(r[4]) for r in R])
    rebuilt = rebuild_payouts(list(ranks), d["payouts"], qa["places_paid"])
    have = cash_c.sum() > 0
    pay = cash_c if have else rebuilt
    qa["cash_amt_present"] = bool(have)
    qa["payout_rebuild_agree"] = float(np.mean(np.abs(cash_c - rebuilt) <= 1.0)) if have else np.nan
    qa["paid_rows"] = int((pay > 0).sum()); qa["cash_rate"] = float(np.mean(pay > 0))
    qa["prizepool_c"] = float(c.get("prizepool") or 0); qa["paid_sum_c"] = float(pay.sum())

    # --- realized ownership (the real field)
    rost = cnt / n * 100.0
    fo = ~np.isnan(fc_own) & (rost >= 1)
    qa["fc_own_mae"] = float(np.mean(np.abs(fc_own[fo] - rost[fo]))) if fo.any() else np.nan
    projok = np.isfinite(proj) & (proj > 0)
    proj_f = np.where(projok, proj, 0.0)
    qa["lineups_with_noproj_player"] = float(np.mean((~projok)[M].any(1)))

    # --- per-entry features (vectorized)
    P9 = pos[M]; S9 = sal[M]; T9 = team[M]; O9 = opp[M]
    qb_t = T9[:, 0]; qb_o = O9[:, 0]
    same = (T9 == qb_t[:, None])
    isWR, isTE, isRB, isDST = (P9 == 2), (P9 == 3), (P9 == 1), (P9 == 4)
    stack_rec = ((isWR | isTE) & same).sum(1)
    stack_rb = (isRB & same).sum(1)
    oppm = (T9 == qb_o[:, None]) & ~isDST & (P9 != 0)
    bb = oppm.sum(1)
    nondst = ~isDST
    studs = ((S9 >= 7000) & nondst).sum(1)
    punts = ((S9 <= 4000) & nondst).sum(1)
    dst_t = T9[:, 8]; dst_o = O9[:, 8]
    dst_conf = ((T9[:, :8] == dst_o[:, None])).sum(1)
    dst_own_rb = ((T9[:, :8] == dst_t[:, None]) & isRB[:, :8]).sum(1)
    tc = np.zeros(n, np.int8)
    games = np.zeros(n, np.int8)
    for r in range(n):
        ct = Counter(T9[r, :8]); tc[r] = max(ct.values())
    # games represented (team or opp pair)
    gkey = np.array([("|".join(sorted([str(a), str(b)]))) for a, b in zip(team, opp)], object)
    G9 = gkey[M]
    qb_game = G9[:, 0]
    game_n = (G9[:, :8] == qb_game[:, None]).sum(1)  # QB game stack size incl. QB
    for r in range(n):
        games[r] = len(set(G9[r]))
    dupkey = pd.Series([tuple(sorted(x)) for x in M.tolist()])
    dupes = dupkey.map(dupkey.value_counts()).values
    rank_own = np.argsort(np.argsort(-rost))  # 0 = most owned overall
    # every WR's own salary, lineup level (2026-10-06 FLEX-WR lineup-level rebuild; additive columns).
    # DK's FLEX can be any of the 4 WRs, so these ignore slot placement. Sorted ascending, NaN-padded (3-WR lineups
    # have wr_sal_4th = NaN); wr_sal_max is always the priciest WR. n_wr_hp uses optimizer CL_FLEX_WR_HIGH_MIN (6300).
    n_wr = isWR.sum(1)
    WS = np.sort(np.where(isWR, S9, np.inf), axis=1)[:, :4]
    WS = np.where(np.isinf(WS), np.nan, WS)
    wr_max = np.nanmax(np.where(isWR, S9, -np.inf), axis=1)
    n_wr_hp = (isWR & (S9 >= 6300)).sum(1)
    cheap_col = np.argmin(np.where(isWR, np.nan_to_num(S9, nan=1e9), np.inf), axis=1)
    cheap_pid = M[np.arange(n), cheap_col]
    qbs = np.where(pos == 0)[0]
    qb_own_rank = {q: k + 1 for k, q in enumerate(sorted(qbs, key=lambda q: -rost[q]))}
    qb_sal_rank = {}
    rostered_qbs = [q for q in qbs if rost[q] >= 0.5]
    for k, q in enumerate(sorted(rostered_qbs, key=lambda q: -np.nan_to_num(sal[q]))):
        qb_sal_rank[q] = k + 1
    ent = pd.DataFrame({
        "rank": ranks.astype(np.int32), "points": pts.astype(np.float32), "payout_c": pay.astype(np.float32),
        "is_me": is_me,
        "qb_sal": S9[:, 0].astype(np.float32), "qb_own": rost[M[:, 0]].astype(np.float32),
        "qb_proj": proj_f[M[:, 0]].astype(np.float32), "qb_pts": np.nan_to_num(fp)[M[:, 0]].astype(np.float32),
        "qb_own_rank": np.array([qb_own_rank.get(q, 99) for q in M[:, 0]], np.int16),
        "qb_sal_rank": np.array([qb_sal_rank.get(q, 99) for q in M[:, 0]], np.int16),
        "stack_rec": stack_rec.astype(np.int8), "stack_rb": stack_rb.astype(np.int8), "bb": bb.astype(np.int8),
        "game_n": game_n.astype(np.int8), "n_games": games, "max_team": tc,
        "sal_used": np.nan_to_num(S9).sum(1).astype(np.float32), "sal_nan": np.isnan(S9).any(1),
        "studs": studs.astype(np.int8), "punts": punts.astype(np.int8),
        "dst_sal": S9[:, 8].astype(np.float32), "dst_conf": dst_conf.astype(np.int8), "dst_own_rb": dst_own_rb.astype(np.int8),
        "flex_pos": P9[:, 7].astype(np.int8),
        "flex_sal": S9[:, 7].astype(np.float32), "flex_own": rost[M[:, 7]].astype(np.float32),
        "flex_proj": proj_f[M[:, 7]].astype(np.float32),
        "te_sal": S9[:, 6].astype(np.float32),
        "own_sum": rost[M].sum(1).astype(np.float32),
        "own_max_rank": rank_own[M].min(1).astype(np.int16),
        "n_top5own": (rank_own[M] < 5).sum(1).astype(np.int8),
        "n_lt2own": (rost[M] < 2).sum(1).astype(np.int8),
        "proj_sum": proj_f[M].sum(1).astype(np.float32), "proj_ok": projok[M].all(1),
        "dupes": dupes.astype(np.int32),
        "n_wr": n_wr.astype(np.int8),
        "wr_sal_min": WS[:, 0].astype(np.float32), "wr_sal_2nd": WS[:, 1].astype(np.float32),
        "wr_sal_3rd": WS[:, 2].astype(np.float32), "wr_sal_4th": WS[:, 3].astype(np.float32),
        "wr_sal_max": np.where(np.isfinite(wr_max), wr_max, np.nan).astype(np.float32),
        "n_wr_hp": n_wr_hp.astype(np.int8), "share_wr_hp": (n_wr_hp / np.maximum(n_wr, 1)).astype(np.float32),
        "wr_min_proj": proj_f[cheap_pid].astype(np.float32), "wr_min_own": rost[cheap_pid].astype(np.float32),
    })
    for k in ("season", "week"):
        ent[k] = qa[k]
    ent["contest"] = cid; ent["ctype"] = qa["ctype"]; ent["type"] = typ; ent["slate"] = f"{season}wk{week}{b}"
    qa["dup_unique_share"] = float(np.mean(dupes == 1))
    qa["proj_std_lineup"] = float(ent.loc[ent["proj_ok"], "proj_sum"].std()) if ent["proj_ok"].any() else np.nan
    qa["me_entries"] = int(is_me.sum())

    # --- per-player table: field / cash / top-10% / top-1% rostership, actual score, meta
    cashed = pay > 0
    top10 = ranks <= max(1, int(0.10 * n)); top1 = ranks <= max(1, int(0.01 * n))
    def rate(mask):
        k = int(mask.sum())
        return np.bincount(M[mask].ravel(), minlength=npl) / max(1, k) * 100.0
    pl = pd.DataFrame({"pid": ids, "pos": pos, "team": team.astype(str), "sal": sal, "proj": proj, "fp": fp,
                       "own": rost, "own_cash": rate(cashed), "own_noncash": rate(~cashed), "own_top10": rate(top10),
                       "own_top1": rate(top1), "fc_own": fc_own, "proj_own": proj_own, "game_total": gtot, "cnt": cnt})
    pl["contest"] = cid; pl["ctype"] = qa["ctype"]; pl["season"] = season; pl["week"] = week; pl["slate"] = ent["slate"].iat[0]
    pl["n_entries"] = n; pl["cash_rate"] = qa["cash_rate"]
    return ent, pl, qa


def week_meta(files):
    meta = {}
    for f in files:
        try:
            d = load(f)
        except Exception:
            continue
        for k, p in d["players"].items():
            if "PlayerId" in p and k not in meta:
                m = pmeta(p); m["sal"] = p.get("Salary")
                meta[k] = m
    return meta


def work(args):
    wkey, files, smeta, gmeta = args
    wmeta = week_meta(files)
    out = []
    for f in files:
        base = os.path.basename(f)[:-8]
        try:
            ent, pl, qa = parse(f, wmeta, smeta, gmeta)
        except Exception as e:
            out.append({"file": os.path.basename(f), "error": repr(e)})
            print("ERR", f, repr(e), flush=True)
            continue
        if ent is not None:
            ent.to_parquet(os.path.join(DER, "entries", base + ".parquet"), index=False)
            pl.to_parquet(os.path.join(DER, "players", base + ".parquet"), index=False)
        print(qa["file"], qa.get("rows_used"), "fp99=%.3g" % qa.get("fp_resid_p99", np.nan), qa.get("score_method"),
              "salmiss", qa.get("sal_missing"), "over", qa.get("sal_overpriced_players"), "pay", qa.get("payout_rebuild_agree"),
              "ownmae %.2f" % qa.get("fc_own_mae", np.nan), flush=True)
        out.append(qa)
    return out


def main():
    files = sorted(f for f in glob.glob(os.path.join(SRC, "*.json.gz"))
                   if "_SHOWDOWN_" not in f and "_LIST" not in f)
    if len(sys.argv) > 1:
        files = [f for f in files if any(a in os.path.basename(f) for a in sys.argv[1:])]
    os.makedirs(os.path.join(DER, "entries"), exist_ok=True)
    os.makedirs(os.path.join(DER, "players"), exist_ok=True)
    os.makedirs(OUT_QA, exist_ok=True)
    byweek = defaultdict(list)
    for f in files:
        s, w, b, _, _ = fname_info(f)
        byweek[(s, w, b)].append(f)
    # season / global fallback meta from EVERY lineup-study file (classic + showdown), cached (gitignored, raw-derived)
    allw = sorted(byweek)
    mcache = os.path.join(DER, "_player_meta_by_week.json")
    if os.path.exists(mcache):
        wm_all = json.load(open(mcache))
    else:
        allf = sorted(f for f in glob.glob(os.path.join(SRC, "*.json.gz")) if "_LIST" not in f)
        keyed = defaultdict(list)
        for f in allf:
            s, w, b, _, _ = fname_info(f)
            keyed[f"{s}_{w:02d}"].append(f)
        with Pool(int(os.environ.get("NPROC", "8"))) as pool:
            res = pool.map(week_meta, [keyed[k] for k in sorted(keyed)])
        wm_all = dict(zip(sorted(keyed), res))
        json.dump(wm_all, open(mcache, "w"))
    gmeta = {}
    for k in sorted(wm_all, reverse=True):          # most recent season wins for the global fallback
        for p, v in wm_all[k].items():
            gmeta.setdefault(p, v)
    def season_meta(season, week):
        sm = {}
        ks = sorted((k for k in wm_all if int(k[:4]) == season), key=lambda k: abs(int(k[5:]) - week))
        for k in ks:                                  # nearest week of the same season wins
            for p, v in wm_all[k].items():
                sm.setdefault(p, v)
        return sm
    jobs = [(k, byweek[k], season_meta(k[0], k[1]), gmeta) for k in allw]
    qas = []
    with Pool(int(os.environ.get("NPROC", "8"))) as pool:
        for res in pool.imap_unordered(work, jobs):
            qas.extend(res)
    Q = pd.DataFrame(qas).sort_values(["season", "week", "type"])
    path = os.path.join(OUT_QA, "cl_qa.csv" if len(sys.argv) <= 1 or sys.argv[1].startswith("--") else "cl_qa_partial.csv")
    Q.to_csv(path, index=False)
    print("files", len(Q), "entries", Q.get("rows_used", pd.Series(dtype=float)).sum())


if __name__ == "__main__":
    main()
