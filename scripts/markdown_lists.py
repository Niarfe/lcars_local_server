"""List compatibility for pasted chat and search results."""

import re

from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension
from markdown.extensions.sane_lists import SaneOListProcessor, SaneUListProcessor


class PastedBulletListProcessor(SaneUListProcessor):
    """Accept a Unicode bullet, including a copied nonbreaking separator."""

    def __init__(self, parser):
        super().__init__(parser)
        self.RE = re.compile(r"^[ ]{0,%d}[*+•-][ \u00a0]+(.*)" % (self.tab_length - 1))
        self.CHILD_RE = re.compile(
            r"^[ ]{0,%d}(([*+•-]))[ \u00a0]+(.*)" % (self.tab_length - 1)
        )
        self.INDENT_RE = nested_item_pattern(self.tab_length)


class PastedOrderedListProcessor(SaneOListProcessor):
    def __init__(self, parser):
        super().__init__(parser)
        # Recognize Unicode bullets nested inside an otherwise ordinary numbered list.
        self.INDENT_RE = nested_item_pattern(self.tab_length)


def nested_item_pattern(tab_length):
    return re.compile(
        r"^[ ]{%d,%d}((\d+\.)|[*+•-])[ \u00a0]+.*" % (tab_length, tab_length * 2 - 1)
    )


class ImmediateBulletListProcessor(BlockProcessor):
    """Split a paragraph from a following list before paragraph rendering."""

    def __init__(self, parser):
        super().__init__(parser)
        self.RE = re.compile(r"\n(?=[ ]{0,%d}[*+•-][ \u00a0]+)" % (self.tab_length - 1))

    def test(self, parent, block):
        return bool(self.RE.search(block))

    def run(self, parent, blocks):
        # Earlier processors already handle code, HTML, headings, rules and quotes.
        # Reparse the two parts so normal list indentation and nesting still apply.
        block = blocks.pop(0)
        boundary = self.RE.search(block)
        blocks[:0] = [block[:boundary.start()], block[boundary.end():]]


class PastedListsExtension(Extension):
    def extendMarkdown(self, md):
        processors = md.parser.blockprocessors
        processors.register(PastedOrderedListProcessor(md.parser), "olist", 40)
        processors.register(PastedBulletListProcessor(md.parser), "ulist", 30)
        processors.register(ImmediateBulletListProcessor(md.parser), "immediate_ulist", 11)
