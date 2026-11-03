"""History page: everything Tidy moved, with undo."""
import os
import time
from tkinter import messagebox, ttk

from ui.widgets import PageHeader, Table, open_in_file_manager

KIND_NAMES = {"sort": "Sorted", "group": "Grouped", "rename": "Renamed", "subtitle": "Subtitles",
              "duplicate": "Recycled"}


class HistoryPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(36, 30, 36, 24))
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        PageHeader(self, "History",
                   "Everything Tidy has moved, newest first. Select anything and undo it to put the files back "
                   "where they were. Ctrl+Z undoes the latest action.").grid(row=0, column=0, sticky="ew")

        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(20, 12))
        self.undo_button = ttk.Button(toolbar, text="Undo selected", style="Accent.TButton",
                                      command=self.undo_selected, state="disabled")
        self.undo_button.pack(side="left")
        self.count_label = ttk.Label(toolbar, style="Muted.TLabel")
        self.count_label.pack(side="left", padx=(14, 0))
        ttk.Button(toolbar, text="Clear history", style="Ghost.TButton", command=self.clear).pack(side="right")

        self.table = Table(self, [("time", "WHEN", 120, False), ("action", "ACTION", 90, False),
                                  ("details", "DETAILS", 420, True), ("status", "STATUS", 100, False)],
                           empty_text="Nothing yet. Files Tidy moves will be listed here.")
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_button())
        self.table.tree.bind("<Double-1>", self._reveal)

    def on_show(self):
        self.refresh()

    def on_history_changed(self, _ids):
        if self.winfo_ismapped():
            self.refresh()

    def refresh(self):
        tree = self.table.tree
        selected = set(tree.selection())
        tree.delete(*tree.get_children())
        entries = self.app.history.entries()
        today = time.strftime("%Y-%m-%d")
        for i, entry in enumerate(entries):
            stamp = time.localtime(entry.time)
            when = time.strftime("%H:%M" if time.strftime("%Y-%m-%d", stamp) == today else "%d %b, %H:%M", stamp)
            status = "Undone" if entry.undone else ("" if entry.undoable else "Can't undo")
            tags = ("muted",) if entry.undone else (("alt",) if i % 2 else ())
            iid = str(entry.id)
            tree.insert("", "end", iid=iid, values=(when, KIND_NAMES.get(entry.kind, entry.kind.title()),
                                                    entry.label, status), tags=tags)
        for iid in selected:
            if tree.exists(iid):
                tree.selection_add(iid)
        active = sum(1 for e in entries if not e.undone)
        self.count_label.configure(text=f"{active} action{'s' if active != 1 else ''} can be undone"
                                   if entries else "")
        self.table.refresh_empty()
        self._update_button()

    def _selected_ids(self):
        ids = []
        for iid in self.table.tree.selection():
            entry = self.app.history.get(int(iid))
            if entry and not entry.undone and entry.undoable:
                ids.append(entry.id)
        return ids

    def _update_button(self):
        self.undo_button.configure(state="normal" if self._selected_ids() else "disabled")

    def undo_selected(self):
        ids = self._selected_ids()
        if ids:
            self.app.undo(ids)

    def _reveal(self, _event):
        iid = self.table.tree.focus()
        entry = self.app.history.get(int(iid)) if iid else None
        if not entry or not entry.moves:
            return
        source, destination = entry.moves[0]
        target = source if entry.undone else destination
        if os.path.exists(target):
            open_in_file_manager(target)

    def clear(self):
        if messagebox.askyesno("Clear history", "Forget all past actions? Files stay where they are, but you "
                                                "won't be able to undo these moves any more.", parent=self):
            self.app.history.clear()
            self.refresh()
