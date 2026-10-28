import unittest
from pathlib import Path

from poltergeist import exorcise

ROOT = Path(__file__).resolve().parent.parent
RISK = {"info": 0, "warn": 1, "high": 2}


class DogfoodTest(unittest.TestCase):
    def test_the_repository_has_no_ghosts_of_its_own(self):
        haunted = {}
        for path in exorcise.iter_files([str(ROOT)]):
            report = exorcise.scan_path(path)
            worst = [f for f in report.findings if RISK[f.risk] >= RISK["warn"]]
            if worst:
                haunted[str(path.relative_to(ROOT))] = [(f.line, f.kind) for f in worst]
        self.assertEqual({}, haunted)

    def test_sources_use_line_feeds_only(self):
        crlf = [
            str(path.relative_to(ROOT))
            for path in exorcise.iter_files([str(ROOT)])
            if path.suffix in {".py", ".json", ".md", ".sh", ".toml"} and b"\r" in path.read_bytes()
        ]
        self.assertEqual([], crlf)


if __name__ == "__main__":
    unittest.main()
