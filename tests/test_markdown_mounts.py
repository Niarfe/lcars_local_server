import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module
from scripts import markdown_mounts


class MarkdownMountTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.primary = self.workspace / "markdown"
        self.external = self.workspace / "academy"
        self.primary.mkdir()
        self.external.mkdir()
        self.config = self.workspace / "content_config.json"
        self.original_config = {"markdown_dir": str(self.primary), "books_dir": "~/books", "other_setting": {"enabled": True}}
        self.config.write_text(json.dumps(self.original_config), encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(app_module, "MARKDOWN_DIR", self.primary).start()
        patch.object(app_module, "CONTENT_CONFIG_PATH", self.config).start()
        self.client = app_module.app.test_client()

    def mount(self, folder: Path | None = None, label: str = "") -> str:
        response = self.client.post("/api/markdown/mounts", json={"path": str(folder or self.external), "label": label})
        self.assertEqual(response.status_code, 201, response.get_json())
        root = response.get_json()["root"]
        self.assertIn(root["id"], response.get_json()["url"])
        return root["id"]

    def write(self, root: Path, relative: str, text: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)

    def init_repo(self, root: Path) -> None:
        self.git(root, "init", "--quiet")
        self.git(root, "config", "core.excludesFile", str(self.workspace / "global-ignore"))

    def document_ids(self, root_id: str) -> set[str]:
        response = self.client.get("/api/markdown", query_string={"root": root_id})
        self.assertEqual(response.status_code, 200)
        return {doc["id"] for doc in response.get_json()["docs"]}

    def test_mount_persists_and_unmount_leaves_files_and_other_config_intact(self) -> None:
        source = self.write(self.external, "course.md", "# Course\n")
        root_id = self.mount(label="Academy course")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(config["markdown_mounts"][0]["id"], root_id)
        self.assertEqual(config["markdown_mounts"][0]["label"], "Academy course")
        for key, value in self.original_config.items():
            self.assertEqual(config[key], value)
        # Re-reading from disk also represents a fresh server process.
        self.assertEqual(markdown_mounts.roots(self.config, self.primary)[1]["id"], root_id)
        response = self.client.post(f"/api/markdown/mounts/{root_id}/unmount")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(source.read_text(encoding="utf-8"), "# Course\n")
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["markdown_mounts"], [])
        self.assertEqual(self.client.get("/api/markdown/mounts").get_json()["roots"][0]["id"], "markdown")

    def test_duplicate_mounts_include_symlink_alias_and_primary(self) -> None:
        self.mount()
        alias = self.workspace / "alias"
        alias.symlink_to(self.external, target_is_directory=True)
        for folder in (self.external, alias, self.primary):
            with self.subTest(folder=folder):
                response = self.client.post("/api/markdown/mounts", json={"path": str(folder)})
                self.assertEqual(response.status_code, 400)
                self.assertIn("already mounted", response.get_json()["error"])

    def test_nonexistent_mount_does_not_create_folder_and_primary_cannot_unmount(self) -> None:
        missing = self.workspace / "missing"
        response = self.client.post("/api/markdown/mounts", json={"path": str(missing)})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(missing.exists())
        self.assertEqual(self.client.post("/api/markdown/mounts/markdown/unmount").status_code, 400)
        self.assertEqual(self.client.post("/api/markdown/mounts", json={"path": "relative/path"}).status_code, 400)

    def test_picker_starts_at_home_and_can_show_hidden_folders(self) -> None:
        home = self.workspace / "home"
        home.mkdir()
        (home / "Documents").mkdir()
        (home / ".notes").mkdir()
        (home / "file.md").write_text("# File", encoding="utf-8")
        with patch.object(markdown_mounts.Path, "home", return_value=home), patch.dict(os.environ, {"HOME": str(home)}):
            listing = self.client.get("/api/markdown/mounts/browse").get_json()
            hidden = self.client.get("/api/markdown/mounts/browse", query_string={"path": "~", "hidden": "1"}).get_json()
            root_id = self.mount(home / "Documents")
        self.assertEqual(listing["path"], str(home))
        self.assertEqual(listing["display_path"], "~")
        self.assertEqual([item["name"] for item in listing["folders"]], ["Documents"])
        self.assertEqual([item["name"] for item in hidden["folders"]], [".notes", "Documents"])
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["markdown_mounts"][0]["path"], "~/Documents")
        self.assertTrue(root_id)

    def test_library_all_and_grep_only_include_selected_root(self) -> None:
        self.write(self.primary, "primary_only.md", "# Primary\nunique primary")
        self.write(self.primary, "same.md", "# Primary\nprimary word")
        self.write(self.external, "same.md", "# External\nexternal word")
        self.write(self.external, "lessons/deep.md", "# Deep\nexternal word")
        root_id = self.mount()
        primary_page = self.client.get("/markdown").get_data(as_text=True)
        mounted_page = self.client.get("/markdown", query_string={"root": root_id}).get_data(as_text=True)
        scoped_page = self.client.get("/markdown", query_string={"root": root_id, "folder": "lessons", "mode": "grep", "q": "external"}).get_data(as_text=True)
        self.assertIn("primary_only.md", primary_page)
        self.assertNotIn("lessons/deep.md", primary_page)
        self.assertNotIn("primary_only.md", mounted_page)
        self.assertIn("lessons/deep.md", mounted_page)
        self.assertIn(f'/md/view?path={self.external}/same.md', mounted_page)
        self.assertIn(f'/markdown?root={root_id}', mounted_page)
        self.assertIn(f'name="root" value="{root_id}"', scoped_page)
        self.assertNotIn('data-path="same.md"', scoped_page)
        self.assertIn("external word", scoped_page)

    def test_view_edit_save_create_rename_delete_stay_in_mount(self) -> None:
        original = self.write(self.primary, "same.md", "# Primary")
        mounted = self.write(self.external, "same.md", "# Mounted")
        root_id = self.mount()
        query = {"root": root_id}
        view = self.client.get("/md/view/same.md", query_string=query).get_data(as_text=True)
        edit = self.client.get("/md/edit/same.md", query_string=query).get_data(as_text=True)
        self.assertIn("Mounted</h1>", view)
        self.assertIn(f'/md/edit?path={mounted}', view)
        self.assertIn("# Mounted", edit)
        saved = self.client.post("/api/markdown/save/same.md", query_string=query, json={"text": "# Updated"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(mounted.read_text(encoding="utf-8"), "# Updated")
        self.assertEqual(original.read_text(encoding="utf-8"), "# Primary")
        (self.external / "lessons").mkdir()
        created = self.client.post("/api/markdown/create", query_string=query, json={"title": "Next lesson", "folder": "lessons"})
        self.assertEqual(created.status_code, 200)
        created_data = created.get_json()
        self.assertEqual(created_data["id"], "lessons/next_lesson.md")
        self.assertEqual(created_data["url"], f"/md/edit?path={self.external}/lessons/next_lesson.md")
        self.assertTrue((self.external / created_data["id"]).exists())
        self.assertFalse((self.primary / "lessons").exists())
        renamed = self.client.post("/api/markdown/rename/same.md", query_string=query, json={"name": "Renamed"})
        self.assertEqual(renamed.get_json()["url"], f"/md/view?path={self.external}/renamed.md")
        self.assertFalse(mounted.exists())
        self.assertEqual(self.client.post("/api/markdown/delete/renamed.md", query_string=query).status_code, 200)
        self.assertFalse((self.external / "renamed.md").exists())
        self.assertEqual(original.read_text(encoding="utf-8"), "# Primary")

    def test_creation_preserves_existing_folder_names_and_nested_context(self) -> None:
        folder = self.external / "Course Notes" / "Unit-One"
        folder.mkdir(parents=True)
        root_id = self.mount()
        response = self.client.post("/api/markdown/create", query_string={"root": root_id}, json={"title": "Exercises/Next Lesson", "folder": "Course Notes/Unit-One"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], "Course Notes/Unit-One/exercises/next_lesson.md")
        self.assertTrue((folder / "exercises" / "next_lesson.md").is_file())
        self.assertFalse((self.external / "course_notes").exists())

    def test_library_finder_opens_selected_folder_even_without_documents(self) -> None:
        root_id = self.mount()
        for root, folder in (("markdown", self.primary), (root_id, self.external)):
            nested = folder / "Empty Folder"
            nested.mkdir()
            for relative, expected in (("", folder), ("Empty Folder", nested)):
                with self.subTest(root=root, folder=relative), patch.object(app_module, "open_local_file") as open_folder:
                    response = self.client.post("/api/markdown/open-folder", query_string={"root": root}, json={"folder": relative})
                    self.assertEqual(response.status_code, 200)
                    open_folder.assert_called_once_with(expected)

    def test_library_finder_rejects_traversal_symlinks_and_invalid_folders(self) -> None:
        outside = self.workspace / "outside"
        outside.mkdir()
        (self.external / "escape").symlink_to(outside, target_is_directory=True)
        root_id = self.mount()
        with patch.object(app_module, "open_local_file") as open_folder:
            for folder in ("../outside", "escape", "missing"):
                with self.subTest(folder=folder):
                    response = self.client.post("/api/markdown/open-folder", query_string={"root": root_id}, json={"folder": folder})
                    self.assertEqual(response.status_code, 404)
            response = self.client.post("/api/markdown/open-folder", query_string={"root": root_id}, json={"folder": 42})
            self.assertEqual(response.status_code, 400)
            open_folder.assert_not_called()

    def test_images_relative_links_collation_and_finder_use_selected_root(self) -> None:
        self.write(self.primary, "lesson.md", "# Primary")
        doc = self.write(self.external, "notes/lesson.md", "# Mounted\n\n![Sample](../images/sample.png?v=2)\n\n[Next](../next.md#chapter)\n\n<!-- pagebreak -->\n\nPage two")
        self.write(self.external, "next.md", "# Next")
        image = self.external / "images" / "sample.png"
        image.parent.mkdir()
        image.write_bytes(b"mounted image")
        root_id = self.mount()
        query = {"root": root_id}
        view = self.client.get("/md/view/notes/lesson.md", query_string=query).get_data(as_text=True)
        self.assertIn(f'/md/asset?path={image}&amp;v=2', view)
        self.assertIn(f'/md/view?path={self.external}/next.md#chapter', view)
        self.assertIn(f'/md/print-collate/1?path={doc}', view)
        response = self.client.get("/md/asset/images/sample.png", query_string=query)
        self.assertEqual(response.data, b"mounted image")
        response.close()
        self.assertEqual(self.client.get("/md/print-collate/1/notes/lesson.md", query_string=query).status_code, 200)
        with patch.object(app_module, "open_local_file") as open_folder:
            self.assertEqual(self.client.post("/api/markdown/open-folder/notes/lesson.md", query_string=query).status_code, 200)
        open_folder.assert_called_once_with(doc.parent)
        redirect = self.client.get("/md/view/notes", query_string=query)
        self.assertIn(f"root={root_id}", redirect.location)

    def test_archive_and_todo_generation_are_unavailable_in_mounts(self) -> None:
        self.write(self.external, "0000/00_todo_list.md", "# External TODO")
        root_id = self.mount()
        query = {"root": root_id}
        page = self.client.get("/md/view/0000/00_todo_list.md", query_string=query).get_data(as_text=True)
        self.assertNotIn('id="refresh-todo-view"', page)
        with patch.object(app_module, "run_content_git") as git:
            self.assertEqual(self.client.get("/api/markdown/archive/preview/0000", query_string=query).status_code, 400)
            self.assertEqual(self.client.post("/api/markdown/archive/0000", query_string=query).status_code, 400)
            self.assertEqual(self.client.post("/api/markdown/todo/refresh/0000/00_todo_list.md", query_string=query).status_code, 404)
        git.assert_not_called()

    def test_unmounted_urls_never_fall_back_to_primary(self) -> None:
        primary = self.write(self.primary, "same.md", "# Primary")
        external = self.write(self.external, "same.md", "# External")
        root_id = self.mount()
        self.client.post(f"/api/markdown/mounts/{root_id}/unmount")
        for method, route in (("get", "/md/view/same.md"), ("post", "/api/markdown/save/same.md"), ("post", "/api/markdown/delete/same.md")):
            with self.subTest(route=route):
                response = getattr(self.client, method)(route, query_string={"root": root_id}, json={"text": "wrong"})
                self.assertEqual(response.status_code, 404)
        self.assertEqual(primary.read_text(encoding="utf-8"), "# Primary")
        self.assertEqual(external.read_text(encoding="utf-8"), "# External")

    def test_missing_folder_remains_visible_and_is_never_recreated(self) -> None:
        root_id = self.mount()
        moved = self.workspace / "moved"
        self.external.rename(moved)
        query = {"root": root_id}
        page = self.client.get("/markdown", query_string={**query, "folder": "old/subfolder"})
        self.assertEqual(page.status_code, 200)
        self.assertIn("FOLDER UNAVAILABLE", page.get_data(as_text=True))
        self.assertIn(f'data-unmount-root="{root_id}"', page.get_data(as_text=True))
        self.assertEqual(self.client.post("/api/markdown/create", query_string=query, json={"title": "New"}).status_code, 409)
        self.assertEqual(self.client.post("/api/markdown/save/note.md", query_string=query, json={"text": "New"}).status_code, 409)
        self.assertFalse(self.external.exists())
        moved.rename(self.external)
        self.assertEqual(self.client.get("/api/markdown", query_string=query).status_code, 200)

    def test_paths_and_symlinks_cannot_escape_root_including_sibling_prefix(self) -> None:
        outside = self.workspace / "academy-other"
        outside.mkdir()
        secret = self.write(outside, "secret.md", "# Secret")
        (outside / "secret.png").write_bytes(b"secret image")
        (self.external / "escape.md").symlink_to(secret)
        (self.external / "escape.png").symlink_to(outside / "secret.png")
        (self.external / "escape-folder").symlink_to(outside, target_is_directory=True)
        root_id = self.mount()
        query = {"root": root_id}
        self.assertEqual(self.client.get("/api/markdown", query_string=query).get_json()["docs"], [])
        for doc in ("../academy-other/secret.md", "escape.md", "escape-folder/secret.md"):
            with self.subTest(doc=doc):
                self.assertEqual(self.client.get(f"/md/view/{doc}", query_string=query).status_code, 404)
                self.assertEqual(self.client.post(f"/api/markdown/save/{doc}", query_string=query, json={"text": "wrong"}).status_code, 404)
        self.assertEqual(self.client.get("/md/asset/escape.png", query_string=query).status_code, 404)
        self.assertEqual(self.client.get("/markdown", query_string={**query, "folder": "escape-folder"}).status_code, 404)
        (self.external / "new.md").symlink_to(outside / "new.md")
        self.assertEqual(self.client.post("/api/markdown/create", query_string=query, json={"title": "New"}).status_code, 400)
        self.assertFalse((outside / "new.md").exists())
        self.assertEqual(secret.read_text(encoding="utf-8"), "# Secret")

    def test_repository_dependency_directories_are_skipped(self) -> None:
        self.write(self.external, "README.md", "# Course")
        self.write(self.external, ".git/secret.md", "# Git")
        self.write(self.external, "node_modules/dependency/README.md", "# Dependency")
        root_id = self.mount()
        docs = self.client.get("/api/markdown", query_string={"root": root_id}).get_json()["docs"]
        self.assertEqual([doc["id"] for doc in docs], ["README.md"])

    def test_mounted_repo_uses_gitignore_for_environment_and_generated_docs(self) -> None:
        self.init_repo(self.external)
        self.write(self.external, ".gitignore", "env/\nvenv/\n*.generated.md\n")
        visible = {"README.md", "LICENSE.md", "notes with spaces.md", "Caf\u00e9.MD", "notes\nwith newline.md", "docs/setup.md"}
        for relative in visible:
            self.write(self.external, relative, "# Project documentation")
        for relative in ("env/lib/package/LICENSE.md", "venv/share/README.md", "docs/cache.generated.md"):
            self.write(self.external, relative, "# Dependency noise")
        root_id = self.mount()
        self.assertEqual(self.document_ids(root_id), visible)

    def test_nested_ignore_negation_and_git_local_and_global_exclusions(self) -> None:
        self.init_repo(self.external)
        self.write(self.external, ".gitignore", "root-ignored.md\n")
        self.write(self.external, "docs/.gitignore", "*.md\n!keep.md\n")
        self.write(self.external, ".git/info/exclude", "local-only.md\n")
        self.write(self.workspace, "global-ignore", "global-only.md\n")
        visible = {"README.md", "docs/keep.md", "elsewhere/keep.md"}
        for relative in visible | {"root-ignored.md", "docs/hidden.md", "local-only.md", "global-only.md"}:
            self.write(self.external, relative, "# Note")
        self.assertEqual(self.document_ids(self.mount()), visible)

    def test_tracked_markdown_stays_visible_even_when_matching_ignore_rules(self) -> None:
        self.init_repo(self.external)
        self.write(self.external, ".gitignore", "env/\n")
        self.write(self.external, "env/tracked.md", "# Explicitly tracked")
        self.write(self.external, "env/untracked.md", "# Ignored dependency")
        deleted = self.write(self.external, "removed.md", "# Removed")
        self.git(self.external, "add", "-f", "--", "env/tracked.md", "removed.md")
        deleted.unlink()
        self.assertEqual(self.document_ids(self.mount()), {"env/tracked.md"})

    def test_mounting_repo_subfolder_honors_parent_ignore_rules_and_scope(self) -> None:
        self.init_repo(self.external)
        self.write(self.external, ".gitignore", "Course Notes/env/\n")
        self.write(self.external, "outside.md", "# Outside this mount")
        self.write(self.external, "Course Notes/README.md", "# Course")
        self.write(self.external, "Course Notes/docs/details.MD", "# Details")
        self.write(self.external, "Course Notes/env/lib/LICENSE.md", "# Dependency")
        self.git(self.external, "add", "--", "Course Notes/README.md")
        root_id = self.mount(self.external / "Course Notes")
        self.assertEqual(self.document_ids(root_id), {"README.md", "docs/details.MD"})

    def test_ignore_changes_apply_to_listing_folder_navigation_and_grep_on_reload(self) -> None:
        self.init_repo(self.external)
        ignored = self.write(self.external, ".gitignore", "env/\n")
        self.write(self.external, "README.md", "# Project\nA searchable project term.")
        hidden = self.write(self.external, "env/lib/LICENSE.md", "# Dependency\nA searchable dependency term.")
        root_id = self.mount()
        query = {"root": root_id}
        page = self.client.get("/markdown", query_string={**query, "mode": "grep", "q": "searchable"}).get_data(as_text=True)
        self.assertIn('data-path="readme.md"', page)
        self.assertNotIn('data-path="env/lib/license.md"', page)
        self.assertNotIn('data-folder-link="env"', page)
        ignored.write_text("", encoding="utf-8")
        self.assertEqual(self.document_ids(root_id), {"README.md", "env/lib/LICENSE.md"})
        page = self.client.get("/markdown", query_string=query).get_data(as_text=True)
        self.assertIn('data-folder-link="env"', page)
        self.assertTrue(hidden.is_file())

    def test_nonrepo_and_missing_git_keep_existing_scan_behavior(self) -> None:
        self.write(self.external, "README.md", "# Project")
        self.write(self.external, ".venv/lib/LICENSE.md", "# Dependency")
        root_id = self.mount()
        self.assertEqual(self.document_ids(root_id), {"README.md"})
        for error in (FileNotFoundError("Git unavailable"), subprocess.TimeoutExpired("git", 15)):
            with self.subTest(error=type(error).__name__), patch.object(app_module.subprocess, "run", side_effect=error):
                self.assertEqual(self.document_ids(root_id), {"README.md"})

    def test_primary_library_keeps_generated_notes_even_if_gitignored(self) -> None:
        self.init_repo(self.primary)
        self.write(self.primary, ".gitignore", "yt_transcripts/\n")
        self.write(self.primary, "yt_transcripts/channel/video.md", "# Generated transcript")
        self.assertEqual(self.document_ids("markdown"), {"yt_transcripts/channel/video.md"})

    def test_parallel_requests_keep_their_own_root(self) -> None:
        self.write(self.primary, "same.md", "primary")
        self.write(self.external, "same.md", "mounted")
        root_id = self.mount()

        def read(root: str) -> str:
            with app_module.app.test_client() as client:
                return client.get("/api/markdown/same.md", query_string={"root": root}).get_json()["text"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            roots = ["markdown", root_id] * 8
            results = list(pool.map(read, roots))
        self.assertEqual(results, ["primary", "mounted"] * 8)

    def test_invalid_config_is_preserved_when_mounting_fails(self) -> None:
        self.config.write_text("{ invalid config", encoding="utf-8")
        response = self.client.post("/api/markdown/mounts", json={"path": str(self.external)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.config.read_text(encoding="utf-8"), "{ invalid config")
