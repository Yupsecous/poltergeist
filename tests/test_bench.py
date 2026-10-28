import json
import re
import unittest
from pathlib import Path

from poltergeist import bench
from poltergeist.ghosts import reveal
from poltergeist.llm import Client
from poltergeist.lore import CATEGORIES
from poltergeist.seance import Diagnosis

from .fakeserver import FakeLlama

ROOT = Path(__file__).resolve().parent.parent


class CasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = bench.load_cases()

    def test_every_class_of_ghost_has_cases(self):
        self.assertEqual(set(CATEGORIES), {c["category"] for c in self.cases})

    def test_the_gold_fix_passes_its_own_rubric(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                gold = Diagnosis(case["category"], "", case["gold_fix"], True, "")
                self.assertTrue(bench.fix_matches(case, gold))

    def test_a_non_answer_fails_every_rubric(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertFalse(bench.fix_matches(case, Diagnosis("", "", "", False, "")))
                self.assertFalse(bench.fix_matches(case, Diagnosis(case["category"], "", "Check the logs.", True, "")))

    def test_rubric_patterns_compile(self):
        for case in self.cases:
            for pattern in case["fix_any"]:
                re.compile(pattern)

    def test_case_files_hold_no_raw_ghosts(self):
        for path in (ROOT / "cases").glob("*.json"):
            with self.subTest(case=path.name):
                path.read_bytes().decode("ascii")

    def test_real_cases_say_where_they_come_from(self):
        real = [c for c in self.cases if bench.is_real(c)]
        self.assertTrue(real)
        for case in real:
            self.assertRegex(case["source"], r"^symfony/ai#\d+$")


class RunTest(unittest.TestCase):
    def test_a_model_that_always_answers_with_the_right_category_scores_full(self):
        cases = bench.load_cases()

        def answer(body):
            user = body["messages"][1]["content"]
            for case in cases:
                if case["code"] in user or reveal(case["code"]) in user:
                    return {"category": case["category"], "why": "because", "fix": case["gold_fix"]}
            return {"category": "gremlins", "why": "", "fix": ""}

        with FakeLlama(answer) as server:
            result = bench.run(Client(server.url), cases, "fake", ("plain", "grounded"), progress=lambda _: None)
        self.assertEqual("fake-model", result["model"])
        for mode in ("plain", "grounded"):
            summary = result["modes"][mode]["summary"]
            self.assertEqual(1.0, summary["category"], mode)
            self.assertEqual(1.0, summary["fix"], mode)
            self.assertEqual(1.0, summary["valid"], mode)

    def test_a_model_that_answers_nonsense_scores_zero_without_crashing(self):
        with FakeLlama({"category": "gremlins", "why": "", "fix": ""}) as server:
            result = bench.run(Client(server.url), bench.load_cases()[:3], "bad", ("plain",), progress=lambda _: None)
        summary = result["modes"]["plain"]["summary"]
        self.assertEqual((0.0, 0.0, 0.0), (summary["category"], summary["fix"], summary["valid"]))

    def test_the_table_lists_every_mode_and_the_baselines(self):
        with FakeLlama({"category": "line-endings", "why": "", "fix": ""}) as server:
            result = bench.run(Client(server.url), bench.load_cases()[:2], "m", ("plain", "grounded"), progress=lambda _: None)
        table = bench.markdown_table([result])
        self.assertIn("| m | plain |", table)
        self.assertIn("| m | grounded |", table)
        self.assertIn("no model", table)
        self.assertIn("chance", table)
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
