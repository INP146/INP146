"""Generate standalone activity SVGs without a third-party chart service."""

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import subprocess


def fetch_days(username, start, end):
    query = """query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"login={username}",
         "-f", f"from={start}", "-f", f"to={end}"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    payload = json.loads(result.stdout)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]
            if start[:10] <= day["date"] <= end[:10]]
    if not days:
        raise RuntimeError("GitHub returned no daily contribution data")
    return sorted(days, key=lambda day: day["date"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=30)).isoformat() + "T00:00:00Z"
    days = fetch_days(args.username, start, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        path = output / f"github-activity-graph{suffix}.svg"
        path.write_text(render_svg(days, theme), encoding="utf-8")
        print(f"Generated {path} from {len(days)} days of GitHub contributions")


def render_svg(days, theme):
    if not days:
        raise ValueError("No daily contribution data received")
    palettes = {
        "light": ("#ffffff", "#d0d7de", "#24292f", "#57606a", "#40c463"),
        "dark": ("#0c1014", "#2a2e34", "#2aa889", "#99d1ce", "#2aa889"),
    }
    background, border, title, muted, line = palettes[theme]
    left, right, top, bottom = 60, 975, 66, 246
    ceiling = max(4, max(day["contributionCount"] for day in days))
    points = [
        (left + (right - left) * i / max(1, len(days) - 1),
         bottom - (bottom - top) * day["contributionCount"] / ceiling)
        for i, day in enumerate(days)
    ]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300" role="img" aria-labelledby="title description">',
        '<title id="title">Total contribution graph in all repositories</title>',
        f'<desc id="description">Daily GitHub contributions from {escape(days[0]["date"])} to {escape(days[-1]["date"])}.</desc>',
        f'<rect x="0.5" y="0.5" width="999" height="299" rx="6" fill="{background}" stroke="{border}"/>',
        '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<text x="25" y="33" fill="{title}" font-size="18" font-weight="600">Total contribution graph in all repositories</text>',
    ]
    for i in range(5):
        y = bottom - (bottom - top) * i / 4
        svg.extend([
            f'<path d="M {left} {y:.2f} H {right}" stroke="{border}" stroke-dasharray="3 5"/>',
            f'<text x="48" y="{y + 4:.2f}" text-anchor="end" fill="{muted}" font-size="11">{ceiling * i / 4:g}</text>',
        ])
    coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    svg.extend([
        f'<polygon points="{left},{bottom} {coordinates} {points[-1][0]:.2f},{bottom}" fill="{line}" opacity="0.12"/>',
        f'<polyline points="{coordinates}" stroke="{line}" stroke-width="2" fill="none" stroke-linejoin="round"/>',
    ])
    label_step = max(1, (len(days) - 1 + 6) // 7)
    for i, (day, (x, y)) in enumerate(zip(days, points)):
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{line}"><title>{escape(day["date"])}: {day["contributionCount"]} contributions</title></circle>')
        if i % label_step == 0 or i == len(days) - 1:
            svg.append(f'<text x="{x:.2f}" y="269" text-anchor="middle" fill="{muted}" font-size="11">{escape(day["date"][5:])}</text>')
    svg.append('</g></svg>')
    return "\n".join(svg) + "\n"


if __name__ == "__main__":
    main()
