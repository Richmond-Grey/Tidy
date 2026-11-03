"""Core sorting logic for Tidy.

Kept free of any UI code so the same logic can back the desktop app today
and other front ends (mobile, CLI) later.
"""
import fnmatch
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Folder used for files that have no extension
NO_EXTENSION_FOLDER = "no_extension"

# Partial downloads are renamed once complete; moving them early breaks the download
TEMP_EXTENSIONS = {"crdownload", "part", "partial", "download", "tmp", "opdownload"}

# System files that must stay where they are
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}

# Folder names for "sort by category" mode
CATEGORIES = {
    "Images": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif", "tif", "tiff", "svg", "ico",
               "raw", "cr2", "nef", "arw", "dng", "psd", "avif"},
    "Videos": {"mp4", "mkv", "avi", "mov", "wmv", "m4v", "webm", "flv", "mpg", "mpeg", "3gp", "ts"},
    "Audio": {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff", "mid", "midi"},
    "Documents": {"pdf", "doc", "docx", "odt", "rtf", "txt", "md", "pages", "tex", "log"},
    "Spreadsheets": {"xls", "xlsx", "xlsm", "ods", "csv", "tsv", "numbers"},
    "Presentations": {"ppt", "pptx", "odp", "key"},
    "Archives": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso", "dmg", "cab"},
    "Installers": {"exe", "msi", "msix", "appx", "apk", "deb", "rpm", "pkg", "appimage", "bat", "cmd"},
    "Code": {"py", "js", "ts", "tsx", "jsx", "html", "css", "json", "xml", "yml", "yaml", "java", "c",
             "cpp", "h", "cs", "go", "rs", "rb", "php", "sh", "ps1", "sql", "ipynb", "kt", "swift"},
    "Ebooks": {"epub", "mobi", "azw", "azw3", "fb2", "djvu", "cbz", "cbr"},
    "Fonts": {"ttf", "otf", "woff", "woff2", "fon"},
    "Subtitles": {"srt", "ass", "ssa", "sub", "vtt", "idx"},
    "Torrents": {"torrent"},
}
OTHER_CATEGORY = "Other"
_CATEGORY_BY_EXT = {ext: name for name, exts in CATEGORIES.items() for ext in exts}

MODE_EXTENSION = "extension"
MODE_CATEGORY = "category"


@dataclass
class SortRules:
    """How files are sorted. Defaults reproduce the original behaviour."""
    mode: str = MODE_EXTENSION
    ignore_patterns: list[str] = field(default_factory=list)  # e.g. ["*.lnk", "keep-*"]

    def folder_for(self, filename: str) -> str:
        if self.mode == MODE_CATEGORY:
            return category_for(filename)
        return folder_for(filename)

    def ignores(self, filename: str) -> bool:
        name = filename.lower()
        return any(fnmatch.fnmatch(name, p.strip().lower()) for p in self.ignore_patterns if p.strip())


@dataclass
class MoveResult:
    """Outcome of sorting a single file."""
    source: str
    destination: str
    error: str | None = None
    history_id: int | None = None


def folder_for(filename: str) -> str:
    """Name of the subfolder a file belongs in, based on its extension."""
    ext = os.path.splitext(filename)[1][1:].lower()
    return ext or NO_EXTENSION_FOLDER


def category_for(filename: str) -> str:
    """'photo.JPG' -> 'Images'."""
    ext = os.path.splitext(filename)[1][1:].lower()
    return _CATEGORY_BY_EXT.get(ext, OTHER_CATEGORY)


def is_sort_folder(folder_name: str, filename: str) -> bool:
    """True if filename sits in a folder Tidy's auto-sort would have put it in."""
    name = folder_name.lower()
    return name in (folder_for(filename), category_for(filename).lower())


def should_skip(filename: str) -> bool:
    """True for system files and unfinished downloads."""
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


def safe_folder_name(name: str) -> str:
    """Strip characters Windows/macOS/Android don't allow in folder names."""
    cleaned = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name)
    return cleaned.strip().rstrip(". ") or "Untitled"


