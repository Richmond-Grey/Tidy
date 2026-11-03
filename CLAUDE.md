# Tidy

Desktop app that keeps a folder (typically Downloads) organised. The project and repo are still
called `Sorter`; the app itself is named **Tidy**. Features:

- **Auto sort** – every file directly inside the chosen folder is moved into a subfolder named after
  its extension (`report.pdf` → `pdf/report.pdf`) or its category (`Documents/`), once and then live.
- **Group similar** – finds files that belong together (episodes of a show, a movie + subtitles,
  `IMG_2031`/`IMG_2032`, `invoice-march`/`invoice-april`); the user edits each group and moves it into
  a named folder, optionally renaming episodes to `Show - S01E02.mkv` and fetching subtitles.
- **Duplicates** – byte-identical files; extra copies go to the Recycle Bin (`send2trash`).
- **Share files** – serves chosen files from this computer under random-token links; optional
  public tunnel (cloudflared, else `ssh` to localhost.run) for people outside the network.
- **History / undo** – every move is journalled and can be put back (Ctrl+Z = latest).
- **Themes + bear intro** – Bear (default), Forest, Ocean, Blossom, Midnight; switchable live in
  Settings. A Remotion-made bear animation plays in a splash window at launch.

The long-term plan is to ship it on both PC and mobile, so keep all logic UI-free.

## Layout

Core (no UI imports):
- `sorter.py` – `sort_file` / `sort_directory` / `plan_directory`, `SortRules` (extension vs category,
  ignore patterns), `move_file`, `FolderWatcher` (watchdog). Callbacks fire on background threads.
- `media.py` – parses show/movie names (`MediaInfo`: title, season, episode, year).
- `grouping.py` – `collect_files`, `find_groups` → `FileGroup`s, `move_group`.
- `subtitles.py` – OpenSubtitles.com REST client (needs a free API key; search and download both).
- `duplicates.py` – size → 64 KB head hash → full hash.
- `history.py` – thread-safe undo journal (`history.json`).
- `sharing.py` – `ShareStore` (`shares.json`), `ShareServer` (stdlib HTTP, Range support), `Tunnel`.
- `settings.py` – `Settings` dataclass saved to `config_dir()` (`%APPDATA%\Tidy`; override with
  `TIDY_CONFIG_DIR`, handy for tests).

UI (Tkinter/ttk):
- `main.py` – `TidyApp`: sidebar, page switching, `post` / `run_async`, toasts, undo.
- `ui/theme.py` – `THEMES` palettes, the live `COLORS` dict (`use_theme` swaps it in place), fonts,
  icon glyphs and ttk styles. Never hard-code a colour elsewhere; add a palette key instead.
- `ui/intro.py` – `IntroPlayer`, plays `assets/intro/frame_*.png` at 30 fps, skippable.
- `ui/widgets.py` – `Card`, `Table`, `Pill`, `Dialog`, `ScrollFrame`, `hline`, helpers.
- `ui/autosort.py`, `ui/groups.py`, `ui/duplicates_page.py`, `ui/share_page.py`,
  `ui/history_page.py`, `ui/settings_page.py` – one page each.
- `intro/` – Remotion project for the intro (`src/BearIntro.tsx`). Re-export after edits:
  `cd intro && npm run render && uv run --with pillow python export_frames.py` (→ `assets/intro/`,
  256-colour PNGs, ~2.5 MB). Preview with `npm run dev`.
- `glob/` – stray, accidentally committed venv binaries; not used. The real env is `.venv/` (uv).

## Running

```
uv sync
uv run main.py
```

Python 3.14 (see `pyproject.toml`); dependencies are `watchdog` and `send2trash`. Tkinter ships with Python.

## Rules worth knowing

- **Never touch Tk widgets from a non-UI thread.** Background work goes through `app.run_async(work,
  on_done, on_error)` or `app.post(fn)`; `_drain_events` runs posted callables on the UI thread.
  Don't capture an `except ... as e` variable in a lambda without binding it (`lambda err=e: ...`).
- Sorting is non-recursive: only files directly in the root are moved, folders are never moved.
  Grouping also looks one level down, but only inside Tidy's own sort folders (`is_sort_folder`).
- Extensions are lowercased for folder names (`.JPG` → `jpg/`); files without one go to `no_extension/`.
- Name clashes get a suffix (`file (1).pdf`) instead of overwriting.
- Partial downloads (`.crdownload`, `.part`, `.tmp`, …) and system files (`desktop.ini`,
  `Thumbs.db`, `.DS_Store`) are skipped. Browsers rename a finished download, so `on_moved` is handled
  as well as `on_created`.
- `wait_until_stable` + `PermissionError` retries guard against moving files still being written.
- Undo calls `sorter.suppress(path)` so a running watcher doesn't immediately re-sort restored files.
- Sharing only ever serves files the user explicitly shared, looked up by token; never add
  directory listings or path-based routes. The tunnel only starts after the user confirms.
- Theme switches (`TidyApp.apply_theme`) destroy and rebuild every page. Keep long-lived state on the
  app (`history`, `share_store`, `share_server`), give pages a `detach()` for cleanup, and guard
  `after` loops and `bind_all` handlers with `winfo_exists()`.
- `ttk.Separator` renders too dark under clam; use `ui.widgets.hline`. `grid_slaves()` skips widgets
  hidden with `grid_remove`, so keep your own list if you need to show them again.

## Testing

No test suite yet. Core logic: call the functions directly on a `tempfile.mkdtemp()` folder (e.g.
`grouping.find_groups([...names...])`, `FolderWatcher`). UI: set `TIDY_CONFIG_DIR` to a temp folder,
create `main.TidyApp()`, drive pages with `app.after(...)`, and screenshot with Pillow's `ImageGrab`.
Bind `app.share_server.host = "127.0.0.1"` in tests to avoid a firewall prompt, and write
`{"play_intro": false}` to the test settings.json to skip the intro. Don't call `update()` from
inside `after` callbacks while the intro plays; it stalls the intro's tick loop.
