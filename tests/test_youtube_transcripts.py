import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest import TestCase
from unittest.mock import Mock, patch

import app as app_module
from scripts.youtube_transcripts import (
    TranscriptRequestError,
    YouTubeTranscriptClient,
    request_error,
    run_worker,
)


def worker_response(document=None, *, error="", kind="connection"):
    payload = (
        {"ok": False, "error": error, "kind": kind}
        if error else {"ok": True, "document": document}
    )
    return subprocess.CompletedProcess([], 0, json.dumps(payload), "")


class TranscriptConnectionTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dotenv_path = Path(self.temp.name) / ".env"
        self.dotenv_path.write_text("WEBSHARE_USER=test-user\nWEBSHARE_PASSWORD=test-secret\n")
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @patch("scripts.youtube_transcripts.subprocess.run")
    def test_working_direct_connection_does_not_use_configured_proxy(self, run):
        run.return_value = worker_response({"available_languages": [{"code": "en"}]})
        client = YouTubeTranscriptClient(self.dotenv_path)

        result = client.probe("ZfV5G5EsJa8", include_metadata=False)

        self.assertEqual(result["available_languages"][0]["code"], "en")
        self.assertEqual(run.call_count, 1)
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertFalse(payload["use_proxy"])
        self.assertFalse(payload["include_metadata"])
        self.assertFalse(client.using_proxy)
        self.assertNotIn("test-secret", str(run.call_args))

    @patch("scripts.youtube_transcripts.subprocess.run")
    def test_youtube_block_uses_proxy_fallback(self, run):
        run.side_effect = [
            worker_response(error="YouTube blocked the direct connection.", kind="blocked"),
            worker_response({"cleaned_text": "English transcript", "language_code": "en"}),
        ]
        client = YouTubeTranscriptClient(self.dotenv_path)

        result = client.fetch("ZfV5G5EsJa8", "en", include_metadata=False)

        self.assertEqual(result["language_code"], "en")
        self.assertTrue(client.using_proxy)
        payloads = [json.loads(call.kwargs["input"]) for call in run.call_args_list]
        self.assertEqual([payload["use_proxy"] for payload in payloads], [False, True])
        self.assertTrue(all(payload["language_code"] == "en" for payload in payloads))

    @patch("scripts.youtube_transcripts.subprocess.run")
    def test_timed_out_direct_connection_can_still_use_proxy(self, run):
        run.side_effect = [subprocess.TimeoutExpired([], 15), worker_response({"video_id": "video001"})]
        client = YouTubeTranscriptClient(self.dotenv_path)

        self.assertEqual(client.probe("video001")["video_id"], "video001")
        self.assertTrue(client.using_proxy)

    @patch("scripts.youtube_transcripts.subprocess.run")
    def test_unavailable_video_does_not_repeat_request_through_proxy(self, run):
        run.return_value = worker_response(error="No transcript tracks.", kind="unavailable")
        with self.assertRaisesRegex(TranscriptRequestError, "No transcript tracks"):
            YouTubeTranscriptClient(self.dotenv_path).probe("video001")
        self.assertEqual(run.call_count, 1)

    @patch("scripts.youtube_transcripts.subprocess.run")
    def test_failed_fallback_reports_both_connections_without_worker_output(self, run):
        run.side_effect = [
            worker_response(error="Direct request blocked.", kind="blocked"),
            subprocess.CompletedProcess([], 1, "test-secret", "test-secret"),
        ]
        with self.assertRaises(TranscriptRequestError) as caught:
            YouTubeTranscriptClient(self.dotenv_path).probe("video001")
        self.assertIn("Direct request blocked", str(caught.exception))
        self.assertIn("Proxy fallback failed", str(caught.exception))
        self.assertNotIn("test-secret", str(caught.exception))

    def test_stalled_worker_is_terminated_within_deadline(self):
        actual_run = subprocess.run

        def stalled_worker(command, **kwargs):
            return actual_run([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

        client = YouTubeTranscriptClient(self.dotenv_path, timeout=0.1)
        client.proxy_available = False
        started = time.monotonic()
        with patch("scripts.youtube_transcripts.subprocess.run", side_effect=stalled_worker):
            with self.assertRaisesRegex(TranscriptRequestError, "timed out"):
                client.probe("video001")
        self.assertLess(time.monotonic() - started, 2)

    def test_wrapped_proxy_error_does_not_leak_credentials(self):
        from requests.exceptions import ProxyError
        from yt_transcripts import NoTranscripts

        error = NoTranscripts("Failed via http://user:test-secret@proxy", "video001")
        error.__cause__ = ProxyError("http://user:test-secret@proxy")
        result = request_error(error, use_proxy=True)
        self.assertEqual(result["kind"], "connection")
        self.assertIn("Webshare", result["error"])
        self.assertNotIn("test-secret", result["error"])

    @patch("yt_transcripts.TranscriptClient")
    def test_multiple_generated_languages_require_a_choice(self, client_class):
        client_class.return_value.probe.return_value = {
            "available_languages": [
                {"code": "ar", "is_generated": True},
                {"code": "en", "is_generated": True},
            ],
            "recommended_language": "ar",
            "recommended_reason": "spoken-audio",
            "ambiguous": False,
        }
        result = run_worker({
            "operation": "probe", "video_id": "ZfV5G5EsJa8", "use_proxy": False,
            "dotenv_path": str(self.dotenv_path), "include_metadata": False,
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["document"]["ambiguous"])
        self.assertEqual(result["document"]["recommended_language"], "")
        self.assertEqual(client_class.call_args.kwargs["proxy_username"], "")

    @patch("yt_transcripts.TranscriptClient")
    def test_empty_transcript_is_not_treated_as_success(self, client_class):
        client_class.return_value.fetch.return_value = {"cleaned_text": "  "}
        result = run_worker({
            "operation": "fetch", "video_id": "video001", "language_code": "en",
            "use_proxy": False, "dotenv_path": str(self.dotenv_path), "include_metadata": False,
        })
        self.assertFalse(result["ok"])
        self.assertIn("empty transcript", result["error"])


class TranscriptRouteTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name, value in (("YOUTUBE_DB_PATH", self.root / "youtube.sqlite3"), ("MARKDOWN_DIR", self.root)):
            patcher = patch.object(app_module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with app_module.get_youtube_db() as conn:
            conn.execute("""
                INSERT INTO youtube_sources (id, name, created_at, updated_at)
                VALUES (1, 'Talk Python', '2026-10-31', '2026-10-31')
            """)
            conn.execute("""
                INSERT INTO youtube_videos (id, source_id, video_id, url, title, created_at, updated_at)
                VALUES (1, 1, 'ZfV5G5EsJa8', 'https://www.youtube.com/watch?v=ZfV5G5EsJa8',
                        'Personal AI Agents', '2026-10-31', '2026-10-31')
            """)
            conn.commit()
        self.client = app_module.app.test_client()
        self.transcripts = Mock(using_proxy=False)
        patcher = patch.object(app_module, "transcript_client", return_value=self.transcripts)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_probe_timeout_displays_error_and_retry_link(self):
        self.transcripts.probe.side_effect = TranscriptRequestError("Direct connection timed out.", "timeout")
        response = self.client.get("/youtube/video/1/transcript")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Direct connection timed out", page)
        self.assertIn("RETRY / CHOOSE LANGUAGE", page)
        self.assertIn("OPEN ITEM", page)

    def test_fetch_failure_does_not_start_another_network_probe(self):
        self.transcripts.fetch.side_effect = TranscriptRequestError("Proxy timed out.", "timeout")
        response = self.client.post("/youtube/video/1/transcript", data={"language_code": "en"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Proxy timed out", response.get_data(as_text=True))
        self.transcripts.probe.assert_not_called()
        self.assertEqual(app_module.get_youtube_transcripts(1), [])

    def test_english_fetch_saves_document_and_reuses_it_on_next_click(self):
        self.transcripts.fetch.return_value = {
            "language_code": "en", "language_name": "English", "is_generated": True,
            "cleaned_text": "Hey Jeff. Hey Michael.", "segment_count": 2,
            "fetched_at": "2026-10-31T12:00:00+00:00",
        }
        response = self.client.post("/youtube/video/1/transcript", data={"language_code": "en"})
        self.assertEqual(response.status_code, 302)
        self.transcripts.fetch.assert_called_once_with("ZfV5G5EsJa8", "en", include_metadata=False)
        record = app_module.get_youtube_transcripts(1)[0]
        self.assertEqual(record["language_code"], "en")
        self.assertIn("Hey Jeff. Hey Michael.", (self.root / record["markdown_rel_path"]).read_text())

        saved = self.client.get("/youtube/video/1/transcript")
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(saved.location, response.location)
        self.transcripts.probe.assert_not_called()
