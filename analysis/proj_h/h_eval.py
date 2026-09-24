"""Step H evaluation: floor-share dilution + with/without fix.
usage: python analysis/proj_h/h_eval.py > analysis/proj_h/h_out.txt
Needs analysis/proj_h/builds/{base,fix}_wk{1,2}_{main,early,afternoon}/ from run_all.sh.
Conventions follow analysis/proj_c/c_calib.py: skill rows alive, final>8 (cut on BASE for pairing;
union cut as sensitivity), with actual; dedup player-weeks main>early>afternoon.
Bootstrap: 2000 resamples, clustered by player-week, seed 0.
"""
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
H = Path(__file__).resolve().parent / "builds"
SUBS = ("main", "early", "afternoon")
DATE = {1: "13Sep2026", 2: "20Sep2026"}
PRI = {"main": 0, "early": 1, "afternoon": 2}
NTOP = {"RB": 5, "WR": 8, "TE": 3}
POS = list(NTOP)
B = int(__import__("os").environ.get("H_B", 2000))
rng = np.random.default_rng(0)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)

L = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
WS = pd.read_parquet(REPO / "data/weekly_stats_2026.parquet")
WS = WS[WS.season_type == "REG"] if "season_type" in WS else WS


def sid(w, s):
    return f"dk_classic_wk{w}_{s}_{DATE[w]}"


def load(tag, w, s, what):
    d = H / f"{tag}_wk{w}_{s}"
    if what == "final":
        return pd.read_csv(d / f"final_projections_dk_{sid(w, s)}.csv", dtype={"player_id": str})
    return pd.read_csv(d / f"{what}.csv", dtype={"player_id": str})


def rk(x):
    return pd.Series(np.asarray(x, float)).rank().to_numpy()


def sp(a, b):
    return np.corrcoef(rk(a), rk(b))[0, 1]


# ---------------------------------------------------------------- 1. dilution
print("=" * 100, "\n1. DILUTION IN THE SHIPPED (base) BUILDS\n")
for w in (1, 2):
    rows = []
    seen = set()
    for s in SUBS:
        pre, post = load("base", w, s, "pool_pre_reconcile"), load("base", w, s, "pool_post_reconcile")
        fl = load("fix", w, s, "floor_players")
        ex = set(fl.loc[fl.excluded, "player_id"])
        rec = pd.read_csv(H / f"base_wk{w}_{s}" / f"statline_reconcile_dk_{sid(w, s)}.csv")
        for team, g in pre.groupby("team"):
            if team in seen:
                continue
            seen.add(team)
            gp = post[post.team == team]
            e = g.player_id.isin(ex)
            r = {"team": team}
            for pos in POS:
                m = e & (g.position == pos)
                r[f"n_{pos}"] = int(m.sum())
            r["rush_ps_all"] = g.rush_price_share.sum()
            r["rush_ps_floor"] = g.loc[e, "rush_price_share"].sum()
            r["recv_ps_all"] = g.recv_price_share.sum()
            r["recv_ps_floor"] = g.loc[e, "recv_price_share"].sum()
            r["rush_mu_floor_post"] = gp.loc[gp.player_id.isin(ex), "rush_mu"].sum()
            r["recv_mu_floor_post"] = gp.loc[gp.player_id.isin(ex), "recv_mu"].sum()
            for comp in ("rush", "recv"):
                q = rec[(rec.team == team) & (rec.component == comp)]
                r[f"{comp}_scale"] = q.scale.iloc[0] if len(q) else np.nan
                r[f"{comp}_basis"] = q.share_basis.iloc[0] if len(q) else ""
            rows.append(r)
    T = pd.DataFrame(rows)
    print(f"--- week {w}: {len(T)} teams ---")
    print(T[[c for c in T.columns if c.startswith("n_")]].sum().to_string())
    print("mean per team:", T[["rush_ps_all", "rush_ps_floor", "recv_ps_all", "recv_ps_floor",
                                "rush_mu_floor_post", "recv_mu_floor_post", "rush_scale", "recv_scale"]].mean().round(3).to_dict())
    print("reconcile share_basis rush:", T.rush_basis.value_counts().to_dict(), " recv:", T.recv_basis.value_counts().to_dict())
    print("teams sorted by floor rush mass (attempts post-reconcile held by excluded floor players):")
    print(T.sort_values("rush_mu_floor_post", ascending=False).head(8).round(3).to_string(index=False))
    print()

