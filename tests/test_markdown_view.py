from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module


class MarkdownViewTests(TestCase):
    def test_nested_markdown_images_are_served_from_asset_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "hobbies" / "draw" / "fem_form_pintrest.md"
            image = document.with_name("fem-form.jpg")
            document.parent.mkdir(parents=True)
            document.write_text("# Draw\n\n![image](./fem-form.jpg)", encoding="utf-8")
            image.write_bytes(b"fake jpg")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                client = app_module.app.test_client()
                page_response = client.get(
                    "/md/view/hobbies/draw/fem_form_pintrest.md"
                )
                image_response = client.get("/md/asset/hobbies/draw/fem-form.jpg")

        page = page_response.get_data(as_text=True)
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('src="/md/asset/hobbies/draw/fem-form.jpg"', page)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.get_data(), b"fake jpg")

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
        self.assertIn('id="open-markdown-folder"', page)
        self.assertIn(">ACTIONS</button>", page)
        self.assertIn('data-md-font-family="serif"', page)
        self.assertIn('data-md-font-family="book"', page)
        self.assertIn('id="print-collate-toggle"', page)
        self.assertIn('disabled aria-disabled="true"', page)
        self.assertIn('data-markdown-library-link href="/markdown">LIBRARY</a>', page)
        self.assertNotIn('id="refresh-todo-view"', page)

    def test_todo_output_view_shows_refresh_action(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "0000" / "00_todo_list.md"
            document.parent.mkdir(parents=True)
            document.write_text("# Todo\n", encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().get(
                    "/md/view/0000/00_todo_list.md"
                )

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="refresh-todo-view"', page)
        self.assertIn('data-doc-id="0000/00_todo_list.md"', page)

    def test_todo_refresh_endpoint_rebuilds_configured_todo_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            todo_dir = markdown_dir / "0000"
            todo_dir.mkdir()
            output = todo_dir / "00_todo_list.md"
            output.write_text(
                "## Matrix (Rx1) old\n\n"
                "### Quadrant I\n"
                "* stale\n\n"
                "## End Matrix\n\n"
                "## **@WaitingFor**\n"
                "* Keep this manual section\n",
                encoding="utf-8",
            )
            (todo_dir / "fidelity_mystery_account.md").write_text(
                "# Fidelity\n\n#%TODO FIDELITY: Log in and move the money\n",
                encoding="utf-8",
            )
            (todo_dir / "done_item.md").write_text("# Done\n\nNo next action.\n", encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().post(
                    "/api/markdown/todo/refresh/0000/00_todo_list.md"
                )
                updated = output.read_text(encoding="utf-8")

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"], 1)
        self.assertEqual(data["no_next_action"], 1)
        self.assertEqual(data["url"], "/md/view/0000/00_todo_list.md")
        self.assertIn("<!-- BEGIN AUTO TODO -->", updated)
        self.assertIn(
            "* [FIDELITY](http://localhost/md/view/0000/fidelity_mystery_account.md) Log in and move the money",
            updated,
        )
        self.assertIn("## NO NEXT ACTION\n* [Done Item]", updated)
        self.assertIn("## **@WaitingFor**\n* Keep this manual section", updated)
        self.assertNotIn("* stale", updated)

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

    def test_signature_page_order_for_two_sheets(self) -> None:
        self.assertEqual(
            app_module.markdown_signature_page_order(8, 2),
            [8, 1, 2, 7, 6, 3, 4, 5],
        )

    def test_signature_page_order_pads_with_blank_pages(self) -> None:
        self.assertEqual(
            app_module.markdown_signature_page_order(6, 2),
            [None, 1, 2, None, 6, 3, 4, 5],
        )

    def test_page_split_ignores_markers_inside_fenced_code(self) -> None:
        pages = app_module.split_markdown_pages(
            "# One\n\n```markdown\n<!-- pagebreak -->\n```\n\n"
            "<!-- pagebreak -->\n\n# Two"
        )

        self.assertEqual(len(pages), 2)
        self.assertIn("<!-- pagebreak -->", pages[0])
        self.assertIn("# Two", pages[1])

    def test_collated_print_route_is_ephemeral_and_imposed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "booklet.md"
            source = "\n\n<!-- pagebreak -->\n\n".join(
                f"# Page {number}" for number in range(1, 7)
            )
            document.write_text(source, encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().get(
                    "/md/print-collate/2/booklet.md",
                    query_string={"autoprint": "0", "font": "book", "scale": "110"},
                )

            files_after_request = list(markdown_dir.iterdir())

        page = response.get_data(as_text=True)
        imposed = re.findall(r'data-logical-page="([^"]+)"', page)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(imposed, ["blank", "1", "2", "blank", "6", "3", "4", "5"])
        self.assertIn('class="collate-print-page font-book"', page)
        self.assertIn('data-auto-print="false"', page)
        self.assertEqual([path.name for path in files_after_request], ["booklet.md"])
