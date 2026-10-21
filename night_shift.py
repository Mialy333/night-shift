#!/usr/bin/env python3
"""Night Shift, step 1: read today's git activity, ask a local Gemma, write a morning note.

Stdlib only. Runs fully offline against a local Ollama server.
Writes a markdown note and a matching HTML "morning card" (no external fonts or scripts).
Config via environment variables:
  NIGHT_SHIFT_REPOS   colon-separated list of repo paths (required)
  NIGHT_SHIFT_MODEL   Ollama model name (default: gemma3:4b)
  NIGHT_SHIFT_OUT     output folder (default: <script folder>/morning)
  NIGHT_SHIFT_NOTES   optional free-form notes file (default: <script folder>/notes.md)
  NIGHT_SHIFT_SINCE   git --since value (default: "24 hours ago")
  NIGHT_SHIFT_OPEN    set to 1 to open the morning card in the browser when done
"""

import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = os.environ.get("NIGHT_SHIFT_MODEL", "gemma3:4b")
OUT_DIR = Path(os.environ.get("NIGHT_SHIFT_OUT", str(HERE / "morning"))).expanduser()
NOTES = Path(os.environ.get("NIGHT_SHIFT_NOTES", str(HERE / "notes.md"))).expanduser()
SINCE = os.environ.get("NIGHT_SHIFT_SINCE", "24 hours ago")
OPEN_CARD = os.environ.get("NIGHT_SHIFT_OPEN") == "1"
MAX_CHARS = 8000  # keep the prompt small enough for a small local model

SYSTEM_PROMPT = """You are Night Shift, a quiet assistant for a solo developer who builds in public.
You read one day of git activity and write a very short morning note. Rules:
- Only state what the commits and notes show. Never add goals, plans, skills or results that are not written there.
- A commit starting with "fix:" means something was broken: mention it under "Broke / struggled".
- Be brief. Respect every word limit below. Short words, no filler.
- Plain, warm English, first person ("I"). No hype, no emojis.
- The notes may be in French: always translate them and write the whole note in English.
- The notes may be grouped under headings like "## build", "## learning", "## career".
  Use only the commits and the build notes for "In two lines", the build journal and the post idea.
  Use the other notes (learning, career, anything else) only for "Off the keyboard".

Output exactly this markdown:
## In two lines
<sentence 1, max 12 words: what got done>
<sentence 2, max 12 words: what is next, only if the commits or notes say it; otherwise "Next step: not decided yet.">

## Build journal draft
- Done: <max 15 words>
- Broke / struggled: <max 15 words, or "nothing visible in the commits">
- Open question: <max 15 words, or "none">

## One post idea
<max 15 words: one concrete angle for a short post>

## Off the keyboard
<max 15 words: one gentle reminder from the non-build notes, or "Nothing noted.">
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


# ---------- morning card (HTML) ----------

def inline(text: str) -> str:
    """Escape text, then allow **bold** and `code` from the model's markdown."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def split_sections(body: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.strip():
            if not sections:
                sections.append(("Note", []))
            sections[-1][1].append(line.strip())
    return sections


def block_html(lines: list[str]) -> str:
    bullets = [l[2:] for l in lines if l.startswith("- ")]
    if bullets and len(bullets) == len(lines):
        items = []
        for b in bullets:
            label, sep, rest = b.partition(":")
            if sep and len(label) < 30:
                key = label.strip().lower()
                tone = "ok" if key.startswith("done") else "bad" if key.startswith("broke") else "ask" if key.startswith("open") else ""
                items.append(f'<li><span class="tag {tone}">{inline(label)}</span>{inline(rest.strip())}</li>')
            else:
                items.append(f"<li>{inline(b)}</li>")
        return f"<ul>{''.join(items)}</ul>"
    return "".join(f"<p>{inline(l.lstrip('- '))}</p>" for l in lines)


