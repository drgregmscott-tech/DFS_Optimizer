"""Generate this week's AI-chat-probe question list for a SHOWDOWN slate --
ready to paste into a fresh Claude.ai chat (same "blind test" setup as the
classic version). See AI_PROBE_QUESTION_TEMPLATES.md for the template
design; see the 2026-11-05 showdown-extension discussion for why this is a
separate script rather than a flag on probe_ai_chat_weekly_questions.py --
showdown's single-game structure changes which questions matter, not just
the file-loading mechanics:
  - game script / blowout risk is first-class here, not one category among
    many, because it decides who's even relevant in a 6-spot, 2-team pool
  - captain selection is its own category (classic has no equivalent)
  - cheap pieces matter more per-lineup (you need ~2 of them to hit for a
    top lineup, not just 1 as a bonus), so the floor and candidate count
    are both widened relative to classic

Usage:
    python3 scripts/probe_ai_chat_weekly_questions_showdown.py [slate_csv]

With no argument, picks the most recently modified
output/final_projections_dk_dk_showdown_wk*_*.csv file.

Output goes to stdout -- copy it straight into a new Claude.ai chat.
"""
import csv
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_cheap_value_finder import candidates_by_position, dedup_cpt_flex  # noqa: E402

# Wider/lower than classic's SALARY_FLOOR ($5000/$4500): showdown's whole
# rosterable pool is cheaper and thinner, so a classic floor would cut out
# real rotational pieces. Checked against wk9 JAX/BAL: Justice Hill ($3200),
# Chris Rodriguez Jr. ($3400), Rashod Bateman ($3800) are real RB2/WR
# depth, not scrubs -- a $4500 floor would drop all three. Starting point,
# revisit after a real showdown probe run.
SALARY_FLOOR = {"QB": 6000, "RB": 3000, "WR": 3000, "TE": 3000}
# pts/$1000 efficiency blows up for a $200 scrub with a ~1pt projection
# (Tanner Koziol: proj 1.25 -> "eff" 6.24, ranked above real role players).
# Checked live wk9 JAX/BAL: 3.0 clears the true $200-800 bench/UDFA names
# while keeping every real rotational piece under the salary floor.
MIN_PROJ = 3.0
CPT_OWNERSHIP_THRESHOLD = 7.0  # pct -- any CPT above this gets a named question
CHEAP_PIECE_TOP_N = 5  # wider than classic's 3: showdown needs ~2 cheap hits per lineup

FRESHNESS_CHECK = (
    "Please confirm this reflects news from today, and name your "
    "source/date -- if you're not confident it's current, say so rather "
    "than guessing."
)
RELEVANCE_QUALIFIER = (
    "Limit this to DFS-relevant situations -- rosterable/salaried players "
    "with a realistic path to meaningful snaps, not deep backups or "
    "practice-squad depth."
)


def pick_latest_showdown_slate() -> str:
    candidates = glob.glob("output/final_projections_dk_dk_showdown_wk*_*.csv")
    if not candidates:
        raise SystemExit("No output/final_projections_dk_dk_showdown_wk*_*.csv found.")
    return max(candidates, key=os.path.getmtime)


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def salary_filtered_questionable(dedup_rows: list[dict]) -> list[dict]:
    out = []
    for r in dedup_rows:
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


def chalk_captains(rows: list[dict]) -> list[dict]:
    """CPT rows (not deduped -- ownership is specifically a CPT-slot
    number, the FLEX row's ownership is a different number for the same
    player) above CPT_OWNERSHIP_THRESHOLD, highest first."""
    out = []
    for r in rows:
        if r.get("roster_role") != "CPT":
            continue
        own = r.get("estimated_ownership_pct") or r.get("estimated_ownership_pct_heuristic")
        try:
            own = float(own)
        except (TypeError, ValueError):
            continue
        if own > CPT_OWNERSHIP_THRESHOLD:
            out.append(r)
    out.sort(key=lambda r: -float(r.get("estimated_ownership_pct") or 0))
    return out


