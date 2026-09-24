from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module


class MarkdownViewTests(TestCase):
    def test_view_uses_sticky_action_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir).resolve()
            document = markdown_dir / "jobskills" / "tool_fivetran.md"
            document.parent.mkdir(parents=True)
            document.write_text("# Tool Fivetran\n\nLong document.", encoding="utf-8")

            with patch.object(app_module, "MARKDOWN_DIR", markdown_dir):
                response = app_module.app.test_client().get(
                    "/md/view/jobskills/tool_fivetran.md"
                )

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="hero markdown-sticky-header"', page)
        self.assertIn(">EDIT</a>", page)
        self.assertIn(">ACTIONS</button>", page)
        self.assertIn(">LIBRARY</a>", page)
