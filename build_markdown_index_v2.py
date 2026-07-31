#!/usr/bin/env python3
"""
Build LCARS Markdown index files from named metadata blocks.

Expected project layout:

    lcars/
        app.py
        content_config.json
        build_markdown_index.py

Example content_config.json:

    {
      "markdown_dir": "/Users/me/Documents/lcars_data/markdown"
    }

Example Markdown document:

    # Lab 10 Git in Snowflake

    ...document content...

    <!-- LCARS
    group: week10
    label: 10_lab
    description: Using Git in Snowflake.
    -->

Usage:

    # Build indexes for every top-level Markdown folder
    python build_markdown_index.py

    # Build an index for one top-level folder
    python build_markdown_index.py 5111

    # Preview without writing
    python build_markdown_index.py 5111 --dry-run

    # Override LCARS URL
    python build_markdown_index.py 5111 \
        --base-url http://127.0.0.1:5050
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


DEFAULT_BASE_URL = "http://127.0.0.1:5050"
DEFAULT_CONFIG_NAME = "content_config.json"
DEFAULT_OUTPUT_NAME = "_Index.md"

H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
LCARS_BLOCK_RE = re.compile(
    r"<!--\s*LCARS\s*(.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")


@dataclass(frozen=True)
class IndexEntry:
    group: str
    label: str
    description: str
    title: str
    relative_path: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate LCARS _Index.md files from Markdown metadata."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help=(
            "Top-level folder under markdown_dir, such as 5111. "
            "If omitted, every top-level folder is indexed."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"LCARS base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME,
        help="Path to content_config.json.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_NAME,
        help=f"Generated index filename. Default: {DEFAULT_OUTPUT_NAME}",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include Markdown files in nested folders beneath the selected folder.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated Markdown instead of writing files.",
    )
    return parser.parse_args()


def load_markdown_root(config_path: Path) -> Path:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Configuration file not found: {config_path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {config_path}: {exc}") from exc

    markdown_dir = config.get("markdown_dir")
    if not isinstance(markdown_dir, str) or not markdown_dir.strip():
        raise ValueError(
            f"{config_path} must contain a non-empty string value for 'markdown_dir'."
        )

    root = Path(markdown_dir).expanduser()
    if not root.is_absolute():
        root = (config_path.parent / root).resolve()
    else:
        root = root.resolve()

    if not root.exists():
        raise ValueError(f"Configured markdown_dir does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Configured markdown_dir is not a directory: {root}")

    return root


def parse_lcars_metadata(text: str) -> dict[str, str]:
    """
    Find the first <!-- LCARS ... --> block and parse simple key:value fields.

    Unknown fields are preserved in the returned dictionary so the metadata
    format can grow without requiring changes to this parser.
    """
    match = LCARS_BLOCK_RE.search(text)
    if not match:
        return {}

    metadata: dict[str, str] = {}

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue

        field_match = KEY_VALUE_RE.match(line)
        if not field_match:
            continue

        key = field_match.group(1).lower()
        value = field_match.group(2).strip()
        metadata[key] = value

    return metadata


def first_h1(text: str) -> str | None:
    match = H1_RE.search(text)
    return match.group(1).strip() if match else None


def parse_document(
    path: Path,
    markdown_root: Path,
    base_url: str,
) -> IndexEntry | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return None

    metadata = parse_lcars_metadata(text)
    if not metadata:
        print(
            f"skip: {path.relative_to(markdown_root)} "
            "(no '<!-- LCARS ... -->' metadata block)",
            file=sys.stderr,
        )
        return None

    group = metadata.get("group", "").strip()
    label = metadata.get("label", "").strip()
    description = metadata.get("description", "").strip()
    title = metadata.get("title", "").strip() or first_h1(text) or path.stem

    missing = [
        name
        for name, value in (
            ("group", group),
            ("label", label),
            ("description", description),
        )
        if not value
    ]
    if missing:
        print(
            f"skip: {path.relative_to(markdown_root)} "
            f"(missing metadata: {', '.join(missing)})",
            file=sys.stderr,
        )
        return None

    relative_path = path.relative_to(markdown_root).as_posix()
    encoded_path = quote(relative_path, safe="/")
    url = f"{base_url.rstrip('/')}/md/view/{encoded_path}"

    return IndexEntry(
        group=group,
        label=label,
        description=description,
        title=title,
        relative_path=relative_path,
        url=url,
    )


def humanize_group(group: str) -> str:
    """Preserve deliberate spelling while making all-lowercase groups readable."""
    if group.islower():
        return group[:1].upper() + group[1:]
    return group


def markdown_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.md" if recursive else "*.md"
    return sorted(
        folder.glob(pattern),
        key=lambda path: path.relative_to(folder).as_posix().casefold(),
    )


def render_index(entries: list[IndexEntry]) -> str:
    grouped: dict[str, list[IndexEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.group].append(entry)

    lines = [
        "# Index",
        "",
        "<!-- Generated by build_markdown_index.py. Manual edits may be overwritten. -->",
        "",
    ]

    for group in sorted(grouped, key=str.casefold):
        lines.append(f"## {humanize_group(group)}")
        lines.append("")

        ordered = sorted(
            grouped[group],
            key=lambda entry: (
                entry.label.casefold(),
                entry.title.casefold(),
                entry.relative_path.casefold(),
            ),
        )

        for entry in ordered:
            lines.append(f"* [{entry.label}]({entry.url})")
            lines.append(f"    - {entry.description}")

        lines.append("")

    if not entries:
        lines.extend(
            [
                "_No documents with valid LCARS index metadata were found._",
                "",
                "Expected metadata:",
                "",
                "```markdown",
                "<!-- LCARS",
                "group: week10",
                "label: 10_lab",
                "description: Using Git in Snowflake.",
                "-->",
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_folder(
    folder: Path,
    markdown_root: Path,
    base_url: str,
    output_name: str,
    recursive: bool,
    dry_run: bool,
) -> tuple[int, Path]:
    if not folder.exists():
        raise ValueError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")

    output_path = folder / output_name
    entries: list[IndexEntry] = []

    for path in markdown_files(folder, recursive):
        if path.resolve() == output_path.resolve():
            continue

        entry = parse_document(path, markdown_root, base_url)
        if entry is not None:
            entries.append(entry)

    content = render_index(entries)

    if dry_run:
        heading = folder.relative_to(markdown_root).as_posix()
        print(f"\n===== {heading}/{output_name} =====\n")
        print(content, end="")
    else:
        output_path.write_text(content, encoding="utf-8")
        print(f"wrote: {output_path}")
        print(f"indexed: {len(entries)} document(s)")

    return len(entries), output_path


def target_folders(markdown_root: Path, folder_name: str | None) -> list[Path]:
    if folder_name:
        requested = Path(folder_name)

        if requested.is_absolute() or ".." in requested.parts:
            raise ValueError("Folder must be a path relative to markdown_dir.")

        target = (markdown_root / requested).resolve()
        try:
            target.relative_to(markdown_root)
        except ValueError as exc:
            raise ValueError("Folder must remain inside markdown_dir.") from exc

        return [target]

    return sorted(
        (path for path in markdown_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )


def main() -> int:
    args = parse_args()

    try:
        markdown_root = load_markdown_root(args.config.resolve())
        folders = target_folders(markdown_root, args.folder)

        if not folders:
            print(f"No top-level folders found under {markdown_root}.")
            return 0

        total = 0
        for folder in folders:
            count, _ = build_folder(
                folder=folder,
                markdown_root=markdown_root,
                base_url=args.base_url,
                output_name=args.output,
                recursive=args.recursive,
                dry_run=args.dry_run,
            )
            total += count

        if len(folders) > 1:
            action = "previewed" if args.dry_run else "indexed"
            print(f"\n{action} {total} document(s) across {len(folders)} folder(s)")

        return 0

    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
