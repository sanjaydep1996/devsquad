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

    def test_escape_closes_any_open_panel(self):
        self.assertIn('document.querySelectorAll(".modal-overlay").forEach(m => { if (m.style.display && m.style.display !== "none") m.style.display = "none"; })', PAGE)

    def test_panels_never_squash_their_contents(self):
        # The Roadmap's Mermaid block shrank to one line inside its scrolling column before this rule
        self.assertIn('.retro-modal-box div[style*="flex-direction:column"] > *', PAGE)
        self.assertIn('class="review-split"', PAGE)

    def test_3d_view_has_views_buttons_and_keys(self):
        for view in ("overview", "desks", "meeting", "lounge", "window", "walk"):
            self.assertIn(f'data-view="{view}"', PAGE)
        for act in ("left", "right", "in", "out", "help"):
            self.assertIn(f'data-act="{act}"', PAGE)
        self.assertIn("controls.zoomToCursor = true", PAGE)

    def test_people_keep_right_instead_of_pushing_each_other_round(self):
        self.assertIn("a.offX = ease(a.offX, rx * lane", PAGE)
        self.assertNotIn("dz * 0.6", PAGE)   # the old sideways push that made two people circle

    def test_the_wall_board_desk_card_and_exports_are_wired(self):
        self.assertIn('data-view="board"', PAGE)
        self.assertIn('fetch("/api/v5/board")', PAGE)
        self.assertIn("/api/v5/desk/", PAGE)
        self.assertIn('id="office3dDesk"', PAGE)
        for kind in ("plan", "replay", "postmortem"):
            self.assertIn(f"/api/v5/export/{kind}/", PAGE)
        # The Flight Recorder shows real runs only: no made-up incident or timeline
        self.assertNotIn("payment webhook", PAGE)
        self.assertNotIn("Fallback mock timeline", PAGE)

    def test_rigged_people_ship_with_their_licence_and_fall_back_to_drawn_people(self):
        people = ROOT / "devsquad" / "web" / "models" / "people"
        looks = set(re.findall(r'"((?:Male|Female)_Adult_\d\d)"', PAGE))
        self.assertEqual(len(looks), 8)
        for name in looks | {"anim_m", "anim_f"}:
            self.assertTrue((people / f"{name}.glb").read_bytes().startswith(b"glTF"), name)
        self.assertIn("Copyright (c) Microsoft Corporation", (people / "LICENSE-Rocketbox.md").read_text())
        self.assertIn("team.forEach(a => dressUp(a).catch(() => {}))", PAGE)
        self.assertIn("img-src 'self' data: blob:", PAGE)

    def test_know_how_tab_and_reef_tank_are_on_the_page(self):
        self.assertIn('data-tab="know"', PAGE)
        self.assertIn('v5("knowledge/brief"', PAGE)
        self.assertIn("Decisions the team took from their field guides", PAGE)
        self.assertIn('makeFish("clown")', PAGE)
        self.assertIn('makeFish("tang")', PAGE)

    def test_review_loop_and_tour_are_wired(self):
        for needle in ('v5(`ship/', '{ confirm: true }', '/lesson`', 'v5("code-review"', 'v5("research"', 'data-tab="research"', "function startTour", '"devsquad_toured"', "openShipModal('${t.task_id}')"):
            self.assertIn(needle, PAGE)

    def test_the_three_copies_of_the_page_match(self):
        for copy in ("index.html", "docs/index.html"):
            self.assertEqual((ROOT / copy).read_text(encoding="utf-8"), PAGE, copy)


if __name__ == "__main__":
    unittest.main()
