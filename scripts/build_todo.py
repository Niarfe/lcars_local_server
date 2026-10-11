#!/usr/bin/env python3
"""Build the LCARS todo view from inline #%TODO markers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = APP_DIR / "content_config.json"
DEFAULT_FOLDER = "0000"
DEFAULT_OUTPUT = "00_todo_list.md"
DEFAULT_BASE_URL = "http://127.0.0.1:5050"
BEGIN_MARKER = "<!-- BEGIN AUTO TODO -->"
END_MARKER = "<!-- END AUTO TODO -->"

TODO_RE = re.compile(r"#%TODO\b\s*(.*)", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MATRIX_RE = re.compile(
    r"(?ms)^##\s+Matrix\s*\([^)]*\).*?^##\s+End\s+Matrix\s*$\n*"
)

ROMAN_BY_QUADRANT = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
}
QUADRANT_BY_TOKEN = {
    "1": 1,
    "I": 1,
    "ONE": 1,
    "Q1": 1,
    "QI": 1,
    "2": 2,
    "II": 2,
    "TWO": 2,
    "Q2": 2,
    "QII": 2,
    "3": 3,
    "III": 3,
    "THREE": 3,
    "Q3": 3,
    "QIII": 3,
    "4": 4,
    "IV": 4,
    "FOUR": 4,
    "Q4": 4,
    "QIV": 4,
}


@dataclass(frozen=True)
class TodoItem:
    label: str
    action: str
    quadrant: int
    source_path: Path
    relative_path: str
    line_number: int


@dataclass(frozen=True)
class TodoSpec:
    label: str
    action: str
    quadrant: int


def clean_token(token: str) -> str:
    return token.strip().strip("[](){}:;,.").upper()


def parse_quadrant_at_start(text: str) -> tuple[int | None, str]:
    stripped = text.lstrip()
    if not stripped:
        return None, ""

    words = stripped.split(maxsplit=2)
    first = clean_token(words[0])
    if first in {"QUADRANT", "QUAD"} and len(words) >= 2:
        quadrant = QUADRANT_BY_TOKEN.get(clean_token(words[1]))
        if quadrant is not None:
            remainder = words[2] if len(words) == 3 else ""
            return quadrant, remainder.strip(" :-")

    quadrant = QUADRANT_BY_TOKEN.get(first)
    if quadrant is not None:
        remainder = stripped[len(words[0]) :]
        return quadrant, remainder.strip(" :-")

    return None, stripped


def parse_todo_text(
    raw_text: str,
    *,
    fallback_label: str,
    default_quadrant: int,
) -> TodoSpec:
    text = raw_text.strip()
    if text.endswith("-->"):
        text = text[:-3].rstrip()
    if text.startswith(":"):
        text = text[1:].strip()

    quadrant, text = parse_quadrant_at_start(text)

    label = ""
    action = text

    bracket_label = re.match(r"^\[([^\]]+)\]\s*(.*)$", text)
    if bracket_label:
        label = bracket_label.group(1).strip()
        action = bracket_label.group(2).strip()
    elif text:
        first_word = text.split(maxsplit=1)[0]
        if ":" in first_word:
            raw_label, raw_action = text.split(":", 1)
            label = raw_label.strip()
            action = raw_action.strip()
        else:
            label = first_word.strip(" :-")
            action = text[len(first_word) :].strip()
    else:
        action = ""

    action_quadrant, action_without_quadrant = parse_quadrant_at_start(action)
    if action_quadrant is not None:
        quadrant = action_quadrant
        action = action_without_quadrant

    clean_label = label.strip(" :-") or fallback_label
    clean_action = action.strip(" :-")
    return TodoSpec(
        label=clean_label,
        action=clean_action,
        quadrant=quadrant or default_quadrant,
    )


def title_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


def encoded_doc_path(relative_path: str) -> str:
    return "/".join(quote(part) for part in Path(relative_path).parts)


def markdown_link_for(relative_path: str, base_url: str) -> str:
    clean_base = base_url.rstrip("/")
    return f"{clean_base}/md/view/{encoded_doc_path(relative_path)}"


def escape_link_label(label: str) -> str:
    return label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def scan_file(path: Path, markdown_root: Path, default_quadrant: int) -> list[TodoItem]:
    relative_path = path.relative_to(markdown_root).as_posix()
    fallback_label = title_from_path(path)
    items: list[TodoItem] = []
    in_fence = False

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        match = TODO_RE.search(line)
        if not match:
            continue

        spec = parse_todo_text(
            match.group(1),
            fallback_label=fallback_label,
            default_quadrant=default_quadrant,
        )
        items.append(
            TodoItem(
                label=spec.label,
                action=spec.action,
                quadrant=spec.quadrant,
                source_path=path,
                relative_path=relative_path,
                line_number=line_number,
            )
        )

    return items


def collect_todos(
    markdown_root: Path,
    folder: str,
    output_path: Path,
    default_quadrant: int,
) -> tuple[list[TodoItem], list[Path]]:
    markdown_root = markdown_root.resolve()
    todo_dir = (markdown_root / folder).resolve()
    if not todo_dir.is_dir():
        raise FileNotFoundError(f"Todo folder not found: {todo_dir}")

    output_path = output_path.resolve()
    items: list[TodoItem] = []
    stragglers: list[Path] = []

    markdown_paths = sorted(
        todo_dir.rglob("*.md"),
        key=lambda candidate: candidate.relative_to(markdown_root).as_posix().casefold(),
    )
    for path in markdown_paths:
        if path.resolve() == output_path:
            continue
        file_items = scan_file(path, markdown_root, default_quadrant)
        if file_items:
            items.extend(file_items)
        else:
            stragglers.append(path)

    items.sort(
        key=lambda item: (
            item.quadrant,
            item.label.casefold(),
            item.relative_path.casefold(),
            item.line_number,
        )
    )
    stragglers.sort(key=lambda path: path.relative_to(markdown_root).as_posix().casefold())
    return items, stragglers


def format_todo_item(item: TodoItem, base_url: str) -> str:
    link = markdown_link_for(item.relative_path, base_url)
    action = f" {item.action}" if item.action else ""
    return f"* [{escape_link_label(item.label)}]({link}){action}"


def format_straggler(path: Path, markdown_root: Path, base_url: str) -> str:
    relative_path = path.relative_to(markdown_root).as_posix()
    link = markdown_link_for(relative_path, base_url)
    return f"* [{escape_link_label(title_from_path(path))}]({link})"


def build_generated_view(
    items: list[TodoItem],
    stragglers: list[Path],
    markdown_root: Path,
    base_url: str,
) -> str:
    items_by_quadrant: dict[int, list[TodoItem]] = {quadrant: [] for quadrant in range(1, 5)}
    for item in items:
        items_by_quadrant.setdefault(item.quadrant, []).append(item)

    lines = [
        BEGIN_MARKER,
        "## Matrix (Rx1) TODO",
        "",
    ]

    for quadrant in range(1, 5):
        lines.append(f"### QUADRANT {ROMAN_BY_QUADRANT[quadrant]}")
        lines.extend(format_todo_item(item, base_url) for item in items_by_quadrant[quadrant])
        lines.append("")

    lines.extend(
        [
            "## End Matrix",
            "",
            "## NO NEXT ACTION",
        ]
    )
    if stragglers:
        lines.extend(format_straggler(path, markdown_root, base_url) for path in stragglers)
    else:
        lines.append("* None")

    lines.extend(["", END_MARKER, ""])
    return "\n".join(lines)


def join_sections(sections: list[str]) -> str:
    return "\n\n".join(section.strip() for section in sections if section.strip()) + "\n"


def merge_generated_view(existing: str, generated: str) -> str:
    begin = existing.find(BEGIN_MARKER)
    end = existing.find(END_MARKER)
    if begin != -1 and end != -1 and begin < end:
        end += len(END_MARKER)
        return join_sections([existing[:begin], generated, existing[end:]])

    matrix = MATRIX_RE.search(existing)
    if matrix:
        return join_sections([existing[: matrix.start()], generated, existing[matrix.end() :]])

    return join_sections([generated, existing])


def load_markdown_root(config_path: Path, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()

    if not config_path.exists():
        return (APP_DIR / "markdown").resolve()

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    markdown_dir = raw.get("markdown_dir") or APP_DIR / "markdown"
    return Path(markdown_dir).expanduser().resolve()


def resolve_output_path(markdown_root: Path, folder: str, output: str) -> Path:
    output_path = Path(output).expanduser()
    if output_path.is_absolute():
        return output_path.resolve()
    if len(output_path.parts) > 1:
        return (markdown_root / output_path).resolve()
    return (markdown_root / folder / output_path).resolve()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate the LCARS todo matrix from #%TODO lines."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Content config JSON.")
    parser.add_argument("--markdown-dir", help="Override the markdown root from content_config.json.")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="Folder to scan below the markdown root.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output file. Bare names are written inside --folder; paths are relative to the markdown root.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LCARS base URL for local links.")
    parser.add_argument(
        "--default-quadrant",
        type=int,
        choices=range(1, 5),
        default=3,
        metavar="{1,2,3,4}",
        help="Quadrant for TODO lines without I/II/III/IV or Q1/Q2/Q3/Q4.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the generated block instead of updating the output file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()
    markdown_root = load_markdown_root(config_path, args.markdown_dir)
    output_path = resolve_output_path(markdown_root, args.folder, args.output)

    items, stragglers = collect_todos(
        markdown_root,
        args.folder.strip("/"),
        output_path,
        args.default_quadrant,
    )
    generated = build_generated_view(items, stragglers, markdown_root, args.base_url)

    if args.stdout:
        sys.stdout.write(generated)
        return 0

    existing = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
    updated = merge_generated_view(existing, generated)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if existing == updated:
        print(f"todo unchanged: {output_path}")
    else:
        output_path.write_text(updated, encoding="utf-8")
        print(f"todo updated: {output_path}")
    print(f"items: {len(items)}; no next action: {len(stragglers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
