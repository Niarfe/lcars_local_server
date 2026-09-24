from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module


class MarkdownLibraryTests(TestCase):
    def make_library(self, root: Path) -> None:
        documents = {
            "root_note.md": "# Root",
            "jobskills/skills.md": "# Skills",
            "yt_transcripts/channel_one/direct.md": "# Direct",
            "yt_transcripts/channel_one/2026/deep.md": "# Deep",
            "yt_transcripts/channel_two/other.md": "# Other",
        }
        for relative_path, content in documents.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def test_folder_navigation_scopes_recursively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            self.make_library(markdown_dir)

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                client = app_module.app.test_client()
                root_page = client.get("/markdown").get_data(as_text=True)
                transcript_page = client.get(
                    "/markdown", query_string={"folder": "yt_transcripts"}
                ).get_data(as_text=True)
                channel_page = client.get(
                    "/markdown",
                    query_string={"folder": "yt_transcripts/channel_one"},
                ).get_data(as_text=True)

        self.assertIn('data-folder-link="jobskills"', root_page)
        self.assertIn('data-folder-link="yt_transcripts"', root_page)
        self.assertNotIn('data-folder-link="yt_transcripts/channel_one"', root_page)
        self.assertIn("root_note.md", root_page)
        self.assertIn("yt_transcripts/channel_one/2026/deep.md", root_page)

        self.assertNotIn("root_note.md", transcript_page)
        self.assertIn("yt_transcripts/channel_one/direct.md", transcript_page)
        self.assertIn("yt_transcripts/channel_one/2026/deep.md", transcript_page)
        self.assertIn('class="mini markdown-folder-crumb current"', transcript_page)
        self.assertIn('data-folder-link="yt_transcripts/channel_one"', transcript_page)
        self.assertIn('data-folder-link="yt_transcripts/channel_two"', transcript_page)

        self.assertIn('class="mini markdown-folder-crumb ancestor"', channel_page)
        self.assertIn('data-folder-link="yt_transcripts/channel_one/2026"', channel_page)
        self.assertIn("yt_transcripts/channel_one/direct.md", channel_page)
        self.assertIn("yt_transcripts/channel_one/2026/deep.md", channel_page)
        self.assertNotIn("yt_transcripts/channel_two/other.md", channel_page)
        self.assertIn("INCLUDING SUBFOLDERS", channel_page)

    def test_nested_document_can_be_renamed_in_place(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            original = markdown_dir / "yt_transcripts" / "channel_one" / "old_name.md"
            original.parent.mkdir(parents=True)
            original.write_text("# Original", encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().post(
                    "/api/markdown/rename/yt_transcripts/channel_one/old_name.md",
                    json={"name": "New Name"},
                )

            renamed = original.with_name("new_name.md")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["ok"])
            self.assertFalse(original.exists())
            self.assertTrue(renamed.exists())
            self.assertEqual(
                response.get_json()["url"],
                "/md/view/yt_transcripts/channel_one/new_name.md",
            )
