"""Pre-lock report of salary rows matched by a non-exact fallback (trades, signings, position mislabels).

Usage: python scripts/match_fallback_report.py [salary_csv ...]
With no args, checks the newest data/salaries_dk_*.csv. Read-only; never blocks a build.

Why: a traded player (e.g. Pittman IND->PIT) gets the right player_id via the name+position
fallback, but nothing surfaced it. Review these before lock: the ID is usually right, but the
reference roster team is stale, so anything keyed off reference team can be wrong.
"""
import glob
import os
import sys

import pandas as pd

FALLBACK = {"auto_fallback_team_mismatch": "medium (likely trade/signing)",
            "auto_fallback_name_only_position_mismatch": "LOW (position mislabel, check)",
            "ambiguous_multiple_candidates": "LOW (unresolved, ambiguous)"}


def report(path):
    df = pd.read_csv(path)
    if "match_method" not in df.columns:
        print(f"{path}: no match_method column"); return 0
    bad = df[df["match_method"].isin(FALLBACK) | df["player_id"].isna()].copy()
    print(f"\n== {os.path.basename(path)}: {len(bad)} fallback/unmatched of {len(df)} rows")
    for _, r in bad.sort_values("Salary", ascending=False).iterrows():
        m = r["match_method"] if isinstance(r["match_method"], str) else "UNMATCHED"
        print(f"  {r['Name']:<24} {r['Position']:<4} {r['TeamAbbrev']:<4} ${int(r['Salary']):>5}  "
              f"{FALLBACK.get(m, m)}  id={r['player_id']}")
    return len(bad)


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob("data/salaries_dk_*.csv"), key=os.path.getmtime)[-1:]
    for f in files:
        report(f)