SLOTH = """<figure class="sloth" aria-label="A sleeping sloth hanging from a branch">
<svg viewBox="0 0 300 270" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 38 Q150 22 292 34" stroke="#6b4f3a" stroke-width="11" stroke-linecap="round" fill="none"/>
  <ellipse cx="40" cy="28" rx="14" ry="6" fill="#34d399" opacity=".75" transform="rotate(-25 40 28)"/>
  <ellipse cx="262" cy="24" rx="14" ry="6" fill="#34d399" opacity=".75" transform="rotate(20 262 24)"/>
  <ellipse cx="236" cy="22" rx="10" ry="4.5" fill="#22d3ee" opacity=".55" transform="rotate(-15 236 22)"/>
  <g class="swing">
    <path d="M112 38 L118 118" stroke="#8b6f5a" stroke-width="20" stroke-linecap="round"/>
    <path d="M188 36 L182 118" stroke="#8b6f5a" stroke-width="20" stroke-linecap="round"/>
    <path d="M104 34 q4 -10 10 -2 M112 33 q4 -10 10 -2" stroke="#f5e6d6" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path d="M180 32 q4 -10 10 -2 M188 31 q4 -10 10 -2" stroke="#f5e6d6" stroke-width="3" fill="none" stroke-linecap="round"/>
    <ellipse cx="150" cy="168" rx="72" ry="64" fill="#8b6f5a"/>
    <ellipse cx="150" cy="178" rx="44" ry="40" fill="#a3866f"/>
    <ellipse cx="116" cy="222" rx="18" ry="13" fill="#7a604d"/>
    <ellipse cx="184" cy="222" rx="18" ry="13" fill="#7a604d"/>
    <circle cx="150" cy="128" r="48" fill="#9c7d66"/>
    <ellipse cx="150" cy="136" rx="38" ry="30" fill="#ead8c3"/>
    <ellipse cx="131" cy="131" rx="14" ry="8" fill="#4a3628" transform="rotate(-18 131 131)"/>
    <ellipse cx="169" cy="131" rx="14" ry="8" fill="#4a3628" transform="rotate(18 169 131)"/>
    <path d="M124 131 q6 5 12 0 M164 131 q6 5 12 0" stroke="#f5e6d6" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    <ellipse cx="150" cy="144" rx="7" ry="4.5" fill="#3a2a1f"/>
    <path d="M140 153 Q150 161 160 153" stroke="#3a2a1f" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    <circle cx="124" cy="146" r="5" fill="#f9a8d4" opacity=".55"/>
    <circle cx="176" cy="146" r="5" fill="#f9a8d4" opacity=".55"/>
  </g>
  <text class="z z1" x="206" y="104">z</text>
  <text class="z z2" x="218" y="88">z</text>
  <text class="z z3" x="230" y="70">Z</text>
</svg>
<figcaption>Working slowly so you don't have to.</figcaption>
</figure>"""


