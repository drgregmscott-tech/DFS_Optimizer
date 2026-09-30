"""LOSO 2016-2025 scoring of: (a) none, (b) flat bump, (c) proportional reallocation, (d) targeted who-replaces-whom
(absorbed fraction of vacated share by cell = OUT player's pos x teammate pos x teammate's depth rank at his pos).
Then fit on all 2016-25 and apply to 2026 wk1-3 (on top of our live production projection where we have it)."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]; D = Path(__file__).parent
F0 = pd.read_parquet(D/"frame.parquet")
CH = ("car", "tgt")

def ppo_fit(d):  # DK points per extra carry / target by position (no intercept), on player-week realized opps
    out = {}
    for pos, g in d.groupby("pos"):
        X = g[["real_car","real_tgt"]].to_numpy(float); out[pos] = np.linalg.lstsq(X, g.act.to_numpy(), rcond=None)[0]
    return out

def cellkey(d, ch): return list(zip(d[f"outpos_{ch}"], d.pos, d[f"rk_{ch}"].clip(upper=3).astype(int)))

def fit(tr):
    m = {"ppo": ppo_fit(tr)}
    for ch in CH:
        y = (tr[f"rs_{ch}"] - tr[f"sh_{ch}"]).to_numpy(); V = tr[f"V_{ch}"].to_numpy(); s = tr[f"sh_{ch}"].to_numpy()
        m[f"flat_{ch}"] = (y*V).sum()/(V*V).sum()
        mult = s*(V/np.clip(1-V, .25, None)); m[f"prop_{ch}"] = (y*mult).sum()/(mult*mult).sum()
        k = pd.Series(cellkey(tr, ch)); cells = {}
        k2 = pd.Series(list(zip(tr[f"outpos_{ch}"], tr.pos)))
        coarse = {}
        for c, ix in k2.groupby(k2).groups.items():
            coarse[c] = (y[ix]*V[ix]).sum()/(V[ix]**2).sum()
        for c, ix in k.groupby(k).groups.items():
            ix = np.asarray(ix); w = (V[ix]**2).sum(); b = (y[ix]*V[ix]).sum()/w
            n = len(ix); sh = n/(n+30)                        # shrink small cells toward the coarse cell
            cells[c] = sh*b + (1-sh)*coarse[c[:2]]
        m[f"cell_{ch}"] = cells; m[f"coarse_{ch}"] = coarse
    return m

def predict(m, d, how):
    dp = np.zeros(len(d))
    for ch in CH:
        V = d[f"V_{ch}"].to_numpy(); s = d[f"sh_{ch}"].to_numpy()
        if how == "none": ds = 0*V
        elif how == "flat": ds = m[f"flat_{ch}"]*V
        elif how == "prop": ds = m[f"prop_{ch}"]*s*(V/np.clip(1-V, .25, None))
        elif how == "cell_rb":
            c = cellkey(d, ch); ds = np.array([m[f"cell_{ch}"].get(k, 0.0) if (k[0]=="RB" and k[1]=="RB") else 0.0 for k in c])*V
        else: ds = np.array([m[f"cell_{ch}"].get(c, m[f"coarse_{ch}"].get(c[:2], 0.0)) for c in cellkey(d, ch)])*V
        vol = d[f"v{ch}"].to_numpy(); ppo = np.array([m["ppo"][p][0 if ch=="car" else 1] for p in d.pos])
        dp += ds*vol*ppo
    return dp

def score(d, pred, name):
    e = d.act.to_numpy() - pred
    return {"method": name, "n": len(d), "MAE": np.abs(e).mean(), "RMSE": np.sqrt((e**2).mean()), "bias(act-proj)": e.mean()}

if __name__ == "__main__":
    for flag in ("fri", "inactive"):
        F = F0[(F0.flag == flag)].reset_index(drop=True)
        H = F[F.season <= 2025].reset_index(drop=True)
        preds = {h: np.zeros(len(H)) for h in ("none","flat","prop","cell","cell_rb")}
        for s in sorted(H.season.unique()):
            te = (H.season == s).to_numpy(); m = fit(H[~te])
            for h in preds: preds[h][te] = H.ppg[te] + predict(m, H[te], h)
        print(f"\n===== OUT definition: {flag}  (LOSO 2016-25, {H[['season','week','team']].drop_duplicates().shape[0]} team-weeks) =====")
        H["gain_cell"] = preds["cell"] - preds["none"]
        subsets = {"all active teammates": np.ones(len(H), bool),
                   "same-pos next man up (rk1 at OUT pos, car or tgt)": ((H.pos==H.outpos_car)&(H.rk_car==1)&(H.V_car>=.2)|(H.pos==H.outpos_tgt)&(H.rk_tgt==1)&(H.V_tgt>=.12)).to_numpy(),
                   "RB1 OUT -> RBs": ((H.outpos_car=="RB")&(H.V_car>=.3)&(H.pos=="RB")).to_numpy(),
                   "WR/TE OUT -> WR/TE": ((H.outpos_tgt!="RB")&(H.V_tgt>=.15)&H.pos.isin(["WR","TE"])).to_numpy(),
                   "model gain >= 2 pts": (H.gain_cell >= 2).to_numpy(),
                   "baseline ppg >= 8": (H.ppg >= 8).to_numpy()}
        for nm, msk in subsets.items():
            print(f"-- {nm}")
            print(pd.DataFrame([score(H[msk], preds[h][msk], h) for h in preds]).round(3).to_string(index=False))
        # per-season stability of the targeted gain on the same-pos subset
        msk = subsets["same-pos next man up (rk1 at OUT pos, car or tgt)"]
        ps = H[msk].assign(en=np.abs(H.act-preds["none"])[msk], ec=np.abs(H.act-preds["cell"])[msk], ep=np.abs(H.act-preds["prop"])[msk])
        print("per-season MAE next-man-up none / cell / prop:\n", ps.groupby("season")[["en","ec","ep"]].mean().round(2).T.to_string())
        m = fit(H)
        print("fitted absorbed fraction (share pts per 1 pt vacated), cells n>=40:")
        for ch in CH:
            k = pd.Series(cellkey(H, ch)).value_counts()
            print(ch, {c: round(v, 2) for c, v in m[f"cell_{ch}"].items() if k.get(c, 0) >= 40})
        print("flat:", {ch: round(m[f"flat_{ch}"],3) for ch in CH}, "prop:", {ch: round(m[f"prop_{ch}"],3) for ch in CH})
        pd.to_pickle(m, D/f"model_{flag}.pkl")
        H.assign(**{f"p_{h}": v for h, v in preds.items()}).to_parquet(D/f"loso_preds_{flag}.parquet")