# Paths the watcher should leave alone for a short while (e.g. files just restored by undo)
_suppressed: dict[str, float] = {}
_suppressed_lock = threading.Lock()


def suppress(path: str, seconds: float = 15.0) -> None:
    with _suppressed_lock:
        _suppressed[os.path.normcase(os.path.abspath(path))] = time.monotonic() + seconds


def is_suppressed(path: str) -> bool:
    key = os.path.normcase(os.path.abspath(path))
    with _suppressed_lock:
        until = _suppressed.get(key)
        if until is None:
            return False
        if until < time.monotonic():
            del _suppressed[key]
            return False
        return True


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


def move_file(path: str, target_dir: str, new_name: str | None = None, retries: int = 3) -> MoveResult:
    """Move path into target_dir (optionally renamed) without overwriting anything."""
    filename = new_name or os.path.basename(path)
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
    return MoveResult(path, target_dir, "Gave up")


def sort_file(root: str, path: str, rules: SortRules | None = None, history=None,
              retries: int = 3) -> MoveResult | None:
    """Move one file into root/<folder>/. Returns None if the file was skipped."""
    rules = rules or SortRules()
    filename = os.path.basename(path)
    if not os.path.isfile(path) or should_skip(filename) or rules.ignores(filename):
        return None
    folder = rules.folder_for(filename)
    result = move_file(path, os.path.join(root, folder), retries=retries)
    if history is not None and not result.error:
        entry = history.record("sort", f"{filename} → {folder}/", [(result.source, result.destination)])
        result.history_id = entry.id
    return result


def plan_directory(root: str, rules: SortRules | None = None) -> list[tuple[str, str]]:
    """Dry run: [(filename, folder)] for everything sort_directory would move."""
    rules = rules or SortRules()
    plan = []
    for entry in sorted(os.listdir(root), key=str.lower):
        path = os.path.join(root, entry)
        if os.path.isfile(path) and not should_skip(entry) and not rules.ignores(entry):
            plan.append((entry, rules.folder_for(entry)))
    return plan


def sort_directory(root: str, on_result: Callable[[MoveResult], None],
                   rules: SortRules | None = None, history=None) -> None:
    """Sort every file currently sitting directly inside root."""
    for entry in sorted(os.listdir(root)):
        result = sort_file(root, os.path.join(root, entry), rules, history)
        if result:
            on_result(result)


def remove_empty_folders(root: str) -> list[str]:
    """Delete empty subfolders of root (deepest first). Returns the removed paths."""
    removed = []
    for dirpath, _dirnames, _files in os.walk(root, topdown=False):
        if _same_path(dirpath, root):
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
                removed.append(dirpath)
        except OSError:
            pass
    return removed


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "FolderWatcher"):
        self.watcher = watcher

    def on_created(self, event):
        # Folders (including the ones we create) are left alone
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        # Browsers download to a temp name, then rename it once finished
        if not event.is_directory and _same_path(os.path.dirname(event.dest_path), self.watcher.root):
            self._handle(event.dest_path)

    def _handle(self, path: str):
        if should_skip(os.path.basename(path)) or is_suppressed(path):
            return
        wait_until_stable(path)
        result = sort_file(self.watcher.root, path, self.watcher.rules, self.watcher.history)
        if result:
            self.watcher.on_result(result)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class FolderWatcher:
    """Sorts a folder once, then keeps sorting new files as they arrive.

    on_result is called from background threads; UI code must marshal it
    back to its own thread.
    """

    def __init__(self, root: str, on_result: Callable[[MoveResult], None],
                 rules: SortRules | None = None, history=None):
        self.root = os.path.abspath(root)
        self.on_result = on_result
        self.rules = rules or SortRules()
        self.history = history
        self._observer = None

    def start(self) -> None:
        """Blocking: sorts existing files, then starts watching. Raises OSError for bad folders."""
        if not os.path.isdir(self.root):
            raise FileNotFoundError(f"Folder not found: {self.root}")
        sort_directory(self.root, self.on_result, self.rules, self.history)
        self._observer = Observer()
        self._observer.schedule(_Handler(self), self.root, recursive=False)
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
