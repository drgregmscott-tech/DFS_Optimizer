"""Coverage check for a pasted-back AI-probe cross-check report.

Built 2026-11-07 after a real Week 9 run: Xavier Worthy (66/100 real
lineup-pool exposure) and most of the build-derived candidate list were
asked about by name in the generated probe questions, but never showed
up anywhere in the final cross-check report -- no error, no "skipped,"
just silently absent. The question generator (probe_ai_chat_weekly_
questions.py) was working correctly; nothing downstream was checking
that every name it asked about actually got dealt with. The user only
caught it because he happened to remember Worthy's real exposure --
this can't depend on that.

This does the dumb, reliable thing: recompute the same candidate list
the probe asked about (named_candidates()), then check whether each name
appears anywhere at all in the pasted report text. It is NOT a
correctness check (it can't tell whether a verdict is right) and it's
NOT exposure-based (exposure counts are never read or used) -- it only
answers "did this player get an answer at all, or did he fall through a
crack."

Usage:
    python scripts/probe_report_coverage_check.py report.txt
    python scripts/probe_report_coverage_check.py        (paste report, then Ctrl-D / Ctrl-Z)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_ai_chat_weekly_questions import named_candidates, pick_latest_slate  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.endswith(".csv")]
    slate_arg = next((a for a in sys.argv[1:] if a.endswith(".csv")), None)
    path = slate_arg or pick_latest_slate()

    if args:
        report_text = Path(args[0]).read_text(encoding="utf-8")
    else:
        print("Paste the cross-check report, then Ctrl-D (mac/linux) or "
              "Ctrl-Z+Enter (Windows):", file=sys.stderr)
        report_text = sys.stdin.read()

    names = named_candidates(path)
    if not names:
        print("No named candidates for this slate (no fringe-value or "
              "build-derived list) -- nothing to check.")
        return

    report_lower = report_text.lower()
    missing = [n for n in names if n.lower() not in report_lower]

    print(f"Checked {len(names)} probed candidates against the pasted report.\n")
    if not missing:
        print("All of them are mentioned somewhere in the report. "
              "(This only confirms the name appears -- it doesn't check "
              "whether it landed in one of the four verdict buckets.)")
        return

    print(f"{len(missing)} probed candidate(s) are NOT mentioned anywhere "
          "in this report -- the chat may not have answered for them, or "
          "the write-up dropped them. Go back to the raw chat answer and "
          "get a verdict for each before treating the report as complete:\n")
    for n in missing:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
