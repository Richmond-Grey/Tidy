"""Desktop (Tkinter) front end for Tidy."""
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from sorter import FolderWatcher, MoveResult

COLORS = {
    "bg": "#F4F3EF",
    "surface": "#FFFFFF",
    "border": "#E2E0DA",
    "text": "#1D1C1A",
    "muted": "#6E6B64",
    "accent": "#2C6E5A",
    "accent_active": "#23584A",
    "danger": "#B3412E",
    "danger_active": "#963524",
    "watching": "#2E9D63",
    "idle": "#B5B1A8",
    "row_alt": "#FAF9F6",
    "select": "#E3EEEA",
}


def enable_high_dpi():
    """Render crisp text on scaled Windows displays."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


class TidyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tidy")
        self.configure(bg=COLORS["bg"])
        self.minsize(640, 520)
        self._center(760, 600)

        self.watcher = None
        self.events = queue.Queue()  # Background threads talk to the UI only through this
        self.moved_count = 0
        self.path_var = tk.StringVar()

        self._setup_fonts()
        self._setup_styles()
        self._build()
        self._set_state("idle")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)

    # ---------- setup ----------

    def _center(self, width, height):
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_fonts(self):
        families = set(tkfont.families())
        family = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu")
                       if f in families), tkfont.nametofont("TkDefaultFont").actual("family"))
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=family, size=10)
        self.fonts = {
            "title": tkfont.Font(family=family, size=20, weight="bold"),
            "section": tkfont.Font(family=family, size=11, weight="bold"),
            "body": tkfont.Font(family=family, size=10),
            "small": tkfont.Font(family=family, size=9),
        }

    def _setup_styles(self):
        c = COLORS
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=c["bg"], foreground=c["text"], font=self.fonts["body"],
                        bordercolor=c["border"], focuscolor=c["accent"])
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["surface"], relief="solid", borderwidth=1)
        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Title.TLabel", font=self.fonts["title"])
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("Small.TLabel", foreground=c["muted"], font=self.fonts["small"])
        style.configure("Card.TLabel", background=c["surface"])
        style.configure("CardSection.TLabel", background=c["surface"], font=self.fonts["section"])
        style.configure("CardMuted.TLabel", background=c["surface"], foreground=c["muted"])
        style.configure("Section.TLabel", font=self.fonts["section"])

        style.configure("TEntry", fieldbackground=c["surface"], bordercolor=c["border"],
                        lightcolor=c["border"], darkcolor=c["border"], padding=(8, 6))
        style.map("TEntry",
                  bordercolor=[("focus", c["accent"])],
                  lightcolor=[("focus", c["accent"])],
                  fieldbackground=[("disabled", c["bg"])],
                  foreground=[("disabled", c["muted"])])

        button_common = dict(padding=(14, 7), borderwidth=1, focusthickness=0, relief="solid")
        style.configure("TButton", background=c["surface"], foreground=c["text"],
                        bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                        **button_common)
        style.map("TButton",
                  background=[("disabled", c["bg"]), ("pressed", c["border"]), ("active", c["row_alt"])],
                  foreground=[("disabled", c["muted"])])

        for name, base, active in (("Accent", c["accent"], c["accent_active"]),
                                   ("Danger", c["danger"], c["danger_active"])):
            style.configure(f"{name}.TButton", background=base, foreground="#FFFFFF",
                            bordercolor=base, lightcolor=base, darkcolor=base,
                            font=self.fonts["section"], **button_common)
            style.map(f"{name}.TButton",
                      background=[("disabled", c["idle"]), ("pressed", active), ("active", active)],
                      bordercolor=[("disabled", c["idle"]), ("active", active)],
                      lightcolor=[("active", active)], darkcolor=[("active", active)])

        row_height = self.fonts["body"].metrics("linespace") + 12
        style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                        foreground=c["text"], bordercolor=c["border"], borderwidth=0,
                        rowheight=row_height)
        style.map("Treeview", background=[("selected", c["select"])],
                  foreground=[("selected", c["text"])])
        style.configure("Treeview.Heading", background=c["surface"], foreground=c["muted"],
                        font=self.fonts["small"], relief="flat", borderwidth=0, padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", c["surface"])])
        style.configure("Vertical.TScrollbar", background=c["border"], troughcolor=c["surface"],
                        bordercolor=c["surface"], arrowcolor=c["muted"], lightcolor=c["border"],
                        darkcolor=c["border"], gripcount=0)

    def _build(self):
        root = ttk.Frame(self, padding=(24, 20, 24, 14))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        # Header
        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Tidy", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Moves each file into a folder named after its type, and keeps doing it as new files arrive.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        # Folder card
        card = ttk.Frame(root, style="Card.TFrame", padding=16)
        card.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Folder to sort", style="CardSection.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.path_entry = ttk.Entry(card, textvariable=self.path_var)
        self.path_entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=2)
        self.path_entry.bind("<Return>", lambda _e: self._toggle())
        self.browse_button = ttk.Button(card, text="Browse…", command=self._browse)
        self.browse_button.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(8, 0))

        status_row = tk.Frame(card, bg=COLORS["surface"])
        status_row.grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.status_dot = tk.Canvas(status_row, width=10, height=10, bg=COLORS["surface"],
                                    highlightthickness=0)
        self.status_dot.pack(side="left")
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, outline="")
        self.status_label = ttk.Label(status_row, style="CardMuted.TLabel")
        self.status_label.pack(side="left", padx=(8, 0))

        self.toggle_button = ttk.Button(card, command=self._toggle, width=16)
        self.toggle_button.grid(row=2, column=1, sticky="e", padx=(8, 0), pady=(14, 0))

        # Activity header
        activity_header = ttk.Frame(root)
        activity_header.grid(row=2, column=0, sticky="ew", pady=(22, 8))
        ttk.Label(activity_header, text="Activity", style="Section.TLabel").pack(side="left")
        self.count_label = ttk.Label(activity_header, style="Muted.TLabel")
        self.count_label.pack(side="left", padx=(10, 0))
        ttk.Button(activity_header, text="Clear", command=self._clear_log).pack(side="right")

        # Activity log
        log_card = ttk.Frame(root, style="Card.TFrame", padding=1)
        log_card.grid(row=3, column=0, sticky="nsew")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(0, weight=1)

        self.log = ttk.Treeview(log_card, columns=("time", "file", "folder"), show="headings",
                                selectmode="browse")
        for column, heading, width, stretch in (("time", "TIME", 90, False),
                                                ("file", "FILE", 300, True),
                                                ("folder", "MOVED TO", 160, True)):
            self.log.heading(column, text=heading, anchor="w")
            self.log.column(column, width=width, minwidth=60, stretch=stretch, anchor="w")
        self.log.tag_configure("alt", background=COLORS["row_alt"])
        self.log.tag_configure("error", foreground=COLORS["danger"])
        self.log.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(log_card, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        self.empty_label = ttk.Label(log_card, style="CardMuted.TLabel",
                                     text="Sorted files will show up here.")
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        # Footer
        ttk.Label(root, text="Made by Richmond", style="Small.TLabel").grid(
            row=4, column=0, sticky="e", pady=(10, 0))

        self._update_count()

    # ---------- actions ----------

    def _browse(self):
        folder = filedialog.askdirectory(title="Choose a folder to sort",
                                         initialdir=self.path_var.get() or os.path.expanduser("~"))
        if folder:
            self.path_var.set(os.path.normpath(folder))

    def _toggle(self):
        if self.watcher:
            self._stop()
            return

        path = self.path_var.get().strip().strip('"')
        if not path:
            messagebox.showinfo("Choose a folder", "Pick a folder to sort first.", parent=self)
            return
        if not os.path.isdir(path):
            messagebox.showerror("Folder not found", f"Couldn't find a folder at:\n{path}", parent=self)
            return

        self.path_var.set(os.path.normpath(path))
        self.watcher = FolderWatcher(path, lambda result: self.events.put(("moved", result)))
        self._set_state("starting")
        threading.Thread(target=self._start_watcher, args=(self.watcher,), daemon=True).start()

    def _start_watcher(self, watcher):
        # Runs off the UI thread: the initial sort can take a while on big folders
        try:
            watcher.start()
            self.events.put(("started", watcher))
        except OSError as e:
            self.events.put(("failed", (watcher, str(e))))

    def _stop(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self._set_state("idle")

    def _clear_log(self):
        self.log.delete(*self.log.get_children())
        self.moved_count = 0
        self._update_count()

    def _on_close(self):
        if self.watcher:
            self.watcher.stop()
        self.destroy()

    # ---------- UI updates ----------

    def _drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "moved":
                    self._add_log_row(payload)
                elif kind == "started" and payload is self.watcher:
                    self._set_state("watching")
                elif kind == "failed" and payload[0] is self.watcher:
                    self.watcher = None
                    self._set_state("idle")
                    messagebox.showerror("Couldn't start sorting", payload[1], parent=self)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _add_log_row(self, result: MoveResult):
        name = os.path.basename(result.source)
        if result.error:
            folder, tags = f"Failed: {result.error}", ("error",)
        else:
            folder, tags = os.path.basename(os.path.dirname(result.destination)) + os.sep, ()
            self.moved_count += 1
        if len(self.log.get_children()) % 2:
            tags += ("alt",)
        row = self.log.insert("", "end", values=(time.strftime("%H:%M:%S"), name, folder), tags=tags)
        self.log.see(row)
        self._update_count()

    def _update_count(self):
        n = self.moved_count
        self.count_label.configure(text=f"{n} file{'s' if n != 1 else ''} sorted")
        if self.log.get_children():
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _set_state(self, state):
        watching_text = f"Watching {os.path.basename(self.path_var.get()) or self.path_var.get()}"
        text, dot, button_text, button_style, button_enabled, inputs_enabled = {
            "idle": ("Not running", COLORS["idle"], "Start sorting", "Accent.TButton", True, True),
            "starting": ("Sorting existing files…", COLORS["accent"], "Starting…", "Accent.TButton", False, False),
            "watching": (watching_text, COLORS["watching"], "Stop", "Danger.TButton", True, False),
        }[state]
        self.status_label.configure(text=text)
        self.status_dot.itemconfigure(self._dot, fill=dot)
        self.toggle_button.configure(text=button_text, style=button_style,
                                     state="normal" if button_enabled else "disabled")
        input_state = "normal" if inputs_enabled else "disabled"
        self.path_entry.configure(state=input_state)
        self.browse_button.configure(state=input_state)


if __name__ == "__main__":
    enable_high_dpi()
    TidyApp().mainloop()
