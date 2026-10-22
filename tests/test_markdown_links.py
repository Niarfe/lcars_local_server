import json
import os
from html import unescape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlparse

import app as app_module


class MarkdownLinkTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.primary = self.workspace / "markdown"
        self.mounted = self.workspace / "project"
        self.primary.mkdir()
        self.mounted.mkdir()
        config = self.workspace / "content_config.json"
        config.write_text(json.dumps({"markdown_mounts": [
            {"id": "project", "label": "Project", "path": str(self.mounted)},
        ]}), encoding="utf-8")
        for name, value in (("MARKDOWN_DIR", self.primary), ("CONTENT_CONFIG_PATH", config)):
            patcher = patch.object(app_module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = app_module.app.test_client()

    def test_copy_links_resolve_to_the_document_in_each_root_on_another_port(self) -> None:
        relative = "notes/Café [planning] (next) #1 + 50%?&.md"
        for root_id, folder, content in (
            ("markdown", self.primary, "# Primary note"),
            ("project", self.mounted, "# Project note"),
        ):
            with self.subTest(root=root_id):
                document = folder / relative
                document.parent.mkdir()
                document.write_text(content, encoding="utf-8")
                query = {} if root_id == "markdown" else {"root": root_id}
                page = self.client.get("/markdown", query_string=query).get_data(as_text=True)
                link = unescape(re.search(r'data-copy-markdown-link="([^"]+)"', page)[1])
                self.assertTrue(link.startswith("/md/view?path=/"))
                self.assertEqual(parse_qs(urlparse(link).query), {"path": [str(document)]})
                self.assertNotIn("root=", link)
                response = self.client.get(link, base_url="http://127.0.0.1:5051")
                self.assertEqual(response.status_code, 200)
                self.assertIn(content[2:], response.get_data(as_text=True))

    def test_peek_renders_tables_and_resolves_links_and_images_in_the_target_mount(self) -> None:
        document = self.mounted / "notes" / "calendar.md"
        document.parent.mkdir()
        document.write_text(
            "# Calendar\n\n| Day | Event |\n| --- | --- |\n| Monday | Planning |\n\n"
            "[Details](./details.md#next)\n\n![Map](./map.png)", encoding="utf-8",
        )
        response = self.client.get("/md/peek/notes/calendar.md?root=project&theme=dark")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("<table>", page)
        self.assertIn("<td>Planning</td>", page)
        self.assertIn(f'href="/md/view?path={self.mounted}/notes/details.md#next"', page)
        self.assertIn(f'src="/md/asset?path={self.mounted}/notes/map.png"', page)
        self.assertIn(f'data-document-url="/md/view?path={document}"', page)
        self.assertIn('markdown-theme-dark', page)
        self.assertNotIn('actions-menu', page)
        self.assertNotIn('markdown_edit', page)

    def test_peek_reads_current_saved_contents_each_time(self) -> None:
        document = self.primary / "calendar.md"
        document.write_text("# Before", encoding="utf-8")
        self.assertIn("Before", self.client.get("/md/peek/calendar.md").get_data(as_text=True))
        document.write_text("# Updated", encoding="utf-8")
        response = self.client.get("/md/peek/calendar.md?theme=unknown")
        self.assertIn("Updated", response.get_data(as_text=True))
        self.assertIn("markdown-theme-paper", response.get_data(as_text=True))

    def test_peek_rejects_missing_nonmarkdown_and_escaping_paths(self) -> None:
        secret = self.workspace / "secret.md"
        secret.write_text("# Outside the library", encoding="utf-8")
        (self.primary / "escape.md").symlink_to(secret)
        (self.primary / "directory.md").mkdir()
        (self.primary / "file.txt").write_text("Text", encoding="utf-8")
        for path in ("missing.md", "file.txt", "directory.md", "escape.md", "../secret.md"):
            with self.subTest(path=path):
                response = self.client.get("/md/peek/" + quote(path))
                self.assertEqual(response.status_code, 404)

    def test_peek_does_not_fall_back_to_primary_for_unknown_or_unavailable_mounts(self) -> None:
        (self.primary / "calendar.md").write_text("# Primary", encoding="utf-8")
        self.mounted.rmdir()
        for root in ("project", "unknown"):
            with self.subTest(root=root):
                response = self.client.get(f"/md/peek/calendar.md?root={root}")
                self.assertEqual(response.status_code, 404)

    def test_home_paths_are_readable_and_open_the_original_file(self) -> None:
        document = self.mounted / "README.md"
        document.write_text("# Home path", encoding="utf-8")
        with patch.object(Path, "home", return_value=self.workspace), patch.dict(os.environ, {"HOME": str(self.workspace)}):
            page = self.client.get("/markdown?root=project").get_data(as_text=True)
            self.assertIn('data-copy-markdown-link="/md/view?path=~/project/README.md"', page)
            response = self.client.get("/md/view?path=~/project/README.md")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Home path</h1>", response.get_data(as_text=True))
            self.assertIn('href="/md/edit?path=~/project/README.md"', response.get_data(as_text=True))

    def test_readable_paths_select_their_own_root_for_view_edit_peek_images_and_print(self) -> None:
        document = self.mounted / "calendar.md"
        document.write_text("# Mounted calendar\n\n<!-- pagebreak -->\n\n# Next week", encoding="utf-8")
        (self.primary / "calendar.md").write_text("# Wrong document", encoding="utf-8")
        for endpoint in ("/md/view", "/md/edit", "/md/peek", "/md/print-collate/1"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, query_string={"path": str(document), "root": "unknown", "autoprint": "0"})
                self.assertEqual(response.status_code, 200)
                self.assertIn("Mounted calendar", response.get_data(as_text=True))
                self.assertNotIn("Wrong document", response.get_data(as_text=True))
        image = self.mounted / "calendar.png"
        image.write_bytes(b"calendar image")
        response = self.client.get("/md/asset", query_string={"path": str(image)})
        self.assertEqual(response.data, b"calendar image")
        response.close()

    def test_readable_links_survive_mount_id_changes(self) -> None:
        document = self.mounted / "same.md"
        document.write_text("# Same file", encoding="utf-8")
        link = "/md/view?path=" + quote(str(document), safe="/~")
        self.assertEqual(self.client.get(link).status_code, 200)
        self.client.post("/api/markdown/mounts/project/unmount")
        self.assertEqual(self.client.get(link).status_code, 404)
        mounted = self.client.post("/api/markdown/mounts", json={"path": str(self.mounted), "label": "Renamed folder"})
        self.assertEqual(mounted.status_code, 201)
        self.assertNotEqual(mounted.get_json()["root"]["id"], "project")
        self.assertIn("Same file</h1>", self.client.get(link).get_data(as_text=True))

    def test_readable_paths_reject_unmounted_files_traversal_symlinks_and_wrong_types(self) -> None:
        secret = self.workspace / "secret.md"
        secret.write_text("# Outside the mounts", encoding="utf-8")
        (self.mounted / "escape.md").symlink_to(secret)
        (self.mounted / "wrong.txt").write_text("Not Markdown", encoding="utf-8")
        paths = ("", "calendar.md", str(secret), str(self.mounted / ".." / "secret.md"),
                 str(self.mounted / "escape.md"), str(self.mounted / "wrong.txt"), str(self.mounted / "missing.md"))
        for endpoint in ("/md/view", "/md/edit", "/md/peek", "/md/print-collate/1"):
            for path in paths:
                with self.subTest(endpoint=endpoint, path=path):
                    self.assertEqual(self.client.get(endpoint, query_string={"path": path}).status_code, 404)
        self.assertEqual(self.client.get("/md/asset", query_string={"path": str(secret)}).status_code, 404)

    def test_nested_mounts_choose_the_closest_containing_folder(self) -> None:
        document = self.mounted / "nested" / "note.md"
        document.parent.mkdir()
        document.write_text("# Nested note", encoding="utf-8")
        nested = self.client.post("/api/markdown/mounts", json={"path": str(document.parent)}).get_json()["root"]
        response = self.client.get("/md/view", query_string={"path": str(document)})
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-markdown-root="{nested["id"]}"', page)
        self.assertIn('data-doc-id="note.md"', page)
