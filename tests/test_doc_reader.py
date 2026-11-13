import pathlib
import tempfile
import unittest
import zlib

from devsquad.core.doc_reader import pdf_text
from devsquad.core.files import ProjectFiles


def make_pdf(content: bytes, compress: bool = True) -> bytes:
    """A small one-page PDF with the given content stream, as a word processor would write it."""
    body = zlib.compress(content) if compress else content
    filt = b"/Filter /FlateDecode " if compress else b""
    return (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
            b"4 0 obj << " + filt + b"/Length " + str(len(body)).encode() + b" >>\nstream\n" + body +
            b"\nendstream\nendobj\ntrailer << /Root 1 0 R >>\n%%EOF\n")


PAGE = (b"BT /F1 12 Tf 72 720 Td (Checkout redesign brief) Tj T* (Users pay with UPI \\(India\\) or card.) Tj ET\n"
        b"BT 72 600 Td [(Deadline:) -250 (March) -250 (15)] TJ ET\n"
        b"BT 72 580 Td <00480069002000740065006100 6D> Tj ET")


class TestPdfText(unittest.TestCase):
    def test_reads_compressed_text(self):
        text = pdf_text(make_pdf(PAGE))
        self.assertIn("Checkout redesign brief", text)
        self.assertIn("Users pay with UPI (India) or card.", text)

    def test_spacing_in_tj_arrays_becomes_spaces(self):
        self.assertIn("Deadline: March 15", pdf_text(make_pdf(PAGE)))

    def test_two_byte_hex_text_is_decoded(self):
        self.assertIn("Hi team", pdf_text(make_pdf(PAGE, compress=False)))

    def test_lines_stay_on_separate_lines(self):
        lines = pdf_text(make_pdf(PAGE)).splitlines()
        self.assertEqual(lines[0], "Checkout redesign brief")

    def test_not_a_pdf_or_no_text_gives_nothing(self):
        self.assertEqual(pdf_text(b"hello"), "")
        self.assertEqual(pdf_text(b"%PDF-1.4\n\x00\xff binary"), "")

    def test_a_broken_stream_is_skipped(self):
        broken = b"%PDF-1.4\n4 0 obj << /Filter /FlateDecode /Length 5 >>\nstream\nnotzl\nendstream\n"
        self.assertEqual(pdf_text(broken + make_pdf(PAGE)[9:]), pdf_text(make_pdf(PAGE)))


class TestAttachmentsForAgents(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.files = ProjectFiles(pathlib.Path(tmp.name))

    def test_agents_read_the_text_of_a_pdf(self):
        self.files.save("brief.pdf", make_pdf(PAGE))
        text = self.files.context_for(["brief.pdf"])
        self.assertIn("brief.pdf (text from the PDF)", text)
        self.assertIn("Users pay with UPI", text)
        self.assertNotIn("couldn't be read", text)

    def test_pdfs_count_as_readable_in_the_file_list(self):
        self.files.save("brief.pdf", make_pdf(PAGE))
        self.assertTrue(self.files.list()[0]["readable"])

    def test_images_are_described_when_a_vision_model_is_given(self):
        self.files.save("mock.png", b"\x89PNG fake")
        seen = []
        text = self.files.context_for(["mock.png"], describe_image=lambda data: seen.append(data) or "A login form with email and password.")
        self.assertEqual(seen, [b"\x89PNG fake"])
        self.assertIn("mock.png (described by a vision model)", text)
        self.assertIn("A login form", text)

    def test_images_are_listed_by_name_without_a_vision_model(self):
        self.files.save("mock.png", b"\x89PNG fake")
        self.assertIn("couldn't be read", self.files.context_for(["mock.png"]))
        self.assertIn("couldn't be read", self.files.context_for(["mock.png"], describe_image=lambda d: None))


if __name__ == "__main__":
    unittest.main()
