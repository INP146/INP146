import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_languages.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("languages", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LanguageTests(unittest.TestCase):
    def test_aggregates_language_bytes_across_repository_pages(self):
        self.assertTrue(SCRIPT.exists(), "Self-hosted language generator is missing")
        module = load_generator()
        def repository(*languages):
            return {"languages": {"totalCount": len(languages), "edges": [
                {"size": size, "node": {"name": name, "color": color}}
                for name, size, color in languages
            ]}}
        responses = [
            {"data": {"user": {"repositories": {"nodes": [repository(("Python", 30, "#3572A5"))],
                "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}}},
            {"data": {"user": {"repositories": {"nodes": [repository(("Python", 10, "#3572A5"), ("Vue", 60, "#41b883"))],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}}}},
        ]
        with patch("subprocess.run", side_effect=[SimpleNamespace(stdout=json.dumps(p)) for p in responses]) as run:
            self.assertEqual(module.fetch_languages("INP146"), [
                {"name": "Vue", "size": 60, "color": "#41b883"},
                {"name": "Python", "size": 40, "color": "#3572A5"},
            ])
            query = run.call_args_list[0].args[0]
            self.assertIn("login=INP146", query)
            self.assertIn("privacy: PUBLIC", " ".join(query))
            self.assertIn("isFork: false", " ".join(query))
            self.assertIn("ownerAffiliations: OWNER", " ".join(query))
            self.assertIn("cursor=next", run.call_args_list[1].args[0])

    def test_renders_six_languages_in_both_themes_with_escaped_labels(self):
        import xml.etree.ElementTree as ET
        module = load_generator()
        languages = [{"name": "C<&", "size": 50, "color": "#555555"}] + [
            {"name": f"Lang{i}", "size": 10, "color": "#3572A5"} for i in range(6)
        ]
        for theme, background in (("light", "#ffffff"), ("dark", "#0c1014")):
            with self.subTest(theme=theme):
                self.assertTrue(hasattr(module, "render_svg"), "Language SVG renderer is missing")
                svg = module.render_svg(languages, theme)
                root = ET.fromstring(svg)
                self.assertEqual(root.attrib["viewBox"], "0 0 780 165")
                self.assertIn(background, svg)
                self.assertIn("Most Used Languages", svg)
                self.assertIn("public, owned, non-fork", svg)
                self.assertIn("C&lt;&amp;", svg)
                self.assertIn("50.00%", svg)
                self.assertIn("Lang4", svg)
                self.assertNotIn("Lang5", svg)
                bars = [node for node in root.iter() if node.attrib.get("class") == "language-bar"]
                self.assertEqual(len(bars), 6)
                self.assertAlmostEqual(sum(float(node.attrib["width"]) for node in bars), 730, places=1)

    def test_api_errors_empty_and_truncated_data_fail_closed(self):
        module = load_generator()
        responses = [
            {"errors": [{"message": "rate limited"}]},
            {"data": {"user": {"repositories": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}},
            {"data": {"user": {"repositories": {"nodes": [{"languages": {"totalCount": 101, "edges": []}}], "pageInfo": {"hasNextPage": False}}}}},
        ]
        for response in responses:
            with self.subTest(response=response), patch("subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(response))):
                with self.assertRaises(RuntimeError):
                    module.fetch_languages("INP146")
        with self.assertRaises(ValueError):
            module.render_svg([], "light")

    def test_cli_writes_both_themes(self):
        import tempfile
        import xml.etree.ElementTree as ET
        module = load_generator()
        self.assertTrue(hasattr(module, "main"), "Language CLI is missing")
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "fetch_languages", return_value=[{"name": "Python", "size": 10, "color": "#3572A5"}]):
            module.main(["--username", "INP146", "--output-dir", directory])
            for suffix in ("", "-dark"):
                root = ET.parse(Path(directory) / f"github-top-langs{suffix}.svg").getroot()
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")

    def test_readme_and_workflow_use_generated_language_cards(self):
        readme = (ROOT / "README.md").read_text()
        workflow = (ROOT / ".github/workflows/snake.yml").read_text()
        self.assertNotIn("beautiful-github-homepage.vercel.app", readme)
        for suffix in ("", "-dark"):
            self.assertIn(f"https://raw.githubusercontent.com/INP146/INP146/output/github-top-langs{suffix}.svg", readme)
        self.assertIn("python3 scripts/generate_languages.py", workflow)
        self.assertIn("- scripts/generate_languages.py", workflow)
        self.assertIn("- tests/test_languages.py", workflow)


if __name__ == "__main__":

    unittest.main()
