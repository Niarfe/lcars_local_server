from contextlib import closing
from html import unescape
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app as app_module


class YouTubeLibraryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database_patch = patch.object(app_module, "YOUTUBE_DB_PATH", Path(temporary.name) / "youtube.sqlite3")
        database_patch.start()
        self.addCleanup(database_patch.stop)
        with closing(app_module.get_youtube_db()) as conn:
            conn.executemany(
                "INSERT INTO youtube_sources (id, name, created_at, updated_at) VALUES (?, ?, '2026-01-01', '2026-01-01')",
                [(1, "French channel"), (2, "Mixed channel"), (3, "Music channel"), (4, "Inbox"), (5, "Empty source")],
            )
            videos = [
                (1, 1, "Simple French"), (2, 1, "Advanced French"),
                (3, 2, "French lesson"), (4, 2, "English coaching"),
                (5, 3, "Moonlight Sonata"), (6, 3, "Classical ensemble"),
                (7, 3, "Ambient loop"), (8, 3, "Musician interview"),
                (9, 4, "Unsorted capture"), (10, 3, "Pianola recording"),
            ]
            conn.executemany(
                """INSERT INTO youtube_videos
                   (id, source_id, video_id, url, title, thumbnail_url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, '2026-01-01', ?)""",
                [(video_id, source_id, f"video{video_id:06}", f"https://example/video{video_id}", title,
                  f"thumb{video_id}.jpg", f"2026-01-{video_id:02}") for video_id, source_id, title in videos],
            )
            tags = ["FRENCH", "FRENCH_BLITZ", "MUSIC-CLASSICAL-PIANO", "MUSIC-CLASSICAL",
                    "MUSIC-BG", "MUSICIAN", "RELAXATION", "WORK", "MUSIC-CLASSICAL-PIANOLA", "ARCHIVE"]
            conn.executemany("INSERT INTO youtube_tags (id, name) VALUES (?, ?)", enumerate(tags, 1))
            conn.executemany("INSERT INTO youtube_source_tags VALUES (?, ?)", [(1, 1), (5, 10)])
            conn.executemany("INSERT INTO youtube_video_tags VALUES (?, ?)", [
                (1, 1), (1, 2), (3, 1), (3, 2), (4, 8),
                (5, 3), (5, 4), (5, 7), (6, 4), (7, 5), (8, 6), (10, 9),
            ])
            conn.commit()
        self.client = app_module.app.test_client()

    def item_ids(self, **kwargs: object) -> set[int]:
        return {item["id"] for item in app_module.get_youtube_items(**kwargs)}

    def test_hierarchy_uses_dash_boundaries_and_keeps_underscores(self) -> None:
        self.assertEqual(self.item_ids(selected_tags="music"), {5, 6, 7, 10})
        self.assertEqual(self.item_ids(selected_tags="MUSIC-CLASSICAL"), {5, 6, 10})
        self.assertEqual(self.item_ids(selected_tags="MUSIC-CLASSICAL-PIANO"), {5})
        self.assertEqual(self.item_ids(selected_tags="french"), {1, 2, 3})
        self.assertEqual(self.item_ids(selected_tags="FRENCH_BLITZ"), {1, 3})
        self.assertEqual(app_module.youtube_tag_paths("SELF_HELP"), ["SELF_HELP"])
        self.assertEqual(app_module.youtube_tag_paths("SELF-HELP"), ["SELF", "SELF-HELP"])
        self.assertFalse(app_module.youtube_tag_matches("FRENCH_BLITZ", "FRENCH"))

    def test_source_inheritance_is_additive_and_deduplicated(self) -> None:
        items = {item["id"]: item for item in app_module.get_youtube_items()}
        self.assertEqual(items[1]["tags"], ["FRENCH", "FRENCH_BLITZ"])
        self.assertEqual(items[2]["tags"], ["FRENCH"])
        self.assertEqual(items[3]["source_tags"], [])
        self.assertEqual(items[4]["tags"], ["WORK"])
        self.assertEqual(self.item_ids(selected_tags=["FRENCH", "FRENCH_BLITZ"]), {1, 3})

    def test_sources_group_the_same_matches_as_video_view(self) -> None:
        sources = app_module.get_youtube_sources(selected_tags="MUSIC-CLASSICAL-PIANO")
        self.assertEqual([source["id"] for source in sources], [3])
        self.assertEqual(sources[0]["matching_count"], 1)
        self.assertEqual(sources[0]["video_count"], 5)
        self.assertEqual(sources[0]["video_titles"], ["Moonlight Sonata"])
        self.assertEqual(sources[0]["thumbnail_url"], "thumb5.jpg")
        # A source must not combine tags or search terms from different videos.
        self.assertEqual(app_module.get_youtube_sources(selected_tags=["FRENCH", "WORK"]), [])
        self.assertEqual(app_module.get_youtube_sources(query="coaching", selected_tags="FRENCH"), [])
        self.assertEqual(self.item_ids(query="sonata", selected_tags="MUSIC"), {5})

    def test_tree_counts_unique_videos_and_keeps_zero_count_branches(self) -> None:
        with app_module.app.test_request_context("/youtube?tag=MUSIC-CLASSICAL-PIANO"):
            context = app_module.youtube_browse_context()
        roots = {node["path"]: node for node in context["tag_tree"]}
        self.assertEqual(roots["MUSIC"]["count"], 4)
        self.assertTrue(roots["MUSIC"]["open"])
        classical = next(node for node in roots["MUSIC"]["children"] if node["label"] == "CLASSICAL")
        self.assertEqual(classical["count"], 3)
        self.assertTrue(classical["open"])
        self.assertIn("FRENCH_BLITZ", roots)
        self.assertEqual(roots["ARCHIVE"]["count"], 0)
        self.assertEqual(context["untagged_count"], 1)
        self.assertEqual(context["matching_video_count"], 1)

        with app_module.app.test_request_context("/youtube?q=sonata&tag=MUSIC"):
            context = app_module.youtube_browse_context()
        roots = {node["path"]: node for node in context["tag_tree"]}
        self.assertEqual(roots["MUSIC"]["count"], 1)
        self.assertEqual(roots["FRENCH"]["count"], 0)

    def test_navigation_replaces_branch_and_preserves_search_and_view(self) -> None:
        response = self.client.get("/youtube?view=items&tag=MUSIC-CLASSICAL-PIANO&q=sonata")
        self.assertEqual(response.status_code, 200)
        page = unescape(response.get_data(as_text=True))
        self.assertIn('href="/youtube?q=sonata&view=items&tag=MUSIC-BG"', page)
        self.assertIn('href="/youtube?q=sonata&tag=MUSIC-CLASSICAL-PIANO"', page)
        self.assertIn('href="/youtube?view=items&tag=MUSIC-CLASSICAL-PIANO"', page)
        self.assertIn('name="tag" type="hidden" value="MUSIC-CLASSICAL-PIANO"', page)
        self.assertIn('data-youtube-tag="FRENCH_BLITZ"', page)
        self.assertIn('>Moonlight Sonata</a>', page)
        self.assertNotIn('>Classical ensemble</a>', page)
        self.assertIn('youtube_sidebar.js', page)

    def test_source_drilldown_and_return_preserve_filters(self) -> None:
        page = self.client.get("/youtube?tag=MUSIC-CLASSICAL-PIANO&q=sonata").get_data(as_text=True)
        self.assertIn('/youtube/source/3?q=sonata&amp;tag=MUSIC-CLASSICAL-PIANO', page)
        self.assertIn('1 MATCHING / 5 SAVED ITEMS', page)
        source_response = self.client.get("/youtube/source/3?tag=MUSIC-CLASSICAL-PIANO&q=sonata")
        self.assertEqual(source_response.status_code, 200)
        source_page = source_response.get_data(as_text=True)
        self.assertIn('>Moonlight Sonata</a>', source_page)
        self.assertNotIn('>Classical ensemble</a>', source_page)
        self.assertIn('href="/youtube?q=sonata&amp;tag=MUSIC-CLASSICAL-PIANO"', source_page)
        self.assertIn('ALL SOURCE VIDEOS', source_page)
        empty_page = self.client.get("/youtube/source/3?tag=FRENCH").get_data(as_text=True)
        self.assertIn('NO MATCHING ITEMS', empty_page)
        self.assertNotIn('DELETE EMPTY SOURCE', empty_page)

    def test_untagged_means_no_direct_or_inherited_tags(self) -> None:
        self.assertEqual(self.item_ids(untagged=True), {9})
        sources = app_module.get_youtube_sources(untagged=True)
        self.assertEqual([source["id"] for source in sources], [4])
        page = self.client.get("/youtube?untagged=1&view=items&q=capture").get_data(as_text=True)
        self.assertIn('>Unsorted capture</a>', page)
        self.assertIn('name="untagged" type="hidden" value="1"', page)
        self.assertIn('href="/youtube?q=capture&amp;untagged=1"', page)

    def test_empty_library_and_unknown_tag_remain_navigable(self) -> None:
        page = self.client.get("/youtube?tag=UNKNOWN-CHILD").get_data(as_text=True)
        self.assertIn('data-youtube-branch="UNKNOWN" open', page)
        self.assertIn('data-youtube-tag="UNKNOWN-CHILD"', page)
        self.assertIn('NO YOUTUBE SOURCES FOUND', page)
        with closing(app_module.get_youtube_db()) as conn:
            conn.execute("DELETE FROM youtube_sources")
            conn.commit()
        page = self.client.get("/youtube").get_data(as_text=True)
        self.assertIn('NO TAGS YET', page)
        self.assertIn('0 MATCHING VIDEOS', page)
