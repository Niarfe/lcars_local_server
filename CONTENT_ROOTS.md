# External Content Roots

LCARS v25 supports keeping user content outside the app folder.

Edit `content_config.json` next to `app.py`:

```json
{
  "markdown_dir": "/Users/praedator/Documents/LCARS_CONTENT/markdown",
  "books_dir": "/Users/praedator/Documents/LCARS_CONTENT/books",
  "sounds_dir": "/Users/praedator/Documents/LCARS_CONTENT/sounds"
}
```

Then restart LCARS.

Suggested setup:

```bash
mkdir -p ~/Documents/LCARS_CONTENT/markdown
mkdir -p ~/Documents/LCARS_CONTENT/books
mkdir -p ~/Documents/LCARS_CONTENT/sounds

cp -R markdown/* ~/Documents/LCARS_CONTENT/markdown/
cp -R books/* ~/Documents/LCARS_CONTENT/books/

cd ~/Documents/LCARS_CONTENT
git init
git add .
git commit -m "Initial LCARS content backup"
```

If a configured folder does not exist, LCARS creates it. Your old local `markdown/` and `books/` folders are not deleted.

## Mounted Markdown Folders

The Markdown sidebar has a **MOUNTS** section. **MOUNT FOLDER** opens a folder picker at your home directory. Select a folder, optionally change its display name, and choose **MOUNT FOLDER**. The arrow beside a folder opens it; double-clicking its name also opens it. The path field accepts absolute paths and `~/...`, including folders on other drives. Hidden folders can be shown with the checkbox.

Each mount is a separate library. **ALL**, folder navigation, name filtering, and GREP apply to the selected mount. Creating, editing, renaming, deleting, Finder access, images, relative Markdown links, and collated printing use that folder directly. LCARS does not copy or synchronize its files.

The document viewer keeps folder navigation available for the document's containing folder. Selecting a folder with visible Markdown subfolders shows its children. Selecting a leaf folder keeps its siblings in place and highlights the selected folder in bold orange, while the document list narrows to that folder. For example, selecting `uva/f26/ai_course` keeps the other `f26` course folders available; selecting `uva/f26` shows all documents beneath the semester. The sidebar keeps its scroll position while switching between siblings or opening a document. Ignored dependency folders do not affect this navigation rule.

Enable **FULL PATHS** above the document list to show each relative file path as a single bold line and sort by the full path. Disable it to restore document titles with their paths underneath and the original filename ordering. This preference is remembered in the browser across folders and mounts; both views use the same name filter and GREP search.

Use the eject control beside a mount, labeled **Unmount Folder**, to remove its entry. Unmounting leaves the folder and its files untouched. The primary `markdown` library remains available and cannot be unmounted.

Mounts are saved automatically in `content_config.json` under `markdown_mounts`, with a stable ID, label, and path. Paths within the current home directory use `~/...`; other paths are absolute. For example:

```json
{
  "markdown_dir": "~/Documents/LCARS_CONTENT/markdown",
  "books_dir": "~/Documents/LCARS_CONTENT/books",
  "sounds_dir": "./static/sounds/",
  "markdown_mounts": [
    {
      "id": "academy",
      "label": "academy",
      "path": "~/Documents/academy"
    }
  ]
}
```

Document URLs show the file's filesystem path, for example `/md/view?path=~/Documents/academy/README.md`. `~/` means your Mac's home directory; files outside it use an absolute path, such as `/md/view?path=/Volumes/Notes/project/README.md`. Editing, peeking, images, and collated printing use the same path format. Special characters are URL-encoded while folder separators remain readable. These URLs resolve only within the primary library or configured mounts, and symlinks cannot leave their selected folder. For nested mounts, LCARS uses the closest containing folder. Moving or renaming a file changes its path; changing a mount's label or ID does not. Unmounting makes its links unavailable until the same path is mounted again.

Older `/md/view/...` URLs still refer to the primary library, and older `?root=<mount-id>` URLs still select their original mount. IDs remain in the configuration for library context and backwards compatibility; keep them unchanged to preserve those older links.

Unavailable mounts stay in the sidebar and can be unmounted. LCARS never creates a missing mounted folder. Duplicate mounts, including aliases through symlinks, are rejected. Document paths and symlinks must stay inside the selected root.

Mounted Git repositories follow Git's ignore rules when listing Markdown, building folder navigation, and searching contents. An `env/` or `venv/` entry in the repository's `.gitignore` also keeps that environment's dependency documentation out of LCARS. Nested `.gitignore` files, negated rules, `.git/info/exclude`, and global Git exclusions work as they do in Git. A mount inside a repository also inherits ignore rules from its parent directories. Reloading the library picks up ignore changes automatically.

Tracked Markdown remains visible even when it matches an ignore rule. LCARS reads the working copy, so new, non-ignored notes appear before they are added to Git, and deleted files disappear. Direct document links and image assets continue to resolve within the mounted folder.

The primary LCARS library keeps its existing scan behavior so Git-ignored generated notes, such as YouTube transcripts, remain available. Ordinary folder mounts and machines without Git also use the existing scan, omitting `.git`, `.hg`, `.svn`, `.venv`, `node_modules`, and `__pycache__` directories.

Archive and generated TODO refresh currently operate only in the primary Markdown library. YouTube transcripts also continue to be saved there. The LCARS repository can remain in its existing location; mounting does not require an installation at `~/.lcars_local_server`.

