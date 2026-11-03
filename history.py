"""Undo history: every move Tidy makes is journalled so it can be put back.

Thread-safe (the folder watcher records from a background thread). No UI imports.
"""
import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field

MAX_ENTRIES = 2000


@dataclass
class HistoryEntry:
    id: int
    time: float
    kind: str               # "sort", "group", "rename", "subtitle", "duplicate"
    label: str              # what the user sees, e.g. 'report.pdf → pdf/'
    moves: list[list[str]]  # [[source, destination], ...]
    undone: bool = False
    undoable: bool = True


@dataclass
class UndoOutcome:
    restored: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class History:
    def __init__(self, path: str | None = None):
        self.path = path
        self._lock = threading.Lock()
        self._entries: list[HistoryEntry] = []
        self._next_id = 1
        self._load()

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self._entries = [HistoryEntry(**item) for item in raw]
            self._next_id = max((e.id for e in self._entries), default=0) + 1
        except (OSError, ValueError, TypeError):
            self._entries = []  # a corrupt journal shouldn't stop the app

    def _save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([asdict(e) for e in self._entries], f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def record(self, kind: str, label: str, moves: list[tuple[str, str]], undoable: bool = True) -> HistoryEntry:
        with self._lock:
            entry = HistoryEntry(self._next_id, time.time(), kind, label,
                                 [list(m) for m in moves], undoable=undoable)
            self._next_id += 1
            self._entries.append(entry)
            del self._entries[:-MAX_ENTRIES]
            self._save()
            return entry

    def entries(self) -> list[HistoryEntry]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._entries))

    def get(self, entry_id: int) -> HistoryEntry | None:
        with self._lock:
            return next((e for e in self._entries if e.id == entry_id), None)

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()

    def undo(self, entry_ids: list[int]) -> UndoOutcome:
        """Move files back to where they came from. Newest entries are undone first."""
        from sorter import suppress, unique_destination  # avoid an import cycle

        outcome = UndoOutcome()
        with self._lock:
            targets = sorted((e for e in self._entries
                              if e.id in set(entry_ids) and not e.undone and e.undoable),
                             key=lambda e: e.id, reverse=True)
            for entry in targets:
                ok = True
                for source, destination in reversed(entry.moves):
                    if not os.path.exists(destination):
                        # Deleted or moved by the user since; nothing left to put back
                        outcome.errors.append(f"{os.path.basename(destination)} no longer exists")
                        continue
                    try:
                        parent = os.path.dirname(source)
                        os.makedirs(parent, exist_ok=True)
                        target = unique_destination(parent, os.path.basename(source))
                        suppress(target)  # stop a running watcher from sorting it straight back
                        shutil.move(destination, target)
                        outcome.restored.append(target)
                        _remove_if_empty(os.path.dirname(destination))
                    except OSError as e:
                        outcome.errors.append(f"{os.path.basename(destination)}: {e}")
                        ok = False
                entry.undone = ok
            self._save()
        return outcome


def _remove_if_empty(folder: str):
    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
    except OSError:
        pass