# ------------------------------------------------ 2. projected vs real usage
print("=" * 100, "\n2. PROJECTED vs REAL USAGE (dedup player-week, main>early>afternoon)\n")


def dedup_builds(tag, w):
    fs = []
    for s in SUBS:
        f = load(tag, w, s, "final"); f["sub"] = s; fs.append(f)
    F = pd.concat(fs).assign(p=lambda d: d["sub"].map(PRI)).sort_values("p").drop_duplicates("player_id")
    return F


usage_rows = []
for w in (1, 2):
    real = WS[WS.week == w].groupby("player_id").agg(car=("carries", "sum"), tgt=("targets", "sum"),
                                                     rteam=("team", "first"), rpos=("position", "first"))
    b, f = dedup_builds("base", w), dedup_builds("fix", w)
    f = f.set_index("player_id").reindex(b.player_id)
    b = b.set_index("player_id")
    D = b[["player_name", "team", "position", "salary", "proj_rush_att", "proj_targets"]].copy()
    D["f_rush"], D["f_tgt"] = f.proj_rush_att, f.proj_targets
    D = D.join(real)
    D[["car", "tgt"]] = D[["car", "tgt"]].fillna(0)
    D["week"] = w
    # team teams that played (have real stats)
    played = set(WS[WS.week == w].team)
    D = D[D.team.isin(played)]
    # team-level RB carries / WR targets / TE targets: projected (in-build players) vs real (all position players)
    for pos, pc, fc, rc, rcol in (("RB", "proj_rush_att", "f_rush", "car", "carries"),
                                  ("WR", "proj_targets", "f_tgt", "tgt", "targets"),
                                  ("TE", "proj_targets", "f_tgt", "tgt", "targets")):
        R = WS[(WS.week == w) & (WS.position == pos)].groupby("team")[rcol].sum()
        P = D[D.position == pos].groupby("team")[[pc, fc]].sum()
        P = P.join(R.rename("real")).dropna()
        eb, ef = P[pc] - P.real, P[fc] - P.real
        print(f"wk{w} team {pos} {rcol}: n_team={len(P)} real_mean={P.real.mean():.1f} base_proj={P[pc].mean():.1f} "
              f"fix_proj={P[fc].mean():.1f} | MAE base {eb.abs().mean():.2f} fix {ef.abs().mean():.2f}")
    # per-starter: RB top1/top2 by base proj carries, WR top3 by base proj targets, TE top1
    for pos, pc, fc, rc, ks in (("RB", "proj_rush_att", "f_rush", "car", (1, 2)), ("WR", "proj_targets", "f_tgt", "tgt", (1, 2, 3)),
                                ("TE", "proj_targets", "f_tgt", "tgt", (1,))):
        g = D[D.position == pos].copy()
        g["r"] = g.groupby("team")[pc].rank(ascending=False, method="first")
        for k in ks:
            h = g[g.r == k]
            eb, ef = h[pc] - h[rc], h[fc] - h[rc]
            d = (ef.abs() - eb.abs()).to_numpy()
            bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(B)]
            usage_rows.append(dict(week=w, pos=pos, slot=f"{pos}{k}", stat=rc, n=len(h), real=h[rc].mean(), base=h[pc].mean(),
                                   fix=h[fc].mean(), ratio_base=h[pc].sum() / h[rc].sum(), ratio_fix=h[fc].sum() / h[rc].sum(),
                                   mae_base=eb.abs().mean(), mae_fix=ef.abs().mean(), dMAE=d.mean(),
                                   lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5)))
    # floor players excluded: their REAL touches
    ex = pd.concat([load("fix", w, s, "floor_players") for s in SUBS]).drop_duplicates("player_id")
    exr = ex[ex.excluded].set_index("player_id").join(real)
    exr[["car", "tgt"]] = exr[["car", "tgt"]].fillna(0)
    print(f"wk{w} excluded floor players: n={len(exr)}; real carries total={exr.car.sum():.0f} targets={exr.tgt.sum():.0f}; "
          f"n with >=5 carries+targets: {int(((exr.car + exr.tgt) >= 5).sum())}")
    print(exr[(exr.car + exr.tgt) >= 3][["player_name", "team", "position", "salary", "depth_rank_h", "car", "tgt"]].to_string())
    print()
