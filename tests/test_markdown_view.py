from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module


class MarkdownViewTests(TestCase):
    def test_view_uses_sticky_action_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "jobskills" / "tool_fivetran.md"
            document.parent.mkdir(parents=True)
            document.write_text("# Tool Fivetran\n\nLong document.", encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().get(
                    "/md/view/jobskills/tool_fivetran.md"
                )

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="hero markdown-sticky-header"', page)
        self.assertIn(">EDIT</a>", page)
        self.assertIn(">ACTIONS</button>", page)
        self.assertIn('data-md-font-family="serif"', page)
        self.assertIn('data-md-font-family="book"', page)
        self.assertIn('data-markdown-library-link href="/markdown">LIBRARY</a>', page)

    def test_markdown_page_break_markers_render_as_separators(self) -> None:
        html = app_module.render_markdown(
            "# Journal headers\n\n<!-- pagebreak -->\n\n# Sentence starters"
        )

        self.assertIn(
            '<div class="markdown-page-break" role="separator" aria-label="Page break"></div>',
            html,
        )
        self.assertIn("<h1", html)
        self.assertNotIn("<!-- pagebreak -->", html)

    def test_markdown_page_break_marker_skips_fenced_code(self) -> None:
        transformed = app_module.render_markdown_page_breaks(
            "```markdown\n<!-- pagebreak -->\n```\n\n---page---"
        )

        self.assertIn("```markdown\n<!-- pagebreak -->\n```", transformed)
        self.assertEqual(transformed.count('class="markdown-page-break"'), 1)
