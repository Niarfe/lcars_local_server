"""Repository milestones for mounted Markdown libraries.

All writes are explicit, scoped to an existing repository, and use Git's normal
index, hooks and non-forced switches/pushes. LCARS metadata lives in the Git
directory, outside the versioned content.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import RLock, local
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

try:
    import fcntl
except ImportError:  # The thread lock still protects a single Windows server.
    fcntl = None


class VersionError(RuntimeError):
    def __init__(self, message: str, *, result: dict | None = None):
        super().__init__(message)
        self.result = result or {}


_LOCKS: dict[str, RLock] = {}
_LOCKS_LOCK = RLock()
_HELD = local()
_EDITORS: dict[str, dict[str, dict]] = {}
_EDITORS_LOCK = RLock()


def git(root: Path, *args: str, check: bool = True) -> str:
    env = {key: value for key, value in os.environ.items() if key not in {
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        completed = subprocess.run(
            ["git", "--literal-pathspecs", *args], cwd=root, env=env,
            capture_output=True, timeout=60,
        )
    except FileNotFoundError as exc:
        raise VersionError("Git is unavailable on this machine.") from exc
    except subprocess.TimeoutExpired as exc:
        raise VersionError("Git timed out. Check repository status before retrying.") from exc
    output = completed.stdout.decode("utf-8", "surrogateescape")
    if check and completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip() or output.strip()
        raise VersionError(detail or "Git operation failed.")
    return output if completed.returncode == 0 else ""


def discover(path: Path) -> Repository | None:
    directory = path.resolve()
    while not directory.is_dir() and directory != directory.parent:
        directory = directory.parent
    try:
        top = git(directory, "rev-parse", "--show-toplevel", check=False).strip()
        if not top:
            return None
        git_dir = git(directory, "rev-parse", "--absolute-git-dir").strip()
        return Repository(Path(top).resolve(), Path(git_dir).resolve())
    except (VersionError, OSError):
        return None


def at_root(path: Path) -> Repository:
    repo = discover(path)
    if repo is None or repo.root != path.resolve():
        raise VersionError("Mount the Git repository root to use VERSION. LCARS does not initialize repositories.")
    return repo


def editor_lease(repo: Repository, editor_id: str, doc: str, dirty: bool, sequence: int = 0) -> None:
    if not isinstance(editor_id, str) or len(editor_id) != 32 or any(char not in "0123456789abcdef" for char in editor_id):
        raise VersionError("Invalid editor session.")
    with _EDITORS_LOCK:
        editors = _EDITORS.setdefault(repo.key, {})
        if sequence < editors.get(editor_id, {}).get("sequence", -1):
            return
        editors[editor_id] = {"doc": str(doc)[:500], "dirty": dirty, "sequence": sequence, "expires": time.monotonic() + 90}


@contextmanager
def writable(path: Path):
    """Also protects nested mounts and generated content in a visited repo."""
    repo = discover(path)
    if repo is None:
        yield
        return
    with repo.lock():
        repo.require_working_branch()
        yield


def document_revision(path: Path, contents: bytes | None = None) -> str:
    repo = discover(path)
    digest = hashlib.sha256()
    if repo:
        digest.update((repo.head() + repo.branch() + repo.state().get("epoch", "")).encode())
    digest.update(contents if contents is not None else path.read_bytes() if path.exists() else b"\0missing")
    return digest.hexdigest()


def public_remote_url(url: str) -> str:
    """Never send embedded HTTPS credentials to the browser."""
    if "://" in url:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    return url


class Repository:
    def __init__(self, root: Path, git_dir: Path):
        self.root = root
        self.git_dir = git_dir
        self.key = hashlib.sha256(str(git_dir).encode()).hexdigest()
        self.state_path = git_dir / "lcars-version.json"

    def run(self, *args: str, check: bool = True) -> str:
        return git(self.root, *args, check=check)

    @contextmanager
    def lock(self):
        with _LOCKS_LOCK:
            lock = _LOCKS.setdefault(self.key, RLock())
        if not lock.acquire(timeout=8):
            raise VersionError("Another LCARS operation is using this repository. Retry shortly.")
        held = getattr(_HELD, "repos", set())
        nested = self.key in held
        handle = None
        try:
            if not nested:
                handle = (self.git_dir / "lcars-version.lock").open("a")
                if fcntl:
                    deadline = time.monotonic() + 8
                    while True:
                        try:
                            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() >= deadline:
                                raise VersionError("Another LCARS operation is using this repository.")
                            time.sleep(0.05)
                _HELD.repos = held | {self.key}
            yield
        finally:
            if not nested:
                _HELD.repos = held
                if handle:
                    handle.close()
            lock.release()

    def head(self) -> str:
        return self.run("rev-parse", "--verify", "HEAD", check=False).strip()

    def branch(self) -> str:
        return self.run("symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()

    def state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Invalid state")
            return data
        except (ValueError, OSError) as exc:
            raise VersionError("Could not read LCARS version state. Check the repository before continuing.") from exc

    def save_state(self, state: dict) -> None:
        fd, temporary = tempfile.mkstemp(prefix="lcars-version-", dir=self.git_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
                handle.write("\n")
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def require_working_branch(self) -> None:
        if not self.branch():
            raise VersionError("This repository is viewing a historical commit and is read-only in LCARS. Return to current work first.")

    def require_supported(self) -> None:
        if self.run("config", "--bool", "core.sparseCheckout", check=False).strip() == "true":
            raise VersionError("VERSION does not yet support sparse checkouts.")
        if any(item.startswith("160000 ") for item in self.run("ls-files", "--stage", "-z").split("\0")):
            raise VersionError("VERSION does not yet support repositories containing submodules.")
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_LOG"):
            if (self.git_dir / marker).exists():
                raise VersionError("Finish the active Git merge, rebase, cherry-pick, revert or bisect before using VERSION.")

    def changes(self) -> list[dict]:
        records = iter(self.run("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none").split("\0"))
        result = []
        for record in records:
            if not record:
                continue
            item = {"status": record[:2], "path": record[3:]}
            if "R" in record[:2] or "C" in record[:2]:
                item["original"] = next(records)
            result.append(item)
        return result

    def tags(self, branch: str = "") -> list[dict]:
        args = ["for-each-ref", "--sort=-creatordate", "--format=%(refname:strip=2)%00%(objecttype)%00%(objectname)%00%(*objectname)%00%(creatordate:iso-strict)%00%(contents)%00"]
        if branch and self.head():
            args.append(f"--merged=refs/heads/{branch}")
        fields = self.run(*args, "refs/tags").split("\0")
        result = []
        for offset in range(0, len(fields) - 6, 6):
            name, kind, oid, peeled, date, message = fields[offset:offset + 6]
            result.append({"name": name.lstrip("\n"), "annotated": kind == "tag", "commit": peeled or oid, "date": date, "description": message.strip()})
        return result

    def remotes(self, branch: str) -> tuple[list[dict], str, str]:
        names = self.run("remote").splitlines()
        configured = self.run("config", "--get", f"branch.{branch}.remote", check=False).strip() if branch else ""
        selected = configured if configured in names else ("origin" if "origin" in names else (names[0] if len(names) == 1 else ""))
        merge = self.run("config", "--get", f"branch.{branch}.merge", check=False).strip() if branch else ""
        destination = merge.removeprefix("refs/heads/") if configured == selected and merge.startswith("refs/heads/") else branch
        return ([{"name": name, "urls": [public_remote_url(url) for url in self.run("remote", "get-url", "--push", "--all", name).splitlines()]} for name in names], selected, destination)

    def token(self, changes: list[dict]) -> str:
        digest = hashlib.sha256()
        for value in (self.head(), self.branch(), json.dumps(self.state(), sort_keys=True), json.dumps(changes, sort_keys=True), self.run("diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv"), self.run("show-ref", check=False), self.run("config", "--get-regexp", "^(remote|branch)\\.", check=False)):
            digest.update(value.encode("utf-8", "surrogateescape") + b"\0")
        for item in changes:
            for name in (item["path"], item.get("original", "")):
                if not name:
                    continue
                path = self.root / name
                digest.update(name.encode("utf-8", "surrogateescape") + b"\0")
                if path.is_symlink():
                    digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
                elif path.is_file():
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(65536), b""):
                            digest.update(chunk)
                else:
                    digest.update(b"\0missing-or-directory")
                if path.exists():
                    digest.update(str(path.lstat().st_mode).encode())
        return digest.hexdigest()

    def status(self, *, application_dir: Path | None = None) -> dict:
        branch, head, state = self.branch(), self.head(), self.state()
        changes = self.changes()
        tags = self.tags()
        working_branch = branch or state.get("return_branch", "")
        reachable = self.tags(working_branch) if working_branch and self.run("show-ref", "--verify", f"refs/heads/{working_branch}", check=False) else []
        remotes, remote, destination = self.remotes(working_branch)
        reason = ""
        try:
            self.require_supported()
        except VersionError as exc:
            reason = str(exc)
        protected = application_dir is not None and application_dir.resolve().is_relative_to(self.root)
        return {
            "enabled": True, "repo": str(self.root), "repo_id": self.key,
            "head": head, "branch": branch, "read_only": not bool(branch),
            "view_tag": state.get("view_tag", "") if not branch and state.get("view_commit") == head else "",
            "return_branch": state.get("return_branch", "") if not branch else "",
            "changes": changes, "clean": not changes, "tags": tags,
            "latest_tag": reachable[0]["name"] if reachable else "",
            "remotes": remotes, "remote": remote, "destination": destination,
            "blocked_reason": reason, "switch_blocked_reason": "This repository contains the running LCARS server. Switch its versions outside LCARS." if protected else reason,
            "token": self.token(changes),
        }

    def validate_preview(self, token: str) -> None:
        if not isinstance(token, str) or not token or token != self.token(self.changes()):
            raise VersionError("The repository changed since this preview. Reopen the dialog to review the current files.")

    def require_saved_editors(self) -> None:
        with _EDITORS_LOCK:
            now = time.monotonic()
            editors = _EDITORS.get(self.key, {})
            dirty = sorted({item["doc"] for item in editors.values() if item["expires"] > now and item["dirty"]})
            _EDITORS[self.key] = {key: item for key, item in editors.items() if item["expires"] > now}
        if dirty:
            raise VersionError("Save or close unsaved LCARS editors first: " + ", ".join(dirty[:5]))

    def commit(self, message: str, path: str = "") -> dict:
        self.require_working_branch()
        if not isinstance(message, str) or not message.strip() or len(message) > 10000:
            raise VersionError("Enter a commit description (up to 10,000 characters).")
        if path:
            candidate = self.root / path
            if Path(path).is_absolute() or not candidate.resolve().is_relative_to(self.root) or ".git" in Path(path).parts or candidate.suffix.lower() != ".md":
                raise VersionError("Invalid Markdown file for commit.")
            staged = self.run("diff", "--cached", "--no-renames", "--name-only", "-z").split("\0")
            if any(name and name != path for name in staged):
                raise VersionError("Other files are staged. Commit them separately or use Commit changes at the repository root.")
            if not any(item["path"] == path for item in self.changes()):
                raise VersionError("This file has no changes to commit.")
        elif not self.changes():
            raise VersionError("There are no changes to commit.")
        if any((self.root / item["path"]).is_dir() for item in self.changes()):
            raise VersionError("Nested repositories must be versioned through their own root mounts.")
        self.run("add", "-A", "--", path or ".")
        self.run("commit", "-m", message.strip())
        return {"commit": self.head(), "message": "Committed locally."}

    def create_tag(self, name: str, description: str) -> dict:
        self.require_working_branch()
        if not isinstance(name, str) or not name or name.startswith("-") or len(name) > 200:
            raise VersionError("Enter a valid, unique tag name (up to 200 characters).")
        self.run("check-ref-format", f"refs/tags/{name}")
        if self.run("show-ref", "--verify", f"refs/tags/{name}", check=False):
            raise VersionError("That tag already exists. Choose a new name; milestones are never overwritten.")
        if not isinstance(description, str) or not description.strip() or len(description) > 10000:
            raise VersionError("Enter a milestone description (up to 10,000 characters).")
        result = {}
        if self.changes():
            result = self.commit(description)
        if not self.head():
            raise VersionError("Create a commit before tagging this repository.")
        try:
            if self.changes():
                raise VersionError("There are still uncommitted files. No tag was created.")
            self.run("tag", "-a", "-m", description.strip(), "--", name, self.head())
        except VersionError as exc:
            raise VersionError(str(exc), result=result) from exc
        return {**result, "tag": name, "commit": self.head(), "message": f"Milestone {name} saved locally."}

    def switch(self, name: str, *, application_dir: Path) -> dict:
        if application_dir.resolve().is_relative_to(self.root):
            raise VersionError("This repository contains the running LCARS server. Switch its versions outside LCARS.")
        if self.changes():
            raise VersionError("Commit all changes before switching versions, including new and deleted files.")
        state, branch = self.state(), self.branch()
        if not branch and not state.get("return_branch"):
            raise VersionError("Check out a working branch in Git before visiting tags through LCARS.")
        if not isinstance(name, str) or not name or name.startswith("-"):
            raise VersionError("Choose a tag.")
        self.run("check-ref-format", f"refs/tags/{name}")
        target = self.run("rev-parse", "--verify", f"refs/tags/{name}^{{commit}}").strip()
        if branch:
            state.update(return_branch=branch, return_commit=self.head())
        state.update(view_tag=name, view_commit=target, epoch=uuid4().hex)
        # Persist the return destination before changing any versioned files.
        self.save_state(state)
        self.run("switch", "--no-overwrite-ignore", "--detach", target)
        return {"tag": name, "message": f"Viewing milestone {name}. LCARS editing is disabled."}

    def return_to_work(self, *, application_dir: Path) -> dict:
        if application_dir.resolve().is_relative_to(self.root):
            raise VersionError("This repository contains the running LCARS server.")
        if self.changes():
            raise VersionError("Uncommitted files block returning to current work. Save them using Git outside LCARS first.")
        state = self.state()
        branch = state.get("return_branch", "")
        if self.branch() or not branch:
            raise VersionError("There is no saved working branch to return to.")
        self.run("show-ref", "--verify", f"refs/heads/{branch}")
        self.run("switch", "--no-overwrite-ignore", "--no-guess", branch)
        self.save_state({"epoch": uuid4().hex})
        return {"branch": branch, "message": f"Returned to current work on {branch}."}

    def push(self, remote: str, tag: str = "") -> dict:
        self.require_working_branch()
        branch = self.branch()
        remotes, default, destination = self.remotes(branch)
        if not isinstance(remote, str) or remote not in {item["name"] for item in remotes}:
            raise VersionError("Choose a configured backup remote. LCARS does not create remotes.")
        if not self.head():
            raise VersionError("Create a commit before pushing.")
        destination = destination if remote == default else branch
        refs = [f"refs/heads/{branch}:refs/heads/{destination}"]
        if tag:
            if not isinstance(tag, str) or tag not in {item["name"] for item in self.tags()}:
                raise VersionError("Choose an existing tag to push.")
            refs.append(f"refs/tags/{tag}:refs/tags/{tag}")
        self.run("-c", "push.followTags=false", "-c", f"remote.{remote}.mirror=false", "push", "--atomic", "--porcelain", "--", remote, *refs)
        return {"message": f"Pushed {branch}" + (f" and tag {tag}" if tag else "") + f" to {remote}.", "pushed": True}
