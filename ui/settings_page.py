"""Settings page. Every change is saved automatically."""
import os
import tkinter as tk
import webbrowser
from tkinter import ttk

from settings import config_dir
from sorter import MODE_CATEGORY, MODE_EXTENSION
from subtitles import LANGUAGES, OpenSubtitles, SubtitleError
from ui.intro import IntroPlayer, intro_available
from ui.theme import COLORS as C
from ui.theme import THEMES
from ui.widgets import Card, PageHeader, ScrollFrame, open_in_file_manager

API_KEY_URL = "https://www.opensubtitles.com/en/consumers"
LANGUAGE_BY_NAME = {name: code for code, name in LANGUAGES.items()}


class SettingsPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        s = app.settings
        self._syncing = False

        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        page = ttk.Frame(scroll.inner, padding=(36, 30, 36, 30))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)

        PageHeader(page, "Settings", "Changes are saved as you make them.").grid(row=0, column=0, sticky="ew")

        # --- Sorting ---
        self._build_appearance(page)

        body = self._card(page, 2, "Auto sort", "How files are sorted when they land in your folder.")
        self.mode_var = tk.StringVar(value=s.sort_mode)
        ttk.Radiobutton(body, text="By file type: one folder per extension (pdf/, jpg/, mkv/)",
                        style="Card.TRadiobutton", value=MODE_EXTENSION, variable=self.mode_var,
                        command=self._sorting_changed).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(body, text="By category: Documents/, Images/, Videos/, Installers/ …",
                        style="Card.TRadiobutton", value=MODE_CATEGORY, variable=self.mode_var,
                        command=self._sorting_changed).grid(row=3, column=0, sticky="w", pady=(4, 0))

        ttk.Label(body, text="Leave these files alone", style="Card.Section.TLabel").grid(
            row=4, column=0, sticky="w", pady=(18, 4))
        ttk.Label(body, text="Comma-separated patterns. * matches anything, e.g.  *.lnk, keep-*, notes.txt",
                  style="Card.Small.TLabel").grid(row=5, column=0, sticky="w")
        self.ignore_var = tk.StringVar(value=", ".join(s.ignore_patterns))
        ttk.Entry(body, textvariable=self.ignore_var).grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self.ignore_var.trace_add("write", lambda *_: self._sorting_changed())

        self.autostart_var = tk.BooleanVar(value=s.start_on_launch)
        ttk.Checkbutton(body, text="Start watching my folder as soon as Tidy opens", style="Card.TCheckbutton",
                        variable=self.autostart_var, command=self._general_changed).grid(
            row=7, column=0, sticky="w", pady=(16, 0))

        # --- Subtitles ---
        body = self._card(page, 3, "Subtitles",
                          "Tidy downloads subtitles from OpenSubtitles.com. You need a free API key: sign in, "
                          "open “API consumers”, create one and paste it below.")
        link = tk.Label(body, text="Get a free API key  →", fg=C["accent"], bg=C["surface"], cursor="hand2",
                        font=app.theme.fonts["section"])
        link.grid(row=2, column=0, sticky="w", pady=(0, 14))
        link.bind("<Button-1>", lambda _e: webbrowser.open(API_KEY_URL))

        grid = ttk.Frame(body, style="Card.TFrame")
        grid.grid(row=3, column=0, sticky="ew")
        grid.columnconfigure(1, weight=1)

        def field_row(row, label, var, show=None, hint=""):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5,
                                                                padx=(0, 16))
            entry = ttk.Entry(grid, textvariable=var, show=show or "")
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if hint:
                ttk.Label(grid, text=hint, style="Card.Small.TLabel").grid(row=row, column=2, sticky="w",
                                                                         padx=(12, 0))
            var.trace_add("write", lambda *_: self._subtitles_changed())
            return entry

        self.lang_var = tk.StringVar(value=LANGUAGES.get(s.subtitle_language, "English"))
        ttk.Label(grid, text="Language", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        lang = ttk.Combobox(grid, textvariable=self.lang_var, values=sorted(LANGUAGES.values()),
                            state="readonly", width=24)
        lang.grid(row=0, column=1, sticky="w", pady=5)
        lang.bind("<<ComboboxSelected>>", lambda _e: self._language_changed())

        self.key_var = tk.StringVar(value=s.opensubtitles_api_key)
        self.key_entry = field_row(1, "API key", self.key_var, show="•")
        self.user_var = tk.StringVar(value=s.opensubtitles_username)
        field_row(2, "Username", self.user_var, hint="Optional: more downloads per day")
        self.pass_var = tk.StringVar(value=s.opensubtitles_password)
        field_row(3, "Password", self.pass_var, show="•", hint="Optional")
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(grid, text="Show key", style="Card.TCheckbutton", variable=self.show_key_var,
                        command=lambda: self.key_entry.configure(show="" if self.show_key_var.get() else "•")
                        ).grid(row=1, column=2, sticky="w", padx=(12, 0))

        test_row = ttk.Frame(body, style="Card.TFrame")
        test_row.grid(row=4, column=0, sticky="w", pady=(14, 0))
        self.test_button = ttk.Button(test_row, text="Test connection", command=self.test_connection)
        self.test_button.pack(side="left")
        self.test_label = ttk.Label(test_row, style="Card.Small.TLabel")
        self.test_label.pack(side="left", padx=(12, 0))
        ttk.Label(body, text="Your key and password are stored only on this computer, in Tidy's settings file.",
                  style="Card.Small.TLabel").grid(row=5, column=0, sticky="w", pady=(12, 0))

        # --- Grouping ---
        body = self._card(page, 4, "Group similar", "Defaults for the Group similar page.")
        self.include_var = tk.BooleanVar(value=s.group_include_sorted)
        ttk.Checkbutton(body, text="Also look inside folders Tidy already sorted (mkv/, Videos/ …)",
                        style="Card.TCheckbutton", variable=self.include_var, command=self._general_changed).grid(
            row=2, column=0, sticky="w")
        self.rename_var = tk.BooleanVar(value=s.rename_episodes)
        ttk.Checkbutton(body, text="Rename TV episodes neatly when grouping  (Show - S01E02.mkv)",
                        style="Card.TCheckbutton", variable=self.rename_var, command=self._general_changed).grid(
            row=3, column=0, sticky="w", pady=(4, 0))

        # --- Data ---
        body = self._card(page, 5, "Your data", f"Settings and undo history are kept in {config_dir()}")
        row = ttk.Frame(body, style="Card.TFrame")
        row.grid(row=2, column=0, sticky="w")
        ttk.Button(row, text="Open settings folder", command=self._open_config).pack(side="left")

    def _build_appearance(self, page):
        body = self._card(page, 1, "Appearance", "Pick a look. It changes straight away.")
        tiles = ttk.Frame(body, style="Card.TFrame")
        tiles.grid(row=2, column=0, sticky="w")
        for i, (key, (name, description, colors)) in enumerate(THEMES.items()):
            self._theme_tile(tiles, key, name, description, colors).grid(
                row=i // 3, column=i % 3, padx=(0, 12), pady=(0, 12), sticky="nw")

        row = ttk.Frame(body, style="Card.TFrame")
        row.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.intro_var = tk.BooleanVar(value=self.app.settings.play_intro)
        ttk.Checkbutton(row, text="Play the bear intro when Tidy opens", style="Card.TCheckbutton",
                        variable=self.intro_var, command=self._intro_changed).pack(side="left")
        if intro_available():
            ttk.Button(row, text="Play it now", style="CardGhost.TButton",
                       command=lambda: IntroPlayer(self.app, on_done=lambda: None)).pack(side="left", padx=(12, 0))

    def _theme_tile(self, parent, key, name, description, colors):
        """Mini screenshot of the theme: sidebar, page, a card and an accent button."""
        selected = key == self.app.theme_key
        tile = tk.Frame(parent, bg=C["surface"], cursor="hand2", highlightthickness=2, bd=0,
                        highlightbackground=C["accent"] if selected else C["border"],
                        highlightcolor=C["accent"] if selected else C["border"])
        preview = tk.Canvas(tile, width=176, height=92, highlightthickness=0, bd=0, bg=colors["bg"])
        preview.pack(padx=8, pady=(8, 6))
        preview.create_rectangle(0, 0, 44, 92, fill=colors["side_bg"], outline="")
        preview.create_oval(10, 10, 22, 22, fill=colors["side_accent"], outline="")
        for i, width in enumerate((26, 20, 23)):
            y = 34 + i * 12
            preview.create_rectangle(10, y, 10 + width, y + 4, fill=colors["side_muted"], outline="")
        preview.create_rectangle(10, 33, 36, 39, fill=colors["side_accent"], outline="")
        preview.create_rectangle(56, 12, 112, 18, fill=colors["text"], outline="")
        preview.create_rectangle(56, 28, 166, 80, fill=colors["surface"], outline=colors["border"])
        preview.create_rectangle(64, 38, 140, 42, fill=colors["muted"], outline="")
        preview.create_rectangle(64, 48, 124, 52, fill=colors["faint"], outline="")
        preview.create_rectangle(118, 62, 158, 72, fill=colors["accent"], outline="")

        text = tk.Frame(tile, bg=C["surface"])
        text.pack(fill="x", padx=10, pady=(0, 8))
        title = tk.Label(text, text=("✓  " if selected else "") + name, bg=C["surface"],
                         fg=C["accent_text"] if selected else C["text"], font=self.app.theme.fonts["section"],
                         anchor="w")
        title.pack(fill="x")
        sub = tk.Label(text, text=description, bg=C["surface"], fg=C["muted"], font=self.app.theme.fonts["small"],
                       anchor="w")
        sub.pack(fill="x")

        def choose(_event=None):
            # Rebuilding destroys this page, so do it after the click handler returns
            self.after(10, lambda: self.app.apply_theme(key))

        def hover(on):
            if not selected:
                tile.configure(highlightbackground=C["border_strong"] if on else C["border"])
        for widget in (tile, preview, text, title, sub):
            widget.bind("<Button-1>", choose)
            widget.bind("<Enter>", lambda _e: hover(True))
            widget.bind("<Leave>", lambda _e: hover(False))
        return tile

    def _intro_changed(self):
        self.app.settings.play_intro = self.intro_var.get()
        self.app.save_settings()

    def _card(self, page, row, title, description):
        card = Card(page, padding=22)
        card.grid(row=row, column=0, sticky="ew", pady=(22 if row == 1 else 16, 0))
        body = card.body
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=title, style="Card.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text=description, style="Card.Muted.TLabel", wraplength=640, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 14))
        return body

    # ---------- syncing ----------

    def sync_from_settings(self):
        """Another page changed a setting shown here."""
        self._syncing = True
        s = self.app.settings
        self.mode_var.set(s.sort_mode)
        self.include_var.set(s.group_include_sorted)
        self.rename_var.set(s.rename_episodes)
        self.lang_var.set(LANGUAGES.get(s.subtitle_language, "English"))
        self._syncing = False

    def on_show(self):
        self.sync_from_settings()

    def focus_api_key(self):
        self.key_entry.focus_set()

    def _sorting_changed(self):
        if self._syncing:
            return
        s = self.app.settings
        s.sort_mode = self.mode_var.get()
        s.ignore_patterns = [p.strip() for p in self.ignore_var.get().split(",") if p.strip()]
        self.app.save_settings()
        self.app.pages["sort"].apply_rules()

    def _general_changed(self):
        if self._syncing:
            return
        s = self.app.settings
        s.start_on_launch = self.autostart_var.get()
        s.group_include_sorted = self.include_var.get()
        s.rename_episodes = self.rename_var.get()
        self.app.save_settings()
        groups = self.app.pages["group"]
        groups.include_var.set(s.group_include_sorted)
        groups.rename_var.set(s.rename_episodes)

    def _language_changed(self):
        code = LANGUAGE_BY_NAME.get(self.lang_var.get(), "en")
        self.app.settings.subtitle_language = code
        self.app.save_settings()
        self.app.pages["group"].set_language(code)

    def _subtitles_changed(self):
        if self._syncing:
            return
        s = self.app.settings
        s.opensubtitles_api_key = self.key_var.get().strip()
        s.opensubtitles_username = self.user_var.get().strip()
        s.opensubtitles_password = self.pass_var.get()
        self.test_label.configure(text="", style="Card.Small.TLabel")
        self.app.save_settings()

    def test_connection(self):
        s = self.app.settings
        client = OpenSubtitles(s.opensubtitles_api_key, s.opensubtitles_username, s.opensubtitles_password)
        lang = s.subtitle_language
        self.test_button.configure(state="disabled")
        self.test_label.configure(text="Checking…", style="Card.Small.TLabel")

        def work():
            results = client.search("Breaking.Bad.S01E01.mkv", lang)
            if s.opensubtitles_username:
                client._login()  # surface bad passwords now rather than on the first download
            return len(results)

        def done(count):
            self.test_button.configure(state="normal")
            self.test_label.configure(text=f"✓ Connected. Test search found {count} subtitles.",
                                      style="Card.Success.TLabel")

        def failed(e):
            self.test_button.configure(state="normal")
            message = str(e) if isinstance(e, SubtitleError) else f"Unexpected error: {e}"
            self.test_label.configure(text=message, style="Card.Error.TLabel")

        self.app.run_async(work, done, failed)

    def _open_config(self):
        os.makedirs(config_dir(), exist_ok=True)
        open_in_file_manager(config_dir())
