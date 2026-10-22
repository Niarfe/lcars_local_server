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

Mounting a folder and discovering its documents do not initialize a repository, stage files, create commits, configure remotes, or push anything. LCARS currently has no Git push action. The separate Archive feature in the primary library can stage content and create local checkpoint commits; it does not invoke `git push`.

Running `git init` alone does not upload files or add a remote. Keeping any repository created only for LCARS without remotes removes the usual default push destination. This is not an absolute publishing restriction: another tool can add a remote or push to an explicit URL. Do not treat an LCARS-only repository as protected against publication merely because it has no remote today.

A document can be visible in LCARS without being tracked or committed. Conversely, ignoring a previously tracked private file does not remove it from Git history. Keep local/private material untracked and ignored where appropriate, and review what is staged before committing or publishing from other tools. LCARS' document list is a local browsing view, not an indication that its contents should be published.
