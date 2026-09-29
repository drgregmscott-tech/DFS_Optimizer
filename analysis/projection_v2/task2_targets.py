"""Task 2: recency-weighted target-share / route-participation model for WR/TE (research; no FC data inside).

History frame = model_vs_fc/frame.parquet (FC main slates 2021-25; OURS = regenerated engine; actual stats nflverse).
Usage features = data/nflverse_usage/usage_features.parquet (public; snaps via PFR, routes = on-field on dropbacks
from nflverse pbp_participation, available 2016-2025 only -> NOT available live in 2026).

Model (targets): ridge-free OLS, leave-one-season-out, on played WR/TE rows:
    targets ~ 1 + eng_tgt + V*share_ewm2 + V*share_ewm8 + V*share_prev + [V*route_ewm4 + V*route_ewm4*tprr_ewm8] + [V*snap_ewm2]
    V = engine team pass attempts (sum of that team's QB proj_pass_att), fallback team dropback EWMA.
Points: cand = ours + g * ppt * (tgt_hat - eng_tgt); ppt = engine DK receiving pts per projected target; g fit LOSO.
"""
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = Path(__file__).resolve().parents[2]
DER = R / "data/fc_history/derived"; OUT = DER / "projection_v2"
U = R / "data/nflverse_usage"

SETS = {
    "share": ["eng_tgt", "v_sh2", "v_sh8", "v_shprev"],
    "share+snap": ["eng_tgt", "v_sh2", "v_sh8", "v_shprev", "v_snap2", "v_snap8"],
    "share+route": ["eng_tgt", "v_sh2", "v_sh8", "v_shprev", "v_rt4", "v_rt4tprr", "v_rt2"],
    "all": ["eng_tgt", "v_sh2", "v_sh8", "v_shprev", "v_snap2", "v_snap8", "v_rt4", "v_rt4tprr", "v_rt2"],
    "no_engine_all": ["v_sh2", "v_sh8", "v_shprev", "v_snap2", "v_snap8", "v_rt4", "v_rt4tprr", "v_rt2"],
}


def frame():
    J = pd.read_parquet(DER / "model_vs_fc/frame.parquet")
    q = J[J.pos == "QB"].groupby(["season", "week", "team"]).proj_pass_att.max().rename("V_eng").reset_index()
    J = J[J.pos.isin(["WR", "TE"])].merge(q, on=["season", "week", "team"], how="left")
    F = pd.read_parquet(U / "usage_features.parquet")
    J = J.merge(F, on=["player_id", "season", "week"], how="left", suffixes=("", "_u"))
    tv = pd.read_parquet(U / "team_volume_features.parquet")
    TF = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS", "LVR": "LV"}
    J["team_n"] = J.team.map(lambda t: TF.get(t, t))
    J = J.merge(tv.rename(columns={"team": "team_n"}), on=["season", "week", "team_n"], how="left")
    J["V"] = J.V_eng.where(J.V_eng > 15, J.team_db_ewm).fillna(34.0)
    z = lambda c: J[c].fillna(0)
    shp = J.prev_share.fillna(J.tgt_share_ewm8).fillna(0)
    J["eng_tgt"] = J.proj_targets.fillna(0)
    J["v_sh2"] = J.V * z("tgt_share_ewm2"); J["v_sh8"] = J.V * z("tgt_share_ewm8"); J["v_shprev"] = J.V * shp
    J["v_snap2"] = J.V * z("snap_pct_ewm2"); J["v_snap8"] = J.V * z("snap_pct_ewm8")
    J["v_rt4"] = J.V * z("route_part_ewm4"); J["v_rt2"] = J.V * z("route_part_ewm2")
    J["v_rt4tprr"] = J.V * z("route_part_ewm4") * J.tprr_ewm8.fillna(J.tprr_ewm8.median())
    rp = (J.proj_rec.fillna(0) + .1 * J.proj_rec_yd.fillna(0) + 6 * J.proj_rec_td.fillna(0))
    J["ppt"] = np.clip(rp / J.eng_tgt.replace(0, np.nan), 0.8, 3.0).fillna(1.6)
    J["played"] = J.targets.notna()
    J["tier"] = np.where(J.salary < 5500, "cheap", "5.5k+")
    J["sk"] = J.season * 100 + J.week
    return J


def ols(t, cols, y):
    A = np.column_stack([np.ones(len(t))] + [t[c].values for c in cols])
    return np.linalg.lstsq(A, t[y].values, rcond=None)[0]


def pred(t, cols, b):
    return np.column_stack([np.ones(len(t))] + [t[c].values for c in cols]) @ b


def rho(d, c, y):
    return np.nanmean([spearmanr(g[c], g[y]).correlation for _, g in d.groupby("sk") if len(g) > 5])