def render_card(body: str, day: date) -> str:
    sections = split_sections(body)
    hero_title, hero_lines = sections[0] if sections else ("Note", [body])
    rest = sections[1:]
    cards = "".join(
        f'<section class="glass card c{i % 3}"><h2>{inline(title)}</h2>{block_html(lines)}</section>'
        for i, (title, lines) in enumerate(rest)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Night Shift · {day:%a %d %b}</title>
<style>
:root {{
  --bg: #0b0920; --ink: #ece9ff; --muted: #a49fd0;
  --violet: #a855f7; --blue: #3b82f6; --cyan: #22d3ee; --orange: #fb923c; --pink: #ec4899;
  --glass: rgba(255,255,255,.06); --line: rgba(255,255,255,.12);
}}
* {{ box-sizing: border-box; margin: 0; }}
html {{ background: var(--bg); }}
body {{
  min-height: 100vh; color: var(--ink); padding: 48px 16px;
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  background:
    radial-gradient(900px 600px at 85% -10%, rgba(168,85,247,.35), transparent 60%),
    radial-gradient(700px 500px at -10% 110%, rgba(59,130,246,.30), transparent 60%),
    linear-gradient(160deg, #120d33 0%, var(--bg) 55%, #1a0f3d 100%);
  }}
main {{ max-width: 880px; margin: 0 auto; position: relative; }}
.orb {{
  position: absolute; right: -10px; top: -20px; width: 120px; height: 120px; border-radius: 50%;
  border: 10px solid transparent; filter: drop-shadow(0 0 24px rgba(236,72,153,.55));
  background: conic-gradient(from 200deg, var(--orange), var(--pink), var(--violet), transparent 75%) border-box;
  -webkit-mask: linear-gradient(#000 0 0) padding-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude; opacity: .9;
}}
.pill {{
  display: inline-flex; gap: 10px; align-items: center; padding: 8px 16px; border-radius: 999px;
  background: var(--glass); border: 1px solid var(--line); color: var(--muted); font-size: 14px;
  backdrop-filter: blur(12px);
}}
.pill b {{ color: var(--ink); font-weight: 600; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 12px var(--cyan); }}
.glass {{
  background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.03));
  border: 1px solid var(--line); border-radius: 22px; backdrop-filter: blur(16px);
  box-shadow: 0 20px 60px rgba(8,4,30,.55), inset 0 1px 0 rgba(255,255,255,.08);
}}
.hero {{ margin: 22px 0 20px; padding: 34px 32px; position: relative; overflow: hidden; }}
.hero::after {{
  content: ""; position: absolute; inset: auto -60px -80px auto; width: 260px; height: 260px;
  background: radial-gradient(circle, rgba(168,85,247,.55), transparent 65%);
}}
.eyebrow {{ font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }}
.hero p {{
  font-size: clamp(18px, 2.6vw, 24px); line-height: 1.4; font-weight: 600; margin-top: 8px;
  background: linear-gradient(90deg, #fff, #d8c7ff 45%, #9ec5ff); -webkit-background-clip: text;
  background-clip: text; color: transparent; position: relative; z-index: 1;
}}
.grid {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; align-items: start; }}
.card {{ padding: 24px 24px 26px; position: relative; }}
.card::before {{
  content: ""; position: absolute; left: 24px; top: 0; width: 56px; height: 3px; border-radius: 0 0 4px 4px;
}}
.c0::before {{ background: linear-gradient(90deg, var(--violet), var(--blue)); box-shadow: 0 0 14px var(--violet); }}
.c1::before {{ background: linear-gradient(90deg, var(--orange), var(--pink)); box-shadow: 0 0 14px var(--orange); }}
.c2::before {{ background: linear-gradient(90deg, var(--cyan), var(--blue)); box-shadow: 0 0 14px var(--cyan); }}
.card h2 {{ font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin-bottom: 14px; }}
.card p {{ color: var(--ink); }}
ul {{ list-style: none; padding: 0; display: grid; gap: 12px; }}
li {{ padding: 12px 14px; border-radius: 14px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07); }}
.tag {{
  display: inline-block; margin-right: 8px; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: linear-gradient(90deg, rgba(168,85,247,.35), rgba(59,130,246,.35)); color: #f3eeff;
}}
.tag.ok  {{ background: rgba(52,211,153,.18); color: #6ee7b7; box-shadow: inset 0 0 0 1px rgba(52,211,153,.45); }}
.tag.bad {{ background: rgba(248,113,113,.18); color: #fca5a5; box-shadow: inset 0 0 0 1px rgba(248,113,113,.45); }}
.tag.ask {{ background: rgba(250,204,21,.16); color: #fde68a; box-shadow: inset 0 0 0 1px rgba(250,204,21,.45); }}
.sloth {{ display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 240px; }}
.sloth svg {{ width: 100%; max-width: 320px; overflow: visible; filter: drop-shadow(0 18px 40px rgba(168,85,247,.35)); }}
.sloth .swing {{ transform-origin: 150px 34px; animation: swing 7s ease-in-out infinite; }}
.sloth .z {{ fill: var(--muted); font: 600 18px ui-rounded, system-ui, sans-serif; animation: float 4s ease-in-out infinite; opacity: 0; }}
.sloth .z2 {{ animation-delay: 1.3s; }} .sloth .z3 {{ animation-delay: 2.6s; }}
.sloth figcaption {{ color: var(--muted); font-size: 14px; margin-top: 4px; font-style: italic; }}
@keyframes swing {{ 0%, 100% {{ transform: rotate(-3deg); }} 50% {{ transform: rotate(3deg); }} }}
@keyframes float {{ 0% {{ opacity: 0; transform: translate(0, 0); }} 30% {{ opacity: .9; }} 100% {{ opacity: 0; transform: translate(14px, -30px); }} }}
@media (prefers-reduced-motion: reduce) {{ .sloth .swing, .sloth .z {{ animation: none; opacity: .8; }} }}
code {{ font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; padding: 1px 6px; border-radius: 6px; background: rgba(255,255,255,.1); }}
footer {{ margin-top: 26px; text-align: center; color: var(--muted); font-size: 13px; }}
footer span {{ color: var(--cyan); }}
@media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} .orb {{ width: 80px; height: 80px; }} .hero {{ padding: 26px 22px; }} }}
</style></head>
<body><main>
  <div class="orb" aria-hidden="true"></div>
  <div class="pill"><span class="dot"></span><b>Night Shift</b> 🦥 {day:%A %d %B}</div>
  <section class="glass hero">
    <div class="eyebrow">{inline(hero_title)}</div>
    {block_html(hero_lines)}
  </section>
  <div class="grid">{cards}{SLOTH}</div>
  <footer>Written overnight by <span>{html.escape(MODEL)}</span> on this Mac · 0 bytes sent anywhere</footer>
</main></body></html>
"""


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
    today = date.today()
    md_file = OUT_DIR / f"{today.isoformat()}.md"
    html_file = OUT_DIR / f"{today.isoformat()}.html"

    activity = collect_activity(repos)
    if not activity:
        body = "Quiet day: no commits and no notes. Rest counts too."
    else:
        try:
            body = ask_gemma(activity)
        except Exception as exc:  # Ollama down, model missing, timeout...
            body = f"Night Shift could not reach the model ({exc}). Raw activity kept below.\n\n{activity}"

    md_file.write_text(f"# Morning note, {today:%a %d %b}\n\n{body}\n", encoding="utf-8")
    html_file.write_text(render_card(body, today), encoding="utf-8")
    notify("Night Shift", "Your morning card is ready.")
    if OPEN_CARD:
        subprocess.run(["open", str(html_file)], check=False, capture_output=True)
    print(f"Wrote {md_file} and {html_file.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
