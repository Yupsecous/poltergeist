import unittest

from poltergeist import seance
from poltergeist.lore import CATEGORIES, lookup

from .fakeserver import FakeLlama


class PromptTest(unittest.TestCase):
    CODE = "timeout\u200b: 30\n"
    OBSERVED = "KeyError: 'timeout'"

    def test_plain_sends_the_text_as_pasted(self):
        prompt = seance.build_prompt("python", self.CODE, self.OBSERVED, "plain")
        self.assertIn("\u200b", prompt)
        self.assertNotIn("‹U+200B›", prompt)
        self.assertNotIn("scanner", prompt)
        self.assertNotIn("Platform facts", prompt)

    def test_grounded_makes_the_ghost_visible_and_adds_evidence(self):
        prompt = seance.build_prompt("python", self.CODE, self.OBSERVED, "grounded")
        self.assertNotIn("\u200b", prompt)
        self.assertIn("timeout‹U+200B›: 30", prompt)
        self.assertIn("zero-width character U+200B", prompt)
        self.assertIn("Platform facts that may apply", prompt)

    def test_every_category_is_offered_to_the_model(self):
        prompt = seance.build_prompt("python", "x", "y")
        for name in CATEGORIES:
            self.assertIn(f"- {name}:", prompt)

    def test_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            seance.build_prompt("python", "x", "y", "psychic")


class ParseTest(unittest.TestCase):
    def test_a_well_formed_answer(self):
        d = seance.parse('{"category": "line-endings", "why": "w", "fix": "f"}')
        self.assertTrue(d.valid)
        self.assertEqual(("line-endings", "w", "f"), (d.category, d.why, d.fix))

    def test_json_wrapped_in_prose_is_still_found(self):
        d = seance.parse('Sure!\n```json\n{"category": "path-and-filesystem", "why": "w", "fix": "f"}\n```')
        self.assertTrue(d.valid)

    def test_an_invented_category_is_invalid(self):
        self.assertFalse(seance.parse('{"category": "gremlins", "why": "w", "fix": "f"}').valid)

    def test_garbage_is_invalid_and_kept_for_inspection(self):
        d = seance.parse("I think it is the line endings.")
        self.assertFalse(d.valid)
        self.assertEqual("I think it is the line endings.", d.raw)

    def test_a_json_value_that_is_not_an_object_is_invalid(self):
        self.assertFalse(seance.parse("[1, 2]").valid)


class DiagnoseTest(unittest.TestCase):
    def test_round_trip_through_a_server(self):
        answer = {"category": "invisible-characters", "why": "a zero-width space", "fix": "delete it"}
        with FakeLlama(answer) as server:
            from poltergeist.llm import Client

            diagnosis, reply = seance.diagnose(Client(server.url), "python", "a\u200bb", "KeyError", "grounded")
        self.assertTrue(diagnosis.valid)
        self.assertEqual("invisible-characters", diagnosis.category)
        self.assertEqual(7, reply.completion_tokens)
        self.assertEqual("diagnosis", server.requests[0]["response_format"]["json_schema"]["name"])


class LoreTest(unittest.TestCase):
    def test_no_match_means_no_lore(self):
        self.assertEqual([], lookup("print('hello')"))

    def test_at_most_three_facts(self):
        text = "PHP_EOL .exe UnicodeDecodeError Cannot find module \\\\data os.sep"
        self.assertLessEqual(len(lookup(text)), 3)

    def test_a_plain_newline_escape_does_not_summon_path_lore(self):
        self.assertEqual([], [e.id for e in lookup('echo "a\\nb"') if e.id == "path-separator"])


if __name__ == "__main__":
    unittest.main()
