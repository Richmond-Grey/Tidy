"""Desktop (Tkinter) front end for Tidy: window shell, sidebar and page switching.

Pages live in ui/. All theme colours are in ui/theme.py (COLORS), all ttk styles in
ui/theme.setup_styles.
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from history import History
from settings import Settings, config_dir
from sorter import SortRules
from ui.autosort import AutoSortPage
from ui.duplicates_page import DuplicatesPage
from ui.groups import GroupsPage
from ui.history_page import HistoryPage
from ui.settings_page import SettingsPage
from ui.share_page import SharePage
from sharing import ShareServer, ShareStore
from ui.intro import IntroPlayer, intro_available
from ui.theme import COLORS as C
from ui.theme import THEMES, Theme, setup_styles, use_theme
from ui.widgets import StatusDot

PAGES = [
    # key, label, icon, class
    ("sort", "Auto sort", "sort", AutoSortPage),
    ("group", "Group similar", "group", GroupsPage),
    ("duplicates", "Duplicates", "duplicates", DuplicatesPage),
    ("share", "Share files", "share", SharePage),
    ("history", "History", "history", HistoryPage),
    ("settings", "Settings", "settings", SettingsPage),
]


def enable_high_dpi():
    """Render crisp text on scaled Windows displays."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


class NavItem(tk.Frame):
    """One row in the sidebar: accent bar, icon, label."""

    def __init__(self, parent, theme, icon, text, command):
        super().__init__(parent, bg=C["side_bg"], cursor="hand2")
        self.command = command
        self.active = False
        self.bar = tk.Frame(self, width=3, bg=C["side_bg"])
        self.bar.pack(side="left", fill="y")
        self.icon = tk.Label(self, text=theme.icon(icon), font=theme.fonts["icon"], bg=C["side_bg"],
                             fg=C["side_muted"], width=2)
        self.icon.pack(side="left", padx=(14, 6), pady=9)
        self.label = tk.Label(self, text=text, font=theme.fonts["body"], bg=C["side_bg"], fg=C["side_text"],
                              anchor="w")
        self.label.pack(side="left", fill="x", expand=True, pady=9)
        self.badge = tk.Label(self, text="", font=theme.fonts["small_strong"], bg=C["side_bg"],
                              fg=C["side_accent"])
        self.badge.pack(side="right", padx=(0, 14))
        for widget in (self, self.icon, self.label, self.badge):
            widget.bind("<Button-1>", lambda _e: self.command())
            widget.bind("<Enter>", lambda _e: self._paint(hover=True))
            widget.bind("<Leave>", lambda _e: self._paint())

    def set_active(self, active):
        self.active = active
        self._paint()

    def set_badge(self, text):
        self.badge.configure(text=text)

    def _paint(self, hover=False):
        bg = C["side_active"] if self.active else (C["side_hover"] if hover else C["side_bg"])
        for widget in (self, self.icon, self.label, self.badge):
            widget.configure(bg=bg)
        self.bar.configure(bg=C["side_accent"] if self.active else bg)
        self.icon.configure(fg=C["side_accent"] if self.active else C["side_muted"])
        self.label.configure(fg=C["side_active_text"] if self.active else C["side_text"])


class TidyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.theme_key = use_theme(self.settings.theme)
        play_intro = self.settings.play_intro and intro_available()
        if play_intro:
            self.withdraw()  # the intro plays first; the window appears when it ends
        self.title("Tidy")
        self.configure(bg=C["bg"])
        self.minsize(940, 620)
        self._center(1120, 740)

        self.history = History(os.path.join(config_dir(), "history.json"))
        # Long-lived sharing state lives on the app so it survives a theme switch
        self.share_store = ShareStore(os.path.join(config_dir(), "shares.json"))
        self.share_server = ShareServer(self.share_store, lambda kind, share: self.post(
            lambda: self.pages["share"].on_server_event(kind, share)))
        self.events = queue.Queue()  # Background threads talk to the UI only through this
        self.path_var = tk.StringVar(value=self.settings.folder)
        self.path_var.trace_add("write", lambda *_: self.save_settings())
        self._save_job = None
        self._toast_job = None

        self.theme = Theme(self)
        setup_styles(self, self.theme)
        self._build()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        for i, (key, *_rest) in enumerate(PAGES, 1):
            self.bind_all(f"<Control-Key-{i}>", lambda _e, k=key: self.show_page(k))
        self.bind_all("<Control-z>", self._undo_last)
        self.show_page("sort")
        if play_intro:
            IntroPlayer(self, on_done=self._after_intro)
        else:
            self.after(300, self.pages["sort"].maybe_autostart)

    def _after_intro(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.after(300, self.pages["sort"].maybe_autostart)

    # ---------- layout ----------

    def _center(self, width, height):
        width = min(width, self.winfo_screenwidth() - 80)
        height = min(height, self.winfo_screenheight() - 120)
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self):
        sidebar = self.sidebar = tk.Frame(self, bg=C["side_bg"], width=228)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=C["side_bg"])
        brand.pack(fill="x", padx=20, pady=(24, 26))
        logo = tk.Canvas(brand, width=30, height=30, bg=C["side_bg"], highlightthickness=0)
        logo.pack(side="left")
        self._draw_logo(logo)
        tk.Label(brand, text="Tidy", font=self.theme.fonts["brand"], bg=C["side_bg"], fg=C["side_brand"]).pack(
            side="left", padx=(10, 0))

        tk.Label(sidebar, text="ORGANISE", font=self.theme.fonts["small_strong"], bg=C["side_bg"],
                 fg=C["side_muted"]).pack(anchor="w", padx=22, pady=(0, 6))
        self.nav = {}
        for key, label, icon, _cls in PAGES:
            if key == "history":
                tk.Label(sidebar, text="MANAGE", font=self.theme.fonts["small_strong"], bg=C["side_bg"],
                         fg=C["side_muted"]).pack(anchor="w", padx=22, pady=(18, 6))
            item = NavItem(sidebar, self.theme, icon, label, lambda k=key: self.show_page(k))
            item.pack(fill="x")
            self.nav[key] = item

        # Watcher status card at the bottom of the sidebar
        footer = tk.Frame(sidebar, bg=C["side_bg"])
        footer.pack(side="bottom", fill="x", padx=16, pady=16)
        status = tk.Frame(footer, bg=C["side_hover"], padx=12, pady=10)
        status.pack(fill="x")
        row = tk.Frame(status, bg=C["side_hover"])
        row.pack(fill="x")
        self.side_dot = StatusDot(row, C["side_hover"], size=9)
        self.side_dot.pack(side="left")
        self.side_status = tk.Label(row, text="Not watching", font=self.theme.fonts["small_strong"],
                                    bg=C["side_hover"], fg=C["side_text"], anchor="w")
        self.side_status.pack(side="left", padx=(8, 0), fill="x")
        self.side_detail = tk.Label(status, text="Auto sort is off", font=self.theme.fonts["small"],
                                    bg=C["side_hover"], fg=C["side_muted"], anchor="w", justify="left",
                                    wraplength=170)
        self.side_detail.pack(fill="x", pady=(4, 0))
        tk.Label(footer, text="Made by Richmond", font=self.theme.fonts["small"], bg=C["side_bg"],
                 fg=C["side_muted"]).pack(anchor="w", pady=(12, 0))
        self.set_watch_status(False)

        # Pages
        self.content = ttk.Frame(self)
        self.content.pack(side="left", fill="both", expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.pages = {}
        for key, _label, _icon, cls in PAGES:
            page = cls(self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self.current_page = None

        self.toast_label = tk.Label(self.content, font=self.theme.fonts["body"], padx=16, pady=9, bd=0)

    def _draw_logo(self, canvas):
        # Tidy's bear mascot: ears, head, muzzle, eyes and nose
        fur, ink, muzzle = C["side_accent"], C["side_bg"], C["side_text"]
        for x in (2, 18):
            canvas.create_oval(x, 2, x + 10, 12, fill=fur, outline="")
            canvas.create_oval(x + 3, 5, x + 7, 9, fill=ink, outline="")
        canvas.create_oval(3, 5, 27, 29, fill=fur, outline="")
        canvas.create_oval(9.5, 16, 20.5, 26, fill=muzzle, outline="")
        canvas.create_oval(9, 12, 12, 15, fill=ink, outline="")
        canvas.create_oval(18, 12, 21, 15, fill=ink, outline="")
        canvas.create_oval(12.5, 17.5, 17.5, 21, fill=ink, outline="")

    def apply_theme(self, key):
        """Switch colours live: swap the palette, restyle ttk, rebuild the widgets."""
        if key == self.theme_key or key not in THEMES:
            return
        page = self.current_page or "sort"
        was_watching = self.pages["sort"].watcher is not None
        for p in self.pages.values():
            if hasattr(p, "detach"):
                p.detach()
        self.pages["sort"].shutdown()
        self.sidebar.destroy()
        self.content.destroy()

        self.theme_key = use_theme(key)
        self.settings.theme = self.theme_key
        self.save_settings(0)
        self.configure(bg=C["bg"])
        setup_styles(self, self.theme)
        self._build()
        self.show_page(page)
        if was_watching:
            self.pages["sort"].toggle()
        self.toast(f"{THEMES[self.theme_key][0]} theme on")

    def show_page(self, key):
        if self.current_page == key:
            return
        self.current_page = key
        for k, item in self.nav.items():
            item.set_active(k == key)
        page = self.pages[key]
        page.tkraise()
        if hasattr(page, "on_show"):
            page.on_show()

    # ---------- shared state ----------

    def rules(self) -> SortRules:
        return SortRules(mode=self.settings.sort_mode, ignore_patterns=list(self.settings.ignore_patterns))

    def folder(self) -> str:
        return self.path_var.get().strip().strip('"')

    def save_settings(self, delay=400):
        """Debounced save so typing in a field doesn't hammer the disk."""
        if self._save_job:
            self.after_cancel(self._save_job)

        def save():
            self._save_job = None
            self.settings.folder = self.folder()
            try:
                self.settings.save()
            except OSError:
                pass
        self._save_job = self.after(delay, save)

    def set_watch_status(self, watching: bool, detail: str = ""):
        self.side_dot.set(C["watching"] if watching else C["idle"])
        self.side_status.configure(text="Watching" if watching else "Not watching")
        self.side_detail.configure(text=detail or ("Sorting new files as they arrive" if watching
                                                   else "Auto sort is off"))

    def set_badge(self, key, text):
        self.nav[key].set_badge(text)

    # ---------- background work ----------

    def post(self, fn):
        """Run fn on the UI thread. Safe to call from any thread."""
        self.events.put(fn)

    def run_async(self, work, on_done=None, on_error=None):
        """Run work() on a background thread, then on_done(result) / on_error(exc) on the UI thread."""
        def runner():
            try:
                result = work()
            except Exception as e:  # reported to the UI rather than lost on a dead thread
                # Bind e now: Python deletes the except variable when the block ends
                if on_error:
                    self.post(lambda err=e: on_error(err))
                else:
                    self.post(lambda err=e: self.toast(f"Something went wrong: {err}", "danger"))
                return
            if on_done:
                self.post(lambda: on_done(result))
        threading.Thread(target=runner, daemon=True).start()

    def _drain_events(self):
        # Polled on the UI thread; the only place background events touch widgets
        try:
            while True:
                self.events.get_nowait()()
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    # ---------- feedback ----------

    def toast(self, text, tone="accent", ms=3200):
        colors = {"accent": (C["accent"], C["on_accent"]), "danger": (C["danger"], C["on_accent"]),
                  "neutral": (C["toast_neutral"], C["toast_text"])}
        bg, fg = colors.get(tone, colors["neutral"])
        self.toast_label.configure(text=text, bg=bg, fg=fg)
        self.toast_label.place(relx=1.0, rely=1.0, x=-28, y=-24, anchor="se")
        self.toast_label.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(ms, self.toast_label.place_forget)

    def _undo_last(self, event=None):
        if isinstance(event.widget if event else None, (tk.Entry, ttk.Entry)):
            return
        entry = next((e for e in self.history.entries() if not e.undone and e.undoable), None)
        if not entry:
            self.toast("Nothing to undo", "neutral")
            return
        self.undo([entry.id])

    def undo(self, entry_ids):
        def done(outcome):
            if outcome.restored:
                self.toast(f"Put back {len(outcome.restored)} file{'s' if len(outcome.restored) != 1 else ''}")
            if outcome.errors:
                self.toast(outcome.errors[0] + (f" (+{len(outcome.errors) - 1} more)"
                                                if len(outcome.errors) > 1 else ""), "danger", 5000)
            for page in self.pages.values():
                if hasattr(page, "on_history_changed"):
                    page.on_history_changed(entry_ids)
        self.run_async(lambda: self.history.undo(entry_ids), done)

    def _on_close(self):
        self.pages["sort"].shutdown()
        self.pages["share"].detach()
        self.share_server.stop()
        if self._save_job:
            self.after_cancel(self._save_job)
        self.settings.folder = self.folder()
        try:
            self.settings.save()
        except OSError:
            pass
        self.destroy()


if __name__ == "__main__":
    enable_high_dpi()
    TidyApp().mainloop()
