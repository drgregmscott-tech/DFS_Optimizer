"""What predicts a cash-line (top-25%) finish in real DK Classic SE3max fields?
6 slates: wk1 main/early/afternoon (2026-09-13) + wk2 main/early/afternoon (2026-09-20).
Mirrors analysis/showdown_own/top10_drivers.py's method for Showdown.
Also reports where the user's own gmscott81 entry landed and what it looked like.
"""
import re
import numpy as np
import pandas as pd

D = "C:/Users/gmsco/Downloads/"
SLATES = {
    "wk1_main": (D + "dk_classic_wk1_main_final_results_13Sep2026.csv", "dk_classic_wk1_main_13Sep2026"),
    "wk1_early": (D + "dk_classic_wk1_early_final_results_13Sep2026.csv", "dk_classic_wk1_early_13Sep2026"),
    "wk1_afternoon": (D + "dk_classic_wk1_afternoon_final_results_13Sep2026.csv", "dk_classic_wk1_afternoon_13Sep2026"),
    "wk2_main": (D + "results_se3max_dk_classic_wk2_main_20Sep2026.csv", "dk_classic_wk2_main_20Sep2026"),
    "wk2_early": (D + "results_se3max_dk_classic_wk2_early_20Sep2026.csv", "dk_classic_wk2_early_20Sep2026"),
    "wk2_afternoon": (D + "results_se3max_dk_classic_wk2_afternoon_20Sep2026.csv", "dk_classic_wk2_afternoon_20Sep2026"),
}
CASH_PCT = 0.25  # SE3max min-cash is ~top 25% per WK2_POSTMORTEM.md

TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")


