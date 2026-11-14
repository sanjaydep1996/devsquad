"""The package installs: only devsquad is packaged, with its page, people and field guides."""

import pathlib
import unittest

try:
    import tomllib   # Python 3.11+
except ImportError:  # 3.10 has no TOML reader in the standard library
    tomllib = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")) if tomllib else {}


@unittest.skipIf(tomllib is None, "needs Python 3.11+ to read pyproject.toml")
class TestPackaging(unittest.TestCase):
    def test_only_the_devsquad_package_is_discovered(self):
        # The repo also tracks data/ (sample usage). Without this, `pip install -e .` stops with
        # "Multiple top-level packages discovered in a flat-layout: ['data', 'devsquad']".
        self.assertEqual(CONFIG["tool"]["setuptools"]["packages"]["find"]["include"], ["devsquad*"])

    def test_the_web_page_people_and_guides_ship_with_it(self):
        data = CONFIG["tool"]["setuptools"]["package-data"]["devsquad"]
        for pattern, example in (("web/*.html", "web/studio.html"), ("web/models/people/*", "web/models/people/anim_m.glb"), ("knowledge/*.md", "knowledge/research.md")):
            self.assertIn(pattern, data)
            self.assertTrue((ROOT / "devsquad" / example).is_file(), example)

    def test_versions_agree(self):
        from devsquad import __version__
        self.assertEqual(CONFIG["project"]["version"], __version__)
        self.assertEqual(CONFIG["project"]["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
