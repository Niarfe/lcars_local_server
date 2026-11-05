"""Render numbered source links copied from chat and search results."""

import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

from markdown.extensions import Extension
from markdown.inlinepatterns import LINK_RE, LinkInlineProcessor
from markdown.util import AtomicString


def is_web_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc) and not re.search(r"\s", value)


class PastedCitationLinkProcessor(LinkInlineProcessor):
    def handleMatch(self, match, data):
        number, index, handled = self.getText(data, match.end())
        gap = re.match(r"[ \t\u00a0]+\([ \t\u00a0]*", data[index:])
        if not handled or not re.fullmatch(r"[0-9]+", number) or not gap:
            return super().handleMatch(match, data)

        opening = index + gap.group().index("(")
        body = index + gap.end()
        if data[body:body + 1] == "[":
            # [1] ([https://example.com](https://example.com))
            label, link_start, label_handled = self.getText(data, body + 1)
            href, title, end, handled = self.getLink(data, link_start)
            closing = re.match(r"[ \t\u00a0]*\)", data[end:])
            if not label_handled or not handled or not closing or self.unescape(label) != href:
                return super().handleMatch(match, data)
            end += closing.end()
        elif re.match(r"<?https?://", data[body:], re.IGNORECASE):
            # [1] (https://example.com), including angle-bracket destinations.
            href, title, end, handled = self.getLink(data, opening)
        else:
            # Do not reinterpret code or links already parsed into placeholders.
            return super().handleMatch(match, data)

        if not handled or not is_web_url(href):
            return super().handleMatch(match, data)

        link = ElementTree.Element("a", {
            "href": href,
            "title": title or href,
            "class": "markdown-citation",
            "aria-label": f"Source {number}: {href}",
        })
        link.text = AtomicString(f"[{number}]")
        return link, match.start(), end


class PastedCitationsExtension(Extension):
    def extendMarkdown(self, md):
        # Keep normal link parsing and precedence, with a narrow citation fallback.
        # Code spans and escapes run first; surrounding links consume their labels first.
        md.inlinePatterns.register(PastedCitationLinkProcessor(LINK_RE, md), "link", 160)
