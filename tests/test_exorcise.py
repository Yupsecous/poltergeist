import os
import tempfile
import unittest
from pathlib import Path

from poltergeist import exorcise


class ExorciseTextTest(unittest.TestCase):
    def test_removes_what_never_belongs_in_source(self):
        hidden = "".join(chr(0xE0000 + ord(c)) for c in "obey")
        dirty = f"\ufeffa\u200bb\u2060c\u202ed{hidden}e"
        self.assertEqual("abcde", exorcise.exorcise_text(dirty))

    def test_keeps_what_prose_may_need_unless_asked(self):
        text = "e\u200d\u200cf\u00a0g\u00adh"
        self.assertEqual(text, exorcise.exorcise_text(text))
        self.assertEqual("ef gh", exorcise.exorcise_text(text, everything=True))

    def test_line_endings_are_only_touched_on_request(self):
        text = "a\r\nb\rc\n"
        self.assertEqual(text, exorcise.exorcise_text(text))
        self.assertEqual("a\nb\nc\n", exorcise.exorcise_text(text, eol="lf"))

    def test_unknown_eol_policy_is_refused(self):
        with self.assertRaises(ValueError):
            exorcise.exorcise_text("a", eol="crlf")

    def test_mixed_script_words_are_never_rewritten(self):
        word = "d\u0430ta"
        self.assertEqual(word, exorcise.exorcise_text(word, everything=True))


class FilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_plan_is_none_for_a_clean_file(self):
        clean = self.root / "clean.txt"
        clean.write_bytes(b"nothing here\n")
        self.assertIsNone(exorcise.plan(clean))

    def test_plan_shows_the_ghost_in_the_diff(self):
        dirty = self.root / "dirty.txt"
        dirty.write_bytes("timeout\u200b: 30\n".encode())
        old, new, diff = exorcise.plan(dirty)
        self.assertEqual("timeout: 30\n", new)
        self.assertIn("-timeout‹U+200B›: 30", diff)
        self.assertIn("+timeout: 30", diff)

    def test_write_keeps_line_endings_byte_for_byte(self):
        target = self.root / "crlf.txt"
        target.write_bytes(b"\xef\xbb\xbfa\r\nb\r\n")
        _, new, _ = exorcise.plan(target)
        exorcise.write(target, new)
        self.assertEqual(b"a\r\nb\r\n", target.read_bytes())
        self.assertEqual([], [p.name for p in self.root.iterdir() if p.name.startswith(".")])

    def test_walk_skips_vcs_and_dependency_folders(self):
        for folder in (".git", "node_modules", "src"):
            (self.root / folder).mkdir()
            (self.root / folder / "f.txt").write_bytes(b"x")
        names = sorted(p.parent.name for p in exorcise.iter_files([str(self.root)]))
        self.assertEqual(["src"], names)

    def test_binary_and_non_utf8_files_are_skipped_with_a_reason(self):
        binary = self.root / "b.bin"
        binary.write_bytes(b"\x00\x01\x02")
        latin = self.root / "l.txt"
        latin.write_bytes(b"caf\xe9\n")
        self.assertEqual((None, "binary"), exorcise.read_text(binary))
        self.assertEqual((None, "not valid UTF-8"), exorcise.read_text(latin))

    def test_utf16_text_is_named_as_such_and_not_called_binary(self):
        utf16 = self.root / "table.md"
        utf16.write_bytes("| a |\n".encode("utf-16"))
        self.assertEqual((None, exorcise.UTF16), exorcise.read_text(utf16))

    def test_symlinks_are_not_followed(self):
        target = self.root / "real.txt"
        target.write_bytes(b"x\n")
        link = self.root / "link.txt"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symlinks")
        self.assertEqual((None, "symlink"), exorcise.read_text(link))


if __name__ == "__main__":
    unittest.main()
