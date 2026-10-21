#!/usr/bin/env python3
"""Night Shift, step 1: read today's git activity, ask a local Gemma, write a morning note.

Stdlib only. Runs fully offline against a local Ollama server.
Config via environment variables:
  NIGHT_SHIFT_REPOS   colon-separated list of repo paths (required)
  NIGHT_SHIFT_MODEL   Ollama model name (default: gemma3:4b)
  NIGHT_SHIFT_OUT     output folder (default: ~/night-shift/morning)
  NIGHT_SHIFT_NOTES   optional free-form notes file (default: ~/night-shift/notes.md)
  NIGHT_SHIFT_SINCE   git --since value (default: "24 hours ago")
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = os.environ.get("NIGHT_SHIFT_MODEL", "gemma3:4b")
OUT_DIR = Path(os.environ.get("NIGHT_SHIFT_OUT", "~/night-shift/morning")).expanduser()
NOTES = Path(os.environ.get("NIGHT_SHIFT_NOTES", "~/night-shift/notes.md")).expanduser()
SINCE = os.environ.get("NIGHT_SHIFT_SINCE", "24 hours ago")
MAX_CHARS = 8000  # keep the prompt small enough for a 4B model

SYSTEM_PROMPT = """You are Night Shift, a quiet assistant for a solo developer who builds in public.
You read one day of git activity and write a short morning note. Rules:
- Only state what the commits and notes show. Never invent features, fixes or results.
- If something looks broken, reverted or retried, say so plainly.
- Plain, warm English. No hype, no emojis.
- The notes may be in French: always translate them and write the whole note in English.

Output exactly this markdown:
## In two lines
<two sentences: what got done, what is next>

## Build journal draft
- Done: ...
- Broke / struggled: ... (write "nothing visible in the commits" if nothing)
- Open question: ...

## One post idea
<one sentence: a concrete angle for a short post, based on today's work>
"""


def git(repo: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def collect_activity(repos: list[str]) -> str:
    chunks = []
    for repo in repos:
        log = git(repo, "log", f"--since={SINCE}", "--stat", "--format=%n### %h %ad%n%s%n%b", "--date=format:%H:%M")
        if log:
            chunks.append(f"# Repo: {Path(repo).name}\n{log}")
    if NOTES.exists():
        notes = NOTES.read_text(encoding="utf-8").strip()
        if notes:
            chunks.append(f"# My notes from today\n{notes}")
    text = "\n\n".join(chunks)
    return text[:MAX_CHARS]


def ask_gemma(activity: str) -> str:
    payload = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0.3},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": activity},
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["message"]["content"].strip()


def notify(title: str, message: str) -> None:
    # macOS notification; silently skipped elsewhere (no osascript)
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            check=False, capture_output=True,
        )
    except FileNotFoundError:
        pass


def main() -> int:
    repos = [r for r in os.environ.get("NIGHT_SHIFT_REPOS", "").split(":") if r]
    if not repos:
        print("Set NIGHT_SHIFT_REPOS to one or more repo paths.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{date.today().isoformat()}.md"

    activity = collect_activity(repos)
    if not activity:
        body = "Quiet day: no commits and no notes. Rest counts too."
    else:
        try:
            body = ask_gemma(activity)
        except Exception as exc:  # Ollama down, model missing, timeout...
            body = f"Night Shift could not reach the model ({exc}). Raw activity kept below.\n\n{activity}"

    out_file.write_text(f"# Morning note, {date.today():%a %d %b}\n\n{body}\n", encoding="utf-8")
    notify("Night Shift", "Your morning note is ready.")
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
