"""Run caption requests outside Flask so DNS/proxy stalls have a time limit."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ATTEMPT_TIMEOUT = 15
APP_DIR = Path(__file__).resolve().parent.parent


class TranscriptRequestError(RuntimeError):
    def __init__(self, message: str, kind: str = "unavailable") -> None:
        super().__init__(message)
        self.kind = kind


class YouTubeTranscriptClient:
    def __init__(self, dotenv_path: Path, timeout: float = ATTEMPT_TIMEOUT) -> None:
        self.dotenv_path = dotenv_path
        self.timeout = timeout
        self.using_proxy = False
        try:
            from dotenv import dotenv_values
        except ImportError:
            values = {}
        else:
            values = dotenv_values(dotenv_path)
        self.proxy_available = bool(
            os.environ.get("WEBSHARE_USER", values.get("WEBSHARE_USER"))
            and os.environ.get("WEBSHARE_PASSWORD", values.get("WEBSHARE_PASSWORD"))
        )

    def probe(self, video_id: str, include_metadata: bool = True) -> dict[str, Any]:
        return self._request("probe", video_id, include_metadata=include_metadata)

    def fetch(
        self, video_id: str, language_code: str, include_metadata: bool = True
    ) -> dict[str, Any]:
        return self._request(
            "fetch", video_id, language_code=language_code, include_metadata=include_metadata
        )

    def _request(self, operation: str, video_id: str, **kwargs: Any) -> dict[str, Any]:
        direct_error = None
        for use_proxy in ([False, True] if self.proxy_available else [False]):
            self.using_proxy = use_proxy
            try:
                return self._attempt(operation, video_id, use_proxy, **kwargs)
            except TranscriptRequestError as exc:
                if use_proxy:
                    raise TranscriptRequestError(
                        f"{direct_error} Proxy fallback failed: {exc}", exc.kind
                    ) from exc
                if not self.proxy_available or exc.kind not in {"blocked", "connection", "timeout"}:
                    raise
                direct_error = exc
        raise RuntimeError("No transcript connection attempted")

    def _attempt(
        self, operation: str, video_id: str, use_proxy: bool, **kwargs: Any
    ) -> dict[str, Any]:
        payload = {
            "operation": operation,
            "video_id": video_id,
            "use_proxy": use_proxy,
            "dotenv_path": str(self.dotenv_path),
            **kwargs,
        }
        connection = "proxy" if use_proxy else "direct connection"
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "scripts.youtube_transcripts", "--worker"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=APP_DIR,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TranscriptRequestError(
                f"The transcript {connection} timed out after {self.timeout:g} seconds. "
                "Please try again or open the transcript on YouTube.",
                "timeout",
            ) from exc
        try:
            result = json.loads(completed.stdout) if completed.returncode == 0 else {}
        except ValueError:
            result = {}
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            # Do not display subprocess output: network errors can contain credentials.
            raise TranscriptRequestError("The transcript worker could not complete the request.")
        if not result["ok"]:
            raise TranscriptRequestError(result["error"], result["kind"])
        return result["document"]


def request_error(error: Exception, use_proxy: bool) -> dict[str, Any]:
    """Classify wrapped errors without exposing proxy URLs or credentials."""
    from requests.exceptions import ConnectionError, Timeout
    from yt_transcripts import Blocked, LanguageUnavailable, NoTranscripts

    chain = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__

    connection = "proxy" if use_proxy else "direct connection"
    if any(isinstance(item, Timeout) for item in chain):
        kind, message = "timeout", f"The transcript {connection} timed out. Please try again."
    elif any(isinstance(item, Blocked) for item in chain):
        kind, message = "blocked", f"YouTube blocked the transcript {connection}."
    elif any(isinstance(item, ConnectionError) for item in chain):
        kind = "connection"
        message = f"The transcript {connection} could not connect."
        if use_proxy:
            message += " Check the Webshare proxy settings and connection."
    elif isinstance(error, LanguageUnavailable):
        kind, message = "language", "The selected transcript language is no longer available. Choose another track."
    elif isinstance(error, NoTranscripts):
        kind, message = "unavailable", "YouTube did not return transcript tracks for this video."
    else:
        kind, message = "unavailable", "YouTube could not return the requested transcript. Please try again."
    return {"ok": False, "kind": kind, "error": message}


def run_worker(payload: dict[str, Any]) -> dict[str, Any]:
    from yt_transcripts import TranscriptClient

    use_proxy = bool(payload["use_proxy"])
    options = {} if use_proxy else {"proxy_username": "", "proxy_password": ""}
    try:
        client = TranscriptClient(dotenv_path=payload["dotenv_path"], **options)
        kwargs = {"include_metadata": payload["include_metadata"]}
        if payload["operation"] == "fetch":
            document = client.fetch(payload["video_id"], payload["language_code"], **kwargs)
            if not str(document.get("cleaned_text") or "").strip():
                return {"ok": False, "kind": "unavailable", "error": "YouTube returned an empty transcript. Please try again."}
        else:
            document = client.probe(payload["video_id"], **kwargs)
            generated_codes = {
                track["code"] for track in document.get("available_languages", [])
                if track.get("is_generated")
            }
            # Dubbed videos can expose many generated tracks; listing order does
            # not identify the original audio language in that case.
            if len(generated_codes) > 1:
                document.update(ambiguous=True, recommended_language="", recommended_reason="multiple-generated-tracks")
        return {"ok": True, "document": document}
    except Exception as exc:
        return request_error(exc, use_proxy)


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("This module is an internal transcript worker.")
    print(json.dumps(run_worker(json.load(sys.stdin))))