U = pd.DataFrame(usage_rows)
print("per-starter usage (slot = rank by BASE projected volume within team). dMAE = fix-base, <0 better; 95% CI bootstrap")
print(U.round(3).to_string(index=False))

# ------------------------------------------------ 3. DK points
print("\n" + "=" * 100, "\n3. DK POINTS, base vs fix\n")


def frame(w, cut="base"):
    rows = []
    for s in SUBS:
        b, f = load("base", w, s, "final"), load("fix", w, s, "final").set_index("player_id")
        b = b[b.position.isin(POS)].copy()
        if "injury_status" in b:
            b = b[b.injury_status != "OUT"]
        b["fix"] = b.player_id.map(f.final_projection)
        b = b.rename(columns={"final_projection": "base"})
        keep = (b.base > 8) if cut == "base" else ((b.base > 8) | (b.fix > 8))
        b = b[keep]
        a = L[L.slate_id == sid(w, s)].drop_duplicates("player_id").set_index("player_id").actual_fpts
        b["act"] = b.player_id.map(a)
        b = b.dropna(subset=["act"])
        b["sub"], b["slate"], b["week"] = s, sid(w, s), w
        rows.append(b)
    D = pd.concat(rows, ignore_index=True)
    D["pw"] = D.player_id + "_" + str(w)
    return D


def ded(D):
    return D.assign(p=D["sub"].map(PRI)).sort_values("p").drop_duplicates("pw").drop(columns="p")


def level(d):
    eb, ef = d.base - d.act, d.fix - d.act
    return np.array([eb.mean(), ef.mean(), eb.abs().mean(), ef.abs().mean(), np.sqrt((eb ** 2).mean()), np.sqrt((ef ** 2).mean())])


def rank_stats(D, pos_list):
    sb, sf, tb, tf = [], [], [], []
    for (_, p), h in D[D.position.isin(pos_list)].groupby(["slate", "position"]):
        if len(h) < 6:
            continue
        sb.append(sp(h.base, h.act)); sf.append(sp(h.fix, h.act))
        tb.append(h.nlargest(NTOP[p], "base").act.mean()); tf.append(h.nlargest(NTOP[p], "fix").act.mean())
    return np.array([np.mean(sb), np.mean(sf), np.mean(tb), np.mean(tf)]) if sb else np.full(4, np.nan)


def evaluate(D, label):
    out = []
    for grp, pl in [(p, [p]) for p in POS] + [("ALL", POS)]:
        Dg = D[D.position.isin(pl)]
        d = ded(Dg).reset_index(drop=True)
        lv, rs = level(d), rank_stats(Dg, pl)
        keys = d.pw.to_numpy()
        pws = np.unique(Dg.pw)
        gidx = {k: v.to_numpy() for k, v in Dg.groupby("pw").groups.items()}
        bl, br = [], []
        for _ in range(B):
            samp = rng.choice(len(d), len(d))
            bl.append(level(d.iloc[samp]))
            pick = rng.choice(pws, len(pws))
            Db = Dg.loc[np.concatenate([gidx[k] for k in pick])]
            # rank stats on resampled rows (duplicates allowed) -> slightly noisy but paired
            br.append(rank_stats(Db, pl))
        bl, br = np.array(bl), np.array(br)
        dl = np.c_[bl[:, 1] - bl[:, 0], bl[:, 3] - bl[:, 2], bl[:, 5] - bl[:, 4]]
        drs = np.c_[br[:, 1] - br[:, 0], br[:, 3] - br[:, 2]]
        ci = lambda x: f"[{np.nanpercentile(x, 2.5):+.3f},{np.nanpercentile(x, 97.5):+.3f}]"
        out.append(dict(cut=label, grp=grp, npw=len(d), nchg=int((abs(d.fix - d.base) > .05).sum()),
                        bias_b=lv[0], bias_f=lv[1], d_bias=lv[1] - lv[0], ci_bias=ci(dl[:, 0]),
                        mae_b=lv[2], mae_f=lv[3], d_mae=lv[3] - lv[2], ci_mae=ci(dl[:, 1]),
                        rmse_b=lv[4], rmse_f=lv[5], d_rmse=lv[5] - lv[4], ci_rmse=ci(dl[:, 2]),
                        sp_b=rs[0], sp_f=rs[1], d_sp=rs[1] - rs[0], ci_sp=ci(drs[:, 0]),
                        top_b=rs[2], top_f=rs[3], d_top=rs[3] - rs[2], ci_top=ci(drs[:, 1])))
    return pd.DataFrame(out)


