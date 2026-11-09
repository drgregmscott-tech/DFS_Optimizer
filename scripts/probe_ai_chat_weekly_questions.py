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
from probe_cheap_value_finder import (  # noqa: E402
    candidates_by_position, latest_lineup_pool, build_pool_candidates,
)

SALARY_FLOOR = {"QB": 5000, "RB": 4500, "WR": 4500, "TE": 4500}
# Used only by sustained_wrte_vacancy_candidates' remaining-pass-catcher list (2026-11-09, WK9
# Item F/G parity) -- same value/reasoning as the showdown script's MIN_PROJ.
MIN_PROJ = 3.0
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


def sustained_wrte_vacancy_candidates(rows: list[dict]) -> list[dict]:
    """WK9 Item F (Jordan Watkins/SF, 2026-11-09): the shipped WR/TE next-man-up mechanism
    (apply_wr_replacement/apply_te_replacement) only credits a vacancy when the OUT player's own
    last appearance is the team's immediately-preceding game (a fresh, k=1 OUT) -- a team that's
    lost multiple WR/TE over SEVERAL different weeks (none individually "fresh") gets zero credit
    even though the real-world vacancy is obvious. This is deliberately NOT the same thing as the
    OUT-player-filtered-by-own_vac_bump question dropped 2026-10-29 (see the note above) -- that
    was a single stale OUT player whose redistribution was already settled in trailing-usage
    stats; this is a standing structural situation (2+ WR or 2+ TE out on one team, any duration)
    that our own pipeline has a confirmed, specific blind spot for. Surfaces the team's remaining
    rosterable WR/TE so the probe explicitly checks whether their role has actually settled,
    since the pipeline's own vacancy signal can't be trusted for this case."""
    from collections import defaultdict
    out_by_team_pos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        pos = r.get("position")
        if r.get("injury_status") != "OUT" or pos not in ("WR", "TE"):
            continue
        # Same salary floor as B/D1/the "who's OUT" filter elsewhere in this file -- without it,
        # this counts every inactive-adjacent $2500/$3000 bench/practice-squad name DK lists as
        # OUT (checked live Wk9 main: 17 of 32 teams "qualified" on raw OUT count alone, pure
        # noise). Only a real rosterable player being out for multiple weeks is the signal.
        floor = SALARY_FLOOR.get(pos)
        if floor is not None and float(r.get("salary") or 0) >= floor:
            out_by_team_pos[(r.get("team"), pos)].append(r)
    affected_teams = {team for (team, _pos), lst in out_by_team_pos.items() if len(lst) >= 2}
    if not affected_teams:
        return []
    # Deliberately NO salary floor on this side: the whole point is to catch cheap/overlooked
    # remaining players (Watkins was $3300, well under the $4500 WR floor used above to decide
    # a team even qualifies) -- a salary floor here would exclude the exact case this was built
    # for. A bare final_projection > 0 check still let every inactive-adjacent bench name through
    # (checked live Wk9 main: 24 names across PHI/SF alone) -- MIN_PROJ (same value/reasoning as
    # the showdown script's cheap-piece filter) keeps real complementary pieces while dropping
    # practice-squad-depth noise.
    out = []
    for r in rows:
        if r.get("team") not in affected_teams or r.get("position") not in ("WR", "TE"):
            continue
        if r.get("injury_status") == "OUT":
            continue  # the OUT players themselves, not who's left to ask about
        if float(r.get("final_projection") or 0) >= MIN_PROJ:
            out.append(r)
    out.sort(key=lambda r: (r.get("team"), -float(r.get("final_projection") or 0)))
    return out


def print_usage_and_trap_questions(n: int, names_str: str) -> int:
    """Shared usage-trend + matchup-trap question pair, factored out
    2026-11-07 so the build-derived section (below) can reuse the exact
    same question wording as the existing fringe-value section instead of
    duplicating it."""
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
    return n


# NOTE: C used to fan out over OUT players (filtered by own_vac_bump).
# Dropped 2026-10-29 live test: 4 of 5 named OUT players turned out to be
# long-settled, multi-week-old situations (season-ending IR etc.) -- old
# news whose real redistribution is already sitting in the trailing-usage
# stats probe_team_usage_rank.py reads directly, making a chat guess about
# it redundant. The genuinely live, forward-looking uncertainty is
# QUESTIONABLE/DOUBTFUL players -- C now reuses B's filtered list instead.


