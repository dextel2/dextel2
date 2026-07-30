#!/usr/bin/env python3
"""Fetch today's WakaTime language stats and inject into README markers.

Uses Summaries API (not Stats all_time). Section: wakatoday
Compatible with free-tier same-day data; no long-range 202 calc delay.
"""

from __future__ import annotations

import base64
import os
import re
import sys
from datetime import date, datetime, timezone

import urllib.error
import urllib.request
import json

SECTION = "wakatoday"
START = f"<!--START_SECTION:{SECTION}-->"
END = f"<!--END_SECTION:{SECTION}-->"
BLOCK_STYLE = "->"
GRAPH_LEN = 25
LANG_COUNT = 8
IGNORED = {"JSON", "YAML", "TOML"}
README_PATH = os.environ.get("README_PATH", "README.md")


def basic_auth_header(api_key: str) -> str:
    token = base64.b64encode(api_key.encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def make_graph(percent: float) -> str:
    markers = len(BLOCK_STYLE) - 1
    proportion = percent / 100 * GRAPH_LEN
    bar = BLOCK_STYLE[-1] * int(proportion + 0.5 / markers)
    remainder = int((proportion - len(bar)) * markers + 0.5)
    if remainder > 0:
        bar += BLOCK_STYLE[remainder]
    bar += BLOCK_STYLE[0] * (GRAPH_LEN - len(bar))
    return bar


def fetch_today_summary(api_key: str) -> dict:
    # User-local "today" is ideal; UTC date is a reasonable Actions default.
    today = date.today().isoformat()
    url = (
        "https://wakatime.com/api/v1/users/current/summaries"
        f"?start={today}&end={today}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": basic_auth_header(api_key),
            "User-Agent": "dextel2-waka-today/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        print(f"WakaTime HTTP {err.code}: {body}", file=sys.stderr)
        sys.exit(1)
    data = payload.get("data") or []
    if not data:
        return {"date": today, "grand_total": {"text": "0 secs"}, "languages": []}
    return data[0]


def format_block(day: dict) -> str:
    day_date = day.get("range", {}).get("date") or day.get("range", {}).get("start", "")
    if day_date and "T" in str(day_date):
        try:
            day_date = datetime.fromisoformat(str(day_date).replace("Z", "+00:00")).strftime(
                "%d %B %Y"
            )
        except ValueError:
            day_date = str(day_date)[:10]
    elif day_date:
        try:
            day_date = datetime.strptime(str(day_date)[:10], "%Y-%m-%d").strftime("%d %B %Y")
        except ValueError:
            pass

    total = (day.get("grand_total") or {}).get("text") or "0 secs"
    lines = [f"Today: {day_date}", "", f"Total Time: {total}", ""]

    languages = day.get("languages") or []
    filtered = [lg for lg in languages if str(lg.get("name")) not in IGNORED]
    if not filtered:
        lines.append("No activity tracked today")
        return "\n".join(lines)

    pad = max(len(str(lg.get("name", ""))) for lg in filtered[:LANG_COUNT])
    for lg in filtered[:LANG_COUNT]:
        name = str(lg.get("name", "?"))
        text = str(lg.get("text", ""))
        percent = float(lg.get("percent") or 0.0)
        bar = make_graph(percent)
        lines.append(
            f"{name.ljust(pad)}   {text: <16}{bar}   {percent:05.2f} %"
        )
    return "\n".join(lines)


def inject_readme(content: str, block: str) -> str:
    pattern = re.compile(
        re.escape(START) + r"[\s\S]*?" + re.escape(END),
        re.MULTILINE,
    )
    if not pattern.search(content):
        print(f"Markers {START} … {END} not found in {README_PATH}", file=sys.stderr)
        sys.exit(1)
    replacement = f"{START}\n\n```rust\n{block}\n```\n\n{END}"
    return pattern.sub(replacement, content)


def main() -> None:
    api_key = os.environ.get("WAKATIME_API_KEY")
    if not api_key:
        print("WAKATIME_API_KEY is required", file=sys.stderr)
        sys.exit(1)

    summary = fetch_today_summary(api_key)
    block = format_block(summary)
    print(block)

    with open(README_PATH, encoding="utf-8") as fh:
        readme = fh.read()
    updated = inject_readme(readme, block)
    if updated == readme:
        print("README unchanged")
        return
    with open(README_PATH, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"Updated {README_PATH} section {SECTION}")


if __name__ == "__main__":
    main()
