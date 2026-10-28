"""Generate language cards from public, owned, non-fork repositories."""

import argparse
from html import escape
import json
from pathlib import Path
import re
import subprocess


def fetch_languages(username):
    query = """query($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                     privacy: PUBLIC, isFork: false) {
          pageInfo { hasNextPage endCursor }
          nodes {
            languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
              totalCount
              edges { size node { name color } }
            }
          }
        }
      }
    }"""
    totals = {}
    cursor = None
    while True:
        command = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"login={username}"]
        if cursor:
            command.extend(["-f", f"cursor={cursor}"])
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        payload = json.loads(result.stdout)
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload["errors"]))
        repositories = payload["data"]["user"]["repositories"]
        for repository in repositories["nodes"]:
            languages = repository["languages"]
            if languages["totalCount"] != len(languages["edges"]):
                raise RuntimeError("GitHub returned incomplete language data")
            for edge in languages["edges"]:
                name = edge["node"]["name"]
                language = totals.setdefault(name, {"name": name, "size": 0,
                                                      "color": edge["node"]["color"] or "#858585"})
                language["size"] += edge["size"]
        page = repositories["pageInfo"]
        if not page["hasNextPage"]:
            break
        if not page["endCursor"] or page["endCursor"] == cursor:
            raise RuntimeError("GitHub returned an invalid pagination cursor")
        cursor = page["endCursor"]
    languages = sorted((item for item in totals.values() if item["size"] > 0),
                       key=lambda item: (-item["size"], item["name"]))
    if not languages:
        raise RuntimeError("GitHub returned no language data")
    return languages


def render_svg(languages, theme):
    selected = languages[:6]
    total = sum(language["size"] for language in selected)
    if not selected or any(language["size"] <= 0 for language in selected):
        raise ValueError("No positive language data received")
    palettes = {
        "light": ("#ffffff", "#e4e2e2", "#2f80ed", "#434d58"),
        "dark": ("#0c1014", "#2a2e34", "#2aa889", "#99d1ce"),
    }
    background, border, title, text = palettes[theme]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="780" height="165" viewBox="0 0 780 165" role="img" aria-labelledby="title description">',
        '<title id="title">Most Used Languages</title>',
        '<desc id="description">Top six languages by bytes in public, owned, non-fork repositories; percentages are normalized over the displayed languages.</desc>',
        f'<rect x="0.5" y="0.5" width="779" height="164" rx="6" fill="{background}" stroke="{border}"/>',
        '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<text x="25" y="33" fill="{title}" font-size="18" font-weight="600">Most Used Languages</text>',
    ]
    x = 25.0
    for index, language in enumerate(selected):
        color = language["color"]
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = "#858585"
        fraction = language["size"] / total
        width = 730 * fraction
        label = escape(f'{language["name"]} {fraction:.2%}')
        column, row = index % 3, index // 3
        label_x, label_y = 25 + column * 245, 108 + row * 26
        svg.extend([
            f'<rect class="language-bar" x="{x:.3f}" y="58" width="{width:.3f}" height="12" fill="{color}"><title>{label}</title></rect>',
            f'<circle cx="{label_x + 5}" cy="{label_y - 4}" r="5" fill="{color}"/>',
            f'<text x="{label_x + 18}" y="{label_y}" fill="{text}" font-size="12">{label}</text>',
        ])
        x += width
    svg.append('</g></svg>')
    return "\n".join(svg) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args(argv)
    languages = fetch_languages(args.username)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        path = output / f"github-top-langs{suffix}.svg"
        path.write_text(render_svg(languages, theme), encoding="utf-8")
        print(f"Generated {path} from {len(languages)} public repository languages")


if __name__ == "__main__":
    main()
