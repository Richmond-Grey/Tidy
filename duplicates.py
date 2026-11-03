"""Finding byte-for-byte duplicate files. No UI imports."""
import hashlib
import os
import re
import threading
from typing import Callable

from sorter import should_skip

_CHUNK = 1024 * 1024
_HEAD = 64 * 1024


def _hash(path: str, limit: int | None = None) -> str | None:
    digest = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as f:
            if limit:
                digest.update(f.read(limit))
            else:
                while chunk := f.read(_CHUNK):
                    digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _walk(root: str, recursive: bool):
    if not recursive:
        for entry in os.scandir(root):
            if entry.is_file() and not should_skip(entry.name):
                yield entry.path
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not should_skip(name):
                yield os.path.join(dirpath, name)


def find_duplicates(root: str, recursive: bool = True, min_size: int = 1,
                    progress: Callable[[str], None] | None = None,
                    cancel: threading.Event | None = None) -> list[list[str]]:
    """Groups of identical files (two or more each), biggest wasted space first.

    Compares size, then the first 64 KB, then the full contents, so large
    folders are cheap to scan.
    """
    by_size: dict[int, list[str]] = {}
    for path in _walk(root, recursive):
        if cancel and cancel.is_set():
            return []
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size >= min_size:
            by_size.setdefault(size, []).append(path)

    candidates = [paths for paths in by_size.values() if len(paths) > 1]
    groups: list[list[str]] = []
    for i, paths in enumerate(candidates, 1):
        if progress:
            progress(f"Comparing files… {i}/{len(candidates)}")
        by_head: dict[str, list[str]] = {}
        for p in paths:
            if cancel and cancel.is_set():
                return []
            if (h := _hash(p, _HEAD)) is not None:
                by_head.setdefault(h, []).append(p)
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            by_full: dict[str, list[str]] = {}
            for p in same_head:
                if cancel and cancel.is_set():
                    return []
                if (h := _hash(p)) is not None:
                    by_full.setdefault(h, []).append(p)
            groups.extend(sorted(g, key=keeper_rank) for g in by_full.values() if len(g) > 1)

    groups.sort(key=lambda g: -os.path.getsize(g[0]) * (len(g) - 1) if os.path.exists(g[0]) else 0)
    return groups


def keeper_rank(path: str):
    """Sort key: the copy to keep comes first ('report.pdf' before 'report (1).pdf', older first)."""
    name = os.path.basename(path)
    is_copy = bool(re.search(r"\(\d+\)|\bcopy\b|- copy", name, re.I))
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    return is_copy, len(name), mtime


def send_to_trash(paths: list[str]) -> list[tuple[str, str]]:
    """Move files to the Recycle Bin / Trash. Returns [(path, error)] for failures."""
    from send2trash import send2trash

    failures = []
    for p in paths:
        try:
            send2trash(p)
        except Exception as e:  # send2trash raises a mix of OSError and its own types
            failures.append((p, str(e)))
    return failures


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
