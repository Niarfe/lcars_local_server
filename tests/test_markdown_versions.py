import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module
from scripts import markdown_versions


class MarkdownVersionTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.repo = self.workspace / "collection"
        self.repo.mkdir()
        self.primary = self.workspace / "primary"
        self.primary.mkdir()
        self.config = self.workspace / "content_config.json"
        self.config.write_text(json.dumps({"markdown_mounts": [{"id": "notes", "label": "Notes", "path": str(self.repo)}]}))
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}).start()
        patch.object(app_module, "CONTENT_CONFIG_PATH", self.config).start()
        patch.object(app_module, "MARKDOWN_DIR", self.primary).start()
        self.client = app_module.app.test_client()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "LCARS Test")
        self.git("config", "user.email", "lcars@example.invalid")
        self.git("config", "commit.gpgSign", "false")
        self.git("config", "tag.gpgSign", "false")
        self.write("README.md", "# Original\n")
        self.write("notes/detail.md", "# Details\n")
        self.write("code/main.py", "print('original')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial collection")

    def git(self, *args, root=None):
        completed = subprocess.run(["git", *args], cwd=root or self.repo, capture_output=True, check=True)
        return completed.stdout.decode("utf-8").strip()

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def status(self):
        response = self.client.get("/api/markdown/version?root=notes")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["version"]

    def action(self, action, *, expected=200, **payload):
        payload.setdefault("token", self.status()["token"])
        response = self.client.post(f"/api/markdown/version/{action}?root=notes", json=payload)
        self.assertEqual(response.status_code, expected, response.get_json())
        return response.get_json()

    def milestone(self, name="reviewed"):
        return self.action("tag", name=name, description="Verified documents and code")

    def revision(self, path="README.md"):
        page = self.client.get(f"/md/edit/{path}?root=notes").get_data(as_text=True)
        return json.loads(re.search(r"window.__MARKDOWN_REVISION__ = (.*?);", page)[1])

    def test_version_menu_is_at_root_and_file_commit_is_in_actions(self):
        root_page = self.client.get("/markdown?root=notes").get_data(as_text=True)
        self.assertIn('id="markdown-version-menu"', root_page)
        self.assertIn('data-version-path="README.md"', root_page)
        nested_page = self.client.get("/markdown?root=notes&folder=notes").get_data(as_text=True)
        self.assertNotIn('id="markdown-version-menu"', nested_page)
        document_page = self.client.get("/md/view/notes/detail.md?root=notes").get_data(as_text=True)
        self.assertIn('data-version-path="notes/detail.md"', document_page)

    def test_nonrepo_and_subfolder_mounts_cannot_version_parent(self):
        self.assertEqual(self.client.get("/api/markdown/version").status_code, 409)
        config = json.loads(self.config.read_text())
        config["markdown_mounts"][0]["path"] = str(self.repo / "notes")
        self.config.write_text(json.dumps(config))
        self.assertEqual(self.client.get("/api/markdown/version?root=notes").status_code, 409)
        page = self.client.get("/markdown?root=notes").get_data(as_text=True)
        self.assertNotIn('id="markdown-version-menu"', page)
        self.assertFalse((self.primary / ".git").exists())

    def test_milestone_commits_documents_code_new_files_and_deletions(self):
        self.write("README.md", "# Verified\n")
        self.write("code/main.py", "print('verified')\n")
        self.write("images/diagram.txt", "diagram")
        (self.repo / "notes/detail.md").unlink()
        result = self.milestone()["result"]
        self.assertEqual(self.git("cat-file", "-t", "reviewed"), "tag")
        self.assertEqual(self.git("show", "reviewed:code/main.py"), "print('verified')")
        self.assertEqual(self.git("show", "reviewed:images/diagram.txt"), "diagram")
        self.assertNotIn("notes/detail.md", self.git("ls-tree", "-r", "--name-only", "reviewed"))
        self.assertEqual(result["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn("Verified documents and code", self.status()["tags"][0]["description"])

    def test_clean_milestone_does_not_create_empty_commit(self):
        original = self.git("rev-parse", "HEAD")
        self.milestone()
        self.assertEqual(self.git("rev-parse", "HEAD"), original)

    def test_duplicate_and_invalid_tags_do_not_stage_or_commit(self):
        self.milestone()
        self.write("README.md", "pending")
        original = self.git("rev-parse", "HEAD")
        for name in ("reviewed", "bad name", "-f", "../escape", "", None, ["bad"]):
            with self.subTest(name=name):
                self.action("tag", expected=409, name=name, description="Milestone")
                self.assertEqual(self.git("rev-parse", "HEAD"), original)
                self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_preview_detects_content_change_with_same_length_and_mtime(self):
        target = self.write("README.md", "first")
        token = self.status()["token"]
        old_stat = target.stat()
        target.write_text("other")
        os.utime(target, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        response = self.action("tag", expected=409, token=token, name="stale", description="Stale")
        self.assertIn("changed since this preview", response["error"])
        self.assertEqual(self.git("tag"), "")

    def test_commit_file_excludes_unstaged_code(self):
        self.write("README.md", "updated note")
        self.write("code/main.py", "uncommitted code")
        self.action("commit", path="README.md", description="Save note")
        self.assertEqual(self.git("show", "HEAD:README.md"), "updated note")
        self.assertEqual(self.git("show", "HEAD:code/main.py"), "print('original')")
        self.assertEqual(self.git("status", "--porcelain"), "M code/main.py")

    def test_commit_file_rejects_other_staged_files_and_literal_pathspecs_work(self):
        self.write("README.md", "updated")
        self.write("code/main.py", "staged code")
        self.git("add", "code/main.py")
        self.action("commit", expected=409, path="README.md", description="Only note")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "code/main.py")
        self.git("reset", "-q")
        name = "notes/[draft] résumé\npart.md"
        self.write(name, "unicode and newline")
        self.action("commit", path=name, description="Save literal filename")
        self.assertEqual(self.git("show", f"HEAD:{name}"), "unicode and newline")
        self.assertIn("README.md", self.git("status", "--porcelain"))

    def test_switch_and_return_restore_newer_untagged_commits(self):
        self.milestone()
        self.write("README.md", "newer committed work")
        self.action("commit", description="Work after milestone")
        newest = self.git("rev-parse", "HEAD")
        self.action("switch", name="reviewed")
        self.assertEqual((self.repo / "README.md").read_text(), "# Original\n")
        version = self.status()
        self.assertTrue(version["read_only"])
        self.assertEqual(version["return_branch"], "main")
        self.assertEqual(version["view_tag"], "reviewed")
        # The destination survives a new Repository instance / server restart.
        self.assertEqual(markdown_versions.at_root(self.repo).state()["return_branch"], "main")
        self.action("return")
        self.assertEqual(self.git("rev-parse", "HEAD"), newest)
        self.assertEqual((self.repo / "README.md").read_text(), "newer committed work")

    def test_all_dirty_states_block_switch(self):
        self.milestone()
        for kind in ("modified", "staged", "untracked", "deleted", "renamed"):
            with self.subTest(kind=kind):
                if kind in {"modified", "staged"}:
                    self.write("code/main.py", "dirty")
                    if kind == "staged":
                        self.git("add", "code/main.py")
                elif kind == "untracked":
                    self.write("new.md", "new work")
                elif kind == "deleted":
                    (self.repo / "README.md").unlink()
                else:
                    self.git("mv", "README.md", "renamed.md")
                self.action("switch", expected=409, name="reviewed")
                self.assertEqual(self.git("branch", "--show-current"), "main")
                self.git("reset", "--hard", "-q", "HEAD")
                if (self.repo / "new.md").exists():
                    (self.repo / "new.md").unlink()

    def test_historical_views_reject_writes_and_hide_actions(self):
        self.milestone()
        self.action("switch", name="reviewed")
        requests = [
            ("/api/markdown/save/README.md", {"text": "overwrite"}),
            ("/api/markdown/create", {"title": "new"}),
            ("/api/markdown/rename/README.md", {"name": "renamed"}),
            ("/api/markdown/delete/README.md", {}),
            ("/api/markdown/archive/notes", {}),
            ("/api/markdown/todo/refresh/README.md", {}),
        ]
        for route, payload in requests:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(route, query_string={"root": "notes"}, json=payload).status_code, 409)
        self.assertEqual(self.client.get("/md/edit/README.md?root=notes").status_code, 409)
        self.assertEqual(self.client.get("/md/new?root=notes").status_code, 409)
        page = self.client.get("/md/view/README.md?root=notes").get_data(as_text=True)
        self.assertIn("REVIEWED", page.upper())
        self.assertIn("READ ONLY", page)
        self.assertNotIn('id="delete-markdown-current"', page)
        self.assertNotIn(">EDIT</a>", page)
        self.action("tag", expected=409, name="forbidden", description="No")

    def test_nested_mount_and_generated_transcript_cannot_bypass_readonly(self):
        config = json.loads(self.config.read_text())
        config["markdown_mounts"].append({"id": "nested", "label": "Nested", "path": str(self.repo / "notes")})
        self.config.write_text(json.dumps(config))
        self.milestone()
        self.action("switch", name="reviewed")
        self.assertEqual(self.client.post("/api/markdown/save/detail.md?root=nested", json={"text": "wrong"}).status_code, 409)
        with patch.object(app_module, "MARKDOWN_DIR", self.repo), patch.object(app_module, "youtube_transcript_rel_path", return_value="notes/video.md"):
            with self.assertRaises(markdown_versions.VersionError):
                app_module.write_youtube_transcript({"id": 1}, {"language_code": "en"})
        self.assertFalse((self.repo / "notes/video.md").exists())

    def test_editor_save_requires_revision_and_rejects_external_edits(self):
        revision = self.revision()
        document = self.client.get("/api/markdown/README.md?root=notes").get_json()
        self.assertEqual(document["revision"], revision)
        response = self.client.post("/api/markdown/save/README.md?root=notes", json={"text": "saved", "revision": revision})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["revision"], self.revision())
        revision = self.revision()
        self.write("README.md", "external edits")
        response = self.client.post("/api/markdown/save/README.md?root=notes", json={"text": "stale", "revision": revision})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.repo / "README.md").read_text(), "external edits")
        self.assertEqual(self.client.post("/api/markdown/save/README.md?root=notes", json={"text": "no revision"}).status_code, 409)

    def test_old_editor_is_rejected_even_after_roundtrip_to_identical_files(self):
        revision = self.revision()
        self.milestone()
        self.action("switch", name="reviewed")
        self.action("return")
        response = self.client.post("/api/markdown/save/README.md?root=notes", json={"text": "old editor", "revision": revision})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.repo / "README.md").read_text(), "# Original\n")

    def test_dirty_editor_blocks_actions_until_released_and_old_heartbeats_are_ignored(self):
        self.milestone()
        lease = {"id": "a" * 32, "doc": "README.md", "dirty": True, "sequence": 1}
        self.client.post("/api/markdown/version/editor?root=notes", json=lease)
        self.action("switch", expected=409, name="reviewed")
        self.client.post("/api/markdown/version/editor?root=notes", json={**lease, "dirty": False, "sequence": 2})
        self.client.post("/api/markdown/version/editor?root=notes", json=lease)
        self.action("switch", name="reviewed")

    def test_ignored_files_are_excluded_and_never_overwritten_on_switch(self):
        self.write("private.md", "old tracked version")
        self.action("tag", name="old", description="Old")
        self.git("rm", "private.md")
        self.write(".gitignore", "private.md\n")
        self.action("commit", description="Keep private notes local")
        self.write("private.md", "private local work")
        self.assertTrue(self.status()["clean"])
        self.action("switch", expected=409, name="old")
        self.assertEqual((self.repo / "private.md").read_text(), "private local work")
        self.assertEqual(self.git("branch", "--show-current"), "main")

    def test_latest_uses_creation_date_and_only_tags_reachable_from_working_branch(self):
        self.milestone("z-first")
        self.git("checkout", "-qb", "other")
        self.write("README.md", "other branch")
        self.action("commit", description="Other work")
        with patch.dict(os.environ, {"GIT_COMMITTER_DATE": "2035-01-01T00:00:00+00:00"}):
            self.milestone("unrelated")
        self.git("checkout", "-q", "main")
        self.write("README.md", "latest main")
        self.action("commit", description="Main work")
        with patch.dict(os.environ, {"GIT_COMMITTER_DATE": "2030-01-01T00:00:00+00:00"}):
            self.milestone("a-latest")
        self.assertEqual(self.status()["latest_tag"], "a-latest")
        self.action("latest")
        self.assertEqual(self.status()["view_tag"], "a-latest")

    def test_push_sends_branch_and_selected_tag_only_to_local_bare_remote(self):
        remote = self.workspace / "backup.git"
        self.git("init", "--bare", "-q", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.milestone("selected")
        self.milestone("keep-local")
        self.git("config", "push.followTags", "true")
        self.action("push", remote="origin", tag="selected")
        self.assertEqual(self.git("tag", root=remote), "selected")
        self.assertEqual(self.git("rev-parse", "refs/heads/main", root=remote), self.git("rev-parse", "HEAD"))

    def test_rejected_push_keeps_local_commits_and_milestones(self):
        remote = self.workspace / "backup.git"
        self.git("init", "--bare", "-q", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.milestone()
        hook = remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho 'Backup rejected for test' >&2\nexit 1\n")
        hook.chmod(0o755)
        head = self.git("rev-parse", "HEAD")
        self.action("push", expected=409, remote="origin", tag="reviewed")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("tag"), "reviewed")
        self.assertEqual(self.git("tag", root=remote), "")

    def test_preview_detects_changed_remote_and_redacts_embedded_credentials(self):
        self.git("remote", "add", "origin", "https://name:secret@example.invalid/docs.git")
        version = self.status()
        self.assertNotIn("secret", json.dumps(version))
        self.git("remote", "set-url", "origin", "https://example.invalid/other.git")
        self.action("push", expected=409, token=version["token"], remote="origin")

    def test_running_lcars_repository_is_protected_from_switch(self):
        self.milestone()
        with patch.object(app_module, "APP_DIR", self.repo):
            self.assertIn("running LCARS", self.status()["switch_blocked_reason"])
            self.action("switch", expected=409, name="reviewed")
        self.assertEqual(self.git("branch", "--show-current"), "main")

    def test_hook_created_changes_report_local_commit_without_creating_tag(self):
        hook = self.repo / ".git/hooks/post-commit"
        hook.write_text("#!/bin/sh\nprintf 'generated' > generated.md\n")
        hook.chmod(0o755)
        self.write("README.md", "commit succeeds")
        response = self.action("tag", expected=409, name="not-created", description="Partial success")
        self.assertEqual(response["result"]["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("show", "HEAD:README.md"), "commit succeeds")
        self.assertEqual(self.git("tag"), "")

    def test_merge_in_progress_and_nested_repository_are_blocked(self):
        self.write("README.md", "pending")
        (self.repo / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"))
        self.action("commit", expected=409, description="No merge commits")
        (self.repo / ".git/MERGE_HEAD").unlink()
        nested = self.repo / "embedded"
        nested.mkdir()
        self.git("init", "-q", str(nested))
        (nested / "README.md").write_text("embedded repository")
        self.action("tag", expected=409, name="no-submodules", description="Blocked")

    def test_path_traversal_and_missing_preview_cannot_commit(self):
        self.write("README.md", "pending")
        for path in ("../outside.md", "/tmp/outside.md", "code/main.py", ".git/config"):
            self.action("commit", expected=409, path=path, description="Invalid")
        self.action("commit", expected=409, token="", description="No preview")

    def test_first_milestone_can_make_initial_commit_in_existing_empty_repo(self):
        empty = self.workspace / "empty"
        empty.mkdir()
        self.git("init", "-q", "-b", "main", root=empty)
        self.git("config", "user.name", "Test", root=empty)
        self.git("config", "user.email", "test@example.invalid", root=empty)
        (empty / "README.md").write_text("First milestone")
        config = json.loads(self.config.read_text())
        config["markdown_mounts"][0]["path"] = str(empty)
        self.config.write_text(json.dumps(config))
        self.milestone("first")
        self.assertEqual(self.git("show", "first:README.md", root=empty), "First milestone")

    def test_worktree_has_independent_persistent_return_state(self):
        self.milestone()
        worktree = self.workspace / "worktree"
        self.git("worktree", "add", "-qb", "side", str(worktree))
        config = json.loads(self.config.read_text())
        config["markdown_mounts"][0]["path"] = str(worktree)
        self.config.write_text(json.dumps(config))
        self.action("switch", name="reviewed")
        self.assertEqual(self.git("branch", "--show-current"), "main")
        self.assertFalse((self.repo / ".git/lcars-version.json").exists())
        self.action("return")
        self.assertEqual(self.git("branch", "--show-current", root=worktree), "side")

    def test_readonly_covers_book_deletion_and_missing_nested_cache_directories(self):
        self.write("books/note.txt", "Preserve book")
        self.milestone()
        self.action("switch", name="reviewed")
        with patch.object(app_module, "BOOKS_DIR", self.repo / "books"):
            response = self.client.post("/api/book/delete/note.txt")
            self.assertEqual(response.status_code, 409)
        missing = self.repo / "missing/nested/cache/book.pdf"
        with patch.object(app_module, "s3_book_cache_path", return_value=missing), patch.object(app_module, "urlopen") as download:
            with self.assertRaises(markdown_versions.VersionError):
                app_module.ensure_s3_book_cached({"filename": "book.pdf"})
            download.assert_not_called()
        self.assertFalse(missing.parent.exists())
        self.assertEqual((self.repo / "books/note.txt").read_text(), "Preserve book")

    def test_sparse_and_submodule_states_are_explicitly_unsupported(self):
        self.git("config", "core.sparseCheckout", "true")
        self.assertIn("sparse", self.status()["blocked_reason"])
        self.action("tag", expected=409, name="blocked", description="Blocked")
        self.git("config", "core.sparseCheckout", "false")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.git('rev-parse', 'HEAD')},module")
        self.assertIn("submodules", self.status()["blocked_reason"])
        self.action("commit", expected=409, description="Blocked")
