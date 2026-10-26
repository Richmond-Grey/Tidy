# Tidy

Desktop app that keeps a folder (typically Downloads) organised: every file directly inside the
chosen folder is moved into a subfolder named after its extension (`report.pdf` → `pdf/report.pdf`),
first as a one-off sort and then live as new files arrive. The project and repo are still called
`Sorter`; the app itself is named **Tidy**.

The long-term plan is to ship it on both PC and mobile, so keep the sorting logic UI-free.

## Layout

- `sorter.py` – core logic, no UI imports. `sort_file` / `sort_directory` do the moving;
  `FolderWatcher` wraps a watchdog `Observer` for live sorting. Callbacks (`on_result`) fire on
  background threads.
- `main.py` – Tkinter/ttk front end (`TidyApp`). All theme colours live in `COLORS`, all ttk styles
  in `_setup_styles`.
- `glob/` – stray, accidentally committed venv binaries; not used. The real env is `.venv/` (uv).

## Running

```
uv sync
uv run main.py
```

Python 3.14 (see `pyproject.toml`); only dependency is `watchdog`. Tkinter ships with Python.

## Rules worth knowing

- **Never touch Tk widgets from a non-UI thread.** Watchdog and the initial sort run off the main
  thread; they push `("moved" | "started" | "failed", payload)` tuples onto `TidyApp.events`, which
  `_drain_events` polls every 100 ms via `after`.
- Sorting is non-recursive: only files directly in the root are moved, folders are never moved.
- Extensions are lowercased for folder names (`.JPG` → `jpg/`); files without one go to `no_extension/`.
- Name clashes get a suffix (`file (1).pdf`) instead of overwriting.
- Partial downloads (`.crdownload`, `.part`, `.tmp`, …) and system files (`desktop.ini`,
  `Thumbs.db`, `.DS_Store`) are skipped. Browsers rename a finished download, so `on_moved` is handled
  as well as `on_created`.
- `wait_until_stable` + `PermissionError` retries guard against moving files still being written.

## Testing

No test suite yet. To check the core logic, point `FolderWatcher` at a `tempfile.mkdtemp()` folder,
create files and check where they end up. To check the UI, run the app against a temp folder.
