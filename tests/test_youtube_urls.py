from unittest import TestCase
from unittest.mock import patch

from app import canonical_youtube_url, parse_youtube_video_id, youtube_metadata_defaults


class YouTubeUrlTests(TestCase):
    def test_parse_shorts_url(self) -> None:
        self.assertEqual(
            parse_youtube_video_id("https://www.youtube.com/shorts/eKg8FmqILhA"),
            "eKg8FmqILhA",
        )

    def test_parse_watch_url(self) -> None:
        self.assertEqual(
            parse_youtube_video_id("https://www.youtube.com/watch?v=eKg8FmqILhA"),
            "eKg8FmqILhA",
        )

    def test_canonical_short_url(self) -> None:
        self.assertEqual(
            canonical_youtube_url("eKg8FmqILhA", "short"),
            "https://www.youtube.com/shorts/eKg8FmqILhA",
        )

    @patch("app.fetch_youtube_oembed", return_value={})
    def test_metadata_defaults_preserve_shorts_url(self, _oembed: object) -> None:
        defaults = youtube_metadata_defaults(
            "eKg8FmqILhA",
            raw_url="https://www.youtube.com/shorts/eKg8FmqILhA",
        )

        self.assertEqual(defaults["url"], "https://www.youtube.com/shorts/eKg8FmqILhA")
