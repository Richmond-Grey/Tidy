# Tidy

Keeps your Downloads folder (or any folder) organised. Written in pure Python; it will later become
an app for both mobile and PC.

## Features

- **Auto sort**: moves every file into a folder by type (`pdf/`, `jpg/`) or category (`Documents/`,
  `Images/`), then keeps doing it as new files arrive. Preview first, ignore patterns, remove empty folders.
- **Group similar files**: spots files that belong together (episodes of a show, a movie and its
  subtitles, numbered photos, monthly invoices). Add or remove files, name the folder, move it, next group.
  Episodes can be renamed to `Show - S01E02.mkv`.
- **Subtitles**: downloads subtitles for shows and movies from OpenSubtitles.com in your language
  (needs a free API key, set in Settings).
- **Duplicates**: finds identical files, even with different names, and recycles the extra copies.
- **Share files**: get a link to any file on your computer; anyone with the link can download it
  while Tidy is open. Works on your Wi-Fi right away, and anywhere once you turn on the internet link.
- **History and undo**: every move can be undone (Ctrl+Z for the latest).

## Run

```
uv sync
uv run main.py
```