res = []
for w in (1, 2):
    for cut in ("base", "union"):
        r = evaluate(frame(w, cut), cut); r.insert(0, "week", w); res.append(r)
R = pd.concat(res)
for cols in (["week", "cut", "grp", "npw", "nchg", "bias_b", "bias_f", "d_bias", "ci_bias", "mae_b", "mae_f", "d_mae", "ci_mae",
              "rmse_b", "rmse_f", "d_rmse", "ci_rmse"],
             ["week", "cut", "grp", "sp_b", "sp_f", "d_sp", "ci_sp", "top_b", "top_f", "d_top", "ci_top"]):
    print(R[cols].round(3).to_string(index=False)); print()
R.to_csv(Path(__file__).resolve().parent / "h_points.csv", index=False)
U.to_csv(Path(__file__).resolve().parent / "h_usage.csv", index=False)

# biggest per-player changes in the backtests
print("biggest |fix-base| changes, backtest (dedup, all rows with actual):")
for w in (1, 2):
    rows = []
    for s in SUBS:
        b, f = load("base", w, s, "final"), load("fix", w, s, "final").set_index("player_id")
        b = b[b.position.isin(POS)].copy(); b["fix"] = b.player_id.map(f.final_projection); b["sub"] = s
        a = L[L.slate_id == sid(w, s)].drop_duplicates("player_id").set_index("player_id").actual_fpts
        b["act"] = b.player_id.map(a); rows.append(b)
    C = pd.concat(rows).assign(p=lambda d: d["sub"].map(PRI)).sort_values("p").drop_duplicates("player_id")
    C["d"] = C.fix - C.final_projection
    print(f"wk{w}: mean delta among base>8: {C[C.final_projection > 8].d.mean():+.3f}; by pos:",
          C[C.final_projection > 8].groupby("position").d.mean().round(3).to_dict())
    print(C.assign(ad=C.d.abs()).sort_values("ad", ascending=False).head(10)[
        ["player_name", "team", "position", "salary", "final_projection", "fix", "d", "act"]].round(2).to_string(index=False))

# wk3 main live-style build: base vs fix
print("\n" + "=" * 100, "\n4. WEEK 3 MAIN (live-style build, no --backtest-no-leak)\n")
b = pd.read_csv(H / "base_wk3_main/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv", dtype={"player_id": str})
f = pd.read_csv(H / "fix_wk3_main/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv", dtype={"player_id": str}).set_index("player_id")
fl = pd.read_csv(H / "fix_wk3_main/floor_players.csv", dtype={"player_id": str})
print("floor players excluded:", fl.excluded.sum(), "guarded:", fl.guarded.sum()); print(fl[fl.guarded].to_string(index=False))
b["fix"] = b.player_id.map(f.final_projection); b["d"] = b.fix - b.final_projection
b["d_rush"] = b.player_id.map(f.proj_rush_att) - b.proj_rush_att; b["d_tgt"] = b.player_id.map(f.proj_targets) - b.proj_targets
print("mean delta base>8 by pos:", b[b.final_projection > 8].groupby("position").d.mean().round(3).to_dict())
print("players with |delta|>=0.5:", int((b.d.abs() >= .5).sum()))
print(b.assign(ad=b.d.abs()).sort_values("ad", ascending=False).head(15)[["player_name","team","position","salary","final_projection","fix","d","d_rush","d_tgt"]].round(2).to_string(index=False))
