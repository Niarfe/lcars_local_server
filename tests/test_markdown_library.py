import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import app as app_module


class FolderLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and "data-folder-link" in values:
            self.links[values["data-folder-link"]] = values


class MarkdownLibraryTests(TestCase):
    def make_library(self, root: Path) -> None:
        documents = {
            "root_note.md": "# Root\n\nMeeting notes with Rafael.",
            "jobskills/skills.md": "# Skills",
            "yt_transcripts/channel_one/direct.md": "# Direct\n\nStage notes for RAFAEL.",
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
        self.assertIn(
            'class="markdown-sidebar-folder markdown-folder-crumb current"',
            transcript_page,
        )
        self.assertIn('data-folder-link="yt_transcripts/channel_one"', transcript_page)
        self.assertIn('data-folder-link="yt_transcripts/channel_two"', transcript_page)

        self.assertIn(
            'class="markdown-sidebar-folder markdown-folder-crumb ancestor"',
            channel_page,
        )
        self.assertIn('data-folder-link="yt_transcripts/channel_one/2026"', channel_page)
        self.assertIn("yt_transcripts/channel_one/direct.md", channel_page)
        self.assertIn("yt_transcripts/channel_one/2026/deep.md", channel_page)
        self.assertNotIn("yt_transcripts/channel_two/other.md", channel_page)
        self.assertIn("INCLUDING SUBFOLDERS", channel_page)

    def test_grep_mode_searches_content_within_current_scope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            self.make_library(markdown_dir)

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                client = app_module.app.test_client()
                root_results = client.get(
                    "/markdown",
                    query_string={"mode": "grep", "q": "rafael"},
                ).get_data(as_text=True)
                scoped_results = client.get(
                    "/markdown",
                    query_string={
                        "folder": "yt_transcripts/channel_one",
                        "mode": "grep",
                        "q": "rafael",
                    },
                ).get_data(as_text=True)

        self.assertIn('data-path="root_note.md"', root_results)
        self.assertIn(
            'data-path="yt_transcripts/channel_one/direct.md"',
            root_results,
        )
        self.assertIn("Meeting notes with Rafael.", root_results)
        self.assertIn("Stage notes for RAFAEL.", root_results)
        self.assertIn("L3", root_results)
        self.assertIn('data-search-mode="grep"', root_results)

        self.assertNotIn('data-path="root_note.md"', scoped_results)
        self.assertIn(
            'data-path="yt_transcripts/channel_one/direct.md"',
            scoped_results,
        )
        self.assertNotIn("jobskills/skills.md", scoped_results)

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
                f"/md/view?path={renamed}",
            )

    def test_open_folder_endpoint_opens_containing_markdown_folder(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "job" / "project" / "source.md"
            document.parent.mkdir(parents=True)
            document.write_text("# Source", encoding="utf-8")

            with (
                patch.object(app_module, "MARKDOWN_DIR", markdown_dir),
                patch.object(app_module, "open_local_file") as open_local_file,
            ):
                response = app_module.app.test_client().post(
                    "/api/markdown/open-folder/job/project/source.md"
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(response.get_json()["path"], "job/project")
        open_local_file.assert_called_once_with(document.parent)


class MarkdownFolderNavigationTests(TestCase):
    courses = {"5004", "ai_course", "base", "course_refreshes", "todo"}

    def setUp(self) -> None:
        self.workspace = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.root = self.workspace / "markdown"
        self.root.mkdir()
        self.config = self.workspace / "content_config.json"
        self.config.write_text(json.dumps({"markdown_dir": str(self.root)}), encoding="utf-8")
        self.enterContext(patch.object(app_module, "MARKDOWN_DIR", self.root))
        self.enterContext(patch.object(app_module, "CONTENT_CONFIG_PATH", self.config))
        self.make_courses(self.root)
        self.client = app_module.app.test_client()

    def write(self, root: Path, relative: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Notes\n\n{relative}", encoding="utf-8")
        return path

    def make_courses(self, root: Path) -> None:
        for course in self.courses:
            self.write(root, f"uva/f26/{course}/notes.md")
        self.write(root, "uva/f26/overview.md")
        self.write(root, "uva/5111/notes.md")
        self.write(root, "uva/future/planning/notes.md")
        self.write(root, "root_note.md")

    def folders(self, response) -> dict[str, dict[str, str]]:
        self.assertEqual(response.status_code, 200)
        parser = FolderLinkParser()
        parser.feed(response.get_data(as_text=True))
        return parser.links

    def assert_selected(self, links: dict, selected: str) -> None:
        active = [path for path, attrs in links.items() if attrs.get("aria-current") == "page"]
        self.assertEqual(active, [selected])
        self.assertIn("current", links[selected]["class"].split())

    def test_leaf_selection_keeps_siblings_and_narrows_documents(self) -> None:
        parent_links = self.folders(self.client.get("/markdown", query_string={"folder": "uva/f26"}))
        response = self.client.get("/markdown", query_string={"folder": "uva/f26/ai_course"})
        links = self.folders(response)
        self.assertEqual(list(links), list(parent_links))
        for course in self.courses:
            self.assertIn(f"uva/f26/{course}", links)
        self.assert_selected(links, "uva/f26/ai_course")
        self.assertIn("ancestor", links["uva/f26"]["class"].split())
        page = response.get_data(as_text=True)
        self.assertIn('data-path="uva/f26/ai_course/notes.md"', page)
        self.assertNotIn('data-path="uva/f26/5004/notes.md"', page)
        self.assertNotIn('data-path="uva/f26/overview.md"', page)
        self.assertIn('data-navigation-folder="uva/f26"', page)

    def test_branch_selection_still_drills_into_children(self) -> None:
        self.write(self.root, "uva/f26/ai_course/projects/assignment.md")
        response = self.client.get("/markdown", query_string={"folder": "uva/f26/ai_course"})
        links = self.folders(response)
        self.assert_selected(links, "uva/f26/ai_course")
        self.assertIn("uva/f26/ai_course/projects", links)
        self.assertNotIn("uva/f26/5004", links)
        self.assertIn('data-navigation-folder="uva/f26/ai_course"', response.get_data(as_text=True))

    def test_viewer_keeps_containing_folder_navigation_for_both_url_forms(self) -> None:
        doc_id = "uva/f26/ai_course/notes.md"
        canonical = self.client.get("/md/view", query_string={"path": str(self.root / doc_id)})
        legacy = self.client.get(f"/md/view/{doc_id}")
        for response in (canonical, legacy):
            links = self.folders(response)
            self.assert_selected(links, "uva/f26/ai_course")
            for course in self.courses:
                self.assertIn(f"uva/f26/{course}", links)
            destination = self.client.get(links["uva/f26/5004"]["href"])
            self.assertIn('data-path="uva/f26/5004/notes.md"', destination.get_data(as_text=True))
            self.assertNotIn('data-path="uva/f26/ai_course/notes.md"', destination.get_data(as_text=True))

    def test_viewer_at_root_and_branch_shows_available_children(self) -> None:
        root_links = self.folders(self.client.get("/md/view/root_note.md"))
        self.assert_selected(root_links, "")
        self.assertIn("uva", root_links)
        branch_links = self.folders(self.client.get("/md/view/uva/f26/overview.md"))
        self.assert_selected(branch_links, "uva/f26")
        for course in self.courses:
            self.assertIn(f"uva/f26/{course}", branch_links)

    def test_top_level_leaf_and_empty_leaf_keep_siblings(self) -> None:
        self.write(self.root, "inbox/note.md")
        links = self.folders(self.client.get("/markdown", query_string={"folder": "inbox"}))
        self.assert_selected(links, "inbox")
        self.assertIn("uva", links)
        empty = "uva/f26/empty"
        (self.root / empty).mkdir()
        links = self.folders(self.client.get("/markdown", query_string={"folder": empty}))
        self.assert_selected(links, empty)
        for course in self.courses:
            self.assertIn(f"uva/f26/{course}", links)

    def test_empty_grep_results_keep_sibling_navigation_and_query(self) -> None:
        query = {"folder": "uva/f26/ai_course", "mode": "grep", "q": "no matching content"}
        response = self.client.get("/markdown", query_string=query)
        links = self.folders(response)
        self.assert_selected(links, "uva/f26/ai_course")
        self.assertIn("NO CONTENT MATCHES FOUND", response.get_data(as_text=True))
        destination = parse_qs(urlparse(links["uva/f26/5004"]["href"]).query)
        self.assertEqual(destination, {**{key: [value] for key, value in query.items()}, "folder": ["uva/f26/5004"]})

    def test_mounted_viewer_keeps_root_and_ignores_dependency_subfolders(self) -> None:
        mount = self.workspace / "courses"
        mount.mkdir()
        self.make_courses(mount)
        subprocess.run(["git", "init", "--quiet"], cwd=mount, check=True, capture_output=True)
        (mount / ".gitignore").write_text("uva/f26/ai_course/env/\nuva/f26/hidden/\n", encoding="utf-8")
        self.write(mount, "uva/f26/ai_course/env/lib/LICENSE.md")
        self.write(mount, "uva/f26/hidden/note.md")
        mounted = self.client.post("/api/markdown/mounts", json={"path": str(mount)})
        self.assertEqual(mounted.status_code, 201)
        root_id = mounted.get_json()["root"]["id"]
        response = self.client.get("/md/view", query_string={"path": str(mount / "uva/f26/ai_course/notes.md")})
        links = self.folders(response)
        self.assert_selected(links, "uva/f26/ai_course")
        self.assertNotIn("uva/f26/hidden", links)
        self.assertNotIn("uva/f26/ai_course/env", links)
        for course in self.courses:
            path = f"uva/f26/{course}"
            self.assertIn(path, links)
            query = parse_qs(urlparse(links[path]["href"]).query)
            self.assertEqual(query, {"folder": [path], "root": [root_id]})
