"""Empirically defines "the cash lineup" for V2 (HANDOFF_dfs_army_variables.md:
SE3max = a pivot off your cash build) from REAL field data instead of guessing --
Greg's own framing, 2026-09-22 follow-up: "when I think cash lineup I think of
chalk... look at the results files, find the most common lineups... the lineups
that are most repeatable or have the highest chalk values are probably going to
be the cash lineups."

Two independent chalk measures, both from the real post-lock DK exports already
used by scripts/replay_validation.py:

1. MOST-REPEATED EXACT LINEUP: group every real entry by its exact roster (as a
   frozenset of players), find the single most-duplicated build. This is the
   literal "most repeatable" lineup Greg described.
2. ASSEMBLED-CHALK LINEUP: sum each player's %Drafted ownership ACROSS roster
   slots (DK's export reports RB-slot and FLEX-slot ownership for the same
   player as separate rows -- summed here, unlike replay_validation.load_real's
   own_map, which keeps only the first row per player and so understates any
   FLEX-eligible player's true total share; that's fine for that script's use
   but wrong for this one), then assembles the single most-owned legal player
   at each roster slot (QB x1, RB x2, WR x3, TE x1, FLEX = highest-owned
   remaining RB/WR/TE, DST x1). Reports whether it's salary-legal as constructed
   (chalk plays aren't always the cheapest, so this isn't guaranteed).

Both are graded against the real field the same way replay_validation.grade()
does, to answer directly: does "just play the chalk" actually cash in a
min-cash SE3max format on these slates? That's the empirical basis for V2's
anchor definition (Greg has NOT yet decided whether to build the anchor from
the more repeatable or the more assembled-chalk version -- this script reports
both so that decision has real numbers behind it).

usage: python analysis/classic_diag/chalk_lineup_analysis.py
"""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer
import replay_validation as rv

ROSTER_REQ = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
FLEX_ELIGIBLE = {"RB", "WR", "TE"}
SALARY_CAP = 50000


def most_repeated_lineup(raw_csv):
    df = pd.read_csv(raw_csv, encoding="utf-8-sig", low_memory=False)
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy()
    counts = Counter()
    example_points = {}
    for _, row in e.iterrows():
        players = frozenset(rv.norm(nm) for _, nm in rv.parse(row.Lineup))
        counts[players] += 1
        example_points.setdefault(players, row.Points)
    top_build, top_count = counts.most_common(1)[0]
    return top_build, top_count, len(e), example_points[top_build]


def assembled_chalk_lineup(raw_csv, site, slate_id):
    df = pd.read_csv(raw_csv, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "Roster Position", "%Drafted"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(rv.norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    total_own = tab.groupby("k")["own"].sum()  # sum across RB/FLEX (or WR/FLEX, TE/FLEX) slot rows

    P = optimizer.load_final_projections(site, slate_id)
    P = P[P.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    P["k"] = P.player_name.map(rv.norm)
    P["total_own"] = P["k"].map(total_own).fillna(0.0)

    chosen = []
    used_k = set()
    for pos, n in ROSTER_REQ.items():
        pool = P[P.position == pos].sort_values("total_own", ascending=False)
        picks = pool.head(n)
        chosen.extend(picks.itertuples())
        used_k.update(picks["k"])
    flex_pool = P[P.position.isin(FLEX_ELIGIBLE) & ~P["k"].isin(used_k)].sort_values("total_own", ascending=False)
    flex_pick = flex_pool.iloc[0]
    chosen.append(flex_pick)

    names = [c.player_name for c in chosen]
    ks = [c.k for c in chosen]
    salary = sum(c.salary for c in chosen)
    return names, ks, salary


def main():
    for lab, (f, sid) in rv.SLATES.items():
        fpts_map, own_map, real_points, mine = rv.load_real(f)

        build, count, n_total, pts_from_file = most_repeated_lineup(f)
        g1 = rv.grade(list(build), fpts_map, real_points)
        print(f"\n=== {lab} ===")
        print(f"Most-repeated exact lineup: {count}/{n_total} entries ({count/n_total:.2%}) played this exact build")
        print(f"  players: {sorted(build)}")
        print(f"  real pct={g1['pct']:.3f} cash={g1['cash']} (pts={g1['pts']:.1f})")

        names, ks, salary = assembled_chalk_lineup(f, "dk", sid)
        g2 = rv.grade(ks, fpts_map, real_points)
        legal = salary <= SALARY_CAP
        print(f"Assembled highest-ownership-per-slot lineup (salary {salary}, "
              f"{'LEGAL' if legal else 'OVER CAP by ' + str(salary - SALARY_CAP)}):")
        print(f"  players: {names}")
        print(f"  real pct={g2['pct']:.3f} cash={g2['cash']} (pts={g2['pts']:.1f})")


if __name__ == "__main__":
    main()
