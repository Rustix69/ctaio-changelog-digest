#!/usr/bin/env python3
"""Build a static digest of the Claude Code changelog.

Most changelog lines are bug fixes. The useful signal for people running
Claude Code in real workflows is the smaller set of entries that change
behavior (removed, changed, now prompts/refuses, regressions). This script
flags those and renders one self-contained index.html. Stdlib only.
"""
import html, json, re, urllib.request
from datetime import datetime, timezone

SRC = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
BLOB = "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"
API = "https://api.github.com/repos/anthropics/claude-code/commits?path=CHANGELOG.md&per_page=1"
MAX_RELEASES = 60

KINDS = ["Added", "Changed", "Removed", "Fixed", "Improved"]
AREAS = {  # area -> keywords (lowercase, matched as substrings)
    "Hooks": ["hook"],
    "Permissions": ["permission", "approve", "auto mode", "allowlist", "sandbox"],
    "MCP": ["mcp"],
    "Plugins": ["plugin", "marketplace"],
    "Subagents": ["subagent", "agent "],
    "Settings & env": ["settings", "claude_code_", "env var", "environment variable"],
    "IDE": ["vs code", "vscode", "jetbrains", "ide", "extension"],
    "Windows": ["windows", "powershell"],
}
# Phrases that signal "your setup may behave differently after upgrading".
BEHAVIOR = re.compile(
    r"\bnow (prompt|refuse|require|ask|default|block|fail|reject)|no longer|"
    r"regression|deprecat|breaking|\bremoved\b|renamed",
    re.I,
)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ctaio-digest"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def source_commit():
    try:
        c = json.loads(fetch(API))[0]
        return c["sha"][:7], c["commit"]["committer"]["date"][:10]
    except Exception:
        return None, None  # still build; just omit provenance line


def classify(text):
    first = text.split(" ", 1)[0]
    kind = first if first in KINDS else "Other"
    low = text.lower()
    # word-boundary match so "ide" doesn't hit "provide" or "override"
    areas = [a for a, kws in AREAS.items()
             if any(re.search(r"\b" + re.escape(k.strip()) + r"\b", low) for k in kws)]
    behavior = kind in ("Changed", "Removed") or bool(BEHAVIOR.search(text))
    return kind, areas, behavior


def parse(md):
    releases, cur = [], None
    for line in md.splitlines():
        if line.startswith("## "):
            if len(releases) >= MAX_RELEASES:
                break
            ver = line[3:].strip()
            cur = {"v": ver, "anchor": re.sub(r"[^0-9a-z-]", "", ver.lower()), "items": []}
            releases.append(cur)
        elif cur and line.startswith("- "):
            text = line[2:].strip()
            kind, areas, behavior = classify(text)
            cur["items"].append({"t": text, "k": kind, "a": areas, "b": behavior})
    return releases


def main():
    releases = parse(fetch(SRC))
    sha, date = source_commit()
    total = sum(len(r["items"]) for r in releases)
    flagged = sum(i["b"] for r in releases for i in r["items"])
    meta = {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sha": sha, "date": date, "total": total, "flagged": flagged,
        "range": f'{releases[-1]["v"]} to {releases[0]["v"]}', "blob": BLOB,
        "areas": list(AREAS),
    }
    page = open("template.html", encoding="utf-8").read()
    data = json.dumps({"meta": meta, "releases": releases}).replace("</", "<\\/")
    page = page.replace("/*DATA*/null", data)
    open("index.html", "w", encoding="utf-8").write(page)
    print(f"{len(releases)} releases, {total} entries, {flagged} behavior changes")


if __name__ == "__main__":
    main()
