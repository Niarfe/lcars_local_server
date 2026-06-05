from __future__ import annotations

import json
import os
import platform
import socket
import re
import subprocess
from pathlib import Path
from typing import Any

import markdown as mdlib
import psutil
from flask import Flask, abort, jsonify, render_template, request
from jupyter_server.serverapp import list_running_servers

app = Flask(__name__)
BASE_DIR = Path.home()
APP_DIR = Path(__file__).parent
REMOTE_CONFIG_PATH = APP_DIR / "remote_jupyter_servers.json"
BOOKS_DIR = APP_DIR / "books"
MARKDOWN_DIR = APP_DIR / "markdown"
LINKS_CONFIG_PATH = APP_DIR / "links.json"
FOCUS_CONFIG_PATH = APP_DIR / "focus_config.json"

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

def get_books() -> list[dict[str, str]]:
    BOOKS_DIR.mkdir(exist_ok=True)
    books = []
    for p in sorted(BOOKS_DIR.rglob("*.txt"), key=lambda x: x.name.lower()):
        rel = p.relative_to(BOOKS_DIR).as_posix()
        title = p.stem.replace("_", " ").replace("-", " ").title()
        books.append({"id": rel, "name": title, "path": rel})
    return books

def safe_book_path(book_id: str) -> Path:
    candidate = (BOOKS_DIR / book_id).resolve()
    if not str(candidate).startswith(str(BOOKS_DIR.resolve())):
        raise ValueError("Invalid book path")
    if candidate.suffix.lower() != ".txt":
        raise ValueError("Only .txt files are supported")
    return candidate

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

def render_markdown(text: str) -> str:
    normalized = normalize_markdown_task_lines(text)
    return mdlib.markdown(
        normalized,
        extensions=["fenced_code", "tables", "toc", "sane_lists"]
    )


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



def normalize_markdown_task_lines(text: str) -> str:
    """Allow bare [x] / [ ] checklist lines to render as Markdown task-list bullets."""
    return re.sub(r"(?m)^(\s*)\[(x|X| )\]\s+", r"\1- [\2] ", text)


def markdown_slug_from_title(title: str) -> str:
    cleaned = title.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "untitled"

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
    return render_template("books.html", books=get_books())

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
    return render_template("markdown_list.html", docs=get_markdown_docs())

@app.get("/md/view/<path:doc_id>")
def markdown_view(doc_id: str) -> str:
    try:
        doc_path = safe_markdown_path(doc_id)
    except ValueError:
        abort(404)
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

    MARKDOWN_DIR.mkdir(exist_ok=True)
    path = unique_markdown_path(title)
    heading = title.strip()
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
        "url": f"/md/view/{new_id}",
    })


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
    return jsonify({"ok": True, "books": get_books()})

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
    app.run(host="127.0.0.1", port=5000, debug=True)