def named_candidates(path: str) -> list[str]:
    """Every player named individually in the fringe-value and
    build-derived sections -- i.e. everyone the probe explicitly asked
    about by name, across both sections. Factored out 2026-11-07 for
    probe_report_coverage_check.py: a real run showed most of the
    build-derived list (and a couple of fringe-value names, including
    the one the user caught -- Xavier Worthy, 66/100 real exposure)
    silently missing from the final cross-check report with no warning.
    The question generator was asking about them correctly; the report
    write-up just dropped them. This lets a separate script verify every
    name asked about actually got an answer, instead of trusting the
    report author caught every drop by eye.
    """
    import re
    m = re.search(r"wk(\d+)", path)
    week_num = int(m.group(1)) if m else 8
    by_pos = candidates_by_position(2026, week_num, "dk", top_n=3)
    fringe_names = [x["name"] for pos in ("WR", "RB", "TE") for x in by_pos.get(pos, [])]

    slate_token = os.path.basename(path)
    if slate_token.startswith("final_projections_"):
        slate_token = slate_token[len("final_projections_"):]
    slate_token = slate_token[:-4] if slate_token.endswith(".csv") else slate_token
    pool_path = latest_lineup_pool(slate_token)
    if pool_path and os.path.getmtime(pool_path) < os.path.getmtime(path):
        pool_path = None  # stale -- same rule as main(), not used either way
    build_names: list[str] = []
    if pool_path:
        pool_by_pos = build_pool_candidates(pool_path, "dk", exclude_names=set(fringe_names))
        build_names = [x["name"] for pos in ("WR", "RB", "TE") for x in pool_by_pos.get(pos, [])]
    return fringe_names + build_names


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

    sv = sustained_wrte_vacancy_candidates(rows)
    if sv:
        teams_affected = sorted({r["team"] for r in sv})
        names = ", ".join(f"{r['player_name']} ({r['position']}, {r['team']})" for r in sv)
        print("## Sustained WR/TE vacancy role clarity\n")
        print(
            f"{n}. {' and '.join(teams_affected)} each have multiple WR/TE out for multiple "
            "weeks now, not just on this week's injury report. For each of these remaining "
            f"pass-catchers on that team -- {names} -- has his role/target share genuinely "
            "settled into a bigger piece of the offense now, or is it still unclear who the "
            "real beneficiary of the missing volume is? Note any specific target competition "
            "still left on the roster that would cap his role.\n"
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
        n = print_usage_and_trap_questions(n, names_str)

    # Build-derived section, added 2026-11-07. Additive, not a replacement
    # for the fringe-value section above (explicit user instruction) --
    # closes the gap where a real salary-saver the solver actually
    # rostered falls outside candidates_by_position's top-3-by-efficiency
    # cutoff and never gets asked about. Needs an actual 100-lineup build
    # to already exist for this slate (run the build first, then the
    # probe); silently skipped if it doesn't, since there's nothing yet
    # to read.
    slate_token = os.path.basename(path)
    if slate_token.startswith("final_projections_"):
        slate_token = slate_token[len("final_projections_"):]
    slate_token = slate_token[:-4] if slate_token.endswith(".csv") else slate_token
    pool_path = latest_lineup_pool(slate_token)
    stale_pool = False
    if pool_path and os.path.getmtime(pool_path) < os.path.getmtime(path):
        # Build predates the projections file it's supposedly built from
        # -- e.g. data got refreshed again after the last 100-lineup build
        # ran, so this pool reflects stale injury/role data. Added
        # 2026-11-07: silently using it anyway would hand back real
        # player names that look current but aren't, with no sign
        # anything's wrong.
        stale_pool = True
        pool_path = None
    build_names: list[str] = []
    if pool_path:
        pool_by_pos = build_pool_candidates(pool_path, "dk", exclude_names=set(fringe_names))
        build_names = [x["name"] for pos in ("WR", "RB", "TE") for x in pool_by_pos.get(pos, [])]
    if build_names:
        names_str = ", ".join(build_names)
        print(
            "## Build-derived value check (actually rostered in this "
            "week's lineup pool, not already covered above)\n"
        )
        n = print_usage_and_trap_questions(n, names_str)
    elif pool_path:
        print(
            "<!-- build-derived check: lineup pool found at "
            f"{pool_path} but every cheap WR/RB/TE in it was already "
            "covered by the fringe-value section above. -->\n"
        )
    elif stale_pool:
        print(
            "<!-- build-derived check skipped: found a lineups_multi_"
            f"{slate_token}_*.csv but it's OLDER than {path} -- the "
            "lineup build predates this projections refresh. Re-run the "
            "100-lineup build, then regenerate this probe. -->\n"
        )
    else:
        print(
            "<!-- build-derived check skipped: no lineups_multi_"
            f"{slate_token}_*.csv found yet. Run the 100-lineup build "
            "first, then regenerate this probe, to get it. -->\n"
        )

    print("## Game script / blowout risk\n")
    print(
        f"{n}. Which games this week project as potential blowouts based "
        "on current lines, and which specific players benefit or get hurt "
        "by that kind of script?\n"
    )


if __name__ == "__main__":
    main()
