from __future__ import annotations

import json
import os
import platform
import socket
import re
import subprocess
from pathlib import Path
from html import escape
from typing import Any

import markdown as mdlib
import psutil

try:
    import boto3
except ImportError:
    boto3 = None
from flask import Flask, abort, jsonify, render_template, request
from jupyter_server.serverapp import list_running_servers

app = Flask(__name__)
BASE_DIR = Path.home()
APP_DIR = Path(__file__).parent
CONTENT_CONFIG_PATH = APP_DIR / "content_config.json"
AWS_CONFIG_PATH = APP_DIR / "aws_servers.json"
REMOTE_CONFIG_PATH = APP_DIR / "remote_jupyter_servers.json"
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


def ensure_content_dirs() -> None:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)


ensure_content_dirs()
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
    semantic = render_semantic_markdown(normalized)
    return mdlib.markdown(
        semantic,
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





def parse_matrix_marker(line: str) -> tuple[int, int, str] | None:
    match = re.match(r"^##\s+Matrix\s*\((\d+)x(\d+)\)\s*(.*)$", line.strip(), re.I)
    if not match:
        return None

    rows = int(match.group(1))
    cols = int(match.group(2))
    suffix = match.group(3).strip(" -:")
    title = suffix if suffix else f"Matrix ({rows}x{cols})"

    if rows < 1 or cols < 1 or rows > 6 or cols > 6:
        return None

    return rows, cols, title


def parse_matrix_section_title(line: str) -> str | None:
    match = re.match(r"^###\s+(.+?)\s*$", line.strip())
    if not match:
        return None
    return match.group(1).strip()


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

    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


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

    return (
        f'<div class="lcars-matrix-block" data-rows="{rows}" data-cols="{cols}">'
        f'<div class="lcars-matrix-heading">{escape(title)}</div>'
        f'<div class="lcars-matrix-grid" style="grid-template-columns: repeat({cols}, minmax(0, 1fr));">'
        + "".join(cells) +
        '</div></div>'
    )


def extract_matrix_block(lines: list[str], start: int) -> tuple[str | None, int]:
    marker = parse_matrix_marker(lines[start])
    if not marker:
        return None, start

    rows, cols, title = marker
    required_sections = rows * cols

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
    return render_template(
        "markdown_list.html",
        docs=get_markdown_docs(),
        markdown_folders=get_markdown_folders(),
    )

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
            "books_dir": str(BOOKS_DIR),
            "sounds_dir": str(SOUNDS_DIR),
            "config_path": str(CONTENT_CONFIG_PATH),
            "markdown_exists": MARKDOWN_DIR.exists(),
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
    app.run(host="127.0.0.1", port=5050, debug=True)