### Git Ignore Design Decision

Recorded 2026-10-16: deliberately delegate repository discovery and ignore handling to Git. The motivation is to piggyback on Git's established implementation, rather than maintain a second interpretation of `.gitignore` in LCARS. Git already handles nested rules, negation, local and global exclusions, and the distinction between tracked and untracked files.

The scanner uses `git ls-files --cached --others --exclude-standard -z` with a Markdown pathspec. This combines tracked Markdown with untracked, non-ignored Markdown from the working copy. For example, with `*.md` in `.gitignore`, `git add -f sample.md` makes `sample.md` visible in LCARS immediately, even before a commit. Other untracked Markdown matching that rule remains hidden. A standalone ignore-pattern parser would miss that index-dependent distinction.

The accepted tradeoff is that a standalone `.gitignore` in an ordinary folder does not activate Git filtering. Mounting itself never requires a repository. For now, prefer granular mounts of individual repositories and useful plain folders; standalone ignore support is deferred. Avoid recommending `git init` across `~/Documents` or the home directory solely to enable LCARS filtering: a broad parent repository increases the scope someone might accidentally stage and complicates navigation around existing repositories. If this decision is revisited, preserve Git's repository semantics and explicitly evaluate any additional behavior for non-repository folders.

### Local Files And Publishing

Mounting a folder and discovering its documents do not initialize a repository, stage files, create commits, configure remotes, or push anything. The explicit **VERSION** actions described below can commit, tag, and push an existing repository. The separate Archive feature in the primary library can stage content and create local checkpoint commits; it does not invoke `git push`.

Running `git init` alone does not upload files or add a remote. Keeping any repository created only for LCARS without remotes removes the usual default push destination. This is not an absolute publishing restriction: another tool can add a remote or push to an explicit URL. Do not treat an LCARS-only repository as protected against publication merely because it has no remote today.

A document can be visible in LCARS without being tracked or committed. Conversely, ignoring a previously tracked private file does not remove it from Git history. Keep local/private material untracked and ignored where appropriate, and review what is staged before committing or publishing from other tools. LCARS' document list is a local browsing view, not an indication that its contents should be published.

### Repository Versions And Milestones

Mount an existing Git repository's **root folder**, then select its **ALL** library view. **VERSION** appears beside **FINDER** there. A mount of only a subfolder, such as `lcars_data/markdown`, does not expose repository version actions: mount `lcars_data` itself to manage that repository's milestones. LCARS does not initialize repositories, configure Git identities, create GitHub repositories, or add remotes.

- **COMMIT CHANGES…** previews changes across the entire repository and asks for a description. It stages and commits the reviewed changes, including code, images, new non-ignored files, and deletions.
- **CREATE TAG…** asks for a unique tag name and description. It commits reviewed changes if needed, requires a clean working copy, then creates an annotated tag. A clean repository is tagged without an empty commit. Existing tags are never replaced. Tags capture all tracked content in the commit, including non-Markdown files.
- **VIEW AT TAG…** lists local tags with their descriptions and dates, then switches the entire working copy to the chosen commit. Finder, terminals, and other applications see those historical files too.
- **LATEST TAG** visits the newest tag by creation date among tags reachable from the saved working branch. For lightweight tags, Git uses the commit date. This action does not mean the latest untagged work.
- **RETURN TO CURRENT WORK** switches back to the saved working branch, including commits after the latest milestone. The return destination is stored in the worktree's Git directory and survives LCARS restarts.
- **PUSH BACKUP…** previews configured push destinations and pushes the working branch plus, optionally, one selected tag. **CREATE TAG…** also offers an optional push after the milestone is saved. GitHub organizations need no LCARS-specific setup: each repository uses its existing remote and Git credentials. Pushes are atomic and never forced; rejected pushes leave local commits and tags intact. LCARS does not automatically pull, merge, or resolve remote divergence.

Document **Actions → COMMIT…** commits that Markdown file without tagging it. Other unstaged files remain pending. Unrelated staged files block a per-file commit; use the repository-level action or resolve the index in Git first. File commits still belong to the repository's normal history.

Switching requires the entire repository to have no staged changes, modified/deleted tracked files, or non-ignored untracked files. LCARS never stashes, resets, cleans, or forces a switch. Ignored untracked files are outside snapshots and normally remain in place; a switch is also blocked if it would overwrite one. An expired preview requires a fresh review, including when changed file contents or remote configuration have changed.

Historical versions are read-only in LCARS, including nested mounts and generated Markdown writes. A banner identifies the selected milestone. External editors can still modify the filesystem; those changes block further version switches until preserved with Git outside LCARS. Open dirty LCARS editors block version actions through browser records and server heartbeats. Browser heartbeats expire after 90 seconds when a tab stops responding; document revision checks independently reject stale saves, including after a round trip between versions. Preserve the editor text before reloading a rejected save.

API clients saving documents inside a Git repository must include the `revision` from `GET /api/markdown/<document>` in the JSON payload to `POST /api/markdown/save/<document>`. Successful saves return the next revision. A stale or missing revision produces HTTP 409 and leaves the file untouched.

Version switching is disabled for repositories containing the running LCARS application. Active Git operations, submodules, and sparse checkouts are also unsupported in this first version. Git hooks and signing settings are respected, and errors are displayed without undoing completed local commits. LCARS serializes its own repository writes; external Git tools and editors should remain idle during a version operation.