def main():
    J = frame()
    H = J[(J.season <= 2025) & J.played & (J.proj_targets.notna())].copy()
    for name, cols in SETS.items():
        H[f"th_{name}"] = np.nan
        for s in H.season.unique():
            tr, te = H.season != s, H.season == s
            H.loc[te, f"th_{name}"] = np.maximum(pred(H[te], cols, ols(H[tr], cols, "targets")), 0)
    # points: LOSO scalar g on best sets
    for name in ["share", "share+snap", "all"]:
        d = H[f"th_{name}"] - H.eng_tgt
        H[f"x_{name}"] = H.ppt * d
        H[f"pts_{name}"] = np.nan
        for s in H.season.unique():
            tr, te = H.season != s, H.season == s
            r = (H.act - H.ours)[tr]; x = H[f"x_{name}"][tr]
            g = (x * r).sum() / (x * x).sum()
            H.loc[te, f"pts_{name}"] = np.maximum(H.ours[te] + g * H[f"x_{name}"][te], 0)
        print(f"points scale g (all-season fit) {name}: {((H[f'x_{name}']*(H.act-H.ours)).sum()/(H[f'x_{name}']**2).sum()):.2f}")
    act = H[(H.act > 0) & (H.fc > 0)]
    print(f"\nrows WR/TE played {len(H)}, active {len(act)}; route coverage {H.route_part_ewm4.notna().mean():.2f}")
    tc = ["eng_tgt", "fc_tar"] + [f"th_{n}" for n in SETS]
    def tstats(d):
        d = d[d.fc_tar.notna()]
        r = {"n": len(d)}
        for c in tc:
            r[f"{c}|mae"] = (d[c] - d.targets).abs().mean(); r[f"{c}|bias"] = (d[c] - d.targets).mean()
            r[f"{c}|rho"] = rho(d, c, "targets")
        return pd.Series(r)
    print("\n== TARGETS (LOSO), active WR/TE, by tier")
    T = act.groupby("tier").apply(tstats).T
    print(T.round(3).to_string())
    print("\n== TARGETS by season (cheap): mae eng / share+snap / all / fc")
    print(act[act.tier == "cheap"].groupby("season").apply(tstats)[["eng_tgt|mae", "th_share+snap|mae", "th_all|mae", "fc_tar|mae", "eng_tgt|rho", "th_share+snap|rho", "th_all|rho", "fc_tar|rho"]].round(3).to_string())
    # receptions: scale by engine catch rate
    act = act.assign(cr=(act.proj_rec / act.eng_tgt.replace(0, np.nan)).clip(.4, .9).fillna(.62))
    for n in ["eng_tgt", "th_share+snap", "th_all"]:
        act[f"rec_{n}"] = act[n] * act.cr
    print("\n== RECEPTIONS mae (active, by tier): engine / share+snap / all / FC")
    print(act.groupby("tier").apply(lambda d: pd.Series({c: (d[c] - d.receptions).abs().mean() for c in ["rec_eng_tgt", "rec_th_share+snap", "rec_th_all", "fc_rec"]})).round(3).to_string())
    pc = ["ours", "pts_share", "pts_share+snap", "pts_all", "fc"]
    def pstats(d):
        r = {"n": len(d)}
        for c in pc:
            e = d[c] - d.act
            r[f"{c}|mae"] = e.abs().mean(); r[f"{c}|rmse"] = np.sqrt((e ** 2).mean()); r[f"{c}|rho"] = rho(d, c, "act")
        return pd.Series(r)
    print("\n== DK POINTS (LOSO), active WR/TE, by tier")
    print(act.groupby("tier").apply(pstats).T.round(3).to_string())
    print("\n== DK POINTS cheap by season (mae ours / pts_share+snap / pts_all)")
    print(act[act.tier == "cheap"].groupby("season").apply(pstats)[["ours|mae", "pts_share+snap|mae", "pts_all|mae", "ours|rho", "pts_share+snap|rho", "pts_all|rho"]].round(3).to_string())
    # role-change rows (ex-post share move >= 8 pts vs prior3) -- does it fix the "share UP" miss?
    mv = (act.tgt_share - act.prior3_share) * 100
    act = act.assign(mv=np.select([mv >= 8, mv <= -8], ["UP", "DOWN"], "stable"))
    print("\n== bias by ex-post share move (targets / points)")
    print(act.groupby("mv").apply(lambda d: pd.Series({"n": len(d), "tbias_eng": (d.eng_tgt - d.targets).mean(), "tbias_all": (d.th_all - d.targets).mean(),
                                                      "pbias_ours": (d.ours - d.act).mean(), "pbias_all": (d.pts_all - d.act).mean()})).round(2).to_string())
    act.to_parquet(OUT / "task2_loso_hist.parquet")
    # full-history coefficients for wiring (snap version is the only live-feasible one)
    for n in ["share+snap", "all"]:
        b = ols(H, SETS[n], "targets")
        print(f"\ncoef {n}: " + ", ".join(f"{c}={v:+.3f}" for c, v in zip(["const"] + SETS[n], b)))


if __name__ == "__main__":
    main()
