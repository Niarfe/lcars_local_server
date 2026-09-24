from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module
from app import (
    canonical_youtube_url,
    get_youtube_items,
    get_youtube_sources,
    get_youtube_tag_labels,
    normalize_youtube_tag,
    parse_tag_list,
    parse_youtube_video_id,
    youtube_metadata_defaults,
)


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

    def test_tag_normalization_is_uppercase_and_case_insensitive(self) -> None:
        self.assertEqual(normalize_youtube_tag("  _French_  "), "_FRENCH_")
        self.assertEqual(
            parse_tag_list("_french_, _FRENCH_\ncar repair"),
            ["_FRENCH_", "CAR", "REPAIR"],
        )

    def test_sources_merge_source_and_item_tags_and_keep_latest_thumbnail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "youtube.sqlite3"
            with patch.object(app_module, "YOUTUBE_DB_PATH", database_path):
                with app_module.get_youtube_db() as conn:
                    conn.execute(
                        """
                        INSERT INTO youtube_sources
                            (id, name, alias, source_url, thumbnail_url, created_at, updated_at)
                        VALUES (1, 'Example Source', '', '', 'source.jpg', '2026-01-01', '2026-01-01')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO youtube_videos
                            (id, source_id, video_id, url, title, thumbnail_url, notes, created_at, updated_at)
                        VALUES
                            (1, 1, 'older01', 'https://example/older', 'Older', 'older.jpg', '', '2026-01-01', '2026-01-01'),
                            (2, 1, 'latest02', 'https://example/latest', 'Latest', 'latest.jpg', '', '2026-01-02', '2026-01-02')
                        """
                    )
                    conn.execute("INSERT INTO youtube_tags (id, name) VALUES (1, '_french_')")
                    conn.execute("INSERT INTO youtube_tags (id, name) VALUES (2, '_FRENCH_')")
                    conn.execute("INSERT INTO youtube_tags (id, name) VALUES (3, 'car repair')")
                    conn.execute("INSERT INTO youtube_source_tags VALUES (1, 1)")
                    conn.execute("INSERT INTO youtube_video_tags VALUES (2, 2)")
                    conn.execute("INSERT INTO youtube_video_tags VALUES (2, 3)")
                    conn.commit()

                sources = get_youtube_sources(selected_tags="_FrEnCh_")

                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0]["thumbnail_url"], "latest.jpg")
                self.assertEqual(sources[0]["tags"], ["_FRENCH_", "CAR", "REPAIR"])
                self.assertEqual(get_youtube_tag_labels(), ["_FRENCH_", "CAR", "REPAIR"])

                self.assertEqual(
                    len(get_youtube_sources(selected_tags=["_FRENCH_", "REPAIR"])),
                    1,
                )
                self.assertEqual(
                    get_youtube_sources(selected_tags=["_FRENCH_", "MONEY"]),
                    [],
                )

    def test_youtube_page_uses_compact_cards_and_footer_utilities(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "youtube.sqlite3"
            with patch.object(app_module, "YOUTUBE_DB_PATH", database_path):
                with app_module.get_youtube_db() as conn:
                    conn.execute(
                        """
                        INSERT INTO youtube_sources
                            (id, name, alias, source_url, thumbnail_url, created_at, updated_at)
                        VALUES (1, 'Example Source', '', '', 'source.jpg', '2026-01-01', '2026-01-01')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO youtube_videos
                            (id, source_id, video_id, url, title, thumbnail_url, notes, created_at, updated_at)
                        VALUES
                            (1, 1, 'latest02', 'https://example/latest', 'Latest linked video', 'latest.jpg', '', '2026-01-02', '2026-01-02')
                        """
                    )
                    conn.execute("INSERT INTO youtube_tags (id, name) VALUES (1, '_french_')")
                    conn.execute("INSERT INTO youtube_video_tags VALUES (1, 1)")
                    conn.commit()

                response = app_module.app.test_client().get("/youtube")
                page = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertIn('class="youtube-tag-nav"', page)
                self.assertIn("_FRENCH_", page)
                self.assertIn("1 SOURCES", page)
                self.assertIn("1 ITEMS", page)
                self.assertIn("YOUTUBE UTILITIES", page)
                self.assertNotIn('<span class="label">SEARCH</span>', page)
                self.assertNotIn("youtube-latest-video", page)
                self.assertNotIn(">Latest linked video</a>", page)
                self.assertNotIn('<div class="youtube-tags">', page)

                filtered_response = app_module.app.test_client().get(
                    "/youtube?tag=_FRENCH_&tag=CAR"
                )
                filtered_page = filtered_response.get_data(as_text=True)
                self.assertIn("TAGS: _FRENCH_ + CAR", filtered_page)
                self.assertIn("_FRENCH_ ×", filtered_page)

    def test_video_watch_list_and_contextual_tag_choices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "youtube.sqlite3"
            with patch.object(app_module, "YOUTUBE_DB_PATH", database_path):
                with app_module.get_youtube_db() as conn:
                    conn.execute(
                        """
                        INSERT INTO youtube_sources
                            (id, name, alias, source_url, thumbnail_url, created_at, updated_at)
                        VALUES
                            (1, 'Work Channel', '', '', '', '2026-01-01', '2026-01-01'),
                            (2, 'Ice Channel', '', '', '', '2026-01-01', '2026-01-01')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO youtube_videos
                            (id, source_id, video_id, url, title, thumbnail_url, notes, created_at, updated_at)
                        VALUES
                            (1, 1, 'jobvideo1', 'https://example/job', 'Job Video', 'job.jpg', '', '2026-01-03', '2026-01-03'),
                            (2, 1, 'funvideo2', 'https://example/fun', 'Fun Video', 'fun.jpg', '', '2026-01-02', '2026-01-02'),
                            (3, 2, 'icevideo3', 'https://example/ice', 'Ice Video', 'ice.jpg', '', '2026-01-01', '2026-01-01')
                        """
                    )
                    conn.executemany(
                        "INSERT INTO youtube_tags (id, name) VALUES (?, ?)",
                        [(1, '_QUE_'), (2, '_JOB_'), (3, '_FUN_'), (4, '_ICE_')],
                    )
                    conn.executemany(
                        "INSERT INTO youtube_source_tags VALUES (?, ?)",
                        [(1, 1), (2, 4)],
                    )
                    conn.executemany(
                        "INSERT INTO youtube_video_tags VALUES (?, ?)",
                        [(1, 2), (2, 3)],
                    )
                    conn.commit()

                items = get_youtube_items(selected_tags=["_QUE_", "_JOB_"])
                self.assertEqual([item["title"] for item in items], ["Job Video"])

                client = app_module.app.test_client()
                que_page = client.get("/youtube?view=items&tag=_QUE_").get_data(as_text=True)
                self.assertIn("_JOB_", que_page)
                self.assertIn("_FUN_", que_page)
                self.assertNotIn("_ICE_", que_page)

                job_page = client.get(
                    "/youtube?view=items&tag=_QUE_&tag=_JOB_"
                ).get_data(as_text=True)
                self.assertIn("WATCH LIST", job_page)
                self.assertIn("Job Video", job_page)
                self.assertNotIn("Fun Video", job_page)
                self.assertNotIn("_FUN_", job_page)

                ice_page = client.get("/youtube?view=items&tag=_ICE_").get_data(as_text=True)
                self.assertIn("_ICE_ ×", ice_page)
                self.assertNotIn("_JOB_", ice_page)
                self.assertNotIn("_FUN_", ice_page)

                stale_page = client.get("/youtube?view=items&tag=_MISSING_").get_data(as_text=True)
                self.assertIn("_MISSING_ ×", stale_page)
                self.assertNotIn("_JOB_", stale_page)
