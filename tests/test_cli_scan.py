import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def scan(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "poltergeist", "scan", str(folder)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ScanSummaryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_quiet_folder_says_nothing_about_skips(self):
        (self.root / "a.txt").write_bytes(b"clean\n")
        done = scan(self.root)
        self.assertEqual(0, done.returncode)
        self.assertIn("No ghosts in 1 file(s).", done.stdout)
        self.assertNotIn("Not scanned", done.stdout)

    def test_files_that_could_not_be_read_as_utf8_are_named(self):
        (self.root / "a.txt").write_bytes(b"clean\n")
        (self.root / "table.md").write_bytes("| a |\n".encode("utf-16"))
        (self.root / "latin.txt").write_bytes(b"caf\xe9\n")
        (self.root / "image.bin").write_bytes(b"\x00\x01\x02")
        done = scan(self.root)
        self.assertEqual(0, done.returncode)
        self.assertIn("No ghosts in 1 file(s).", done.stdout)
        self.assertIn("Not scanned: binary (1), not valid UTF-8 (1), starts with a UTF-16 byte order mark (1).", done.stdout)
        self.assertIn("table.md  starts with a UTF-16 byte order mark", done.stdout)
        self.assertIn("latin.txt  not valid UTF-8", done.stdout)
        self.assertNotIn("image.bin  ", done.stdout)


if __name__ == "__main__":
    unittest.main()
