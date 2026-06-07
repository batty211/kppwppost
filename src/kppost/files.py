from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import ValidationError


def ensure_within(root: Path, path: Path) -> Path:
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValidationError(f"Path escapes batch directory: {path}")
    return resolved


def relative_posix(root: Path, path: Path) -> str:
    return ensure_within(root, path).relative_to(root.resolve()).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

