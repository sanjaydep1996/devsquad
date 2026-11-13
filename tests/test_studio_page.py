import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "devsquad" / "web" / "studio.html").read_text(encoding="utf-8")


class TestStudioPage(unittest.TestCase):
    def test_every_toolbar_menu_item_opens_a_real_panel(self):
        names = re.findall(r'role="menuitem"[^>]*data-fn="([A-Za-z_]\w*)"', PAGE)
        self.assertGreaterEqual(len(names), 16)
        for name in names:
            self.assertRegex(PAGE, rf"function {name}\s*\(", name)

    def test_menus_are_labelled_and_start_closed(self):
        for key in ("build", "quality", "tools"):
            self.assertIn(f'aria-controls="menu-{key}"', PAGE)
            self.assertRegex(PAGE, rf'id="menu-{key}" role="menu" aria-labelledby="menuBtn-{key}" hidden')

    def test_menu_actions_do_not_use_eval(self):
        # The page's Content-Security-Policy has no 'unsafe-eval', so eval or new Function would silently fail.
        self.assertNotIn("new Function(", PAGE)
        self.assertNotIn("'unsafe-eval'", PAGE)

    def test_the_three_copies_of_the_page_match(self):
        for copy in ("index.html", "docs/index.html"):
            self.assertEqual((ROOT / copy).read_text(encoding="utf-8"), PAGE, copy)


if __name__ == "__main__":
    unittest.main()
