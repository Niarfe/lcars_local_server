from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from markdown import markdown

import app as app_module


class MarkdownCitationTests(TestCase):
    def test_exported_citations_keep_both_sources_visible_and_clickable(self) -> None:
        first = "https://github.com/malfoyslastname/character-card-spec-v2"
        second = "https://github.com/bradennapier/character-cards-v2/blob/main/README.md"
        html = app_module.render_markdown(
            "- malfoyslastname / character-card-spec-v2 : C'est le Saint-Graal de la communauté. "
            f"[1] ([{first}]({first})), [2] ([{second}]({second}))"
        )

        self.assertIn("<li>malfoyslastname / character-card-spec-v2 : ", html)
        self.assertEqual(html.count("<a "), 2)
        for number, href in ((1, first), (2, second)):
            self.assertIn(f'href="{href}"', html)
            self.assertIn(f'title="{href}"', html)
            self.assertIn(f'aria-label="Source {number}: {href}"', html)
            self.assertIn(f">[{number}]</a>", html)
            self.assertNotIn(f">{href}</a>", html)

    def test_simple_citations_accept_copied_whitespace_and_angle_destinations(self) -> None:
        for space in (" ", "  ", "\t", "\u00a0"):
            for destination in ("https://example.com", "<https://example.com>"):
                with self.subTest(space=space, destination=destination):
                    html = app_module.render_markdown(f"[12]{space}({destination})")

                    self.assertEqual(html.count("<a "), 1)
                    self.assertIn('href="https://example.com"', html)
                    self.assertIn(">[12]</a>", html)

    def test_citations_preserve_url_parentheses_queries_fragments_and_titles(self) -> None:
        url = "https://example.com/page_(detail)?a=1&b=2#sources"
        for source in (f'[1] ({url} "Details")', f'[1] ([{url}]({url} "Details"))'):
            with self.subTest(source=source):
                html = app_module.render_markdown(source)

                self.assertIn('href="https://example.com/page_(detail)?a=1&amp;b=2#sources"', html)
                self.assertIn('title="Details"', html)
                self.assertIn(">[1]</a>", html)

    def test_standard_links_images_references_and_other_text_keep_their_meaning(self) -> None:
        for source in (
            '[Normal **link**](https://example.com "Title")',
            "[1](https://example.com)",
            "![1](https://example.com/image.png)",
            "[1] [doc]\n\n[doc]: https://example.com",
            "[1]\n\n[1]: https://example.com",
            "[1] (additional explanation)",
            "[Name] (https://example.com)",
            "\\[1] (https://example.com)",
            "[Read [1] (https://example.com)](https://other.example.com)",
            "[1] ([Different label](https://example.com))",
            "[1] ([https://example.com](https://other.example.com))",
            "[1] (`https://example.com`)",
        ):
            with self.subTest(source=source):
                self.assertEqual(app_module.render_markdown(source), markdown(source, output_format="html5"))

    def test_incomplete_citations_and_nonweb_destinations_are_not_repaired(self) -> None:
        for source in (
            "[1] (https://example.com",
            "[1] ([https://example.com](https://example.com)",
            "[1] (javascript:alert(1))",
            "[1] (file:///tmp/example.md)",
            "[1] (relative.md)",
            "[1] (https://)",
            "[1] (https://[invalid)",
        ):
            with self.subTest(source=source):
                html = app_module.render_markdown(source)

                self.assertNotIn('class="markdown-citation"', html)

    def test_code_examples_and_raw_html_preserve_literal_citation_syntax(self) -> None:
        citation = "[1] ([https://example.com](https://example.com))"
        for source in (
            f"`{citation}`",
            f"```\n{citation}\n```",
            f"~~~\n{citation}\n~~~",
            f"    {citation}",
            f"<pre>\n{citation}\n</pre>",
        ):
            with self.subTest(source=source):
                html = app_module.render_markdown(source)

                self.assertIn(citation, html)
                self.assertNotIn("<a ", html)

    def test_citations_render_in_tables_and_blockquotes(self) -> None:
        for source in (
            "| Source |\n| --- |\n| [1] (https://example.com) |",
            "> Source [1] (https://example.com)",
        ):
            with self.subTest(source=source):
                html = app_module.render_markdown(source)

                self.assertIn('href="https://example.com"', html)
                self.assertIn(">[1]</a>", html)

    def test_citations_render_across_document_routes_without_rewriting_the_file(self) -> None:
        source = "Source [1] (https://example.com)\n\n<!-- pagebreak -->\n\nNext page\n"
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "sources.md"
            document.write_text(source, encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                client = app_module.app.test_client()
                for route in ("view", "peek", "print-collate/1"):
                    with self.subTest(route=route):
                        response = client.get(f"/md/{route}/sources.md?autoprint=0")

                        self.assertEqual(response.status_code, 200)
                        self.assertIn('href="https://example.com"', response.get_data(as_text=True))
                        self.assertIn(">[1]</a>", response.get_data(as_text=True))

            self.assertEqual(document.read_text(encoding="utf-8"), source)
