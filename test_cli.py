#!/usr/bin/env python3
"""End-to-end: text file (+ optional emphasis sidecar) -> .docx on disk."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).parent


def run_docx_out(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "docx_out.py"), *map(str, args)],
        capture_output=True, text=True,
    )


class TestDocxOutCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.txt = self.tmp / "speechify.txt"
        self.txt.write_text("CHAPTER ONE\n\nIt was never about the money.\n", encoding="utf-8")
        self.docx = self.tmp / "speechify.docx"

    def test_writes_a_docx_from_a_text_file(self):
        result = run_docx_out(self.txt, self.docx)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.docx.exists())

    def test_body_text_survives_the_round_trip(self):
        run_docx_out(self.txt, self.docx)
        xml = zipfile.ZipFile(self.docx).read("word/document.xml").decode()
        self.assertIn("It was never about the money.", xml)

    def test_emphasis_sidecar_is_applied_when_present(self):
        (self.tmp / "speechify.txt.emphasis.json").write_text(json.dumps(["never"]), encoding="utf-8")
        run_docx_out(self.txt, self.docx)
        xml = zipfile.ZipFile(self.docx).read("word/document.xml").decode()
        self.assertIn("<w:i/>", xml)

    def test_no_italics_when_the_sidecar_is_absent(self):
        run_docx_out(self.txt, self.docx)
        xml = zipfile.ZipFile(self.docx).read("word/document.xml").decode()
        self.assertNotIn("<w:i/>", xml)

    def test_missing_input_file_exits_nonzero(self):
        result = run_docx_out(self.tmp / "nope.txt", self.docx)
        self.assertNotEqual(result.returncode, 0)

    def test_corrupt_sidecar_is_ignored_rather_than_fatal(self):
        (self.tmp / "speechify.txt.emphasis.json").write_text("{{ not json", encoding="utf-8")
        result = run_docx_out(self.txt, self.docx)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.docx.exists())


if __name__ == "__main__":
    unittest.main()
