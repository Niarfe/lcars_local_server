"""Persistent references to Markdown folders on this machine."""

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from uuid import uuid4


CONFIG_LOCK = RLock()


def read_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Content configuration must be a JSON object")
    return config


def portable_path(path: Path) -> str:
    try:
        relative = path.relative_to(Path.home())
        return "~" if not relative.parts else f"~/{relative.as_posix()}"
    except ValueError:
        return str(path)


def roots(config_path: Path, primary: Path) -> list[dict]:
    result = [{"id": "markdown", "label": "markdown", "path": str(primary.resolve()), "primary": True}]
    mounts = read_config(config_path).get("markdown_mounts", [])
    if not isinstance(mounts, list):
        raise ValueError("Markdown mounts must be a list")
    seen_ids = {"markdown"}
    seen_paths = {primary.resolve()}
    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        root_id, label, raw_path = (mount.get(key) for key in ("id", "label", "path"))
        if not all(isinstance(value, str) and value.strip() for value in (root_id, label, raw_path)):
            continue
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            continue
        path = path.resolve()
        if root_id in seen_ids or path in seen_paths:
            continue
        seen_ids.add(root_id)
        seen_paths.add(path)
        result.append({"id": root_id, "label": label, "path": str(path), "primary": False})
    for root in result:
        root["display_path"] = portable_path(Path(root["path"]))
        root["available"] = Path(root["path"]).is_dir() and os.access(root["path"], os.R_OK | os.X_OK)
    return result


def write_config(config_path: Path, config: dict) -> None:
    # Replace atomically so a restart cannot read a half-written mount list.
    fd, temporary = tempfile.mkstemp(prefix=".content-config-", dir=config_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, config_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def mount(config_path: Path, primary: Path, raw_path: str, label: str = "") -> dict:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("Choose a folder to mount")
    if not isinstance(label, str):
        raise ValueError("Invalid folder label")
    path = Path(raw_path.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("Use an absolute path or a path starting with ~/")
    path = path.resolve()
    if not path.is_dir():
        raise ValueError("Folder not found")
    if not os.access(path, os.R_OK | os.X_OK):
        raise ValueError("Folder is not readable")
    label = label.strip() or path.name or str(path)
    if len(label) > 100:
        raise ValueError("Folder label must be 100 characters or fewer")
    with CONFIG_LOCK:
        for root in roots(config_path, primary):
            if Path(root["path"]) == path:
                raise ValueError("This folder is already mounted")
        config = read_config(config_path)
        entry = {"id": uuid4().hex, "label": label, "path": portable_path(path)}
        config.setdefault("markdown_mounts", []).append(entry)
        write_config(config_path, config)
        return next(root for root in roots(config_path, primary) if root["id"] == entry["id"])


def unmount(config_path: Path, root_id: str) -> None:
    if root_id == "markdown":
        raise ValueError("The primary Markdown library cannot be unmounted")
    with CONFIG_LOCK:
        config = read_config(config_path)
        mounts = config.get("markdown_mounts", [])
        if not isinstance(mounts, list):
            raise ValueError("Markdown mounts must be a list")
        remaining = [entry for entry in mounts if not isinstance(entry, dict) or entry.get("id") != root_id]
        if len(remaining) == len(mounts):
            raise ValueError("Mounted folder not found")
        config["markdown_mounts"] = remaining
        write_config(config_path, config)


def browse(raw_path: str = "", show_hidden: bool = False) -> dict:
    path = Path(raw_path or Path.home()).expanduser()
    if not path.is_absolute():
        raise ValueError("Use an absolute path or a path starting with ~/")
    path = path.resolve()
    if not path.is_dir():
        raise ValueError("Folder not found")
    children = []
    for child in path.iterdir():
        if (show_hidden or not child.name.startswith(".")) and child.is_dir():
            children.append({"name": child.name, "path": str(child), "display_path": portable_path(child)})
    return {
        "path": str(path),
        "display_path": portable_path(path),
        "parent": str(path.parent),
        "home": str(Path.home()),
        "folders": sorted(children, key=lambda item: item["name"].casefold()),
    }
