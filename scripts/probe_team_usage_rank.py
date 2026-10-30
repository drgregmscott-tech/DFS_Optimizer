"""Sunday-morning cross-check for the AI-chat-probe workflow: when a probe
answer names a specific beneficiary (e.g. "Godwin gets the bump if Egbuka
sits") but that player's final_projection hasn't moved, this pulls the
SAME underlying trailing usage data the vacancy-redistribution mechanisms
(apply_rb_replacement / apply_te_replacement in statline_model.py) are
built on, so you can see in ~30 seconds whether our own raw data agrees
with the probe's specific claim -- the tiebreaker described in the
AI_PROBE_QUESTION_TEMPLATES.md workflow discussion (2026-10-29).

Usage:
    python3 scripts/probe_team_usage_rank.py TB [--season 2026] [--week 8]

Prints every RB/WR/TE on that team ranked by trailing target share and
carry share. If the probe's named player ranks near the top and our own
final_projection still looks flat, that's a real mechanism gap -- worth a
--thumbs-up in this week's build. If someone else ranks higher, that's the
real next-man-up candidate instead.
"""
import argparse
import csv
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from statline_model import _wrw_trailing_usage, _wrte_stepup_params  # noqa: E402


def load_name_map(slate_file: str | None = None) -> dict[str, tuple[str, str]]:
    """player_id -> (player_name, injury_status), from the given slate
    file (or the latest classic main file by default), so the usage table
    is readable without memorizing ids. Pass --slate-file explicitly for
    a showdown slate (TNF/SNF/MNF games aren't in the classic main file
    at all -- see project_wk8_stale_departed_players_pipeline memory)."""
    if slate_file:
        path = slate_file
    else:
        candidates = glob.glob("output/final_projections_dk_dk_classic_wk*_main_*.csv")
        if not candidates:
            return {}
        path = max(candidates, key=os.path.getmtime)
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {
        r["player_id"]: (r["player_name"], r.get("injury_status", ""))
        for r in rows
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("team", help="Team abbreviation, e.g. TB")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--week", type=int, default=8)
    ap.add_argument("--slate-file", default=None,
                     help="Explicit slate CSV to resolve names/status from "
                          "-- required for a showdown or any team not on "
                          "the classic main slate (e.g. TNF/SNF/MNF).")
    args = ap.parse_args()

    names = load_name_map(args.slate_file)

    p = _wrte_stepup_params(None) or {
        "trail_team_games": 6, "trail_player_apps": 4, "team_vol_games": 4,
    }
    # _wrw_trailing_usage reads its own params internally from the WRW
    # json files in practice; this fallback only matters if that lookup
    # fails, so the script still runs and shows something useful.
    try:
        import json
        from statline_model import WRW_TE_PARAMS
        full_p = json.loads(WRW_TE_PARAMS.read_text(encoding="utf-8"))
    except Exception:
        full_p = p

    ag, tvr = _wrw_trailing_usage(args.season, args.week, [args.team], full_p)
    if ag is None or ag.empty or args.team not in ag.index.get_level_values(0):
        print(f"No trailing usage data found for {args.team}.")
        return

    a = ag.loc[args.team].copy()
    a = a.sort_values("sh_tgt", ascending=False)
    print(f"\n{args.team} trailing usage (as of {args.season} wk{args.week}, "
          f"last {full_p.get('trail_player_apps', '?')} games):\n")
    print(f"{'player':22s} {'pos':4s} {'status':12s} {'tgt share':>10s} {'car share':>10s} {'last_g':>7s}")
    for pid, row in a.iterrows():
        name, status = names.get(pid, (pid, "?"))
        print(f"{name:22s} {row['pos']:4s} {status:12s} {row['sh_tgt']:>10.1%} {row['sh_car']:>10.1%} {int(row['last_g']):>7d}")

    print(
        "\nCross-check: does the probe's named beneficiary rank near the "
        "top here? If yes and final_projection still looks flat, that's a "
        "real mechanism gap -- worth --thumbs-up this week. If someone "
        "else ranks higher, they're the real candidate instead."
    )


if __name__ == "__main__":
    main()
