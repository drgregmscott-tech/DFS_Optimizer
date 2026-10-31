"""Generate this week's resolved AI-chat-probe question list -- ready to
paste into a fresh Claude.ai chat (no project context, matching the
"blind test" setup we've been using). See AI_PROBE_QUESTION_TEMPLATES.md
for the template design and the relevance-filter rationale (own_vac_bump
for C, salary floor for B/D1).

Usage:
    python3 scripts/probe_ai_chat_weekly_questions.py [slate_csv]

With no argument, picks the most recently modified
output/final_projections_dk_dk_classic_wk*_main_*.csv file.

Output goes to stdout -- copy it straight into a new Claude.ai chat. Bring
the answers back to this project; they get triaged into:
  A. usable in this week's build right now
  B. a real system/projection mechanism gap (-> postmortem backlog)
  C. ownership-model calibration signal (-> logged, pattern-checked later)
  D. discard (stale/unreliable -- verify from a primary source instead)
"""
import csv
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_cheap_value_finder import candidates_by_position  # noqa: E402

SALARY_FLOOR = {"QB": 5000, "RB": 4500, "WR": 4500, "TE": 4500}
FRESHNESS_CHECK = (
    "Please confirm this reflects news from the current week, and name "
    "your source/date -- if you're not confident it's current, say so "
    "rather than guessing."
)
RELEVANCE_QUALIFIER = (
    "Limit this to DFS-relevant situations -- rosterable/salaried players "
    "with a realistic path to meaningful snaps, not deep backups or "
    "practice-squad depth."
)


def pick_latest_slate() -> str:
    candidates = glob.glob("output/final_projections_dk_dk_classic_wk*_main_*.csv")
    if not candidates:
        raise SystemExit("No output/final_projections_dk_dk_classic_wk*_main_*.csv found.")
    return max(candidates, key=os.path.getmtime)


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def salary_filtered_questionable(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r.get("injury_status") not in ("QUESTIONABLE", "DOUBTFUL"):
            continue
        pos = r["position"]
        floor = SALARY_FLOOR.get(pos)
        if floor is None:
            continue
        if float(r.get("salary") or 0) >= floor:
            out.append(r)
    out.sort(key=lambda r: -float(r.get("salary") or 0))
    return out


# NOTE: C used to fan out over OUT players (filtered by own_vac_bump).
# Dropped 2026-10-29 live test: 4 of 5 named OUT players turned out to be
# long-settled, multi-week-old situations (season-ending IR etc.) -- old
# news whose real redistribution is already sitting in the trailing-usage
# stats probe_team_usage_rank.py reads directly, making a chat guess about
# it redundant. The genuinely live, forward-looking uncertainty is
# QUESTIONABLE/DOUBTFUL players -- C now reuses B's filtered list instead.


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else pick_latest_slate()
    rows = load(path)
    print(f"<!-- generated from {path} -->\n")
    print(
        "I'm going to ask you several DFS-relevant questions about this "
        "week's NFL slate. Answer each one directly, and for every answer: "
        f"{FRESHNESS_CHECK}\n"
    )

    print("## Roster moves / correctness check\n")
    print(
        "1. Are there any recent trades, waiver moves, or practice-squad "
        "elevations this week that would change an active player's role "
        f"on an NFL offense? {RELEVANCE_QUALIFIER}\n"
    )

    q = salary_filtered_questionable(rows)
    if q:
        names = ", ".join(f"{r['player_name']} ({r['position']}, {r['team']})" for r in q)
        print("## Injury-tag nuance\n")
        print(
            f"2. For these questionable/doubtful players this week -- {names} "
            "-- summarize the latest practice-participation reporting and "
            "whether each is trending toward playing or sitting.\n"
        )

    n = 3
    if q:
        names = ", ".join(f"{r['player_name']} ({r['position']}, {r['team']})" for r in q)
        print("## Next-man-up / vacated-role beneficiary (if he sits)\n")
        print(
            f"{n}. For each of these same questionable/doubtful players -- "
            f"{names} -- if he doesn't play, who's expected to get the "
            "bulk of his vacated snaps/touches/targets, based on beat "
            "reporter or coaching staff reporting? Skip anyone where "
            "there's no clear single beneficiary.\n"
        )
        n += 1

    print("## Usage trajectory\n")
    print(
        f"{n}. Has any team's offensive game plan or play-calling tendency "
        "shifted recently (more pass-heavy, more up-tempo, new OC "
        f"influence, etc.) in a way beat reporters have flagged? "
        f"{RELEVANCE_QUALIFIER}\n"
    )
    n += 1

    print("## Field chalk / overlooked value\n")
    print(
        f"{n}. What storylines or players are fantasy analysts and DFS "
        "communities most focused on heading into this week's slate, and "
        "why?\n"
    )
    n += 1
    print(
        f"{n}. Heading into this week's DraftKings main slate, which "
        "players are shaping up to be chalk (high-owned) at QB, RB, WR, "
        "TE, and DST, and why?\n"
    )
    n += 1

    # Fringe-value / matchup-trap questions, 2026-10-31: fanned out onto
    # OUR OWN cheap-value candidates (probe_cheap_value_finder.py) instead
    # of asked as an open question. Open "what's good value" questions
    # have been the weakest-performing category all session (generic,
    # hard to verify, prone to stale/pattern-matched answers); named
    # questions about a specific player have been the strongest. This
    # closes that loop: our data picks the candidates, the chat verifies
    # usage trend + matchup-trap risk on exactly those names.
    import re
    m = re.search(r"wk(\d+)", path)
    week_num = int(m.group(1)) if m else 8
    by_pos = candidates_by_position(2026, week_num, "dk", top_n=3)
    fringe_names = [x["name"] for pos in ("WR", "RB", "TE") for x in by_pos.get(pos, [])]
    if fringe_names:
        names_str = ", ".join(fringe_names)
        print("## Fringe-value verification (named, from our own data)\n")
        print(
            f"{n}. For each of these specific players -- {names_str} -- "
            "has his usage (snap share, target/carry share, red-zone role) "
            "specifically trended up, down, or stayed steady over his last "
            "2-3 games? Note anything a beat reporter or coach has said "
            "about why.\n"
        )
        n += 1
        print(
            f"{n}. For each of those same players, is this week's matchup "
            "a trap -- does it LOOK favorable (weak defense, high implied "
            "total) but actually work against him (wrong position the "
            "defense is weak against, a game script/pace issue, a stat "
            "driven by garbage time not real volume) -- or conversely, "
            "does a bad-looking matchup actually not matter for him "
            "specifically? Answer only for players where you have a real "
            "basis, skip the rest rather than guessing.\n"
        )
        n += 1

    print("## Game script / blowout risk\n")
    print(
        f"{n}. Which games this week project as potential blowouts based "
        "on current lines, and which specific players benefit or get hurt "
        "by that kind of script?\n"
    )


if __name__ == "__main__":
    main()
