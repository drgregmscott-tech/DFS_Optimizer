"""One-off verification: does the Gemini API's Search-grounding tool match
what the Gemini chat app gave us on 2026-10-29 (see
AI_PROBE_QUESTION_TEMPLATES.md and the project memory on the Rams TE
step-up gap)? Not part of the production pipeline yet -- this just answers
"is the API the same tool as the chat app" before we wire anything up.

Usage:
    set GEMINI_API_KEY=<your free AI Studio key>
    python3 scripts/probe_ai_chat_gemini.py

If the model name below 404s, Google has likely renamed/retired it since
this was written (Jan 2026 knowledge cutoff) -- check
https://ai.google.dev/gemini-api/docs/models for the current grounding-
capable model name and pass it as the first CLI arg.
"""
import json
import os
import sys
import urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.5-flash"

QUESTIONS = [
    (
        "adams_nacua",
        "If Davante Adams doesn't play for the Rams this week (Week 8, 2026), "
        "who's expected to benefit the most in the passing game? Please confirm "
        "this reflects news from the current week, and name your source/date -- "
        "if you're not confident it's current, say so rather than guessing.",
    ),
    (
        "st_brown",
        "Is Amon-Ra St. Brown's injury status trending toward playing or sitting "
        "out this week (Week 8, 2026)? Please confirm this reflects news from "
        "the current week, and name your source/date -- if you're not confident "
        "it's current, say so rather than guessing.",
    ),
]


def ask(api_key: str, question: str) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": question}]}],
        "tools": [{"google_search": {}}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY first (free key from https://aistudio.google.com/apikey).")
        sys.exit(1)

    for name, question in QUESTIONS:
        print(f"\n===== {name} (model={MODEL}) =====")
        try:
            result = ask(api_key, question)
        except urllib.error.HTTPError as exc:
            print(f"HTTP {exc.code}: {exc.read().decode('utf-8')[:500]}")
            continue

        try:
            candidate = result["candidates"][0]
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
            print(text.strip())

            grounding = candidate.get("groundingMetadata", {})
            queries = grounding.get("webSearchQueries", [])
            if queries:
                print("\n--- search queries the model actually ran ---")
                for q in queries:
                    print(" -", q)
            chunks = grounding.get("groundingChunks", [])
            if chunks:
                print("--- sources ---")
                for c in chunks[:8]:
                    web = c.get("web", {})
                    if web:
                        print(" -", web.get("title"), web.get("uri"))
        except (KeyError, IndexError):
            print("Unexpected response shape:")
            print(json.dumps(result, indent=2)[:2000])


if __name__ == "__main__":
    main()
