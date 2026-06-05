# LCARS Flask Monolith v11

Single-process Flask app with:
- LCARS dashboard
- Jupyter local + remote launcher
- Books library + reader
- Markdown library + rendered view + edit/save flow
- Markdown print support
- tmux session monitor

## Run

```bash
cd lcars-flask-monolith-v11
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:
- Dashboard: http://127.0.0.1:5000/
- Jupyter: http://127.0.0.1:5000/jupyter
- Books: http://127.0.0.1:5000/books
- Markdown: http://127.0.0.1:5000/markdown
- tmux: http://127.0.0.1:5000/tmux

## Books

Put UTF-8 `.txt` files into the `books/` folder.

## Markdown

Put `.md` files into the `markdown/` folder.

## v13

- Markdown create-new-file flow
- Markdown wide document surface and themes
- Optional left-nav document switcher

## v14

- Dashboard now includes a local visual link tree.
- Add links by folder path, name, and URL.
- Markdown toolbar groups theme buttons under a THEME menu.

## v15

- Smaller LCARS-style buttons.
- Markdown delete buttons on list/view pages.
- Books delete buttons on list/reader pages.
- Markdown list filter for prefix/text matching.
- Rendered Markdown links are visibly highlighted.

## v17

- Added FOCUS page with Pomodoro-style timer.
- Presets: 10/3, 25/5, 50/10.
- Custom focus/break minutes.
- Large countdown, progress bar, pause/reset, and alert on phase completion.

## v18

- Bugfix: Markdown document nav only persists on Markdown pages.
- Bugfix: Sticky Markdown filter applies immediately when returning to the list.
- Bugfix: Markdown code copy buttons are visibly rendered on code blocks.


## v20

- Focus timer now stops at each boundary instead of automatically rolling into the next phase.
- Done state is purple.
- START from done intentionally advances to the next phase.
- Removed alert/notification behavior.
- Added audible cue support:
  - default WebAudio beep fallback
  - optional MP3 paths in `focus_config.json`
  - place local files under `static/sounds/` and use paths like `/static/sounds/work_done.mp3`


## v21c

- Markdown Actions menu now nests Theme choices under THEME.
- Added Markdown font controls under Actions -> Font: A-, A0, A+.
- Removed buggy whole-body nowrap behavior that caused extra visual spacing in lists.
- Long Markdown content remains contained without moving toolbar controls.


## v22

- Markdown Actions now includes Rename.
- Markdown A-/A+ font scaling applies to headings too.
- Focus timer now starts work audio immediately on START.
- Work expiry switches directly to break, stops work audio, starts break audio, and starts break timer.
- Break expiry stops at static DONE state and waits for START to begin a new work cycle.
- Focus audio supports `work_mode_sound` and `break_mode_sound`, with old config names still supported.


## v22b

- Markdown Actions menu now renders RENAME and DELETE as text-style menu items by default.
- RENAME and DELETE still highlight on hover.


## v22c

- Bugfix: Markdown rename now returns valid JSON after successful rename.
- Fixes browser popup error: `Unexpected token '<', "<!doctype"... is not valid JSON`.


## v22d

- Added default favicon at `static/favicon.png`.
- Wired favicon into `templates/base.html`.
- Replace `static/favicon.png` with any PNG you prefer to customize browser tab/bookmark icons.


## v22e

- Markdown renderer now normalizes bare checklist lines:
  - `[x] item` becomes `- [x] item`
  - `[ ] item` becomes `- [ ] item`
- This keeps checklist-style notes from collapsing into one paragraph.


## v22f

- Bugfix: checklist normalization now patches the actual Markdown render path.
- Bare `[x] item` and `[ ] item` lines should render as separate task-list bullets.


## v22g

- Bugfix: checklist normalization now runs inside `render_markdown()`, the actual Markdown rendering function.
- Bare `[x] item` / `[ ] item` lines should render as separate list items.


## v23b

- Corrected v23 selectors for actual app structure (`.shell` / `.nav`).
- Collapsible side nav now works.
- Size selector now appears in side nav and persists.
- Dashboard Quick Links block removed.
- Link tree now defaults collapsed and persists open/closed state.
- Duplicate Close All button bug fixed.


## v23c

- Moved UI size controls into top-right SETTINGS dropdown.
- Removed side-nav size selector.
- Removed legacy DOCS button.
- Sidebar now contains only navigation + collapse control.


## v23d

- Bugfix: replaced the actual FLASK / MONOLITH hero badges with SETTINGS.
- SETTINGS contains Size -> Compact / Normal / Large.
