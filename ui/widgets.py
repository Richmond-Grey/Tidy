"""Small reusable building blocks for the desktop UI."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from ui.theme import COLORS as C


class Card(tk.Frame):
    """White panel with a hairline border. Put children in .body."""

    def __init__(self, parent, padding=18, **kw):
        super().__init__(parent, bg=C["surface"], highlightthickness=1, highlightbackground=C["border"],
                         highlightcolor=C["border"], bd=0, **kw)
        self.body = ttk.Frame(self, style="Card.TFrame")
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


def hline(parent, bg=None):
    """1px divider in the border colour (ttk.Separator draws too dark under clam)."""
    return tk.Frame(parent, height=1, bg=C["border"])


class Pill(tk.Label):
    """Small rounded-looking tag, e.g. 'TV show'."""
    TONES = {
        "accent": ("accent_text", "accent_soft"),
        "info": ("info", "info_soft"),
        "warn": ("warn", "warn_soft"),
        "danger": ("danger", "danger_soft"),
        "neutral": ("muted", "bg"),
    }

    def __init__(self, parent, text="", tone="accent", font=None):
        fg, bg = self.TONES[tone]
        super().__init__(parent, text=text, fg=C[fg], bg=C[bg], font=font, padx=8, pady=2, bd=0)

    def set(self, text, tone="accent"):
        fg, bg = self.TONES[tone]
        self.configure(text=text, fg=C[fg], bg=C[bg])


class StatusDot(tk.Canvas):
    def __init__(self, parent, bg, size=10):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self._oval = self.create_oval(1, 1, size - 1, size - 1, outline="")

    def set(self, color):
        self.itemconfigure(self._oval, fill=color)


class PageHeader(ttk.Frame):
    def __init__(self, parent, title, subtitle):
        super().__init__(parent)
        ttk.Label(self, text=title, style="Display.TLabel").pack(anchor="w")
        ttk.Label(self, text=subtitle, style="Muted.TLabel", wraplength=720, justify="left").pack(
            anchor="w", pady=(4, 0))


class Table(tk.Frame):
    """Bordered Treeview with a scrollbar and an empty-state message."""

    def __init__(self, parent, columns, empty_text="", show="headings", selectmode="extended", height=8):
        super().__init__(parent, bg=C["surface"], highlightthickness=1, highlightbackground=C["border"], bd=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        ids = [c[0] for c in columns if c[0] != "#0"]
        self.tree = ttk.Treeview(self, columns=ids, show=show, selectmode=selectmode, height=height)
        for col_id, heading, width, stretch in columns:
            self.tree.heading(col_id, text=heading, anchor="w")
            self.tree.column(col_id, width=width, minwidth=40, stretch=stretch, anchor="w")
        self.tree.tag_configure("alt", background=C["surface_alt"])
        self.tree.tag_configure("muted", foreground=C["faint"])
        self.tree.tag_configure("error", foreground=C["danger"])
        self.tree.tag_configure("success", foreground=C["accent"])
        self.tree.tag_configure("group", font=("TkDefaultFont",), background=C["surface_alt"])
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns", pady=1)
        self.tree.configure(yscrollcommand=bar.set)
        self.empty = ttk.Label(self, text=empty_text, style="Card.Muted.TLabel", justify="center")
        self.refresh_empty()

    def set_empty_text(self, text):
        self.empty.configure(text=text)

    def refresh_empty(self):
        if self.tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.55, anchor="center")

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.refresh_empty()


class ScrollFrame(ttk.Frame):
    """Vertically scrollable area. Add children to .inner."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_wheel(self, event):
        # Only scroll when the pointer is over this area and it's actually visible
        if not self.winfo_ismapped():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None and widget is not self:
            widget = widget.master
        if widget is self and self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


class Dialog(tk.Toplevel):
    """Modal window centred on its parent."""

    def __init__(self, parent, title, width, height):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=C["bg"])
        self.transient(parent.winfo_toplevel())
        self.minsize(min(width, 420), min(height, 300))
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - width) // 2
        y = top.winfo_rooty() + (top.winfo_height() - height) // 3
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.body = ttk.Frame(self, padding=(24, 20, 24, 18))
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _e: self.destroy())

    def show(self):
        self.deiconify()
        self.grab_set()
        self.focus_set()


def open_in_file_manager(path: str):
    """Open a folder (or reveal a file) in Explorer / Finder / the desktop's file manager."""
    try:
        if sys.platform == "win32":
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)  # noqa: S606 - opening a user folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
    except OSError:
        pass


def short_path(path: str, root: str | None) -> str:
    """Path relative to root when inside it, e.g. 'mkv\\'."""
    if root:
        try:
            rel = os.path.relpath(path, root)
            if not rel.startswith(".."):
                return "" if rel == "." else rel
        except ValueError:  # different drives on Windows
            pass
    return path


def plural(n: int, word: str, plural_word: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural_word or word + 's')}"
