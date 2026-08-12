import unittest

from src.report_formatting import inline_segments, parse_markdown, strip_inline_markdown


class ReportFormattingTests(unittest.TestCase):
    def test_parse_markdown_recognizes_structural_blocks(self):
        blocks = parse_markdown(
            "# Report\n\n## Risks\n- Missing work\n1. Contact student\nPlain paragraph"
        )
        self.assertEqual(
            [block.kind for block in blocks],
            ["heading1", "blank", "heading2", "bullet", "numbered", "paragraph"],
        )
        self.assertEqual(blocks[3].text, "Missing work")

    def test_inline_segments_preserve_bold_code_and_plain_text(self):
        self.assertEqual(
            inline_segments("Use **evidence** and `course_id`."),
            [
                ("text", "Use "),
                ("bold", "evidence"),
                ("text", " and "),
                ("code", "course_id"),
                ("text", "."),
            ],
        )

    def test_strip_inline_markdown_removes_supported_markers(self):
        self.assertEqual(
            strip_inline_markdown("**Student** used `evidence`."),
            "Student used evidence.",
        )


if __name__ == "__main__":
    unittest.main()
