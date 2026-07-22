"""
optimizer.py
============

Session 3.1 -- Single Lineup Optimizer.

For a given site (DK/FD) and week, reads that site's
`final_projections_{site}_{week}.csv` (Session 2.4, extended in Session 3.1
to include DST/DEF -- see build_projections.py's module docstring, decision
#5) and solves for the single salary-cap-legal lineup that maximizes total
projected points, using each site's own cap/roster rules from
`ingest_salaries.py`'s `SITE_CONFIGS` (Session 1.3) rather than hardcoding
DK's numbers and assuming FD follows.

Design decisions (cleared with the same "flag, don't silently assume"
pattern as every prior session):

  1. Solver: PuLP (already pinned in requirements.txt for exactly this
     phase, per Session 1.1's card). Uses PuLP's bundled CBC solver --
     no separate install needed. This is an integer LINEAR program, so
     CBC's branch-and-bound finds a certified GLOBAL optimum for a problem
     this size (9 slots, ~90 players) essentially instantly -- there is no
     approximation/heuristic risk here, which is what makes the roadmap's
     second validation checkbox ("no single-player swap would increase
     points without breaking a constraint") mathematically guaranteed by
     construction, not just something to eyeball.

  2. FLEX eligibility = {RB, WR, TE}. This is standard classic-contest DFS
     rule on both DK and FD, but it is NOT present anywhere in
     `SITE_CONFIGS` (Session 1.3 only stores the roster_slots list itself,
     e.g. [...,"TE","FLEX","DST"], not which positions can fill FLEX).
     Hardcoded here as `FLEX_ELIGIBLE_POSITIONS` rather than silently
     assumed inline, flagged as a convention this project has never
     explicitly confirmed with the user -- if a future site/format allows
     QB in flex (superflex) this constant is the one place to change.

  3. Constraint formulation: rather than one binary decision variable per
     (player, specific slot) -- which would need arbitrary tie-breaking
     between e.g. "RB slot 1" and "RB slot 2" for two interchangeable RBs
     -- this uses one binary variable per PLAYER (selected or not), with
     aggregate count constraints per position:
       - non-flex-eligible positions (QB, DST/DEF): exact count required.
       - flex-eligible positions (RB, WR, TE): each >= its own fixed
         minimum, and the RB+WR+TE pool together == fixed minimums + FLEX
         count. This is the standard DFS-optimizer ILP formulation and is
         equivalent to true per-slot assignment for any single-lineup
         problem, but avoids a meaningless symmetry the solver would
         otherwise have to break arbitrarily (which specific RB fills
         "RB1" vs "RB2" doesn't matter -- only which 2 RBs are selected
         does). Human-readable slot labels (RB1/RB2/FLEX/etc) are assigned
         AFTER solving, cosmetically, for the output file's `roster_slot`
         column -- this labeling never affects the optimization itself.

  4. Zero-projection players (bye-week skill players and defenses --
     Session 2.4's decision #4b / this session's decision #5 in
     build_projections.py) are NOT filtered out of the player pool before
     optimizing. They're left in deliberately: the ILP will naturally
     never select a 0.0-projection player over a positive-projection
     alternative at the same or lower salary (there's no cap benefit to
     spending money on a locked $0), so filtering them out first would be
     redundant, not incorrect -- but leaving them in doubles as a live
     correctness check: if a bye-week player ever DOES get selected,
     something upstream (or in this file's constraints) is broken, since
     that should be mathematically impossible while any legal alternative
     exists at the same slot.

Usage:
  python3 optimizer.py --site dk --week 10
  python3 optimizer.py --site fd --week 10

Outputs:
  output/lineup_single_{site}_{week}.csv
      One row per roster slot: roster_slot, player_name, position, team,
      salary, projection. Also prints total salary used, cap remaining,
      and total projected points to stdout.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import pulp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS  # noqa: E402 -- Session 1.3's single source of truth for cap/roster/scoring per site

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# See decision #2 above -- not present in SITE_CONFIGS, hardcoded here as
# the one place to change if a future site/format needs a different rule
# (e.g. superflex allowing QB in FLEX).
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}
FLEX_SLOT_LABEL = "FLEX"


# ---------------------------------------------------------------------------
# Step 0: Load projections
# ---------------------------------------------------------------------------

def load_final_projections(site: str, week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections.py --site {site} "
            f"--week {week} first (Session 2.4, extended in Session 3.1 "
            f"for DST/DEF -- decision #5)."
        )
    df = pd.read_csv(path, dtype={"player_id": str})
    required = {"player_id", "player_name", "position", "team", "salary", "final_projection"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections.py's output schema may have changed -- "
            f"update this script's load_final_projections() to match."
        )
    return df


# ---------------------------------------------------------------------------
# Step 1: Parse a site's roster_slots list into position requirements
# ---------------------------------------------------------------------------

def parse_roster_requirements(roster_slots: list) -> tuple:
    """Returns (fixed_counts, flex_count) where fixed_counts is
    {position: required_count} for every non-FLEX slot (e.g.
    {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}) and flex_count is the
    number of FLEX slots (normally 1)."""
    fixed_counts = {}
    flex_count = 0
    for slot in roster_slots:
        if slot == FLEX_SLOT_LABEL:
            flex_count += 1
        else:
            fixed_counts[slot] = fixed_counts.get(slot, 0) + 1
    return fixed_counts, flex_count


# ---------------------------------------------------------------------------
# Step 2: Build and solve the ILP
# ---------------------------------------------------------------------------

def solve_lineup(players: pd.DataFrame, salary_cap: int, fixed_counts: dict,
                  flex_count: int) -> pd.DataFrame:
    prob = pulp.LpProblem("dfs_single_lineup", pulp.LpMaximize)

    # One binary variable per player -- see decision #3 above.
    x = {
        pid: pulp.LpVariable(f"x_{pid}", cat="Binary")
        for pid in players["player_id"]
    }

    proj = players.set_index("player_id")["final_projection"]
    salary = players.set_index("player_id")["salary"]
    position = players.set_index("player_id")["position"]

    prob += pulp.lpSum(x[pid] * proj[pid] for pid in x), "total_projected_points"

    # Salary cap.
    prob += pulp.lpSum(x[pid] * salary[pid] for pid in x) <= salary_cap, "salary_cap"

    # Total roster size.
    total_slots = sum(fixed_counts.values()) + flex_count
    prob += pulp.lpSum(x[pid] for pid in x) == total_slots, "total_roster_size"

    by_position = {
        pos: players.loc[players["position"] == pos, "player_id"].tolist()
        for pos in set(position)
    }

    for pos, required in fixed_counts.items():
        pool = by_position.get(pos, [])
        if pos in FLEX_ELIGIBLE_POSITIONS:
            # Own minimum, can exceed via FLEX -- exact total enforced below.
            prob += pulp.lpSum(x[pid] for pid in pool) >= required, f"min_{pos}"
        else:
            # QB / DST-DEF -- no FLEX eligibility, exact count.
            prob += pulp.lpSum(x[pid] for pid in pool) == required, f"exact_{pos}"

    flex_pool = [pid for pos in FLEX_ELIGIBLE_POSITIONS for pid in by_position.get(pos, [])]
    flex_fixed_total = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS)
    prob += (
        pulp.lpSum(x[pid] for pid in flex_pool) == flex_fixed_total + flex_count,
        "rb_wr_te_pool_total",
    )

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"Solver did not find an optimal solution (status: "
            f"{pulp.LpStatus[status]}). Check that enough players exist "
            f"at every required position within the salary cap."
        )

    selected_ids = [pid for pid in x if x[pid].value() == 1]
    return players[players["player_id"].isin(selected_ids)].copy()


# ---------------------------------------------------------------------------
# Step 3: Assign human-readable roster_slot labels (cosmetic, post-solve)
# ---------------------------------------------------------------------------

def assign_roster_slots(selected: pd.DataFrame, fixed_counts: dict) -> pd.DataFrame:
    remaining = selected.copy()
    rows = []

    # Non-flex-eligible fixed positions first (QB, DST/DEF) -- always an
    # exact match, no ambiguity possible.
    for pos, count in fixed_counts.items():
        if pos in FLEX_ELIGIBLE_POSITIONS:
            continue
        pool = remaining[remaining["position"] == pos]
        for i, row in enumerate(pool.itertuples(), start=1):
            label = pos if count == 1 else f"{pos}{i}"
            rows.append((label, row))
        remaining = remaining.drop(pool.index)

    # Flex-eligible positions -- fill each position's own fixed slots
    # first (highest projection first, arbitrary but deterministic tie-
    # break -- doesn't affect optimality, already solved), whatever's left
    # over across the whole RB/WR/TE pool becomes FLEX.
    leftover = []
    for pos in ["RB", "WR", "TE"]:
        count = fixed_counts.get(pos, 0)
        pool = remaining[remaining["position"] == pos].sort_values(
            "final_projection", ascending=False
        )
        fixed_players = pool.iloc[:count]
        leftover.append(pool.iloc[count:])
        for i, row in enumerate(fixed_players.itertuples(), start=1):
            label = pos if count == 1 else f"{pos}{i}"
            rows.append((label, row))
        remaining = remaining.drop(pool.index)

    leftover_df = pd.concat(leftover) if leftover else remaining.iloc[0:0]
    for row in leftover_df.itertuples():
        rows.append((FLEX_SLOT_LABEL, row))

    out = pd.DataFrame([
        {
            "roster_slot": label,
            "player_name": row.player_name,
            "position": row.position,
            "team": row.team,
            "salary": row.salary,
            "projection": row.final_projection,
        }
        for label, row in rows
    ])
    return out


# ---------------------------------------------------------------------------
# Step 4: Validation assertions (roadmap's first checkbox -- automated,
# not manual eyeballing)
# ---------------------------------------------------------------------------

def validate_lineup(lineup: pd.DataFrame, salary_cap: int, roster_slots: list):
    total_salary = lineup["salary"].sum()
    assert total_salary <= salary_cap, (
        f"VALIDATION FAILED: lineup salary {total_salary} exceeds cap {salary_cap}"
    )
    assert len(lineup) == len(roster_slots), (
        f"VALIDATION FAILED: lineup has {len(lineup)} players, roster needs {len(roster_slots)}"
    )
    fixed_counts, flex_count = parse_roster_requirements(roster_slots)
    for pos, required in fixed_counts.items():
        if pos in FLEX_ELIGIBLE_POSITIONS:
            actual = (lineup["position"] == pos).sum()
            assert actual >= required, (
                f"VALIDATION FAILED: only {actual} {pos}(s) in lineup, need >= {required}"
            )
        else:
            actual = (lineup["position"] == pos).sum()
            assert actual == required, (
                f"VALIDATION FAILED: {actual} {pos}(s) in lineup, need exactly {required}"
            )
    flex_total_actual = lineup["position"].isin(FLEX_ELIGIBLE_POSITIONS).sum()
    flex_total_required = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS) + flex_count
    assert flex_total_actual == flex_total_required, (
        f"VALIDATION FAILED: RB+WR+TE total {flex_total_actual}, need exactly {flex_total_required}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_single_lineup(site: str, week: int) -> pd.DataFrame:
    config = SITE_CONFIGS[site]
    players = load_final_projections(site, week)
    fixed_counts, flex_count = parse_roster_requirements(config["roster_slots"])

    selected = solve_lineup(players, config["salary_cap"], fixed_counts, flex_count)
    lineup = assign_roster_slots(selected, fixed_counts)
    validate_lineup(lineup, config["salary_cap"], config["roster_slots"])

    zero_proj_selected = lineup[lineup["projection"] == 0.0]
    if len(zero_proj_selected):
        print(
            f"WARNING: {len(zero_proj_selected)} zero-projection player(s) selected "
            f"({', '.join(zero_proj_selected['player_name'])}) -- per decision #4 above "
            f"this should be mathematically impossible unless there is no legal "
            f"alternative at that slot/salary. Investigate before trusting this lineup.",
            file=sys.stderr,
        )

    return lineup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    lineup = build_single_lineup(args.site, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"lineup_single_{args.site}_{args.week}.csv"
    lineup.to_csv(out_path, index=False)

    config = SITE_CONFIGS[args.site]
    total_salary = lineup["salary"].sum()
    total_points = lineup["projection"].sum()
    print(f"[{config['label']}] Optimal single lineup for week {args.week}:")
    print(lineup.to_string(index=False))
    print(f"Total salary: {total_salary} / {config['salary_cap']} "
          f"({config['salary_cap'] - total_salary} remaining)")
    print(f"Total projected points: {total_points:.2f}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
