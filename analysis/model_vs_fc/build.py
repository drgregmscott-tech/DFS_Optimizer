"""Build the OUR-vs-FC head-to-head frame (research only; this script contains no FC data).

One row per (season, week, player) on the FC single-entry MAIN classic slate:
  FC:   fc_proj, fc projected stat line (targets/rec/yd/td, rush att), fc_own_proj (FC's pre-lock
        projected ownership 'Own' column -- only present in 2021-2023 exports), realized own (own_pct), score
  OURS: 2021-25 = regenerated pre-game projection (run_ourproj.py; NO props/injuries/depth/weather/role overrides)
        2026 wk1-2 = real pre-lock production file from git (cefc761 wk1 16:31Z, 7e57cfe wk2 16:31Z)
        ours_own = production ownership artifact applied to history (pub_val=0) / live pre-lock estimate (2026)
  ACTUAL: nflverse weekly stats (targets, rec, yd, td, carries) + lagged role info available pre-lock.
Output (FC-derived -> git-ignored): data/fc_history/derived/model_vs_fc/frame.parquet
"""
import glob, io, os, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[2]
DER = R / "data/fc_history/derived"
OUT = DER / "model_vs_fc"; OUT.mkdir(parents=True, exist_ok=True)


def num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.rstrip("%").replace({"nan": None, "": None}), errors="coerce").values


def parse_raw(f):
    raw = pd.read_csv(f, header=None, dtype=str)
    hi = int(np.where(raw.iloc[:10, 0].values == "Player")[0][0])
    h = list(raw.iloc[hi]); d = raw.iloc[hi + 1:].reset_index(drop=True)
    d = d[d.iloc[:, 0].notna()]
    ix = {n: h.index(n) for n in ["Player", "Pos", "Team", "Salary", "FC Proj"]}
    o = pd.DataFrame({"player": d.iloc[:, ix["Player"]].values, "pos": d.iloc[:, ix["Pos"]].values,
                      "team": d.iloc[:, ix["Team"]].values, "salary": num(d.iloc[:, ix["Salary"]]),
                      "fc_proj_raw": num(d.iloc[:, ix["FC Proj"]])})
    o["fc_own_proj"] = num(d.iloc[:, h.index("Own")]) if "Own" in h else np.nan
    if "Att+Tar" in h:
        k = h.index("Att+Tar")
        for nm, off in [("fc_rush_att", -3), ("fc_rush_yd", -2), ("fc_rush_td", -1), ("fc_tar", 2), ("fc_rec", 3),
                        ("fc_rec_yd", 4), ("fc_rec_td", 5)]:
            o[nm] = num(d.iloc[:, k + off])
    o["source_file"] = os.path.basename(f)
    return o


def fc_frame():
    m = pd.read_csv(DER / "fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
    m = m[(m.contest == "single_entry") & (m.slate_kind == "classic") & m.pos.isin(["QB", "RB", "WR", "TE", "DST"])]
    raws = pd.concat([parse_raw(f) for f in sorted(glob.glob(str(R / "data/fc_history/20*/*_main_single_entry.csv")))])
    raws = raws.drop_duplicates(["source_file", "player", "pos", "team", "salary"])
    j = m.merge(raws, on=["source_file", "player", "pos", "team", "salary"], how="left")
    j = j[j.player_id.notna()].drop_duplicates(["season", "week", "player_id"])
    return j


def ours_hist():
    fs = glob.glob(str(DER / "ourproj/proj_*.csv"))
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in fs])
    o = o[o.season <= 2025].drop_duplicates(["season", "week", "player_id"])
    return o


def ours_2026():
    out = []
    for wk, sha, fn in [(1, "cefc761", "final_projections_dk_dk_classic_wk1_main_13Sep2026.csv"),
                        (2, "7e57cfe", "final_projections_dk_dk_classic_wk2_main_20Sep2026.csv")]:
        txt = subprocess.run(["git", "-C", str(R), "show", f"{sha}:output/{fn}"], capture_output=True, text=True, check=True).stdout
        d = pd.read_csv(io.StringIO(txt), dtype={"player_id": str}); d["season"], d["week"] = 2026, wk
        out.append(d)
    return pd.concat(out).drop_duplicates(["season", "week", "player_id"])


