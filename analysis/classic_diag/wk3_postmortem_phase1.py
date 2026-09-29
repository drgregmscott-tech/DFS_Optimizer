"""Phase 1 player-level diagnostics for the Wk1-3 postmortem (WK3_ROOT_CAUSE_FINDINGS.md).

Per slate: parse contest export -> one row per entry, cash line at top 25%
(single-entry) or top 22% (MME/3max pool per checklist -- using 25% uniformly
here since these are all single-entry-style payout structures unless noted).
Per rostered player: field ownership %, cash rate rostered vs not, lift.
Four-way miss taxonomy vs our own projection+ownership model.

usage: python analysis/classic_diag/wk3_postmortem_phase1.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import optimizer

ROOT = Path(__file__).resolve().parents[2]
CR = ROOT / "data" / "contest_results"
TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")

SLATES = {
    "wk1_early": (CR / "dk_classic_wk1_early_13Sep2026_full.csv", "dk_classic_wk1_early_13Sep2026", 0.25),
    "wk1_afternoon": (CR / "dk_classic_wk1_afternoon_13Sep2026_full.csv", "dk_classic_wk1_afternoon_13Sep2026", 0.25),
    "wk1_main": (CR / "dk_classic_wk1_main_13Sep2026_full.csv", "dk_classic_wk1_main_13Sep2026", 0.25),
    "wk2_early": (CR / "dk_classic_wk2_early_20Sep2026_se3max_full.csv", "dk_classic_wk2_early_20Sep2026", 0.25),
    "wk2_afternoon": (CR / "dk_classic_wk2_afternoon_20Sep2026_se3max_full.csv", "dk_classic_wk2_afternoon_20Sep2026", 0.25),
    "wk2_main_se3max": (CR / "dk_classic_wk2_main_20Sep2026_se3max_full.csv", "dk_classic_wk2_main_20Sep2026", 0.25),
    "wk2_main_mme": (CR / "dk_classic_wk2_main_20Sep2026_mme_full.csv", "dk_classic_wk2_main_20Sep2026", 0.22),
    "wk3_early": (CR / "dk_classic_wk3_early_27Sep2026_se3max_full.csv", "dk_classic_wk3_early_27Sep2026", 0.25),
    "wk3_afternoon": (CR / "dk_classic_wk3_afternoon_27Sep2026_se3max_full.csv", "dk_classic_wk3_afternoon_27Sep2026", 0.25),
    "wk3_main_se3max": (CR / "dk_classic_wk3_main_27Sep2026_se3max_full.csv", "dk_classic_wk3_main_27Sep2026", 0.25),
    "wk3_main_mme": (CR / "dk_classic_wk3_main_27Sep2026_mme_full.csv", "dk_classic_wk3_main_27Sep2026", 0.22),
}


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def parse_lineup(s):
    p = TOK.split(" " + str(s).strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def load_slate(f, cash_pct):
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    tab["own_pct"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    fpts_map = tab.drop_duplicates("k").set_index("k")["FPTS"].to_dict()
    pos_map = tab.drop_duplicates("k").set_index("k")["Roster Position"].to_dict()

    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy()
    e = e.drop_duplicates("EntryId")
    N = len(e)
    cash_n = int(np.floor(N * cash_pct))
    e = e.sort_values("Points", ascending=False).reset_index(drop=True)
    e["cash"] = e.index < cash_n

    # per-player: field ownership (from %Drafted, own-slot only -- FLEX counted separately
    # via distinct roster string parse below, summed like replay_validation.load_real)
    own_map = tab.groupby("k")["own_pct"].sum().to_dict()

    # build entry x player incidence directly from each entry's Lineup string
    # (more robust than the %Drafted table alone, since it lets us tie player
    # presence to THIS entry's cash outcome directly)
    player_cash_n = {}
    player_field_n = {}
    for _, row in e.iterrows():
        L = parse_lineup(row.Lineup)
        seen = set(norm(nm) for _, nm in L)
        for k in seen:
            player_field_n[k] = player_field_n.get(k, 0) + 1
            if row.cash:
                player_cash_n[k] = player_cash_n.get(k, 0) + 1

    rows = []
    for k, field_n in player_field_n.items():
        cash_n_k = player_cash_n.get(k, 0)
        rows.append(dict(
            k=k, field_n=field_n, field_pct=field_n / N,
            cash_rate=cash_n_k / field_n if field_n else np.nan,
            fpts=fpts_map.get(k, np.nan), roster_position=pos_map.get(k, ""),
            own_pct_reported=own_map.get(k, np.nan),
        ))
    players = pd.DataFrame(rows)
    field_cash_rate = cash_pct  # baseline: this is what "no info" cash rate would be
    players["lift"] = players["cash_rate"] - field_cash_rate
    return e, players, N, cash_n


def load_our_model(sid):
    try:
        pool = optimizer.load_final_projections("dk", sid)
    except Exception as exc:
        print(f"  [warn] could not load our projections for {sid}: {exc}", file=sys.stderr)
        return None
    pool = pool[pool.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    pool["k"] = pool.player_name.map(norm)
    return pool.drop_duplicates("k").set_index("k")


def taxonomy(field_pct, our_own_pct, field_cash_lift, our_proj_z):
    """Four-way tag: did the field roster this heavily & did it cash well,
    vs did OUR model like this player (high modeled ownership / high projection z)."""
    field_liked = field_pct >= 0.15  # rough chalk threshold, slate-relative caveats noted in writeup
    we_liked = (our_own_pct is not None and pd.notna(our_own_pct) and our_own_pct >= 15.0) or (our_proj_z is not None and pd.notna(our_proj_z) and our_proj_z >= 0.5)
    hit = field_cash_lift is not None and pd.notna(field_cash_lift) and field_cash_lift > 0
    if field_liked and we_liked:
        return "both_liked"
    if field_liked and not we_liked:
        return "field_hit_we_missed" if hit else "field_over_we_correct"
    if not field_liked and we_liked:
        return "we_liked_field_didnt"
    return "both_passed"


def main():
    all_players = []
    summary_rows = []
    for lab, (f, sid, cash_pct) in SLATES.items():
        if not f.exists():
            print(f"[skip] {lab}: {f} not found")
            continue
        e, players, N, cash_n = load_slate(f, cash_pct)
        our = load_our_model(sid)
        players["slate"] = lab
        if our is not None:
            players["our_proj"] = players["k"].map(our["final_projection"]) if "final_projection" in our.columns else np.nan
            players["our_own_pct"] = players["k"].map(our["estimated_ownership_pct"]) if "estimated_ownership_pct" in our.columns else np.nan
            z = (players["our_proj"] - players["our_proj"].mean()) / max(players["our_proj"].std(ddof=0), 1e-9)
            players["our_proj_z"] = z
        else:
            players["our_proj"] = np.nan
            players["our_own_pct"] = np.nan
            players["our_proj_z"] = np.nan
        players["tag"] = [
            taxonomy(fp, oo, lift, pz) for fp, oo, lift, pz in
            zip(players.field_pct, players.our_own_pct, players.lift, players.our_proj_z)
        ]
        all_players.append(players)
        summary_rows.append(dict(slate=lab, entries=N, cash_line_n=cash_n, cash_pct=cash_pct))
        print(f"{lab}: {N} entries, cash line top {cash_n} ({cash_pct:.0%})")

    A = pd.concat(all_players, ignore_index=True)
    A.to_csv("analysis/classic_diag/wk3_postmortem_phase1_players.csv", index=False)
    pd.DataFrame(summary_rows).to_csv("analysis/classic_diag/wk3_postmortem_phase1_summary.csv", index=False)

    print(f"\nTotal player-slate rows: {len(A)}\n")
    print("--- tag counts overall ---")
    print(A.tag.value_counts().to_string())

    print("\n--- top cash-drivers per slate (highest lift among field_pct>=10%, min field_n>=20) ---")
    for lab, g in A.groupby("slate"):
        sub = g[(g.field_pct >= 0.10) & (g.field_n >= 20)].sort_values("lift", ascending=False)
        print(f"\n{lab}:")
        print(sub.head(6)[["k", "field_pct", "cash_rate", "lift", "our_own_pct", "our_proj_z", "tag"]].to_string(index=False))

    print("\n--- 'field hit, we missed' flags: high field_pct + positive lift + we had them low (our_own_pct<10 or nan) ---")
    flags = A[(A.field_pct >= 0.15) & (A.lift > 0.05) & ((A.our_own_pct.isna()) | (A.our_own_pct < 10))]
    flags = flags.sort_values(["slate", "lift"], ascending=[True, False])
    print(flags[["slate", "k", "field_pct", "lift", "our_own_pct", "our_proj_z", "tag"]].to_string(index=False))
    flags.to_csv("analysis/classic_diag/wk3_postmortem_phase1_flags.csv", index=False)


if __name__ == "__main__":
    main()
