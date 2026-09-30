from __future__ import annotations

import json
import os
import platform
import socket
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from html import escape
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

import markdown as mdlib
import psutil

try:
    import boto3
except ImportError:
    boto3 = None
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from jupyter_server.serverapp import list_running_servers

app = Flask(__name__)
BASE_DIR = Path.home()
APP_DIR = Path(__file__).parent
CONTENT_CONFIG_PATH = APP_DIR / "content_config.json"
AWS_CONFIG_PATH = APP_DIR / "aws_servers.json"
REMOTE_CONFIG_PATH = APP_DIR / "remote_jupyter_servers.json"
S3_LIBRARY_CONFIG_PATH = APP_DIR / "s3_library.local.json"
S3_LIBRARY_CATALOG_PATH = APP_DIR / "s3_library_catalog.json"
S3_LIBRARY_DOTENV_PATH = APP_DIR / ".env"


def expand_content_path(raw_path: str | Path, fallback: Path) -> Path:
    if not raw_path:
        return fallback
    raw_text = str(raw_path).strip()
    if not raw_text:
        return fallback
    return Path(raw_text).expanduser().resolve()


def load_content_config() -> dict[str, str]:
    default_config = {
        "markdown_dir": str(APP_DIR / "markdown"),
        "books_dir": str(APP_DIR / "books"),
        "sounds_dir": str(APP_DIR / "static" / "sounds"),
    }

    if not CONTENT_CONFIG_PATH.exists():
        CONTENT_CONFIG_PATH.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
        return default_config

    try:
        raw = json.loads(CONTENT_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_config

    if not isinstance(raw, dict):
        return default_config

    return {
        "markdown_dir": str(raw.get("markdown_dir") or default_config["markdown_dir"]),
        "books_dir": str(raw.get("books_dir") or default_config["books_dir"]),
        "sounds_dir": str(raw.get("sounds_dir") or default_config["sounds_dir"]),
    }


CONTENT_CONFIG = load_content_config()
BOOKS_DIR = expand_content_path(CONTENT_CONFIG.get("books_dir", ""), APP_DIR / "books")
MARKDOWN_DIR = expand_content_path(CONTENT_CONFIG.get("markdown_dir", ""), APP_DIR / "markdown")
SOUNDS_DIR = expand_content_path(CONTENT_CONFIG.get("sounds_dir", ""), APP_DIR / "static" / "sounds")
ARCHIVE_DIR = MARKDOWN_DIR.parent / "archive"

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "toc", "sane_lists", "codehilite"]
MARKDOWN_EXTENSION_CONFIGS = {
    "codehilite": {
        "guess_lang": False,
        "noclasses": False,
        "use_pygments": True,
    }
}
MERMAID_FENCE_RE = re.compile(
    r"(?ms)(^|\n)(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*)\n"
    r"(?P<body>.*?)(?:\n(?P=fence)[ \t]*(?=\n|$))"
)
MARKDOWN_FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
MARKDOWN_PAGE_BREAK_RE = re.compile(
    r"^\s*(?:-{3,}\s*(?:page|pagebreak|page-break)\s*-{3,}|"
    r"<!--\s*(?:pagebreak|page-break|page break)\s*-->)\s*$",
    re.IGNORECASE,
)


def ensure_content_dirs() -> None:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)


ensure_content_dirs()
LINKS_CONFIG_PATH = APP_DIR / "links.json"
FOCUS_CONFIG_PATH = APP_DIR / "focus_config.json"
YOUTUBE_DB_PATH = APP_DIR / "youtube_library.sqlite3"
YOUTUBE_DOTENV_PATH = APP_DIR / ".env"
YOUTUBE_INBOX_SOURCE = "YouTube Inbox"
YOUTUBE_VIDEO_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com"}
YOUTUBE_DIRECT_VIDEO_PATHS = {"shorts", "embed", "live", "v"}
YOUTUBE_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{6,}")

ALLOWED_ACTIONS: dict[str, list[str]] = {
    "open_documents": ["open", str(BASE_DIR / "Documents")],
    "open_downloads": ["open", str(BASE_DIR / "Downloads")],
    "list_home": ["ls", "-la", str(BASE_DIR)],
}

def safe_path(raw_path: str) -> Path:
    candidate = (
        (BASE_DIR / raw_path).expanduser().resolve()
        if not raw_path.startswith("/")
        else Path(raw_path).expanduser().resolve()
    )
    if not str(candidate).startswith(str(BASE_DIR)):
        raise ValueError("Path must stay within the home directory")
    return candidate

def get_system_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": {
            "platform": platform.system(),
            "release": platform.release(),
            "hostname": platform.node(),
        },
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "cwd": os.getcwd(),
    }

def get_directory_listing(raw_path: str = "") -> dict[str, Any]:
    try:
        target = safe_path(raw_path) if raw_path else BASE_DIR
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists():
        return {"ok": False, "error": "Path does not exist"}

    if not target.is_dir():
        return {"ok": False, "error": "Path is not a directory"}

    items: list[dict[str, str]] = []
    for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        items.append(
            {
                "name": entry.name,
                "path": str(entry),
                "type": "dir" if entry.is_dir() else "file",
            }
        )

    return {"ok": True, "base": str(target), "items": items}

