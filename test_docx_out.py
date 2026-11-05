#!/usr/bin/env python3
"""Tests for the DOCX writer.

Speechify ignores document structure but does honor bold/italic runs, so the
only thing that matters audibly is which runs carry emphasis.
"""
import tempfile
import unittest
import xml.dom.minidom
import zipfile
from pathlib import Path

import docx_out


def document_xml(path: Path) -> str:
    return zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")


def write_tmp(text, emphasis=()):
    tmp = Path(tempfile.mkdtemp()) / "out.docx"
    docx_out.write_docx(text, tmp, emphasis)
    return tmp


class TestResolveEmphasis(unittest.TestCase):
    def test_uniquely_matching_span_resolves_to_its_offsets(self):
        text = "the quick brown fox"
        self.assertEqual(docx_out.resolve_emphasis(text, ["quick"]), [(4, 9)])

    def test_span_occurring_twice_is_skipped(self):
        text = "fox and fox"
        self.assertEqual(docx_out.resolve_emphasis(text, ["fox"]), [])

    def test_span_never_occurring_is_skipped(self):
        self.assertEqual(docx_out.resolve_emphasis("abc", ["zzz"]), [])

    def test_overlapping_spans_keep_only_the_first(self):
        text = "the quick brown fox"
        self.assertEqual(
            docx_out.resolve_emphasis(text, ["quick brown", "brown fox"]),
            [(4, 15)],
        )

    def test_results_are_sorted_by_position(self):
        text = "alpha beta gamma"
        self.assertEqual(
            docx_out.resolve_emphasis(text, ["gamma", "alpha"]),
            [(0, 5), (11, 16)],
        )


class TestSplitIntoRuns(unittest.TestCase):
    def test_segment_without_emphasis_is_one_plain_run(self):
        self.assertEqual(
            docx_out.split_into_runs("hello world", 0, []),
            [("hello world", False)],
        )

    def test_emphasis_splits_the_segment_into_three_runs(self):
        self.assertEqual(
            docx_out.split_into_runs("the quick fox", 0, [(4, 9)]),
            [("the ", False), ("quick", True), (" fox", False)],
        )

    def test_span_outside_the_segment_is_ignored(self):
        self.assertEqual(
            docx_out.split_into_runs("hello", 0, [(90, 95)]),
            [("hello", False)],
        )

    def test_offsets_are_relative_to_the_document_not_the_segment(self):
        # segment starts at document offset 100
        self.assertEqual(
            docx_out.split_into_runs("the quick fox", 100, [(104, 109)]),
            [("the ", False), ("quick", True), (" fox", False)],
        )


class TestWriteDocx(unittest.TestCase):
    def test_produces_a_readable_zip_with_the_required_parts(self):
        path = write_tmp("Hello world.")
        names = zipfile.ZipFile(path).namelist()
        self.assertIn("[Content_Types].xml", names)
        self.assertIn("_rels/.rels", names)
        self.assertIn("word/document.xml", names)

    def test_every_part_is_well_formed_xml(self):
        path = write_tmp("Hello world.")
        z = zipfile.ZipFile(path)
        for name in z.namelist():
            xml.dom.minidom.parseString(z.read(name))

    def test_body_text_appears_in_the_document(self):
        path = write_tmp("Hello world.")
        self.assertIn("Hello world.", document_xml(path))

    def test_chapter_heading_is_bold(self):
        path = write_tmp("THE SECOND AGREEMENT\n\nBody text here.")
        xml_text = document_xml(path)
        heading_para = xml_text.split("THE SECOND AGREEMENT")[0]
        self.assertIn("<w:b/>", heading_para)

    def test_body_paragraph_is_not_bold(self):
        path = write_tmp("Just ordinary prose.")
        self.assertNotIn("<w:b/>", document_xml(path))

    def test_emphasized_span_becomes_an_italic_run(self):
        path = write_tmp("This word is critical to the point.", ["critical"])
        xml_text = document_xml(path)
        self.assertIn("<w:i/>", xml_text)
        self.assertIn("<w:t xml:space=\"preserve\">critical</w:t>", xml_text)

    def test_text_without_emphasis_has_no_italics(self):
        path = write_tmp("This word is critical to the point.")
        self.assertNotIn("<w:i/>", document_xml(path))

    def test_xml_special_characters_are_escaped(self):
        path = write_tmp("Tom & Jerry <loud> stuff.")
        raw = document_xml(path)
        self.assertIn("Tom &amp; Jerry &lt;loud&gt; stuff.", raw)
        xml.dom.minidom.parseString(raw)

    def test_each_paragraph_becomes_its_own_w_p_element(self):
        path = write_tmp("First para.\n\nSecond para.\n\nThird para.")
        self.assertEqual(document_xml(path).count("<w:p>"), 3)

    def test_blank_lines_do_not_produce_empty_paragraphs(self):
        # Speechify ignores them, and they'd only bloat the file
        path = write_tmp("First para.\n\n\n\nSecond para.")
        self.assertEqual(document_xml(path).count("<w:p>"), 2)


if __name__ == "__main__":
    unittest.main()
