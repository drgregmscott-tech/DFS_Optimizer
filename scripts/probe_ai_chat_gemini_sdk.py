"""Second attempt at the Gemini grounding verification, using the official
google-genai SDK + chat session (as suggested as a possible fix for the
429/402 the raw REST call hit in probe_ai_chat_gemini.py) instead of a bare
REST call, to see if that changes the quota behavior.

Usage:
    set GEMINI_API_KEY=<key>
    python3 scripts/probe_ai_chat_gemini_sdk.py [model_name]
"""
import os
import sys

from google import genai
from google.genai import types

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.5-flash"

QUESTIONS = [
    "If Davante Adams doesn't play for the Rams this week (Week 8, 2026), "
    "who's expected to benefit the most in the passing game? Please confirm "
    "this reflects news from the current week, and name your source/date -- "
    "if you're not confident it's current, say so rather than guessing.",
    "Is Amon-Ra St. Brown's injury status trending toward playing or sitting "
    "out this week (Week 8, 2026)? Please confirm this reflects news from "
    "the current week, and name your source/date -- if you're not "
    "confident it's current, say so rather than guessing.",
]


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY first.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    for q in QUESTIONS:
        print(f"\n===== question (model={MODEL}) =====\n{q}\n")
        try:
            resp = chat.send_message(q)
            print(resp.text)
            gm = getattr(resp.candidates[0], "grounding_metadata", None)
            if gm and getattr(gm, "web_search_queries", None):
                print("\n--- search queries ---")
                for sq in gm.web_search_queries:
                    print(" -", sq)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR ({type(exc).__name__}): {exc}")


if __name__ == "__main__":
    main()
