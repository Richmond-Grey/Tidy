"""Core sorting logic for Tidy.

Kept free of any UI code so the same logic can back the desktop app today
and other front ends (mobile, CLI) later.
"""
import os
import shutil
import time
from dataclasses import dataclass
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Folder used for files that have no extension
NO_EXTENSION_FOLDER = "no_extension"

# Partial downloads are renamed once complete; moving them early breaks the download
TEMP_EXTENSIONS = {"crdownload", "part", "partial", "download", "tmp", "opdownload"}

# System files that must stay where they are
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


@dataclass
class MoveResult:
    """Outcome of sorting a single file."""
    source: str
    destination: str
    error: str | None = None


def folder_for(filename: str) -> str:
    """Name of the subfolder a file belongs in, based on its extension."""
    ext = os.path.splitext(filename)[1][1:].lower()
    return ext or NO_EXTENSION_FOLDER


def should_skip(filename: str) -> bool:
    name = filename.lower()
    if name in IGNORED_NAMES:
        return True
    return os.path.splitext(name)[1][1:] in TEMP_EXTENSIONS


def unique_destination(directory: str, filename: str) -> str:
    """Path inside directory that doesn't clash with an existing file, e.g. 'report (1).pdf'."""
    destination = os.path.join(directory, filename)
    stem, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(destination):
        destination = os.path.join(directory, f"{stem} ({counter}){ext}")
        counter += 1
    return destination


def wait_until_stable(path: str, timeout: float = 10.0, interval: float = 0.5) -> None:
    """Wait until a file stops growing, so files still being written aren't moved."""
    deadline = time.monotonic() + timeout
    last_size = -1
    while time.monotonic() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size == last_size:
            return
        last_size = size
        time.sleep(interval)


def sort_file(root: str, path: str, retries: int = 3) -> MoveResult | None:
    """Move one file into root/<extension>/. Returns None if the file was skipped."""
    filename = os.path.basename(path)
    if not os.path.isfile(path) or should_skip(filename):
        return None

    target_dir = os.path.join(root, folder_for(filename))
    for attempt in range(retries):
        try:
            os.makedirs(target_dir, exist_ok=True)
            destination = unique_destination(target_dir, filename)
            shutil.move(path, destination)
            return MoveResult(path, destination)
        except PermissionError as e:
            # Usually another program still has the file open
            if attempt == retries - 1:
                return MoveResult(path, target_dir, str(e))
            time.sleep(1)
        except OSError as e:
            return MoveResult(path, target_dir, str(e))
    return None


def sort_directory(root: str, on_result: Callable[[MoveResult], None]) -> None:
    """Sort every file currently sitting directly inside root."""
    for entry in sorted(os.listdir(root)):
        result = sort_file(root, os.path.join(root, entry))
        if result:
            on_result(result)


class _Handler(FileSystemEventHandler):
    def __init__(self, root: str, on_result: Callable[[MoveResult], None]):
        self.root = root
        self.on_result = on_result

    def on_created(self, event):
        # Folders (including the ones we create) are left alone
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        # Browsers download to a temp name, then rename it once finished
        if not event.is_directory and _same_path(os.path.dirname(event.dest_path), self.root):
            self._handle(event.dest_path)

    def _handle(self, path: str):
        if should_skip(os.path.basename(path)):
            return
        wait_until_stable(path)
        result = sort_file(self.root, path)
        if result:
            self.on_result(result)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class FolderWatcher:
    """Sorts a folder once, then keeps sorting new files as they arrive.

    on_result is called from background threads; UI code must marshal it
    back to its own thread.
    """

    def __init__(self, root: str, on_result: Callable[[MoveResult], None]):
        self.root = os.path.abspath(root)
        self.on_result = on_result
        self._observer = None

    def start(self) -> None:
        """Blocking: sorts existing files, then starts watching. Raises OSError for bad folders."""
        if not os.path.isdir(self.root):
            raise FileNotFoundError(f"Folder not found: {self.root}")
        sort_directory(self.root, self.on_result)
        self._observer = Observer()
        self._observer.schedule(_Handler(self.root, self.on_result), self.root, recursive=False)
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