def actual_stats():
    rows = []
    for s in range(2020, 2027):
        p = R / f"data/weekly_stats_{s}.parquet"
        if not p.exists():
            continue
        w = pd.read_parquet(p)
        w = w[w.season_type.fillna("REG") == "REG"] if "season_type" in w else w
        rows.append(w[["player_id", "season", "week", "team", "targets", "receptions", "receiving_yards", "receiving_tds",
                       "carries", "rushing_yards", "rushing_tds", "target_share"]])
    a = pd.concat(rows)
    a = a.sort_values(["player_id", "season", "week"])
    # team totals -> shares
    tt = a.groupby(["season", "week", "team"]).targets.transform("sum")
    a["tgt_share"] = a.targets / tt.replace(0, np.nan)
    # pre-lock role info: previous game (any season) and in-season mean of prior games (fallback prior season)
    g = a.groupby("player_id")
    a["lag1_tgt"] = g.targets.shift(1); a["lag1_share"] = g.tgt_share.shift(1)
    a["lag1_season"] = g.season.shift(1)
    a["prior3_tgt"] = g.targets.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    a["prior3_share"] = g.tgt_share.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    return a


def main():
    fc = fc_frame()
    oh_ = ours_hist(); o26 = ours_2026()
    keep = ["season", "week", "player_id", "final_projection", "sigma", "proj_targets", "proj_rec", "proj_rec_yd", "proj_rec_td",
            "proj_rush_att", "proj_pass_att", "implied_total", "over_under", "estimated_ownership_pct", "roster_role"]
    o26x = o26.copy()
    for c in ["injury_status"]:
        o26x[c] = o26x.get(c)
    ours = pd.concat([oh_[keep].assign(regime="hist"), o26x[keep + ["injury_status"]].assign(regime="prod2026")])
    ours = ours.rename(columns={"final_projection": "ours", "estimated_ownership_pct": "ours_own_file"})
    J = fc.merge(ours, on=["season", "week", "player_id"], how="inner")
    J = J.rename(columns={"fc_proj": "fc", "score": "act", "own_pct": "own"})
    # production ownership artifact on history features (pub_val=0), as in evaluate_ourproj.py
    sys.path.insert(0, str(R / "scripts")); sys.path.insert(0, str(R / "analysis/ownership_fc_refit"))
    import ownership_model as om
    from evaluate import add_extras, predict
    H = add_extras(pd.read_parquet(DER / "fc_own_features_ourproj.parquet"))
    H = H[H.season <= 2025].copy(); H["pub_val"] = 0.0
    H["ours_own_model"] = np.asarray(predict(H, om.load_artifact("dk")))
    J = J.merge(H[["season", "week", "player_id", "ours_own_model"]], on=["season", "week", "player_id"], how="left")
    # 2026: live pre-lock estimate from ownership_actual_log (single-entry main rows) else file
    lg = pd.read_csv(R / "data/ownership_actual_log.csv", dtype={"player_id": str})
    lg = lg[lg.slate_id.str.contains("classic_wk[12]_main", regex=True)]
    lg["week"] = lg.slate_id.str.extract(r"wk(\d)").astype(int)
    lg = lg.groupby(["week", "player_id"]).agg(live_est=("estimated_ownership_pct_at_lock", "first"),
                                               live_real=("actual_ownership_pct", "sum")).reset_index()
    lg["season"] = 2026
    J = J.merge(lg, on=["season", "week", "player_id"], how="left")
    J["ours_own"] = np.where(J.regime == "hist", J.ours_own_model, J.live_est.fillna(J.ours_own_file))
    A = actual_stats()
    J = J.merge(A.drop(columns=["team"]), on=["season", "week", "player_id"], how="left")
    J["tier"] = pd.cut(J.salary, [0, 5499, 6999, 99999], labels=["cheap<5.5k", "mid5.5-7k", "7k+"])
    J["slate"] = J.season * 100 + J.week
    J.to_parquet(OUT / "frame.parquet")
    print(J.groupby(["regime", "season"]).agg(n=("act", "size"), slates=("week", "nunique"),
                                             fc_own_proj=("fc_own_proj", lambda x: x.notna().mean()),
                                             tar=("fc_tar", lambda x: x.notna().mean()),
                                             ours_own=("ours_own", lambda x: x.notna().mean())))


if __name__ == "__main__":
    main()
