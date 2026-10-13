import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import json
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_activity_graph.py"


class ActivityGraphTests(unittest.TestCase):
    def load_generator(self):
        self.assertTrue(SCRIPT.exists(), "The self-hosted activity graph generator is missing")
        spec = importlib.util.spec_from_file_location("activity_graph", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_generates_light_and_dark_svg_from_daily_contributions(self):
        module = self.load_generator()
        days = [
            {"date": "2026-10-01", "contributionCount": 0},
            {"date": "2026-10-02", "contributionCount": 4},
            {"date": "2026-10-03", "contributionCount": 2},
        ]
        for theme, background in [("light", "#ffffff"), ("dark", "#0c1014")]:
            with self.subTest(theme=theme):
                svg = module.render_svg(days, theme)
                root = ET.fromstring(svg)
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertEqual(root.attrib["viewBox"], "0 0 1000 300")
                self.assertIn(background, svg)
                self.assertIn("Total contribution graph in all repositories", svg)
                self.assertIn("2026-10-01: 0 contributions", svg)
                self.assertIn("2026-10-02: 4 contributions", svg)
                self.assertIn("2026-10-03: 2 contributions", svg)
                circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
                self.assertEqual(len(circles), len(days))
                self.assertGreater(float(circles[0].attrib["cy"]), float(circles[1].attrib["cy"]))
    def test_fetches_and_flattens_real_graphql_calendar_shape(self):
        module = self.load_generator()
        self.assertTrue(hasattr(module, "fetch_days"), "GraphQL contribution fetcher is missing")
        days = [{"date": "2026-10-01", "contributionCount": 3}]
        response = {"data": {"user": {"contributionsCollection": {"contributionCalendar": {
            "weeks": [{"contributionDays": days}]
        }}}}}
        with patch("subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(response))) as run:
            self.assertEqual(module.fetch_days("INP146", "2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z"), days)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["gh", "api", "graphql"])
            self.assertIn("login=INP146", command)

    def test_rejects_graphql_errors_instead_of_publishing_empty_data(self):
        module = self.load_generator()
        self.assertTrue(hasattr(module, "fetch_days"), "GraphQL contribution fetcher is missing")
        with patch("subprocess.run", return_value=SimpleNamespace(stdout='{"errors":[{"message":"rate limited"}]}')):
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                module.fetch_days("INP146", "2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z")

    def test_cli_writes_both_themes(self):
        module = self.load_generator()
        self.assertTrue(hasattr(module, "main"), "Generation CLI is missing")
        days = [{"date": "2026-10-01", "contributionCount": 3}]
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "fetch_days", return_value=days):
            module.main(["--username", "INP146", "--output-dir", directory])
            for name in ("github-activity-graph.svg", "github-activity-graph-dark.svg"):
                self.assertEqual(ET.parse(Path(directory) / name).getroot().tag, "{http://www.w3.org/2000/svg}svg")

    def test_readme_and_workflow_use_self_hosted_graphs(self):
        readme = (ROOT / "README.md").read_text()
        workflow = (ROOT / ".github/workflows/snake.yml").read_text()
        self.assertNotIn("github-readme-activity-graph.vercel.app", readme)
        for suffix in ("", "-dark"):
            self.assertIn(f"https://raw.githubusercontent.com/INP146/INP146/output/github-activity-graph{suffix}.svg", readme)
        self.assertIn("actions/checkout@", workflow)
        self.assertIn("python3 scripts/generate_activity_graph.py", workflow)
        self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", workflow)
        self.assertIn("- scripts/generate_activity_graph.py", workflow)


if __name__ == "__main__":
    unittest.main()
