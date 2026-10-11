from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_todo.py"
SPEC = importlib.util.spec_from_file_location("build_todo", SCRIPT_PATH)
assert SPEC is not None
build_todo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = build_todo
SPEC.loader.exec_module(build_todo)


class BuildTodoTests(TestCase):
    def test_todo_parser_accepts_label_quadrant_action(self) -> None:
        spec = build_todo.parse_todo_text(
            "INSPIRA III print out form and mail it",
            fallback_label="Inspira Close Fractional Account",
            default_quadrant=2,
        )

        self.assertEqual(spec.label, "INSPIRA")
        self.assertEqual(spec.quadrant, 3)
        self.assertEqual(spec.action, "print out form and mail it")

    def test_todo_parser_accepts_hidden_html_comment_payload(self) -> None:
        spec = build_todo.parse_todo_text(
            "RAM1500 IV Clean out the inside of truck -->",
            fallback_label="Ram 1500 Smog Check",
            default_quadrant=3,
        )

        self.assertEqual(spec.label, "RAM1500")
        self.assertEqual(spec.quadrant, 4)
        self.assertEqual(spec.action, "Clean out the inside of truck")

    def test_todo_parser_accepts_colon_label(self) -> None:
        spec = build_todo.parse_todo_text(
            "FIDELITY: Log in and see how to get this money out",
            fallback_label="Fidelity Mystery Account",
            default_quadrant=3,
        )

        self.assertEqual(spec.label, "FIDELITY")
        self.assertEqual(spec.quadrant, 3)
        self.assertEqual(spec.action, "Log in and see how to get this money out")

    def test_main_replaces_first_matrix_and_preserves_suffix(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_root = Path(temp_dir)
            todo_dir = markdown_root / "0000"
            todo_dir.mkdir()
            (todo_dir / "inspira_close_fractional_account.md").write_text(
                "# Inspira\n\n<!-- #%TODO INSPIRA III print out form and mail it -->\n",
                encoding="utf-8",
            )
            (todo_dir / "fidelity_mystery_account.md").write_text(
                "# Fidelity\n\n#%TODO FIDELITY: Log in and move the money\n",
                encoding="utf-8",
            )
            (todo_dir / "done_item.md").write_text("# Done\n\nNo next action.\n", encoding="utf-8")
            output = todo_dir / "00_todo_list.md"
            output.write_text(
                "## Matrix (Rx1) old\n\n"
                "### Quadrant I\n"
                "* stale\n\n"
                "## End Matrix\n\n"
                "## **@WaitingFor**\n"
                "* Keep this manual section\n",
                encoding="utf-8",
            )

            exit_code = build_todo.main(
                [
                    "--markdown-dir",
                    str(markdown_root),
                    "--base-url",
                    "http://127.0.0.1:5050",
                ]
            )

            content = output.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn(build_todo.BEGIN_MARKER, content)
        self.assertIn("### QUADRANT III\n* [FIDELITY]", content)
        self.assertIn(
            "* [INSPIRA](http://127.0.0.1:5050/md/view/0000/inspira_close_fractional_account.md) print out form and mail it",
            content,
        )
        self.assertIn("## NO NEXT ACTION\n* [Done Item]", content)
        self.assertIn("## **@WaitingFor**\n* Keep this manual section", content)
        self.assertNotIn("* stale", content)

    def test_collect_todos_recurses_into_subfolders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_root = Path(temp_dir)
            todo_dir = markdown_root / "0000"
            truck_dir = todo_dir / "RAM1500"
            truck_dir.mkdir(parents=True)
            (truck_dir / "smog.md").write_text(
                "# Smog\n\n<!-- #%TODO RAM1500 II Clean out the inside of truck -->\n",
                encoding="utf-8",
            )
            output = todo_dir / "00_todo_list.md"
            output.write_text("# Todo\n", encoding="utf-8")

            items, stragglers = build_todo.collect_todos(
                markdown_root,
                "0000",
                output,
                default_quadrant=3,
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "RAM1500")
        self.assertEqual(items[0].quadrant, 2)
        self.assertEqual(items[0].relative_path, "0000/RAM1500/smog.md")
        self.assertEqual(stragglers, [])