def port_open(host: str, port: int, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def get_local_jupyter_servers() -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    for server in list_running_servers():
        base_url = server.get("url", "")
        token = server.get("token", "")
        full_url = f"{base_url}?token={token}" if token and "token=" not in base_url else base_url
        servers.append(
            {
                "url": full_url,
                "base_url": base_url,
                "token_present": bool(token),
                "root_dir": server.get("root_dir") or server.get("notebook_dir") or "",
                "port": server.get("port"),
                "hostname": server.get("hostname"),
                "pid": server.get("pid"),
                "is_remote": False,
                "remote_status": "LOCAL",
                "label": "",
                "name": "",
            }
        )
    return servers

def get_remote_jupyter_servers() -> list[dict[str, Any]]:
    if not REMOTE_CONFIG_PATH.exists():
        return []

    try:
        raw = json.loads(REMOTE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    servers: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        host = str(item.get("host", "")).strip()
        port = item.get("port")
        protocol = str(item.get("protocol", "http")).strip() or "http"

        try:
            port_int = int(port)
        except (TypeError, ValueError):
            continue

        if not host:
            continue

        url = f"{protocol}://{host}:{port_int}"
        status = "UP" if port_open(host, port_int) else "DOWN"

        servers.append(
            {
                "url": url,
                "base_url": url,
                "token_present": False,
                "root_dir": str(item.get("label") or item.get("name") or f"{host}:{port_int}"),
                "port": port_int,
                "hostname": host,
                "pid": "REMOTE",
                "is_remote": True,
                "remote_status": status,
                "label": str(item.get("label", "")).strip(),
                "name": str(item.get("name", "")).strip(),
            }
        )
    return servers

def get_all_jupyter_servers() -> list[dict[str, Any]]:
    return get_local_jupyter_servers() + get_remote_jupyter_servers()


def path_title(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ")
    title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    for acronym in ("LCARS", "AWS", "S3", "PDF", "API", "URL", "HTM", "AI"):
        title = re.sub(rf"\b{acronym}(?=[A-Z])", f"{acronym} ", title)
    words = re.sub(r"\s+", " ", title).strip().split(" ")
    return " ".join(word if word.isupper() else word.capitalize() for word in words)


def relative_path_if_inside(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def get_books() -> list[dict[str, str]]:
    BOOKS_DIR.mkdir(exist_ok=True)
    books = []
    for p in sorted(BOOKS_DIR.rglob("*.txt"), key=lambda x: x.name.lower()):
        rel = p.relative_to(BOOKS_DIR).as_posix()
        title = path_title(p)
        books.append({"id": rel, "name": title, "path": rel})
    return books


def s3_library_config_path() -> Path:
    raw_path = os.environ.get("S3_LIBRARY_CONFIG_PATH", str(S3_LIBRARY_CONFIG_PATH))
    return Path(raw_path).expanduser().resolve()


def s3_library_catalog_path() -> Path:
    raw_path = os.environ.get("S3_LIBRARY_CATALOG_PATH", str(S3_LIBRARY_CATALOG_PATH))
    return Path(raw_path).expanduser().resolve()


def load_s3_library_config() -> dict[str, str]:
    config = {
        "bucket": "",
        "region": "us-east-1",
        "prefix": "",
        "cache_dir": str(BOOKS_DIR / "s3_pdfs"),
    }
    config_path = s3_library_config_path()

    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}

        if isinstance(raw, dict):
            config["bucket"] = str(raw.get("bucket") or raw.get("s3_bucket") or "").strip()
            config["region"] = str(raw.get("region") or raw.get("s3_region") or config["region"]).strip()
            config["prefix"] = str(raw.get("prefix") or raw.get("s3_prefix") or "").strip()
            config["cache_dir"] = str(
                raw.get("cache_dir")
                or raw.get("s3_book_cache_dir")
                or config["cache_dir"]
            ).strip()

    dotenv_values = load_s3_dotenv_config()
    config["bucket"] = str(dotenv_values.get("S3_BUCKET") or config["bucket"]).strip()
    config["region"] = str(dotenv_values.get("S3_REGION") or config["region"] or "us-east-1").strip()
    config["prefix"] = str(dotenv_values.get("S3_PREFIX") or config["prefix"]).strip()
    config["cache_dir"] = str(dotenv_values.get("S3_BOOK_CACHE_DIR") or config["cache_dir"]).strip()

    config["bucket"] = str(os.environ.get("S3_BUCKET") or config["bucket"]).strip()
    config["region"] = str(os.environ.get("S3_REGION") or config["region"] or "us-east-1").strip()
    config["prefix"] = str(os.environ.get("S3_PREFIX") or config["prefix"]).strip().strip("/")
    config["cache_dir"] = str(os.environ.get("S3_BOOK_CACHE_DIR") or config["cache_dir"]).strip()
    return config


def load_s3_dotenv_config() -> dict[str, str]:
    dotenv_path = Path(
        os.environ.get("S3_LIBRARY_DOTENV_PATH", str(S3_LIBRARY_DOTENV_PATH))
    ).expanduser().resolve()
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        if clean_key.startswith("export "):
            clean_key = clean_key.removeprefix("export ").strip()
        if clean_key not in {"S3_BUCKET", "S3_REGION", "S3_PREFIX", "S3_BOOK_CACHE_DIR"}:
            continue
        values[clean_key] = value.strip().strip('"').strip("'")
    return values


def s3_library_status() -> dict[str, Any]:
    config = load_s3_library_config()
    dotenv_path = Path(
        os.environ.get("S3_LIBRARY_DOTENV_PATH", str(S3_LIBRARY_DOTENV_PATH))
    ).expanduser().resolve()
    missing = [
        label
        for label, value in (
            ("S3_BUCKET", config["bucket"]),
            ("S3_REGION", config["region"]),
            ("S3_PREFIX", config["prefix"]),
        )
        if not value
    ]
    return {
        "configured": not missing,
        "missing": missing,
        "config_path": str(s3_library_config_path()),
        "config_exists": s3_library_config_path().exists(),
        "dotenv_path": str(dotenv_path),
        "catalog_path": str(s3_library_catalog_path()),
        "catalog_exists": s3_library_catalog_path().exists(),
        "cache_dir": str(s3_book_cache_dir()),
    }


def s3_book_slug(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9._:-]+", "-", cleaned)
    cleaned = cleaned.strip("-._:")
    return cleaned or "book"


def clean_s3_catalog_filename(raw_filename: str) -> str:
    filename = raw_filename.strip().replace("\\", "/")
    parts = [part for part in filename.split("/") if part]
    if not filename or filename.startswith("/") or any(part in {".", ".."} for part in parts):
        raise ValueError("Invalid S3 catalog filename")
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF catalog entries are supported")
    return "/".join(parts)


def normalize_s3_book_entry(
    raw_entry: Any,
    index: int,
    used_ids: set[str],
) -> dict[str, Any] | None:
    if isinstance(raw_entry, str):
        raw_filename = raw_entry
        raw_title = ""
        raw_id = ""
        raw_category = ""
    elif isinstance(raw_entry, dict):
        raw_filename = str(
            raw_entry.get("filename")
            or raw_entry.get("path")
            or raw_entry.get("key")
            or ""
        )
        raw_title = str(raw_entry.get("title") or raw_entry.get("name") or "").strip()
        raw_id = str(raw_entry.get("id") or "").strip()
        raw_category = str(raw_entry.get("category") or raw_entry.get("section") or "").strip()
    else:
        return None

    try:
        filename = clean_s3_catalog_filename(raw_filename)
    except ValueError:
        return None

    title = raw_title or Path(filename).stem.replace("_", " ").replace("-", " ").title()

    base_id = s3_book_slug(raw_id or title or filename or f"book-{index + 1}")
    book_id = base_id
    counter = 2
    while book_id in used_ids:
        book_id = f"{base_id}-{counter}"
        counter += 1
    used_ids.add(book_id)

    return {
        "id": book_id,
        "name": title,
        "title": title,
        "filename": filename,
        "path": filename,
        "category": raw_category,
        "source": "s3",
    }


def s3_book_cache_dir() -> Path:
    config = load_s3_library_config()
    return expand_content_path(config.get("cache_dir", ""), BOOKS_DIR / "s3_pdfs")


def s3_book_cache_path(book: dict[str, Any]) -> Path:
    filename = clean_s3_catalog_filename(str(book.get("filename") or ""))
    cache_root = s3_book_cache_dir().resolve()
    cache_path = (cache_root / filename).resolve()
    try:
        cache_path.relative_to(cache_root)
    except ValueError as exc:
        raise ValueError("Invalid S3 book cache path") from exc
    return cache_path


def add_s3_book_cache_fields(book: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(book)
    try:
        cache_path = s3_book_cache_path(book)
        cached = cache_path.exists() and cache_path.stat().st_size > 0
    except (OSError, ValueError):
        cache_path = Path("")
        cached = False
    enriched["cached"] = cached
    enriched["cache_path"] = str(cache_path) if cache_path else ""
    return enriched


def get_s3_books() -> list[dict[str, Any]]:
    catalog_path = s3_library_catalog_path()
    if not catalog_path.exists():
        return []

    try:
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    raw_books = raw.get("books", []) if isinstance(raw, dict) else raw
    if not isinstance(raw_books, list):
        return []

    used_ids: set[str] = set()
    books = [
        book
        for index, raw_entry in enumerate(raw_books)
        if (book := normalize_s3_book_entry(raw_entry, index, used_ids)) is not None
    ]
    return [
        add_s3_book_cache_fields(book)
        for book in sorted(books, key=lambda book: (book["category"].lower(), book["name"].lower()))
    ]


def get_local_pdfs() -> list[dict[str, str]]:
    BOOKS_DIR.mkdir(exist_ok=True)
    cache_root = s3_book_cache_dir().resolve()
    cataloged_cache_paths = {
        str(book.get("filename") or "")
        for book in get_s3_books()
        if book.get("filename")
    }

    pdfs: list[dict[str, str]] = []
    seen_paths: set[Path] = set()

    def add_pdf(path: Path, root: Path) -> None:
        resolved = path.resolve()
        if resolved in seen_paths:
            return

        cache_rel = relative_path_if_inside(resolved, cache_root)
        if cache_rel and cache_rel in cataloged_cache_paths:
            return

        rel = relative_path_if_inside(resolved, root)
        if not rel:
            return

        seen_paths.add(resolved)
        pdfs.append({
            "id": rel,
            "name": path_title(path),
            "path": rel,
            "location": "S3 CACHE" if cache_rel else "BOOKS",
        })

    if BOOKS_DIR.exists():
        for path in sorted(BOOKS_DIR.rglob("*.pdf"), key=lambda item: item.name.lower()):
            add_pdf(path, BOOKS_DIR)

    if cache_root.exists() and not relative_path_if_inside(cache_root, BOOKS_DIR.resolve()):
        for path in sorted(cache_root.rglob("*.pdf"), key=lambda item: item.name.lower()):
            add_pdf(path, cache_root)

    return sorted(pdfs, key=lambda book: (book["location"].lower(), book["name"].lower()))


def s3_book_by_id(book_id: str) -> dict[str, Any] | None:
    return next((book for book in get_s3_books() if book["id"] == book_id), None)


def quote_s3_key(key: str) -> str:
    return "/".join(quote(part, safe="!$&'()*+,;=:@") for part in key.split("/"))


def build_s3_book_url(filename: str) -> str:
    config = load_s3_library_config()
    missing = [
        label
        for label, value in (
            ("S3_BUCKET", config["bucket"]),
            ("S3_REGION", config["region"]),
            ("S3_PREFIX", config["prefix"]),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"S3 library is missing: {', '.join(missing)}")

    safe_filename = clean_s3_catalog_filename(filename)
    key = f"{config['prefix'].strip('/')}/{safe_filename}"
    return f"https://{config['bucket']}.s3.{config['region']}.amazonaws.com/{quote_s3_key(key)}"


def ensure_s3_book_cached(book: dict[str, Any]) -> dict[str, Any]:
    cache_path = s3_book_cache_path(book)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return {"path": cache_path, "downloaded": False}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_name(f".{cache_path.name}.part")
    request_obj = Request(
        build_s3_book_url(str(book.get("filename") or "")),
        headers={"User-Agent": "LCARS Local Server/1.0"},
    )

    try:
        with urlopen(request_obj, timeout=300) as response:
            with partial_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        partial_path.replace(cache_path)
    except (TimeoutError, URLError, OSError) as exc:
        if partial_path.exists():
            partial_path.unlink()
        raise RuntimeError(f"Download failed: {exc}") from exc

    if not cache_path.exists() or cache_path.stat().st_size <= 0:
        raise RuntimeError("Download failed: empty PDF")

    return {"path": cache_path, "downloaded": True}


def open_local_file(path: Path) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise RuntimeError(f"Could not open local file: {exc}") from exc


def safe_book_path(book_id: str) -> Path:
    candidate = (BOOKS_DIR / book_id).resolve()
    if not str(candidate).startswith(str(BOOKS_DIR.resolve())):
        raise ValueError("Invalid book path")
    if candidate.suffix.lower() != ".txt":
        raise ValueError("Only .txt files are supported")
    return candidate


def safe_local_pdf_path(book_id: str) -> Path:
    clean_id = book_id.strip().replace("\\", "/")
    if not clean_id or clean_id.startswith("/") or "\x00" in clean_id:
        raise ValueError("Invalid PDF path")

    roots = []
    for root in (BOOKS_DIR.resolve(), s3_book_cache_dir().resolve()):
        if root not in roots:
            roots.append(root)

    first_candidate: Path | None = None
    for root in roots:
        candidate = (root / clean_id).resolve()
        if not relative_path_if_inside(candidate, root):
            continue
        if candidate.suffix.lower() != ".pdf":
            raise ValueError("Only .pdf files are supported")
        if candidate.exists():
            return candidate
        if first_candidate is None:
            first_candidate = candidate

    if first_candidate is None:
        raise ValueError("Invalid PDF path")
    return first_candidate


def get_markdown_docs() -> list[dict[str, str]]:
    MARKDOWN_DIR.mkdir(exist_ok=True)
    docs = []
    for p in sorted(MARKDOWN_DIR.rglob("*.md"), key=lambda x: x.name.lower()):
        rel = p.relative_to(MARKDOWN_DIR).as_posix()
        title = p.stem.replace("_", " ").replace("-", " ").title()
        docs.append({"id": rel, "name": title, "path": rel})
    return docs

def safe_markdown_path(doc_id: str) -> Path:
    candidate = (MARKDOWN_DIR / doc_id).resolve()
    if not str(candidate).startswith(str(MARKDOWN_DIR.resolve())):
        raise ValueError("Invalid markdown path")
    if candidate.suffix.lower() != ".md":
        raise ValueError("Only .md files are supported")
    return candidate

def safe_markdown_folder_path(folder_id: str) -> Path:
    folder_id = folder_id.strip("/")
    if not folder_id:
        raise ValueError("Invalid markdown folder")
    candidate = (MARKDOWN_DIR / folder_id).resolve()
    if not str(candidate).startswith(str(MARKDOWN_DIR.resolve())):
        raise ValueError("Invalid markdown folder")
    if not candidate.is_dir():
        raise ValueError("Markdown folder not found")
    return candidate

def safe_markdown_top_folder(folder_id: str) -> tuple[str, Path]:
    folder = folder_id.strip().strip("/")
    if not folder or "/" in folder or "\\" in folder or folder in {".", ".."}:
        raise ValueError("Invalid markdown folder")
    path = safe_markdown_folder_path(folder)
    return folder, path

def git_root_for_content() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=MARKDOWN_DIR.parent,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Content root is not a Git repository"
        raise RuntimeError(detail)
    return Path(completed.stdout.strip()).resolve()

def path_in_root(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Path must stay inside the content Git repository") from exc

def run_content_git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

def is_under_path(path: str, parent: str) -> bool:
    clean_parent = parent.rstrip("/")
    return path == clean_parent or path.startswith(f"{clean_parent}/")

def staged_files(repo_root: Path) -> list[str]:
    completed = run_content_git(["diff", "--cached", "--name-only"], repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Git diff failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

def staged_files_for_paths(repo_root: Path, paths: list[str]) -> list[str]:
    allowed = [path.rstrip("/") for path in paths]
    return [
        path
        for path in staged_files(repo_root)
        if any(is_under_path(path, parent) for parent in allowed)
    ]

def ensure_staged_scope(repo_root: Path, paths: list[str]) -> None:
    allowed = [path.rstrip("/") for path in paths]
    outside = [
        path
        for path in staged_files(repo_root)
        if not any(is_under_path(path, parent) for parent in allowed)
    ]
    if outside:
        preview = ", ".join(outside[:5])
        suffix = "" if len(outside) <= 5 else f", and {len(outside) - 5} more"
        raise RuntimeError(f"Staged changes outside archive scope: {preview}{suffix}")

def stage_paths(repo_root: Path, paths: list[str]) -> None:
    for path in paths:
        full_path = repo_root / path
        if full_path.exists():
            completed = run_content_git(["add", "-A", "--", path], repo_root)
        else:
            completed = run_content_git(["rm", "-r", "--cached", "--ignore-unmatch", "--", path], repo_root)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Git stage failed")

def checkpoint_paths(repo_root: Path, paths: list[str], message: str) -> str | None:
    stage_paths(repo_root, paths)
    ensure_staged_scope(repo_root, paths)
    if not staged_files_for_paths(repo_root, paths):
        return None
    commit = run_content_git(["commit", "-m", message], repo_root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr.strip() or "Git commit failed")
    rev = run_content_git(["rev-parse", "--short", "HEAD"], repo_root)
    if rev.returncode != 0:
        raise RuntimeError(rev.stderr.strip() or "Could not read commit hash")
    return rev.stdout.strip()

def archive_preview(folder_id: str) -> dict[str, Any]:
    folder, active_path = safe_markdown_top_folder(folder_id)
    archive_path = (ARCHIVE_DIR / folder).resolve()
    repo_root = git_root_for_content()
    rel_active = path_in_root(active_path, repo_root)
    rel_archive = path_in_root(archive_path, repo_root)
    active_files = {
        item.relative_to(active_path).as_posix()
        for item in active_path.rglob("*")
        if item.is_file()
    }
    archive_files = {
        item.relative_to(archive_path).as_posix()
        for item in archive_path.rglob("*")
        if item.is_file()
    } if archive_path.exists() else set()
    return {
        "folder": folder,
        "active_path": rel_active,
        "archive_path": rel_archive,
        "archive_exists": archive_path.exists(),
        "active_files": len(active_files),
        "archive_files": len(archive_files),
        "overwrite_files": len(active_files & archive_files),
        "repo_root": str(repo_root),
    }

def merge_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            if target.exists() and not target.is_dir():
                target.unlink()
            merge_directory(item, target)
            item.rmdir()
        else:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))

def archive_markdown_folder(folder_id: str) -> dict[str, Any]:
    preview = archive_preview(folder_id)
    folder = preview["folder"]
    active_path = MARKDOWN_DIR / folder
    archive_path = ARCHIVE_DIR / folder
    repo_root = Path(preview["repo_root"])
    rel_active = str(preview["active_path"])
    rel_archive = str(preview["archive_path"])
    commits: list[dict[str, str]] = []

    active_commit = checkpoint_paths(
        repo_root,
        [rel_active],
        f"Archive checkpoint: {rel_active} before archive",
    )
    if active_commit:
        commits.append({"kind": "active_checkpoint", "hash": active_commit})

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_commit = checkpoint_paths(
            repo_root,
            [rel_archive],
            f"Archive checkpoint: {rel_archive} before merge",
        )
        if archive_commit:
            commits.append({"kind": "archive_checkpoint", "hash": archive_commit})

        merge_directory(active_path, archive_path)
        active_path.rmdir()
    else:
        move = run_content_git(["mv", rel_active, rel_archive], repo_root)
        if move.returncode != 0:
            raise RuntimeError(move.stderr.strip() or "Git move failed")

    final_commit = checkpoint_paths(
        repo_root,
        [rel_active, rel_archive],
        f"Archive {rel_active} into {rel_archive}",
    )
    if final_commit:
        commits.append({"kind": "archive", "hash": final_commit})

    return {
        "folder": folder,
        "active_path": rel_active,
        "archive_path": rel_archive,
        "commits": commits,
    }

def markdown_to_html(text: str) -> str:
    return mdlib.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
        output_format="html5",
    )


def is_mermaid_fence_info(info: str) -> bool:
    tokens = [token.strip("{}.,").lower() for token in info.split()]
    return "mermaid" in tokens or ".mermaid" in tokens


def render_mermaid_fences(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        info = match.group("info").strip()
        if not is_mermaid_fence_info(info):
            return match.group(0)

        diagram = escape(match.group("body").strip("\n"))
        return f'{match.group(1)}<div class="mermaid">{diagram}</div>\n'

    return MERMAID_FENCE_RE.sub(replace, text)


def render_markdown_page_breaks(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in lines:
        fence_match = MARKDOWN_FENCE_LINE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_char = fence[0]
                fence_len = len(fence)
            elif fence[0] == fence_char and len(fence) >= fence_len:
                in_fence = False
            output.append(line)
            continue

        if not in_fence and MARKDOWN_PAGE_BREAK_RE.match(line):
            if output and output[-1] != "":
                output.append("")
            output.append(
                '<div class="markdown-page-break" role="separator" '
                'aria-label="Page break"></div>'
            )
            output.append("")
            continue

        output.append(line)

    return "\n".join(output)


def render_markdown(text: str) -> str:
    normalized = normalize_markdown_task_lines(text)
    semantic = render_semantic_markdown(normalized)
    with_page_breaks = render_markdown_page_breaks(semantic)
    with_diagrams = render_mermaid_fences(with_page_breaks)
    return markdown_to_html(with_diagrams)


def get_tmux_sessions() -> list[dict[str, Any]]:
    command = [
        "tmux",
        "list-sessions",
        "-F",
        "#{session_name}|#{session_windows}|#{session_attached}|#{session_created}|#{session_activity}",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except FileNotFoundError:
        return [{
            "name": "TMUX NOT INSTALLED",
            "windows": "",
            "attached": "",
            "created": "",
            "activity": "",
            "attach_command": "",
            "status": "MISSING",
        }]
    except subprocess.TimeoutExpired:
        return [{
            "name": "TMUX TIMEOUT",
            "windows": "",
            "attached": "",
            "created": "",
            "activity": "",
            "attach_command": "",
            "status": "TIMEOUT",
        }]

    if completed.returncode != 0:
        return []

    sessions: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("|")
        while len(parts) < 5:
            parts.append("")
        name, windows, attached, created, activity = parts[:5]
        sessions.append({
            "name": name,
            "windows": windows,
            "attached": attached,
            "created": created,
            "activity": activity,
            "attach_command": f"tmux attach -t {name}",
            "status": "ATTACHED" if attached not in ("0", "", "False", "false") else "DETACHED",
        })
    return sessions



def load_link_tree() -> dict[str, Any]:
    if not LINKS_CONFIG_PATH.exists():
        default_tree: dict[str, Any] = {}
        LINKS_CONFIG_PATH.write_text(json.dumps(default_tree, indent=2), encoding="utf-8")
        return default_tree
    try:
        raw = json.loads(LINKS_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}

def save_link_tree(tree: dict[str, Any]) -> None:
    LINKS_CONFIG_PATH.write_text(json.dumps(tree, indent=2), encoding="utf-8")

def add_link_to_tree(path: str, name: str, url: str) -> dict[str, Any]:
    clean_path = path.strip()
    clean_name = name.strip()
    clean_url = url.strip()
    if not clean_name:
        raise ValueError("Name is required")
    if not clean_url:
        raise ValueError("URL is required")
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise ValueError("URL must start with http:// or https://")
    parts = [p for p in clean_path.strip("/").split("/") if p]
    tree = load_link_tree()
    node: dict[str, Any] = tree
    for part in parts:
        existing = node.get(part)
        if isinstance(existing, str):
            raise ValueError(f"Path segment already exists as a link: {part}")
        if not isinstance(existing, dict):
            node[part] = {}
        node = node[part]
    node[clean_name] = clean_url
    save_link_tree(tree)
    return tree





def parse_matrix_marker(line: str) -> tuple[int | None, int, str] | None:
    match = re.match(r"^##\s+Matrix\s*\(((?:\d+)|R)x(\d+)\)\s*(.*)$", line.strip(), re.I)
    if not match:
        return None

    row_token = match.group(1).upper()
    rows = None if row_token == "R" else int(row_token)
    cols = int(match.group(2))
    suffix = match.group(3).strip(" -:")
    title = suffix if suffix else ""

    if rows is None and cols != 1:
        return None

    if cols < 1 or cols > 6:
        return None

    if rows is not None and (rows < 1 or rows > 6):
        return None

    return rows, cols, title


def parse_matrix_section_title(line: str) -> str | None:
    match = re.match(r"^###\s+(.+?)\s*$", line.strip())
    if not match:
        return None
    return match.group(1).strip()



def render_inline_matrix_markdown(text: str) -> str:
    """Render a single matrix bullet item as inline Markdown."""
    rendered = markdown_to_html(text).strip()

    paragraph = re.match(r"^<p>(.*)</p>$", rendered, re.S)
    return paragraph.group(1) if paragraph else rendered


def render_matrix_items(lines: list[str]) -> str:
    items: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        text = " ".join(part.strip() for part in current if part.strip()).strip()
        if text:
            items.append(text)
        current = []

    for raw in lines:
        line = raw.rstrip()
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            flush()
            current = [bullet.group(1)]
        elif current and line.strip():
            current.append(line.strip())
        elif current:
            flush()

    flush()

    if not items:
        return '<div class="matrix-empty">-</div>'

    return "<ul>" + "".join(f"<li>{render_inline_matrix_markdown(item)}</li>" for item in items) + "</ul>"


def matrix_cell_position(index: int, rows: int) -> tuple[int, int]:
    row = index % rows
    col = index // rows
    return row, col


def build_matrix_html(title: str, rows: int, cols: int, sections: list[tuple[str, list[str]]]) -> str:
    cells = []
    for index, (section_title, section_lines) in enumerate(sections):
        row, col = matrix_cell_position(index, rows)
        items_html = render_matrix_items(section_lines)
        cells.append(
            f'<div class="lcars-matrix-cell matrix-cell-{index + 1}" '
            f'style="grid-row:{row + 1};grid-column:{col + 1};">'
            f'<div class="lcars-matrix-title">{escape(section_title)}</div>'
            f'<div class="lcars-matrix-items">{items_html}</div>'
            f'</div>'
        )

    heading_html = f'<div class="lcars-matrix-heading">{escape(title)}</div>' if title else ""

    return (
        f'<div class="lcars-matrix-block" data-rows="{rows}" data-cols="{cols}">'
        + heading_html +
        f'<div class="lcars-matrix-grid" style="grid-template-columns: repeat({cols}, minmax(0, 1fr));">'
        + "".join(cells) +
        '</div></div>'
    )

def extract_matrix_block(lines: list[str], start: int) -> tuple[str | None, int]:
    marker = parse_matrix_marker(lines[start])
    if not marker:
        return None, start

    rows, cols, title = marker

    idx = start + 1
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush_section() -> None:
        nonlocal current_title, current_lines
        if current_title is not None:
            sections.append((current_title, current_lines))
        current_title = None
        current_lines = []

    while idx < len(lines):
        line = lines[idx]

        if re.match(r"^##\s+End\s+Matrix\s*$", line.strip(), re.I):
            flush_section()
            idx += 1
            break

        if idx > start + 1 and re.match(r"^##\s+", line):
            flush_section()
            break

        section_title = parse_matrix_section_title(line)
        if section_title:
            flush_section()
            current_title = section_title
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)

        idx += 1
    else:
        flush_section()

    if rows is None:
        rows = len(sections)
        if rows < 1 or rows > 36:
            return None, start

    required_sections = rows * cols
    if len(sections) == required_sections:
        return build_matrix_html(title, rows, cols, sections), idx

    return None, start


def render_semantic_markdown(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    idx = 0

    while idx < len(lines):
        matrix_html, next_idx = extract_matrix_block(lines, idx)
        if matrix_html is not None:
            output.append(matrix_html)
            idx = next_idx
        else:
            output.append(lines[idx])
            idx += 1

    return "\n".join(output)



def normalize_markdown_task_lines(text: str) -> str:
    """Allow bare [x] / [ ] checklist lines to render as Markdown task-list bullets."""
    return re.sub(r"(?m)^(\s*)\[(x|X| )\]\s+", r"\1- [\2] ", text)


def markdown_slug_from_title(title: str) -> str:
    cleaned = title.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "untitled"


def unique_markdown_path_from_rel(raw_name: str) -> Path:
    """Create a safe unique Markdown path, allowing folder segments."""
    cleaned = raw_name.strip().replace("\\", "/")
    if cleaned.lower().endswith(".md"):
        cleaned = cleaned[:-3]
    parts = [part for part in cleaned.split("/") if part.strip()]
    if not parts:
        parts = ["untitled"]

    folder_parts = [markdown_slug_from_title(part) for part in parts[:-1]]
    filename = markdown_slug_from_title(parts[-1]) + ".md"

    base_dir = MARKDOWN_DIR.joinpath(*folder_parts).resolve() if folder_parts else MARKDOWN_DIR.resolve()
    if not str(base_dir).startswith(str(MARKDOWN_DIR.resolve())):
        raise ValueError("Invalid markdown path")

    base_dir.mkdir(parents=True, exist_ok=True)
    candidate = base_dir / filename

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    for idx in range(2, 1000):
        next_candidate = candidate.with_name(f"{stem}_{idx}{suffix}")
        if not next_candidate.exists():
            return next_candidate

    raise ValueError("Could not create unique markdown filename")


def unique_markdown_path(title: str) -> Path:
    slug = markdown_slug_from_title(title)
    candidate = MARKDOWN_DIR / f"{slug}.md"
    counter = 2
    while candidate.exists():
        candidate = MARKDOWN_DIR / f"{slug}_{counter}.md"
        counter += 1
    return candidate


def load_focus_config() -> dict[str, Any]:
    default_config = {
        "work_complete_sound": "",
        "break_complete_sound": "",
        "use_beep_fallback": True,
    }

    if not FOCUS_CONFIG_PATH.exists():
        FOCUS_CONFIG_PATH.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
        return default_config

    try:
        raw = json.loads(FOCUS_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_config

    if not isinstance(raw, dict):
        return default_config

    return {**default_config, **raw}



def get_markdown_folders() -> list[str]:
    MARKDOWN_DIR.mkdir(exist_ok=True)
    folders: set[str] = set()
    for p in MARKDOWN_DIR.rglob("*.md"):
        rel = p.relative_to(MARKDOWN_DIR).as_posix()
        parts = rel.split("/")
        if len(parts) > 1 and parts[0]:
            folders.add(parts[0])
    return sorted(folders, key=lambda x: x.lower())


def get_markdown_scope(folder_id: str = "") -> dict[str, Any]:
    requested_folder = folder_id.strip().strip("/")
    current_folder = ""
    if requested_folder:
        folder_path = safe_markdown_folder_path(requested_folder)
        current_folder = folder_path.relative_to(MARKDOWN_DIR.resolve()).as_posix()

    all_docs = get_markdown_docs()
    prefix = f"{current_folder}/" if current_folder else ""
    docs = [doc for doc in all_docs if not prefix or doc["id"].startswith(prefix)]

    current_parts = tuple(part for part in current_folder.split("/") if part)
    child_names: set[str] = set()
    for doc in docs:
        folder_parts = tuple(Path(doc["id"]).parts[:-1])
        if folder_parts[:len(current_parts)] != current_parts:
            continue
        if len(folder_parts) > len(current_parts):
            child_names.add(folder_parts[len(current_parts)])

    children = [
        {
            "name": name,
            "path": "/".join((*current_parts, name)),
        }
        for name in sorted(child_names, key=str.casefold)
    ]

    breadcrumbs: list[dict[str, str]] = [{"name": "ALL", "path": ""}]
    path_parts: list[str] = []
    for part in current_parts:
        path_parts.append(part)
        breadcrumbs.append({"name": part, "path": "/".join(path_parts)})

    return {
        "docs": docs,
        "current_folder": current_folder,
        "current_name": current_parts[-1] if current_parts else "ALL",
        "breadcrumbs": breadcrumbs,
        "children": children,
        "archive_folder": current_folder if current_folder and len(current_parts) == 1 else "",
    }


def search_markdown_contents(
    docs: list[dict[str, str]],
    query: str,
    snippet_limit: int = 2,
) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    if not needle:
        return [dict(doc) for doc in docs]

    results: list[dict[str, Any]] = []
    for doc in docs:
        path = safe_markdown_path(doc["id"])
        text = path.read_text(encoding="utf-8", errors="replace")
        matches: list[dict[str, Any]] = []
        match_count = 0
        for line_number, line in enumerate(text.splitlines(), start=1):
            folded_line = line.casefold()
            occurrences = folded_line.count(needle)
            if not occurrences:
                continue
            match_count += occurrences
            if len(matches) >= snippet_limit:
                continue

            clean_line = re.sub(r"\s+", " ", line).strip()
            match_index = folded_line.find(needle)
            if len(clean_line) > 220:
                start = max(0, match_index - 80)
                end = min(len(clean_line), start + 220)
                clean_line = (
                    ("…" if start else "")
                    + clean_line[start:end].strip()
                    + ("…" if end < len(clean_line) else "")
                )
            matches.append({"line": line_number, "text": clean_line or "(blank line)"})

        if matches:
            result: dict[str, Any] = dict(doc)
            result["matches"] = matches
            result["match_count"] = match_count
            result["hidden_match_count"] = max(0, match_count - len(matches))
            results.append(result)

    return results


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_youtube_db() -> sqlite3.Connection:
    conn = sqlite3.connect(YOUTUBE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_youtube_schema(conn)
    return conn


def ensure_youtube_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS youtube_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            alias TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            thumbnail_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS youtube_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES youtube_sources(id) ON DELETE CASCADE,
            video_id TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            thumbnail_url TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS youtube_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS youtube_source_tags (
            source_id INTEGER NOT NULL REFERENCES youtube_sources(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES youtube_tags(id) ON DELETE CASCADE,
            PRIMARY KEY (source_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS youtube_video_tags (
            video_id INTEGER NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES youtube_tags(id) ON DELETE CASCADE,
            PRIMARY KEY (video_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS youtube_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
            language_code TEXT NOT NULL,
            language_name TEXT NOT NULL DEFAULT '',
            is_generated INTEGER NOT NULL DEFAULT 0,
            markdown_rel_path TEXT NOT NULL UNIQUE,
            segment_count INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(video_id, language_code)
        );
        """
    )
    ensure_sqlite_column(conn, "youtube_sources", "source_url", "TEXT NOT NULL DEFAULT ''")


def ensure_sqlite_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def normalize_youtube_url_value(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("YouTube URL is required")
    if "://" not in value and ("youtube." in value.lower() or "youtu.be" in value.lower()):
        value = f"https://{value}"
    return value


def parse_youtube_url(raw_url: str) -> tuple[str, str]:
    value = normalize_youtube_url_value(raw_url)
    parsed = urlparse(value)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    video_id = ""
    url_kind = "video"
    if host in YOUTUBE_VIDEO_HOSTS:
        query = parse_qs(parsed.query)
        video_id = (query.get("v") or [""])[0]
        if path_parts and path_parts[0] == "shorts":
            url_kind = "short"
        if not video_id and path_parts and path_parts[0] in YOUTUBE_DIRECT_VIDEO_PATHS:
            video_id = path_parts[1] if len(path_parts) > 1 else ""
    elif host == "youtube-nocookie.com" and path_parts and path_parts[0] in YOUTUBE_DIRECT_VIDEO_PATHS:
        video_id = path_parts[1] if len(path_parts) > 1 else ""
    elif host == "youtu.be" and path_parts:
        video_id = path_parts[0]

    video_id = video_id.strip()
    if not YOUTUBE_VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("Could not find a YouTube video id in that URL")
    return video_id, url_kind


def parse_youtube_video_id(raw_url: str) -> str:
    video_id, _url_kind = parse_youtube_url(raw_url)
    return video_id


def canonical_youtube_url(video_id: str, url_kind: str = "video") -> str:
    if url_kind == "short":
        return f"https://www.youtube.com/shorts/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


def youtube_thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def clean_youtube_title(raw_title: str) -> str:
    title = re.sub(r"\s+", " ", raw_title.strip())
    return re.sub(r"\s+-\s+YouTube\s*$", "", title, flags=re.IGNORECASE)


def fetch_youtube_oembed(video_url: str) -> dict[str, str]:
    endpoint = "https://www.youtube.com/oembed?" + urlencode({"url": video_url, "format": "json"})
    request_obj = Request(endpoint, headers={"User-Agent": "LCARS Local Server/1.0"})
    try:
        with urlopen(request_obj, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, URLError, OSError, ValueError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    return {
        "title": clean_youtube_title(str(payload.get("title") or "")),
        "source_name": str(payload.get("author_name") or "").strip(),
        "source_url": str(payload.get("author_url") or "").strip(),
        "thumbnail_url": str(payload.get("thumbnail_url") or "").strip(),
    }


def youtube_metadata_defaults(
    video_id: str,
    raw_title: str = "",
    raw_source_name: str = "",
    raw_source_url: str = "",
    raw_url: str = "",
) -> dict[str, str]:
    url_kind = "video"
    if raw_url:
        try:
            parsed_video_id, parsed_url_kind = parse_youtube_url(raw_url)
            if parsed_video_id == video_id:
                url_kind = parsed_url_kind
        except ValueError:
            url_kind = "video"

    url = canonical_youtube_url(video_id, url_kind)
    metadata = fetch_youtube_oembed(url)
    if not metadata and url_kind == "short":
        metadata = fetch_youtube_oembed(canonical_youtube_url(video_id))
    fallback_title = f"YouTube video {video_id}"
    title = metadata.get("title") or clean_youtube_title(raw_title) or fallback_title
    source_name = metadata.get("source_name") or raw_source_name.strip() or YOUTUBE_INBOX_SOURCE
    return {
        "url": url,
        "title": title,
        "source_name": source_name,
        "source_url": metadata.get("source_url") or raw_source_url.strip(),
        "thumbnail_url": metadata.get("thumbnail_url") or youtube_thumbnail_url(video_id),
    }


def normalize_youtube_tag(raw_tag: str) -> str:
    normalized = re.sub(r"\s+", " ", raw_tag.strip()).strip("_")
    return re.sub(r"_+", "_", normalized).upper()


def youtube_tag_key(raw_tag: str) -> str:
    return normalize_youtube_tag(raw_tag).casefold()


def parse_tag_list(raw_tags: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,#\s]+", raw_tags):
        tag = normalize_youtube_tag(raw)
        key = youtube_tag_key(tag)
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def transcript_client() -> Any:
    try:
        from yt_transcripts import TranscriptClient
    except ImportError as exc:
        raise RuntimeError(
            "yt_transcripts is not installed. Run: pip install -e "
            "/Users/praedator/Documents/COMICS/repos/mini_data_pipeline"
        ) from exc

    if not hasattr(app, "_yt_transcript_client"):
        app._yt_transcript_client = TranscriptClient(dotenv_path=YOUTUBE_DOTENV_PATH)  # type: ignore[attr-defined]
    return app._yt_transcript_client  # type: ignore[attr-defined]


def safe_language_slug(language_code: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "_", language_code.lower()).strip("_")
    return slug or "auto"


def youtube_transcript_rel_path(video: dict[str, Any], language_code: str) -> str:
    source_slug = markdown_slug_from_title(str(video.get("source_name") or "youtube"))
    title_slug = markdown_slug_from_title(str(video.get("title") or video.get("video_id") or "transcript"))
    video_slug = markdown_slug_from_title(str(video.get("video_id") or "video"))
    language_slug = safe_language_slug(language_code)
    return f"yt_transcripts/{source_slug}/{title_slug}_{video_slug}_{language_slug}.md"


def youtube_transcript_abs_path(rel_path: str) -> Path:
    path = (MARKDOWN_DIR / rel_path).resolve()
    if not str(path).startswith(str(MARKDOWN_DIR.resolve())):
        raise ValueError("Transcript path must stay inside markdown directory")
    return path


def markdown_link(label: str, url: str) -> str:
    clean_label = str(label or url).replace("[", "\\[").replace("]", "\\]")
    clean_url = str(url or "").replace(")", "%29").replace("(", "%28")
    return f"[{clean_label}]({clean_url})" if clean_url else clean_label


def transcript_value(doc: Any, key: str, default: Any = "") -> Any:
    if isinstance(doc, dict):
        return doc.get(key, default)
    return getattr(doc, key, default)


def youtube_transcript_markdown(video: dict[str, Any], doc: Any) -> str:
    title = str(video.get("title") or transcript_value(doc, "title") or video.get("video_id") or "YouTube Transcript")
    source_name = str(video.get("source_name") or transcript_value(doc, "channel") or "")
    source_url = str(video.get("source_url") or transcript_value(doc, "channel_url") or "")
    language_code = str(transcript_value(doc, "language_code") or "")
    language_name = str(transcript_value(doc, "language_name") or language_code)
    generated = "yes" if transcript_value(doc, "is_generated") else "no"
    source_tags = ", ".join(video.get("source_tags", [])) or "-"
    video_tags = ", ".join(video.get("tags", [])) or "-"
    transcript = str(transcript_value(doc, "cleaned_text") or "").strip()

    lines = [
        f"# {title}",
        "",
        "## Metadata",
        "",
        f"- Source: {markdown_link(source_name, source_url)}",
        f"- Video: {markdown_link(str(video.get('url') or transcript_value(doc, 'url') or ''), str(video.get('url') or transcript_value(doc, 'url') or ''))}",
        f"- YouTube ID: `{video.get('video_id') or transcript_value(doc, 'video_id') or ''}`",
        f"- Language: {language_name} (`{language_code}`)",
        f"- Auto-generated: {generated}",
        f"- Segment count: {transcript_value(doc, 'segment_count') or 0}",
        f"- Fetched at: {transcript_value(doc, 'fetched_at') or ''}",
        f"- Source tags: {source_tags}",
        f"- Video tags: {video_tags}",
        "",
        "## Transcript",
        "",
        transcript,
        "",
    ]
    return "\n".join(lines)


def get_or_create_youtube_tag(conn: sqlite3.Connection, name: str) -> int:
    normalized_name = normalize_youtube_tag(name)
    row = conn.execute(
        "SELECT id FROM youtube_tags WHERE lower(name) = lower(?) ORDER BY id LIMIT 1",
        (normalized_name,),
    ).fetchone()
    if row:
        return int(row["id"])

    conn.execute("INSERT OR IGNORE INTO youtube_tags (name) VALUES (?)", (normalized_name,))
    row = conn.execute("SELECT id FROM youtube_tags WHERE name = ?", (normalized_name,)).fetchone()
    if not row:
        raise RuntimeError("Could not create YouTube tag")
    return int(row["id"])


def replace_youtube_tags(
    conn: sqlite3.Connection,
    table: str,
    owner_column: str,
    owner_id: int,
    tags: list[str],
) -> None:
    if table not in {"youtube_source_tags", "youtube_video_tags"}:
        raise ValueError("Invalid tag table")
    if owner_column not in {"source_id", "video_id"}:
        raise ValueError("Invalid tag owner")

    conn.execute(f"DELETE FROM {table} WHERE {owner_column} = ?", (owner_id,))
    for tag in tags:
        tag_id = get_or_create_youtube_tag(conn, tag)
        conn.execute(
            f"INSERT OR IGNORE INTO {table} ({owner_column}, tag_id) VALUES (?, ?)",
            (owner_id, tag_id),
        )


def normalize_youtube_tag_database(
    database_path: Path | None = None,
) -> dict[str, int]:
    path = database_path or YOUTUBE_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_youtube_schema(conn)

    try:
        conn.execute("BEGIN IMMEDIATE")
        tags_before = int(conn.execute("SELECT COUNT(*) FROM youtube_tags").fetchone()[0])
        source_links_before = int(
            conn.execute("SELECT COUNT(*) FROM youtube_source_tags").fetchone()[0]
        )
        video_links_before = int(
            conn.execute("SELECT COUNT(*) FROM youtube_video_tags").fetchone()[0]
        )

        source_tags_by_owner: dict[int, set[str]] = {}
        for row in conn.execute(
            """
            SELECT link.source_id AS owner_id, tag.name
            FROM youtube_source_tags link
            JOIN youtube_tags tag ON tag.id = link.tag_id
            """
        ).fetchall():
            source_tags_by_owner.setdefault(int(row["owner_id"]), set()).update(
                parse_tag_list(str(row["name"]))
            )

        video_tags_by_owner: dict[int, set[str]] = {}
        for row in conn.execute(
            """
            SELECT link.video_id AS owner_id, tag.name
            FROM youtube_video_tags link
            JOIN youtube_tags tag ON tag.id = link.tag_id
            """
        ).fetchall():
            video_tags_by_owner.setdefault(int(row["owner_id"]), set()).update(
                parse_tag_list(str(row["name"]))
            )

        canonical_tags = sorted(
            {
                tag
                for owner_tags in [*source_tags_by_owner.values(), *video_tags_by_owner.values()]
                for tag in owner_tags
            },
            key=str.casefold,
        )

        conn.execute("DELETE FROM youtube_source_tags")
        conn.execute("DELETE FROM youtube_video_tags")
        conn.execute("DELETE FROM youtube_tags")

        tag_ids: dict[str, int] = {}
        for tag in canonical_tags:
            cursor = conn.execute("INSERT INTO youtube_tags (name) VALUES (?)", (tag,))
            tag_ids[tag] = int(cursor.lastrowid)

        for source_id, tags in source_tags_by_owner.items():
            for tag in sorted(tags, key=str.casefold):
                conn.execute(
                    "INSERT INTO youtube_source_tags (source_id, tag_id) VALUES (?, ?)",
                    (source_id, tag_ids[tag]),
                )
        for video_id, tags in video_tags_by_owner.items():
            for tag in sorted(tags, key=str.casefold):
                conn.execute(
                    "INSERT INTO youtube_video_tags (video_id, tag_id) VALUES (?, ?)",
                    (video_id, tag_ids[tag]),
                )

        result = {
            "tags_before": tags_before,
            "tags_after": len(canonical_tags),
            "source_links_before": source_links_before,
            "source_links_after": sum(len(tags) for tags in source_tags_by_owner.values()),
            "video_links_before": video_links_before,
            "video_links_after": sum(len(tags) for tags in video_tags_by_owner.values()),
        }
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_empty_youtube_sources(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        DELETE FROM youtube_sources
        WHERE id NOT IN (SELECT DISTINCT source_id FROM youtube_videos)
        """
    )
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def delete_empty_youtube_source(conn: sqlite3.Connection, source_id: int) -> bool:
    video_count = conn.execute(
        "SELECT COUNT(*) AS video_count FROM youtube_videos WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    if video_count and int(video_count["video_count"]) > 0:
        return False

    cursor = conn.execute("DELETE FROM youtube_sources WHERE id = ?", (source_id,))
    return int(cursor.rowcount if cursor.rowcount is not None else 0) > 0


def youtube_tags_for(conn: sqlite3.Connection, table: str, owner_column: str) -> dict[int, list[str]]:
    if table not in {"youtube_source_tags", "youtube_video_tags"}:
        raise ValueError("Invalid tag table")
    if owner_column not in {"source_id", "video_id"}:
        raise ValueError("Invalid tag owner")

    rows = conn.execute(
        f"""
        SELECT link.{owner_column} AS owner_id, tag.name
        FROM {table} link
        JOIN youtube_tags tag ON tag.id = link.tag_id
        ORDER BY tag.name
        """
    ).fetchall()
    tags: dict[int, list[str]] = {}
    seen_by_owner: dict[int, set[str]] = {}
    for row in rows:
        owner_id = int(row["owner_id"])
        seen = seen_by_owner.setdefault(owner_id, set())
        for tag in parse_tag_list(str(row["name"])):
            key = youtube_tag_key(tag)
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.setdefault(owner_id, []).append(tag)
    for owner_tags in tags.values():
        owner_tags.sort(key=str.casefold)
    return tags


def get_youtube_tag_labels() -> list[str]:
    with get_youtube_db() as conn:
        rows = conn.execute(
            """
            SELECT tag.name
            FROM youtube_tags tag
            JOIN youtube_source_tags link ON link.tag_id = tag.id
            UNION ALL
            SELECT tag.name
            FROM youtube_tags tag
            JOIN youtube_video_tags link ON link.tag_id = tag.id
            """
        ).fetchall()

    labels = {
        tag
        for row in rows
        for tag in parse_tag_list(str(row["name"]))
    }
    return sorted(labels, key=str.casefold)


def get_youtube_library_counts() -> tuple[int, int]:
    with get_youtube_db() as conn:
        source_count = int(
            conn.execute("SELECT COUNT(*) FROM youtube_sources").fetchone()[0]
        )
        video_count = int(
            conn.execute("SELECT COUNT(*) FROM youtube_videos").fetchone()[0]
        )
    return source_count, video_count


def upsert_youtube_source(
    conn: sqlite3.Connection,
    source_name: str,
    source_alias: str,
    source_url: str,
    thumbnail_url: str,
    timestamp: str,
    replace_source_identity: bool = False,
) -> int:
    source_row = conn.execute(
        """
        SELECT *
        FROM youtube_sources
        WHERE (? != '' AND source_url = ?)
           OR lower(name) = lower(?)
           OR (? != '' AND lower(alias) = lower(?))
        ORDER BY id
        LIMIT 1
        """,
        (source_url, source_url, source_name, source_alias, source_alias),
    ).fetchone()

    if source_row:
        source_id = int(source_row["id"])
        if replace_source_identity:
            next_alias = source_alias
            next_source_url = source_url
        else:
            next_alias = source_alias or str(source_row["alias"] or "")
            next_source_url = source_url or str(source_row["source_url"] or "")
        conn.execute(
            """
            UPDATE youtube_sources
            SET name = ?, alias = ?, source_url = ?, thumbnail_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (source_name, next_alias, next_source_url, thumbnail_url, timestamp, source_id),
        )
        return source_id

    cursor = conn.execute(
        """
        INSERT INTO youtube_sources
            (name, alias, source_url, thumbnail_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_name, source_alias, source_url, thumbnail_url, timestamp, timestamp),
    )
    return int(cursor.lastrowid)


def save_youtube_video(form: dict[str, str]) -> dict[str, Any]:
    raw_url = form.get("url", "").strip()
    video_id = form.get("video_id", "").strip() or parse_youtube_video_id(raw_url)
    submitted_title = clean_youtube_title(form.get("title", ""))
    submitted_source_name = form.get("source_name", "").strip()
    submitted_source_url = form.get("source_url", "").strip()
    metadata = youtube_metadata_defaults(
        video_id,
        submitted_title,
        submitted_source_name,
        submitted_source_url,
        raw_url,
    )
    url = metadata["url"]
    title = submitted_title
    if not title or title == f"YouTube video {video_id}":
        title = metadata["title"]
    source_name = submitted_source_name
    if not source_name or source_name.lower() == YOUTUBE_INBOX_SOURCE.lower():
        source_name = metadata["source_name"]
    source_alias = form.get("source_alias", "").strip()
    replace_source_identity = form.get("replace_source_identity", "").strip() == "1"
    source_url = submitted_source_url if replace_source_identity else metadata["source_url"]
    raw_source_tags = form.get("source_tags", "")
    replace_source_tags = form.get("replace_source_tags", "").strip() == "1"
    source_tags = parse_tag_list(raw_source_tags)
    video_tags = parse_tag_list(form.get("video_tags", ""))
    video_notes = form.get("video_notes", "").strip()

    if not source_name:
        source_name = source_alias or YOUTUBE_INBOX_SOURCE

    timestamp = now_iso()
    thumbnail_url = metadata["thumbnail_url"]

    with get_youtube_db() as conn:
        source_id = upsert_youtube_source(
            conn,
            source_name,
            source_alias,
            source_url,
            thumbnail_url,
            timestamp,
            replace_source_identity,
        )

        video_row = conn.execute(
            "SELECT id FROM youtube_videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()

        if video_row:
            saved_video_id = int(video_row["id"])
            conn.execute(
                """
                UPDATE youtube_videos
                SET source_id = ?, url = ?, title = ?, thumbnail_url = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (source_id, url, title, thumbnail_url, video_notes, timestamp, saved_video_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO youtube_videos
                    (source_id, video_id, url, title, thumbnail_url, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_id, video_id, url, title, thumbnail_url, video_notes, timestamp, timestamp),
            )
            saved_video_id = int(cursor.lastrowid)

        if replace_source_tags or raw_source_tags.strip():
            replace_youtube_tags(conn, "youtube_source_tags", "source_id", source_id, source_tags)
        replace_youtube_tags(conn, "youtube_video_tags", "video_id", saved_video_id, video_tags)
        delete_empty_youtube_sources(conn)
        conn.commit()

    return {
        "source_id": source_id,
        "video_id": saved_video_id,
        "youtube_video_id": video_id,
    }


def enrich_youtube_library(limit: int = 25) -> dict[str, int]:
    with get_youtube_db() as conn:
        candidates = [dict(row) for row in conn.execute(
            """
            SELECT video.*,
                   source.name AS current_source_name,
                   source.source_url AS current_source_url
            FROM youtube_videos video
            JOIN youtube_sources source ON source.id = video.source_id
            WHERE lower(source.name) = lower(?)
               OR video.title = 'YouTube video ' || video.video_id
               OR video.thumbnail_url = ''
            ORDER BY video.updated_at DESC
            LIMIT ?
            """,
            (YOUTUBE_INBOX_SOURCE, limit),
        ).fetchall()]

        updated = 0
        skipped = 0
        for video in candidates:
            video_id = str(video["video_id"])
            metadata = fetch_youtube_oembed(canonical_youtube_url(video_id))
            source_name = str(metadata.get("source_name") or "").strip()
            if not source_name:
                skipped += 1
                continue

            timestamp = now_iso()
            thumbnail_url = (
                str(metadata.get("thumbnail_url") or "").strip()
                or str(video.get("thumbnail_url") or "")
                or youtube_thumbnail_url(video_id)
            )
            source_id = upsert_youtube_source(
                conn,
                source_name,
                "",
                str(metadata.get("source_url") or "").strip(),
                thumbnail_url,
                timestamp,
            )
            current_title = str(video.get("title") or "")
            default_title = f"YouTube video {video_id}"
            next_title = str(metadata.get("title") or "").strip()
            if current_title and current_title != default_title:
                next_title = current_title
            if not next_title:
                next_title = default_title

            changed = (
                source_id != int(video["source_id"])
                or next_title != current_title
                or thumbnail_url != str(video.get("thumbnail_url") or "")
            )
            conn.execute(
                """
                UPDATE youtube_videos
                SET source_id = ?, title = ?, thumbnail_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (source_id, next_title, thumbnail_url, timestamp, int(video["id"])),
            )
            if changed:
                updated += 1

        delete_empty_youtube_sources(conn)
        conn.commit()

    return {"checked": len(candidates), "updated": updated, "skipped": skipped}


def delete_youtube_video(video_id: int) -> dict[str, Any]:
    with get_youtube_db() as conn:
        row = conn.execute(
            "SELECT id, source_id FROM youtube_videos WHERE id = ?",
            (video_id,),
        ).fetchone()
        if not row:
            return {"deleted": False, "source_id": 0, "source_deleted": False}

        source_id = int(row["source_id"])
        conn.execute("DELETE FROM youtube_videos WHERE id = ?", (video_id,))
        source_deleted = delete_empty_youtube_source(conn, source_id)
        conn.commit()

    return {"deleted": True, "source_id": source_id, "source_deleted": source_deleted}


def delete_youtube_source(source_id: int, require_empty: bool = True) -> dict[str, int]:
    with get_youtube_db() as conn:
        row = conn.execute(
            """
            SELECT source.id, COUNT(video.id) AS video_count
            FROM youtube_sources source
            LEFT JOIN youtube_videos video ON video.source_id = source.id
            WHERE source.id = ?
            GROUP BY source.id
            """,
            (source_id,),
        ).fetchone()
        if not row:
            return {"deleted": 0, "video_count": 0}

        video_count = int(row["video_count"])
        if require_empty and video_count:
            raise ValueError("Delete saved videos before deleting this source")

        conn.execute("DELETE FROM youtube_sources WHERE id = ?", (source_id,))
        conn.commit()

    return {"deleted": 1, "video_count": video_count}


def get_youtube_sources(
    query: str = "",
    selected_tags: str | list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    normalized_query = query.strip().casefold()
    raw_selected_tags = [selected_tags] if isinstance(selected_tags, str) else selected_tags
    selected_tag_keys = {
        youtube_tag_key(tag)
        for tag in raw_selected_tags
        if normalize_youtube_tag(tag)
    }
    with get_youtube_db() as conn:
        source_tags = youtube_tags_for(conn, "youtube_source_tags", "source_id")
        video_tags = youtube_tags_for(conn, "youtube_video_tags", "video_id")
        sources = [dict(row) for row in conn.execute(
            """
            SELECT source.*,
                   COUNT(video.id) AS video_count,
                   MAX(video.updated_at) AS last_saved_at
            FROM youtube_sources source
            LEFT JOIN youtube_videos video ON video.source_id = source.id
            GROUP BY source.id
            ORDER BY COALESCE(MAX(video.updated_at), source.updated_at) DESC, source.name
            """
        ).fetchall()]
        videos = [dict(row) for row in conn.execute(
            """
            SELECT video.*
            FROM youtube_videos video
            ORDER BY video.updated_at DESC
            """
        ).fetchall()]

    videos_by_source: dict[int, list[dict[str, Any]]] = {}
    for video in videos:
        video["tags"] = video_tags.get(int(video["id"]), [])
        videos_by_source.setdefault(int(video["source_id"]), []).append(video)

    cards: list[dict[str, Any]] = []
    for source in sources:
        source_id = int(source["id"])
        source_videos = videos_by_source.get(source_id, [])
        latest_video = source_videos[0] if source_videos else None
        source_only_tags = source_tags.get(source_id, [])
        tags: list[str] = []
        tag_keys: set[str] = set()
        for tag in source_only_tags:
            key = youtube_tag_key(tag)
            if key and key not in tag_keys:
                tag_keys.add(key)
                tags.append(normalize_youtube_tag(tag))
        for video in source_videos:
            for tag in video.get("tags", []):
                key = youtube_tag_key(tag)
                if key and key not in tag_keys:
                    tag_keys.add(key)
                    tags.append(normalize_youtube_tag(tag))
        tags.sort(key=str.casefold)
        thumbnail = (
            str(latest_video["thumbnail_url"])
            if latest_video and latest_video.get("thumbnail_url")
            else str(source.get("thumbnail_url") or "")
        )
        search_blob = " ".join(
            [
                str(source.get("name") or ""),
                str(source.get("alias") or ""),
                str(source.get("source_url") or ""),
                str(source.get("notes") or ""),
                " ".join(tags),
                " ".join(
                    " ".join(
                        [
                            str(video.get("title") or ""),
                            str(video.get("notes") or ""),
                            " ".join(video.get("tags", [])),
                        ]
                    )
                    for video in source_videos
                ),
            ]
        ).casefold()
        if normalized_query and normalized_query not in search_blob:
            continue
        if not selected_tag_keys.issubset(tag_keys):
            continue

        source["tags"] = tags
        source["source_tags"] = source_only_tags
        source["videos"] = source_videos[:1]
        source["video_titles"] = [str(video.get("title") or "") for video in source_videos]
        source["latest_video"] = latest_video
        source["thumbnail_url"] = thumbnail
        cards.append(source)

    return cards


def get_youtube_items(
    query: str = "",
    selected_tags: str | list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    normalized_query = query.strip().casefold()
    raw_selected_tags = [selected_tags] if isinstance(selected_tags, str) else selected_tags
    selected_tag_keys = {
        youtube_tag_key(tag)
        for tag in raw_selected_tags
        if normalize_youtube_tag(tag)
    }
    with get_youtube_db() as conn:
        source_tags = youtube_tags_for(conn, "youtube_source_tags", "source_id")
        video_tags = youtube_tags_for(conn, "youtube_video_tags", "video_id")
        items = [dict(row) for row in conn.execute(
            """
            SELECT video.*,
                   source.name AS source_name,
                   source.alias AS source_alias
            FROM youtube_videos video
            JOIN youtube_sources source ON source.id = video.source_id
            ORDER BY video.updated_at DESC, video.title
            """
        ).fetchall()]

    results: list[dict[str, Any]] = []
    for item in items:
        tags: list[str] = []
        tag_keys: set[str] = set()
        for tag in [
            *source_tags.get(int(item["source_id"]), []),
            *video_tags.get(int(item["id"]), []),
        ]:
            key = youtube_tag_key(tag)
            if key and key not in tag_keys:
                tag_keys.add(key)
                tags.append(normalize_youtube_tag(tag))
        tags.sort(key=str.casefold)
        search_blob = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("notes") or ""),
                str(item.get("source_name") or ""),
                str(item.get("source_alias") or ""),
                " ".join(tags),
            ]
        ).casefold()
        if normalized_query and normalized_query not in search_blob:
            continue
        if not selected_tag_keys.issubset(tag_keys):
            continue
        item["tags"] = tags
        results.append(item)

    return results


def get_youtube_source(source_id: int) -> dict[str, Any] | None:
    with get_youtube_db() as conn:
        row = conn.execute(
            "SELECT * FROM youtube_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if not row:
            return None

        source = dict(row)
        source_tags = youtube_tags_for(conn, "youtube_source_tags", "source_id")
        video_tags = youtube_tags_for(conn, "youtube_video_tags", "video_id")
        videos = [dict(video) for video in conn.execute(
            """
            SELECT *
            FROM youtube_videos
            WHERE source_id = ?
            ORDER BY updated_at DESC
            """,
            (source_id,),
        ).fetchall()]
        transcripts = [dict(transcript) for transcript in conn.execute(
            """
            SELECT transcript.*
            FROM youtube_transcripts transcript
            JOIN youtube_videos video ON video.id = transcript.video_id
            WHERE video.source_id = ?
            ORDER BY transcript.updated_at DESC, transcript.language_code
            """,
            (source_id,),
        ).fetchall()]

    source["tags"] = source_tags.get(source_id, [])
    transcripts_by_video: dict[int, list[dict[str, Any]]] = {}
    for transcript in transcripts:
        transcripts_by_video.setdefault(int(transcript["video_id"]), []).append(transcript)
    for video in videos:
        video["tags"] = video_tags.get(int(video["id"]), [])
        video["transcripts"] = transcripts_by_video.get(int(video["id"]), [])
    source["videos"] = videos
    source["thumbnail_url"] = (
        str(videos[0]["thumbnail_url"])
        if videos and videos[0].get("thumbnail_url")
        else str(source.get("thumbnail_url") or "")
    )
    return source


def get_youtube_video(video_id: int) -> dict[str, Any] | None:
    with get_youtube_db() as conn:
        row = conn.execute(
            """
            SELECT video.*,
                   source.name AS source_name,
                   source.alias AS source_alias,
                   source.source_url AS source_url,
                   source.thumbnail_url AS source_thumbnail_url
            FROM youtube_videos video
            JOIN youtube_sources source ON source.id = video.source_id
            WHERE video.id = ?
            """,
            (video_id,),
        ).fetchone()
        if not row:
            return None

        video = dict(row)
        source_tags = youtube_tags_for(conn, "youtube_source_tags", "source_id")
        video_tags = youtube_tags_for(conn, "youtube_video_tags", "video_id")

    video["source_tags"] = source_tags.get(int(video["source_id"]), [])
    video["tags"] = video_tags.get(int(video["id"]), [])
    video["transcripts"] = get_youtube_transcripts(int(video["id"]))
    return video


def get_youtube_video_by_youtube_id(youtube_video_id: str) -> dict[str, Any] | None:
    with get_youtube_db() as conn:
        row = conn.execute(
            "SELECT id FROM youtube_videos WHERE video_id = ?",
            (youtube_video_id,),
        ).fetchone()

    return get_youtube_video(int(row["id"])) if row else None


def get_youtube_transcripts(video_id: int) -> list[dict[str, Any]]:
    with get_youtube_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM youtube_transcripts
            WHERE video_id = ?
            ORDER BY updated_at DESC, language_code
            """,
            (video_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_youtube_transcript(video_id: int, language_code: str) -> dict[str, Any] | None:
    with get_youtube_db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM youtube_transcripts
            WHERE video_id = ? AND language_code = ?
            """,
            (video_id, language_code),
        ).fetchone()
    return dict(row) if row else None


def first_saved_youtube_transcript_path(video: dict[str, Any]) -> str:
    for transcript in video.get("transcripts", []):
        rel_path = str(transcript.get("markdown_rel_path") or "")
        if not rel_path:
            continue
        try:
            transcript_path = youtube_transcript_abs_path(rel_path)
        except ValueError:
            continue
        if transcript_path.exists():
            return rel_path
    return ""


def save_youtube_transcript_record(
    video_id: int,
    doc: Any,
    markdown_rel_path: str,
) -> dict[str, Any]:
    timestamp = now_iso()
    language_code = str(transcript_value(doc, "language_code") or "")
    language_name = str(transcript_value(doc, "language_name") or language_code)
    with get_youtube_db() as conn:
        conn.execute(
            """
            INSERT INTO youtube_transcripts
                (video_id, language_code, language_name, is_generated, markdown_rel_path,
                 segment_count, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id, language_code) DO UPDATE SET
                language_name = excluded.language_name,
                is_generated = excluded.is_generated,
                markdown_rel_path = excluded.markdown_rel_path,
                segment_count = excluded.segment_count,
                fetched_at = excluded.fetched_at,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                language_code,
                language_name,
                1 if transcript_value(doc, "is_generated") else 0,
                markdown_rel_path,
                int(transcript_value(doc, "segment_count") or 0),
                str(transcript_value(doc, "fetched_at") or ""),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()

    existing = get_youtube_transcript(video_id, language_code)
    if not existing:
        raise RuntimeError("Could not save transcript record")
    return existing


def write_youtube_transcript(video: dict[str, Any], doc: Any) -> dict[str, Any]:
    language_code = str(transcript_value(doc, "language_code") or "")
    rel_path = youtube_transcript_rel_path(video, language_code)
    path = youtube_transcript_abs_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(youtube_transcript_markdown(video, doc), encoding="utf-8")
    return save_youtube_transcript_record(int(video["id"]), doc, rel_path)


def build_youtube_bookmarklet(base_url: str) -> str:
    capture_url = f"{base_url.rstrip('/')}/youtube/capture"
    return (
        "javascript:(()=>{"
        "const owner=document.querySelector('ytd-watch-metadata ytd-channel-name a')"
        "||document.querySelector('ytd-video-owner-renderer ytd-channel-name a')"
        "||document.querySelector('#owner-name a');"
        "const channel=owner?.textContent?.trim()||'';"
        f"const url=new URL('{capture_url}');"
        "url.searchParams.set('url',location.href);"
        "url.searchParams.set('title',document.title.replace(/\\s+-\\s+YouTube\\s*$/i,''));"
        "if(channel)url.searchParams.set('source',channel);"
        "if(owner?.href)url.searchParams.set('source_url',owner.href);"
        "window.open(url.toString(),'_blank')"
        "})()"
    )


def get_lcars_lab_status() -> dict[str, Any]:
    session_name = "lcars_lab"
    tmux_running = False
    try:
        completed = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True, timeout=3, check=False)
        tmux_running = completed.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tmux_running = False

    matching_server: dict[str, Any] | None = None
    app_dir_text = str(APP_DIR.resolve())

    try:
        servers = list(list_running_servers())
    except Exception:
        servers = []

    for server in servers:
        root_dir = str(server.get("root_dir") or server.get("notebook_dir") or "")
        if root_dir and (root_dir == app_dir_text or root_dir.startswith(app_dir_text)):
            matching_server = {
                "url": server.get("url", ""),
                "token": server.get("token", ""),
                "root_dir": root_dir,
                "port": server.get("port", ""),
            }
            break

    if matching_server:
        url = matching_server.get("url", "")
        token = matching_server.get("token", "")
        if token and "token=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={token}"
        matching_server["open_url"] = url

    return {
        "session": session_name,
        "tmux_running": tmux_running,
        "jupyter_running": matching_server is not None,
        "server": matching_server,
        "app_dir": app_dir_text,
        "status": "UP" if matching_server else ("STARTING" if tmux_running else "DOWN"),
    }


def start_lcars_lab() -> tuple[bool, str]:
    session_name = "lcars_lab"
    status = get_lcars_lab_status()
    if status.get("tmux_running"):
        return True, "tmux session already exists"

    try:
        completed = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", str(APP_DIR.resolve()), "make up"],
            capture_output=True, text=True, timeout=8, check=False
        )
    except FileNotFoundError:
        return False, "tmux is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return False, "tmux start timed out"

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "tmux start failed"
        return False, detail

    return True, "started lcars_lab"




def load_aws_servers() -> list[dict[str, Any]]:
    default_config = {
        "servers": [
            {
                "name": "GPU SERVER",
                "region": "us-east-1",
                "instance_id": "i-xxxxxxxxxxxxxxxxx",
                "jupyter_url": "http://YOUR_ELASTIC_IP:8888",
                "ssh_hint": "ssh ubuntu@YOUR_ELASTIC_IP",
                "enabled": False
            }
        ]
    }

    if not AWS_CONFIG_PATH.exists():
        AWS_CONFIG_PATH.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
        return []

    try:
        raw = json.loads(AWS_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    servers = raw.get("servers", []) if isinstance(raw, dict) else []
    cleaned: list[dict[str, Any]] = []

    for item in servers:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue

        region = str(item.get("region") or "").strip()
        instance_id = str(item.get("instance_id") or "").strip()
        if not region or not instance_id:
            continue

        cleaned.append({
            "name": str(item.get("name") or "AWS SERVER"),
            "region": region,
            "instance_id": instance_id,
            "jupyter_url": str(item.get("jupyter_url") or ""),
            "ssh_hint": str(item.get("ssh_hint") or ""),
            "notes": str(item.get("notes") or ""),
        })

    return cleaned


def aws_server_by_instance(instance_id: str) -> dict[str, Any] | None:
    for server in load_aws_servers():
        if server.get("instance_id") == instance_id:
            return server
    return None


def aws_ec2_client(region: str) -> Any:
    if boto3 is None:
        raise RuntimeError("boto3 is not installed. Run: pip install boto3")
    return boto3.client("ec2", region_name=region)


def get_aws_instance_status(server: dict[str, Any]) -> dict[str, Any]:
    base = {
        **server,
        "state": "UNKNOWN",
        "state_code": None,
        "public_ip": "",
        "private_ip": "",
        "launch_time": "",
        "error": "",
    }

    try:
        ec2 = aws_ec2_client(str(server["region"]))
        response = ec2.describe_instances(InstanceIds=[server["instance_id"]])
        reservations = response.get("Reservations", [])
        instances = reservations[0].get("Instances", []) if reservations else []
        instance = instances[0] if instances else None

        if not instance:
            base["error"] = "Instance not found"
            return base

        state = instance.get("State", {})
        launch_time = instance.get("LaunchTime")

        base.update({
            "state": str(state.get("Name") or "UNKNOWN").upper(),
            "state_code": state.get("Code"),
            "public_ip": str(instance.get("PublicIpAddress") or ""),
            "private_ip": str(instance.get("PrivateIpAddress") or ""),
            "launch_time": launch_time.isoformat() if launch_time else "",
        })
        return base
    except Exception as exc:
        base["error"] = str(exc)
        return base


def get_aws_statuses() -> list[dict[str, Any]]:
    return [get_aws_instance_status(server) for server in load_aws_servers()]


def aws_instance_action(instance_id: str, action: str) -> tuple[bool, str, dict[str, Any] | None]:
    server = aws_server_by_instance(instance_id)
    if not server:
        return False, "Instance is not configured/enabled in aws_servers.json", None

    try:
        ec2 = aws_ec2_client(str(server["region"]))
        if action == "start":
            ec2.start_instances(InstanceIds=[instance_id])
            message = "Start requested"
        elif action == "stop":
            ec2.stop_instances(InstanceIds=[instance_id])
            message = "Stop requested"
        else:
            return False, "Invalid AWS action", None

        return True, message, get_aws_instance_status(server)
    except Exception as exc:
        return False, str(exc), get_aws_instance_status(server)



@app.get("/")
def dashboard() -> str:
    listing = get_directory_listing("")
    return render_template(
        "dashboard.html",
        status=get_system_status(),
        listing=listing,
        link_tree=load_link_tree(),
        logs=[
            "BOOT: LCARS interface ready",
            "STATUS: system telemetry initialized",
            "FILES: home directory indexed",
        ],
    )

@app.get("/jupyter")
def jupyter_page() -> str:
    return render_template("jupyter.html", servers=get_all_jupyter_servers())

@app.get("/books")
def books_page() -> str:
    return render_template(
        "books.html",
        books=get_books(),
        local_pdfs=get_local_pdfs(),
        s3_books=get_s3_books(),
        s3_library=s3_library_status(),
    )


@app.get("/pdf/<path:book_id>")
def local_pdf_page(book_id: str) -> Any:
    try:
        pdf_path = safe_local_pdf_path(book_id)
    except ValueError:
        abort(404)
    if not pdf_path.exists():
        abort(404)
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=pdf_path.name,
    )


@app.get("/book/<book_id>")
def open_s3_book(book_id: str) -> Any:
    book = s3_book_by_id(book_id)
    if not book:
        abort(404)
    try:
        return redirect(build_s3_book_url(book["filename"]))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

@app.get("/reader/<path:book_id>")
def reader_page(book_id: str) -> str:
    try:
        book_path = safe_book_path(book_id)
    except ValueError:
        abort(404)
    return render_template(
        "reader.html",
        book_id=book_id,
        book_name=book_path.stem.replace("_", " ").replace("-", " ").title(),
    )

@app.get("/markdown")
def markdown_page() -> str:
    query = request.args.get("q", "").strip()[:200]
    search_mode = "grep" if request.args.get("mode", "").strip().lower() == "grep" else "names"
    try:
        scope = get_markdown_scope(request.args.get("folder", ""))
    except ValueError:
        abort(404)
    if search_mode == "grep" and query:
        scope["docs"] = search_markdown_contents(scope["docs"], query)

    navigation_params: dict[str, str] = {}
    if search_mode == "grep":
        navigation_params["mode"] = "grep"
    if query:
        navigation_params["q"] = query
    for folder in [*scope["breadcrumbs"], *scope["children"]]:
        params = dict(navigation_params)
        if folder["path"]:
            params["folder"] = folder["path"]
        folder["url"] = url_for("markdown_page", **params)

    return render_template(
        "markdown_list.html",
        **scope,
        query=query,
        search_mode=search_mode,
    )

@app.get("/youtube")
def youtube_page() -> str:
    query = request.args.get("q", "").strip()
    selected_tags = parse_tag_list("\n".join(request.args.getlist("tag")))
    view = "items" if request.args.get("view", "").strip().lower() == "items" else "sources"
    notice = request.args.get("notice", "").strip()
    sources = get_youtube_sources(query, selected_tags) if view == "sources" else []
    items = get_youtube_items(query, selected_tags) if view == "items" else []
    results = sources if view == "sources" else items
    source_count, video_count = get_youtube_library_counts()
    selected_tag_keys = {youtube_tag_key(tag) for tag in selected_tags}
    available_tag_keys = set(selected_tag_keys)
    for result in results:
        available_tag_keys.update(youtube_tag_key(tag) for tag in result.get("tags", []))
    tag_filters: list[dict[str, Any]] = []
    tag_labels = get_youtube_tag_labels()
    known_tag_keys = {youtube_tag_key(tag) for tag in tag_labels}
    tag_labels.extend(
        tag for tag in selected_tags if youtube_tag_key(tag) not in known_tag_keys
    )
    for tag in sorted(tag_labels, key=str.casefold):
        active = youtube_tag_key(tag) in selected_tag_keys
        if not active and youtube_tag_key(tag) not in available_tag_keys:
            continue
        next_tags = (
            [selected for selected in selected_tags if youtube_tag_key(selected) != youtube_tag_key(tag)]
            if active
            else [*selected_tags, tag]
        )
        params: dict[str, Any] = {"tag": next_tags}
        if query:
            params["q"] = query
        if view == "items":
            params["view"] = "items"
        tag_filters.append(
            {"label": tag, "active": active, "url": url_for("youtube_page", **params)}
        )
    all_params = {"q": query} if query else {}
    if view == "items":
        all_params["view"] = "items"
    shared_view_params: dict[str, Any] = {"tag": selected_tags}
    if query:
        shared_view_params["q"] = query
    return render_template(
        "youtube.html",
        query=query,
        selected_tags=selected_tags,
        view=view,
        tag_filters=tag_filters,
        all_tags_url=url_for("youtube_page", **all_params),
        sources_url=url_for("youtube_page", **shared_view_params),
        items_url=url_for("youtube_page", view="items", **shared_view_params),
        notice=notice,
        sources=sources,
        items=items,
        source_count=source_count,
        video_count=video_count,
        bookmarklet=build_youtube_bookmarklet(request.host_url),
    )


@app.get("/youtube/capture")
def youtube_capture() -> Any:
    raw_url = request.args.get("url", "").strip()
    raw_title = request.args.get("title", "").strip()
    raw_source = request.args.get("source", "").strip()
    raw_source_url = request.args.get("source_url", "").strip()
    error = ""
    video_id = ""
    canonical_url = raw_url
    thumbnail_url = ""
    default_title = ""
    default_source_name = ""
    default_source_url = ""
    if raw_url:
        try:
            video_id = parse_youtube_video_id(raw_url)
            existing_video = get_youtube_video_by_youtube_id(video_id)
            if existing_video:
                return redirect(url_for(
                    "youtube_video_edit",
                    video_id=existing_video["id"],
                    notice="ALREADY SAVED",
                ))
            defaults = youtube_metadata_defaults(video_id, raw_title, raw_source, raw_source_url, raw_url)
            canonical_url = defaults["url"]
            thumbnail_url = defaults["thumbnail_url"]
            default_title = defaults["title"]
            default_source_name = defaults["source_name"]
            default_source_url = defaults["source_url"]
        except ValueError as exc:
            error = str(exc)

    return render_template(
        "youtube_capture.html",
        error=error,
        raw_url=raw_url,
        video_id=video_id,
        canonical_url=canonical_url,
        thumbnail_url=thumbnail_url,
        default_title=default_title,
        default_source_name=default_source_name or YOUTUBE_INBOX_SOURCE,
        default_source_url=default_source_url,
        default_source_alias="",
        default_source_tags="",
        default_video_tags="",
        default_video_notes="",
    )


@app.post("/youtube/capture")
def youtube_capture_save() -> Any:
    try:
        submitted_video_id = request.form.get("video_id", "").strip() or parse_youtube_video_id(request.form.get("url", ""))
        existing_video = get_youtube_video_by_youtube_id(submitted_video_id)
    except ValueError:
        existing_video = None

    if existing_video:
        return redirect(url_for(
            "youtube_video_edit",
            video_id=existing_video["id"],
            notice="ALREADY SAVED",
        ))

    try:
        result = save_youtube_video(dict(request.form.items()))
    except ValueError as exc:
        return render_template(
            "youtube_capture.html",
            error=str(exc),
            raw_url=request.form.get("url", ""),
            video_id=request.form.get("video_id", ""),
            canonical_url=request.form.get("url", ""),
            thumbnail_url=(
                youtube_thumbnail_url(request.form.get("video_id", ""))
                if request.form.get("video_id", "")
                else ""
            ),
            default_title=request.form.get("title", ""),
            default_source_name=request.form.get("source_name", "") or YOUTUBE_INBOX_SOURCE,
            default_source_url=request.form.get("source_url", ""),
            default_source_alias=request.form.get("source_alias", ""),
            default_source_tags=request.form.get("source_tags", ""),
            default_video_tags=request.form.get("video_tags", ""),
            default_video_notes=request.form.get("video_notes", ""),
        ), 400

    return redirect(url_for("youtube_source", source_id=result["source_id"]))


@app.post("/youtube/enrich")
def youtube_enrich() -> Any:
    summary = enrich_youtube_library()
    notice = (
        f"INBOX SCAN: CHECKED {summary['checked']}, UPDATED {summary['updated']}, "
        f"SKIPPED {summary['skipped']}"
    )
    return redirect(url_for("youtube_page", notice=notice))


@app.post("/youtube/video/<int:video_id>/delete")
def youtube_video_delete(video_id: int) -> Any:
    result = delete_youtube_video(video_id)
    if not result["deleted"]:
        return redirect(url_for("youtube_page", notice="VIDEO NOT FOUND"))
    if result["source_deleted"]:
        return redirect(url_for("youtube_page", notice="DELETED VIDEO AND EMPTY SOURCE"))
    return redirect(url_for("youtube_source", source_id=result["source_id"], notice="DELETED VIDEO"))


@app.get("/youtube/video/<int:video_id>/edit")
def youtube_video_edit(video_id: int) -> str:
    video = get_youtube_video(video_id)
    if not video:
        abort(404)

    notice = request.args.get("notice", "").strip()
    return render_template("youtube_edit.html", video=video, error="", notice=notice)


@app.get("/youtube/video/<int:video_id>/transcript")
def youtube_video_transcript(video_id: int) -> Any:
    video = get_youtube_video(video_id)
    if not video:
        abort(404)

    choose_language = request.args.get("choose", "").strip() == "1"
    existing_rel_path = first_saved_youtube_transcript_path(video)
    if existing_rel_path and not choose_language:
        return redirect(url_for("markdown_view", doc_id=existing_rel_path))

    client = None
    probe_info: dict[str, Any] = {}
    error = ""
    try:
        client = transcript_client()
        probe_info = client.probe(str(video["video_id"]), include_metadata=False)
    except Exception as exc:
        error = str(exc)

    return render_template(
        "youtube_transcript.html",
        video=video,
        probe=probe_info,
        languages=probe_info.get("available_languages", []),
        existing_transcripts=video.get("transcripts", []),
        using_proxy=bool(getattr(client, "using_proxy", False)),
        error=error,
    )


@app.post("/youtube/video/<int:video_id>/transcript")
def youtube_video_transcript_fetch(video_id: int) -> Any:
    video = get_youtube_video(video_id)
    if not video:
        abort(404)

    language_code = request.form.get("language_code", "").strip()
    if not language_code:
        return redirect(url_for("youtube_video_transcript", video_id=video_id))

    existing = get_youtube_transcript(video_id, language_code)
    if existing:
        existing_path = youtube_transcript_abs_path(str(existing["markdown_rel_path"]))
        if existing_path.exists():
            return redirect(url_for("markdown_view", doc_id=existing["markdown_rel_path"]))

    client = None
    probe_info: dict[str, Any] = {}
    try:
        client = transcript_client()
        doc = client.fetch(str(video["video_id"]), language_code, include_metadata=False)
        record = write_youtube_transcript(video, doc)
        return redirect(url_for("markdown_view", doc_id=record["markdown_rel_path"]))
    except Exception as exc:
        try:
            if client:
                probe_info = client.probe(str(video["video_id"]), include_metadata=False)
        except Exception:
            probe_info = {}

        return render_template(
            "youtube_transcript.html",
            video=video,
            probe=probe_info,
            languages=probe_info.get("available_languages", []),
            existing_transcripts=get_youtube_transcripts(video_id),
            using_proxy=bool(getattr(client, "using_proxy", False)),
            error=str(exc),
        ), 400


@app.post("/youtube/video/<int:video_id>/edit")
def youtube_video_update(video_id: int) -> Any:
    video = get_youtube_video(video_id)
    if not video:
        abort(404)

    form = dict(request.form.items())
    form["video_id"] = str(video["video_id"])
    form["url"] = str(video["url"])
    form["replace_source_identity"] = "1"
    form["replace_source_tags"] = "1"

    try:
        result = save_youtube_video(form)
    except ValueError as exc:
        edited_video = {**video, **form}
        edited_video["source_name"] = form.get("source_name", video.get("source_name", ""))
        edited_video["source_alias"] = form.get("source_alias", video.get("source_alias", ""))
        edited_video["source_url"] = form.get("source_url", video.get("source_url", ""))
        edited_video["source_tags"] = parse_tag_list(form.get("source_tags", ""))
        edited_video["tags"] = parse_tag_list(form.get("video_tags", ""))
        edited_video["notes"] = form.get("video_notes", video.get("notes", ""))
        return render_template("youtube_edit.html", video=edited_video, error=str(exc), notice=""), 400

    return redirect(url_for("youtube_source", source_id=result["source_id"], notice="UPDATED VIDEO"))


@app.post("/youtube/source/<int:source_id>/delete")
def youtube_source_delete(source_id: int) -> Any:
    try:
        result = delete_youtube_source(source_id)
    except ValueError as exc:
        return redirect(url_for("youtube_source", source_id=source_id, notice=str(exc).upper()))

    notice = "DELETED EMPTY SOURCE" if result["deleted"] else "SOURCE NOT FOUND"
    return redirect(url_for("youtube_page", notice=notice))


@app.get("/youtube/source/<int:source_id>")
def youtube_source(source_id: int) -> str:
    source = get_youtube_source(source_id)
    if not source:
        abort(404)
    notice = request.args.get("notice", "").strip()
    return render_template("youtube_source.html", source=source, notice=notice)


@app.get("/md/view/<path:doc_id>")
def markdown_view(doc_id: str) -> Any:
    try:
        doc_path = safe_markdown_path(doc_id)
    except ValueError:
        try:
            folder_path = safe_markdown_folder_path(doc_id)
        except ValueError:
            abort(404)
        folder = folder_path.relative_to(MARKDOWN_DIR).as_posix()
        return redirect(url_for("markdown_page", folder=f"{folder}/"))
    if not doc_path.exists():
        abort(404)
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    return render_template(
        "markdown_view.html",
        doc_id=doc_id,
        doc_name=doc_path.stem.replace("_", " ").replace("-", " ").title(),
        rendered=render_markdown(text),
        source_text=text,
        file_path=doc_path.relative_to(MARKDOWN_DIR).as_posix(),
    )

@app.get("/md/edit/<path:doc_id>")
def markdown_edit(doc_id: str) -> str:
    try:
        doc_path = safe_markdown_path(doc_id)
    except ValueError:
        abort(404)
    if not doc_path.exists():
        abort(404)
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    return render_template(
        "markdown_edit.html",
        doc_id=doc_id,
        doc_name=doc_path.stem.replace("_", " ").replace("-", " ").title(),
        source_text=text,
        file_path=doc_path.relative_to(MARKDOWN_DIR).as_posix(),
    )


@app.get("/tmux")
def tmux_page() -> str:
    return render_template("tmux.html", sessions=get_tmux_sessions())

@app.get("/api/tmux/sessions")
def api_tmux_sessions() -> Any:
    return jsonify({"ok": True, "sessions": get_tmux_sessions()})


@app.get("/md/new")
def markdown_new() -> str:
    return render_template("markdown_new.html")

@app.post("/api/markdown/create")
def api_markdown_create() -> Any:
    payload = request.get_json(silent=True) or {}
    title = payload.get("title", "")
    if not isinstance(title, str) or not title.strip():
        return jsonify({"ok": False, "error": "Title is required"}), 400

    folder = payload.get("folder", "")
    if not isinstance(folder, str):
        folder = ""

    raw_title = title.strip()
    if folder.strip() and "/" not in raw_title:
        raw_path = f"{folder.strip().strip('/')}/{raw_title}"
    else:
        raw_path = raw_title

    MARKDOWN_DIR.mkdir(exist_ok=True)
    path = unique_markdown_path_from_rel(raw_path)
    heading = title.strip().split("/")[-1].strip()
    path.write_text(f"# {heading}\n\n", encoding="utf-8")

    return jsonify({
        "ok": True,
        "id": path.relative_to(MARKDOWN_DIR).as_posix(),
        "name": path.stem.replace("_", " ").replace("-", " ").title(),
    })


@app.get("/api/links")
def api_links() -> Any:
    return jsonify({"ok": True, "links": load_link_tree()})

@app.post("/api/links/add")
def api_links_add() -> Any:
    payload = request.get_json(silent=True) or {}
    path = payload.get("path", "")
    name = payload.get("name", "")
    url = payload.get("url", "")
    if not isinstance(path, str) or not isinstance(name, str) or not isinstance(url, str):
        return jsonify({"ok": False, "error": "Invalid payload"}), 400
    try:
        tree = add_link_to_tree(path, name, url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "links": tree})


@app.post("/api/markdown/delete/<path:doc_id>")
def api_markdown_delete(doc_id: str) -> Any:
    try:
        path = safe_markdown_path(doc_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid markdown path"}), 404
    if not path.exists():
        return jsonify({"ok": False, "error": "Document not found"}), 404
    path.unlink()
    return jsonify({"ok": True})

@app.get("/api/markdown/archive/preview/<folder_id>")
def api_markdown_archive_preview(folder_id: str) -> Any:
    try:
        preview = archive_preview(folder_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "archive": preview})

@app.post("/api/markdown/archive/<folder_id>")
def api_markdown_archive(folder_id: str) -> Any:
    try:
        result = archive_markdown_folder(folder_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "archive": result})

@app.post("/api/book/delete/<path:book_id>")
def api_book_delete(book_id: str) -> Any:
    try:
        path = safe_book_path(book_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid book path"}), 404
    if not path.exists():
        return jsonify({"ok": False, "error": "Book not found"}), 404
    path.unlink()
    return jsonify({"ok": True})

@app.get("/focus")
def focus_page() -> str:
    return render_template("focus.html")


@app.get("/api/focus/config")
def api_focus_config() -> Any:
    return jsonify({"ok": True, "config": load_focus_config()})



@app.post("/api/markdown/rename/<path:doc_id>")
def api_markdown_rename(doc_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    new_name = payload.get("name", "")

    if not isinstance(new_name, str) or not new_name.strip():
        return jsonify({"ok": False, "error": "New name is required"}), 400

    try:
        old_path = safe_markdown_path(doc_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid markdown path"}), 404

    if not old_path.exists():
        return jsonify({"ok": False, "error": "Document not found"}), 404

    cleaned = new_name.strip()
    cleaned = cleaned[:-3] if cleaned.lower().endswith(".md") else cleaned
    slug = markdown_slug_from_title(cleaned)
    new_path = old_path.with_name(f"{slug}.md")

    if new_path.exists() and new_path != old_path:
        return jsonify({"ok": False, "error": "A document with that name already exists"}), 400

    old_path.rename(new_path)
    new_id = new_path.relative_to(MARKDOWN_DIR).as_posix()

    return jsonify({
        "ok": True,
        "id": new_id,
        "url": url_for("markdown_view", doc_id=new_id),
    })



@app.get("/api/lcars-lab/status")
def api_lcars_lab_status() -> Any:
    return jsonify({"ok": True, "lab": get_lcars_lab_status()})


@app.post("/api/lcars-lab/start")
def api_lcars_lab_start() -> Any:
    ok, message = start_lcars_lab()
    status = get_lcars_lab_status()
    http_status = 200 if ok else 500
    return jsonify({"ok": ok, "message": message, "lab": status}), http_status


@app.get("/api/content/config")
def api_content_config() -> Any:
    return jsonify({
        "ok": True,
        "content": {
            "markdown_dir": str(MARKDOWN_DIR),
            "archive_dir": str(ARCHIVE_DIR),
            "books_dir": str(BOOKS_DIR),
            "sounds_dir": str(SOUNDS_DIR),
            "config_path": str(CONTENT_CONFIG_PATH),
            "markdown_exists": MARKDOWN_DIR.exists(),
            "archive_exists": ARCHIVE_DIR.exists(),
            "books_exists": BOOKS_DIR.exists(),
            "sounds_exists": SOUNDS_DIR.exists(),
        }
    })



@app.get("/aws")
def aws_page() -> str:
    return render_template("aws.html")


@app.get("/api/aws/instances")
def api_aws_instances() -> Any:
    return jsonify({
        "ok": True,
        "instances": get_aws_statuses(),
        "config_path": str(AWS_CONFIG_PATH),
        "boto3_available": boto3 is not None,
    })


@app.post("/api/aws/instances/<instance_id>/start")
def api_aws_instance_start(instance_id: str) -> Any:
    ok, message, status = aws_instance_action(instance_id, "start")
    return jsonify({"ok": ok, "message": message, "instance": status}), 200 if ok else 400


@app.post("/api/aws/instances/<instance_id>/stop")
def api_aws_instance_stop(instance_id: str) -> Any:
    ok, message, status = aws_instance_action(instance_id, "stop")
    return jsonify({"ok": ok, "message": message, "instance": status}), 200 if ok else 400


@app.get("/api/status")
def api_status() -> Any:
    return jsonify(get_system_status())

@app.get("/api/files")
def api_files() -> Any:
    payload = get_directory_listing(request.args.get("path", ""))
    return jsonify(payload), 200 if payload.get("ok") else 400

@app.get("/api/jupyter/servers")
def api_jupyter_servers() -> Any:
    return jsonify({"ok": True, "servers": get_all_jupyter_servers()})

@app.get("/api/books")
def api_books() -> Any:
    return jsonify({
        "ok": True,
        "books": get_books(),
        "local_pdfs": get_local_pdfs(),
    })

@app.get("/api/s3/books")
def api_s3_books() -> Any:
    return jsonify({
        "ok": True,
        "books": get_s3_books(),
        "s3_library": s3_library_status(),
    })

@app.get("/api/s3/book/<book_id>")
def api_s3_book(book_id: str) -> Any:
    book = s3_book_by_id(book_id)
    if not book:
        return jsonify({"ok": False, "error": "Book not found"}), 404
    try:
        url = build_s3_book_url(book["filename"])
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    return jsonify({"ok": True, "book": book, "url": url})

@app.post("/api/s3/book/<book_id>/open")
def api_s3_book_open(book_id: str) -> Any:
    book = s3_book_by_id(book_id)
    if not book:
        return jsonify({"ok": False, "error": "Book not found"}), 404

    try:
        cache = ensure_s3_book_cached(book)
        open_local_file(cache["path"])
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

    return jsonify({
        "ok": True,
        "book": add_s3_book_cache_fields(book),
        "downloaded": cache["downloaded"],
        "path": str(cache["path"]),
    })

@app.get("/api/book/<path:book_id>")
def api_book(book_id: str) -> Any:
    try:
        path = safe_book_path(book_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid book path"}), 404

    if not path.exists():
        return jsonify({"ok": False, "error": "Book not found"}), 404

    text = path.read_text(encoding="utf-8", errors="replace")
    return jsonify({
        "ok": True,
        "id": book_id,
        "name": path.stem.replace("_", " ").replace("-", " ").title(),
        "path": path.relative_to(BOOKS_DIR).as_posix(),
        "text": text,
    })

@app.get("/api/markdown")
def api_markdown_docs() -> Any:
    return jsonify({"ok": True, "docs": get_markdown_docs()})

@app.get("/api/markdown/<path:doc_id>")
def api_markdown_doc(doc_id: str) -> Any:
    try:
        path = safe_markdown_path(doc_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid markdown path"}), 404

    if not path.exists():
        return jsonify({"ok": False, "error": "Document not found"}), 404

    text = path.read_text(encoding="utf-8", errors="replace")
    return jsonify({
        "ok": True,
        "id": doc_id,
        "name": path.stem.replace("_", " ").replace("-", " ").title(),
        "path": path.relative_to(MARKDOWN_DIR).as_posix(),
        "text": text,
        "rendered": render_markdown(text),
        "mtime": path.stat().st_mtime,
    })

@app.post("/api/markdown/save/<path:doc_id>")
def api_markdown_save(doc_id: str) -> Any:
    try:
        path = safe_markdown_path(doc_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid markdown path"}), 404

    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    if not isinstance(text, str):
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return jsonify({"ok": True, "mtime": path.stat().st_mtime})

@app.post("/api/action/<action_name>")
def run_action(action_name: str) -> Any:
    command = ALLOWED_ACTIONS.get(action_name)
    if command is None:
        return jsonify({"ok": False, "error": "Unknown action"}), 404

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return jsonify(
            {
                "ok": completed.returncode == 0,
                "action": action_name,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Command timed out"}), 500

@app.post("/api/reveal")
def reveal() -> Any:
    payload = request.get_json(silent=True) or {}
    raw_path = payload.get("path", "")
    if not raw_path:
        return jsonify({"ok": False, "error": "Missing path"}), 400

    try:
        target = safe_path(raw_path)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    if not target.exists():
        return jsonify({"ok": False, "error": "Path does not exist"}), 404

    completed = subprocess.run(
        ["open", "-R", str(target)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return jsonify(
        {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
