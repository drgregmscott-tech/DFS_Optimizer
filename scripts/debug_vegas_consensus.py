"""
debug_vegas_consensus.py
=========================

One-off diagnostic for Session 2.3's implied-total sum-mismatch bug.

Does NOT modify vegas_odds.py. Reuses its load_api_key() and fetch_nfl_odds()
functions, then dumps raw per-bookmaker spread/total data for the games with
the two most different mismatch sizes, so we can see exactly why home_spreads
and away_spreads (or totals) aren't behaving as expected.

Run this from the same place you ran vegas_odds.py (repo root), with:
  python scripts\\debug_vegas_consensus.py
(Windows) or
  python3 scripts/debug_vegas_consensus.py
(Mac/Linux)

It must sit in the same scripts/ folder as vegas_odds.py, since it imports
from it directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vegas_odds import load_api_key, fetch_nfl_odds, consensus_lines, TEAM_NAME_MAP


def main():
    api_key = load_api_key()
    games = fetch_nfl_odds(api_key)

    if not games:
        print("No games returned.")
        return

    # Just look at the first 2 games in detail -- enough to see the pattern.
    for game in games[:2]:
        home = game["home_team"]
        away = game["away_team"]
        print("=" * 70)
        print(f"GAME: {away} @ {home}")
        print("=" * 70)

        for book in game.get("bookmakers", []):
            book_key = book.get("key", "?")
            print(f"\n  Bookmaker: {book_key}")
            for market in book.get("markets", []):
                if market["key"] not in ("spreads", "totals"):
                    continue
                print(f"    Market: {market['key']}")
                for outcome in market["outcomes"]:
                    print(f"      name={outcome.get('name')!r}  point={outcome.get('point')}  price={outcome.get('price')}")

        # Now show what consensus_lines() actually computed for this game
        lines = consensus_lines(game)
        print(f"\n  --> consensus_lines() result: {lines}")
        if lines:
            implied_home = (lines["total"] / 2) - (lines["home_spread"] / 2)
            implied_away = (lines["total"] / 2) - (lines["away_spread"] / 2)
            print(f"  --> implied_home={implied_home:.2f}  implied_away={implied_away:.2f}  "
                  f"sum={implied_home + implied_away:.2f}  expected_total={lines['total']:.2f}")
        print()


if __name__ == "__main__":
    main()