def parse(s):
    p = TOK.split(" " + s.strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'\u2019]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


frames = []
mine_rows = []
for lab, (f, sid) in SLATES.items():
    P = pd.read_csv(f"output/final_projections_dk_{sid}.csv", dtype={"player_id": str})
    P["k"] = P.player_name.map(norm)
    opp_implied = P.dropna(subset=["implied_total"]).drop_duplicates("team").set_index("team").implied_total
    info = P.set_index("k")[["team", "position", "salary", "final_projection", "estimated_ownership_pct", "opponent"]].to_dict("index")

    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    ownmap = tab.drop_duplicates("k").set_index("k")["own"].to_dict()
    actmap = tab.drop_duplicates("k").set_index("k")["FPTS"].to_dict()

    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy()
    N = len(e)
    rows = []
    for r in e.itertuples():
        L = [(slot, norm(nm)) for slot, nm in parse(r.Lineup)]
        qb_k = next((k for s, k in L if s == "QB"), None)
        dst_k = next((k for s, k in L if s == "DST"), None)
        flex_k = next((k for s, k in L if s == "FLEX"), None)
        skill_ks = [k for s, k in L if s in ("RB", "WR", "TE", "FLEX")]
        qb_team = info.get(qb_k, {}).get("team")
        stack = sum(1 for k in skill_ks if info.get(k, {}).get("team") == qb_team)
        bb = sum(1 for k in skill_ks if info.get(k, {}).get("team") == info.get(qb_k, {}).get("opponent"))
        dst_opp = info.get(dst_k, {}).get("opponent")
        dst_opp_total = opp_implied.get(dst_opp, np.nan)
        all_ks = [k for s, k in L]
        own = [ownmap.get(k, np.nan) for k in all_ks]
        own = [o for o in own if not pd.isna(o)]
        sal = sum((info.get(k, {}) or {}).get("salary", 0) or 0 for k in all_ks)
        flex_pos = info.get(flex_k, {}).get("position")
        is_mine = "gmscott81" in str(r.EntryName)
        rec = dict(
            slate=lab, rank=r.Rank, pts=r.Points, pct=1 - (r.Rank - 1) / N,
            cash=(1 - (r.Rank - 1) / N) >= (1 - CASH_PCT),
            stack=stack, bb=bb,
            dst_own=ownmap.get(dst_k, np.nan), dst_opp_total=dst_opp_total,
            dst_sal=(info.get(dst_k, {}) or {}).get("salary", np.nan),
            own_sum=sum(own), n_low=sum(1 for o in own if o < 5), n_chalk=sum(1 for o in own if o >= 20),
            sal=sal, flex_pos=flex_pos, entry=r.EntryName, mine=is_mine,
        )
        rows.append(rec)
        if is_mine:
            mine_rows.append({**rec, "lineup": r.Lineup})
    frames.append(pd.DataFrame(rows))

A = pd.concat(frames, ignore_index=True)
CUT = 1 - CASH_PCT  # e.g. 0.75

print(f"\n=== Cash-line ({CASH_PCT:.0%}) hit rate by slate ===")
print(A.groupby("slate").cash.agg(n="size", cash_rate="mean").to_string())

print("\n=== YOUR entries ===")
for m in mine_rows:
    print(f"{m['slate']}: rank {m['rank']} pct {m['pct']:.3f} pts {m['pts']:.1f} cash={m['cash']} "
          f"stack={m['stack']} bb={m['bb']} dst_own={m['dst_own']} "
          f"dst_opp_total={m['dst_opp_total']} own_sum={m['own_sum']:.0f} n_chalk={m['n_chalk']} n_low={m['n_low']} "
          f"sal={m['sal']} flex={m['flex_pos']}")
    print("   ", m["lineup"])

A["stack_bin"] = A["stack"].clip(upper=3).astype(str)
A["bb_bin"] = A["bb"].clip(upper=2).astype(str)
A["dst_tier"] = pd.cut(A.dst_own, [-1, 5, 12, 25, 100], labels=["<5%", "5-12%", "12-25%", ">25%"])
A["dst_opp_tier"] = A.groupby("slate").dst_opp_total.transform(
    lambda x: pd.qcut(x, 3, labels=["low O/U", "mid", "high O/U"], duplicates="drop"))
A["own_q"] = A.groupby("slate").own_sum.transform(lambda x: pd.qcut(x, 4, labels=["Q1 low", "Q2", "Q3", "Q4 chalk"]))
A["sal_bin"] = pd.cut(A.sal, [0, 49000, 49600, 49900, 50001], labels=["<49k", "49-49.6k", "49.6-49.9k", ">49.9k"])

for col in ["stack_bin", "bb_bin", "dst_tier", "dst_opp_tier", "flex_pos", "own_q", "sal_bin"]:
    g = A.groupby(col, observed=True).agg(n=("cash", "size"), cash_rate=("cash", "mean")).reset_index()
    g["lift"] = (g.cash_rate / CASH_PCT).round(2)
    print(f"\n--- {col} ---")
    print(g.to_string(index=False))

# pooled logistic on cash outcome
X = pd.DataFrame({
    "stack1": (A["stack"] == 1) * 1.0, "stack2p": (A["stack"] >= 2) * 1.0,
    "bb1p": (A.bb >= 1) * 1.0,
    "dst_own_z": A.groupby("slate").dst_own.transform(lambda x: (x - x.mean()) / x.std()),
    "dst_opp_total_z": A.groupby("slate").dst_opp_total.transform(lambda x: (x - x.mean()) / x.std()),
    "own_sum_z": A.groupby("slate").own_sum.transform(lambda x: (x - x.mean()) / x.std()),
    "sal_z": A.groupby("slate").sal.transform(lambda x: (x - x.mean()) / x.std()),
    "flex_te": (A.flex_pos == "TE") * 1.0,
})
mask = X.notna().all(axis=1)
Xm = np.c_[np.ones(mask.sum()), X[mask].values]
y = A.cash[mask].values.astype(float)
b = np.zeros(Xm.shape[1])
for _ in range(25):
    p = 1 / (1 + np.exp(-Xm @ b))
    W = p * (1 - p)
    H = Xm.T @ (Xm * W[:, None]) + 1e-6 * np.eye(len(b))
    b = b + np.linalg.solve(H, Xm.T @ (y - p))
se = np.sqrt(np.diag(np.linalg.inv(H)))
print(f"\n--- pooled logistic for cash ({mask.sum()} rows; |z|>2 ~ real) ---")
print(pd.DataFrame({"coef": b, "z": b / se}, index=["const"] + list(X.columns)).round(2).to_string())

A.to_csv("analysis/classic_diag/classic_lineup_feats.csv", index=False)