def game_order(path: str, teams: list[str]) -> list[str]:
    """Filename encodes away_home order (e.g. ..._wk9_JAX_BAL_... = JAX at
    BAL). Falls back to alphabetical if the filename doesn't contain both
    team codes in a parseable order."""
    base = os.path.basename(path)
    positions = {t: base.find(f"_{t}_") if f"_{t}_" in base else base.find(f"_{t}.") for t in teams}
    if all(p != -1 for p in positions.values()) and len(set(positions.values())) == len(teams):
        return sorted(teams, key=lambda t: positions[t])
    return teams


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else pick_latest_showdown_slate()
    rows = load(path)
    dedup_rows = dedup_cpt_flex(rows)
    teams = game_order(path, sorted({r["team"] for r in dedup_rows if r.get("team")}))

    print(f"<!-- generated from {path} -->\n")
    print(
        "I'm going to ask you several DFS-relevant questions about "
        f"tonight's {' at '.join(teams) if len(teams) == 2 else '/'.join(teams)} "
        f"NFL showdown slate. Answer each one directly, and for every answer: {FRESHNESS_CHECK}\n"
    )

    n = 1
    print("## Roster moves / correctness check\n")
    print(
        f"{n}. Are there any recent trades, waiver moves, or practice-squad "
        f"elevations affecting {' or '.join(teams)}'s offense that would change "
        f"an active player's role tonight? {RELEVANCE_QUALIFIER}\n"
    )
    n += 1

    q = salary_filtered_questionable(dedup_rows)
    if q:
        names = ", ".join(f"{r['player_name']} ({r['position']}, {r['team']})" for r in q)
        print("## Injury-tag nuance\n")
        print(
            f"{n}. For these questionable/doubtful players tonight -- {names} "
            "-- summarize the latest practice-participation reporting and "
            "whether each is trending toward playing or sitting.\n"
        )
        n += 1
        print("## Next-man-up / vacated-role beneficiary (if he sits)\n")
        print(
            f"{n}. For each of these same questionable/doubtful players -- "
            f"{names} -- if he doesn't play tonight, who's expected to get "
            "the bulk of his vacated snaps/touches/targets? In a showdown "
            "pool that player could be CPT/FLEX-relevant even at a low "
            "salary, so name him even if he looks like a deep-bench piece "
            "today. Skip anyone where there's no clear single beneficiary.\n"
        )
        n += 1

    print("## Game script / blowout risk (CPT survival)\n")
    print(
        f"{n}. Based on current lines for {' @ '.join(teams)}, how likely is "
        "this game to be a blowout rather than staying close? For each "
        "team, which specific players' roles survive a lopsided script "
        "(bellcow volume protecting/chasing a lead) versus get cut short "
        "(abandoned game plan, early exit, backups playing late)? Call out "
        "anyone whose captain-worthy volume depends specifically on the "
        "game staying competitive.\n"
    )
    n += 1

    print("## Captain selection\n")
    print(
        f"{n}. Heading into tonight's {' vs. '.join(teams)} showdown, which "
        "player is shaping up to be the chalk (highest-owned) captain "
        "play, and why?\n"
    )
    n += 1

    cpts = chalk_captains(rows)
    if cpts:
        for r in cpts:
            print(
                f"{n}. We're seeing {r['player_name']} ({r['position']}, "
                f"{r['team']}) priced as a captain play with real field "
                "attention tonight. Does that captain pick hold up -- is "
                "his role/matchup/game-script case strong enough to "
                "justify the ownership, or is there a specific risk "
                "(usage cap, game-script dependency, a cheaper teammate "
                "doing the same job) that makes him a weaker captain than "
                "the ownership number suggests?\n"
            )
            n += 1

    import re
    m = re.search(r"wk(\d+)", path)
    week_num = int(m.group(1)) if m else 9
    by_pos = candidates_by_position(
        2026, week_num, "dk", top_n=CHEAP_PIECE_TOP_N, slate_path=path,
        team_filter=teams, thresholds=SALARY_FLOOR, min_proj=MIN_PROJ,
    )
    cheap_names = [x["name"] for pos in ("WR", "RB", "TE") for x in by_pos.get(pos, [])]
    if cheap_names:
        names_str = ", ".join(cheap_names)
        print("## Cheap-piece viability (named, from our own data)\n")
        print(
            f"{n}. A top showdown lineup usually needs 2 cheap pieces to "
            f"actually hit, not just survive. For each of these specific "
            f"players -- {names_str} -- does tonight's specific matchup or "
            "game script give him a real path to the volume a cheap piece "
            "needs to pay off (a role vacancy, a soft matchup, a game "
            "total that supports garbage-time or extended-script volume), "
            "or is his cheap price just reflecting a real role limit with "
            "no realistic path to more? Answer only for players where you "
            "have a real basis, skip the rest rather than guessing.\n"
        )
        n += 1


if __name__ == "__main__":
    main()
