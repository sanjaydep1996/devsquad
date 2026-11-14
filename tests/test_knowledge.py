"""Field guides: what each agent refers to when a task is assigned, and the decisions it takes from them."""

import pathlib
import tempfile
import unittest

from devsquad.core.knowledge import AGENT_FIELDS, KnowledgeBase
from devsquad.core.planner import Planner
from devsquad.server.v5_api import V5Api


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.kb = KnowledgeBase(self.root)

    def test_every_field_ships_with_entries_and_every_agent_has_fields(self):
        fields = {f["field"] for f in self.kb.fields()}
        self.assertTrue({"Architecture", "Backend", "Frontend", "Testing", "DevOps", "Security", "Docs", "Research"} <= fields)
        self.assertTrue(all(e.decide and e.title for e in self.kb.entries))
        for agent in ("apex", "alpha_be", "beta_fe", "gamma_qa", "delta_devops", "zeta_docs"):
            self.assertTrue(AGENT_FIELDS[agent])

    def test_agents_draw_on_their_own_fields_for_the_task(self):
        brief = self.kb.brief("alpha_be", "Add login with password reset by email")
        titles = [e.title for e in brief]
        self.assertIn("Store passwords properly", titles)
        self.assertTrue(all(e.field in AGENT_FIELDS["alpha_be"] for e in brief))
        self.assertNotIn("Frontend", {e.field for e in brief})

    def test_decisions_come_with_a_reason_and_a_source(self):
        decisions = self.kb.decide("alpha_be", "Show the order history list with search")
        self.assertTrue(any("Paginate" in d["decision"] for d in decisions))
        self.assertTrue(all(d["source"] and d["field"] for d in decisions))

    def test_research_picks_a_method_from_the_question(self):
        decisions = self.kb.decide("apex", "Find out why users drop off during onboarding")
        self.assertTrue(any(d["field"] == "Research" for d in decisions))

    def test_project_guides_add_to_the_shipped_ones(self):
        (self.root / ".devsquad" / "knowledge").mkdir(parents=True)
        (self.root / ".devsquad" / "knowledge" / "ours.md").write_text(
            "---\nfield: Backend\nowners: alpha_be\n---\n## Use our money type\ntags: money, payment\nwhen: payment, price\ndecide: Store money as integer cents.\nNever floats.\n")
        kb = KnowledgeBase(self.root)
        self.assertIn("Use our money type", [e.title for e in kb.brief("alpha_be", "Add a price to products")])
        self.assertEqual([e for e in kb.entries if e.title == "Use our money type"][0].source, "project")

    def test_prompt_text_names_the_fundamentals(self):
        text = self.kb.as_prompt(self.kb.brief("gamma_qa", "Fix the crash when the cart is empty"))
        self.assertIn("FUNDAMENTALS", text)
        self.assertIn("Reproduce a bug before fixing it", text)

    def test_template_plans_carry_decisions(self):
        plan = Planner(self.root).propose("Add team invites by email", provider=None)
        self.assertTrue(plan["decisions"])
        self.assertTrue(all({"owner", "decision", "source"} <= set(d) for d in plan["decisions"]))

    def test_routes(self):
        api = V5Api(self.root, provider=lambda: None, run_task=lambda g, r: None)
        status, body = api.handle("GET", "/api/v5/knowledge")
        self.assertEqual(status, 200)
        self.assertTrue(body["fields"] and body["agents"]["apex"])
        status, body = api.handle("POST", "/api/v5/knowledge/brief", {"agent": "delta_devops", "goal": "Deploy the API with Docker"})
        self.assertEqual(status, 200)
        self.assertTrue(body["entries"] and body["decisions"])
        self.assertEqual(api.handle("POST", "/api/v5/knowledge/brief", {"agent": "nobody", "goal": "x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
