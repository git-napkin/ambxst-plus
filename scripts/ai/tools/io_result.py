"""Abstract file reads shared by read_files and apply_file_diffs."""

from __future__ import annotations

from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024

FOUND = "Found"
NOT_FOUND = "NotFound"
READ_ERROR = "ReadError"


class FileReadResult:
    def __init__(self, status, path, content=None, truncated=False, error=None, size=0):
        self.status = status
        self.path = str(path)
        self.content = content
        self.truncated = bool(truncated)
        self.error = error
        self.size = size

    @property
    def found(self):
        return self.status == FOUND

    def to_dict(self):
        return {
            "status": self.status,
            "path": self.path,
            "content": self.content,
            "truncated": self.truncated,
            "error": self.error,
            "size": self.size,
        }


def read_file(path, max_bytes=MAX_FILE_BYTES):
    target = Path(path)
    try:
        if not target.exists() or not target.is_file():
            return FileReadResult(NOT_FOUND, target, error="not found")
        size = target.stat().st_size
        truncated = size > max_bytes
        with open(target, "rb") as fh:
            raw = fh.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            truncated = True
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return FileReadResult(
            FOUND,
            target,
            content=text,
            truncated=truncated,
            size=size,
        )
    except OSError as exc:
        return FileReadResult(READ_ERROR, target, error=str(exc))


def write_file(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
