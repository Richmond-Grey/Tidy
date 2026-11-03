"""Duplicates page: find identical files and send the extra copies to the Recycle Bin."""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from duplicates import find_duplicates, human_size, send_to_trash
from ui.widgets import PageHeader, Table, plural, short_path

KEEP, REMOVE = "Keep", "Remove"


class DuplicatesPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(36, 30, 36, 24))
        self.app = app
        self.root_folder = None
        self.cancel = None
        self.rows: dict[str, str] = {}       # child row -> path
        self.actions: dict[str, str] = {}    # child row -> KEEP / REMOVE
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        PageHeader(self, "Duplicates",
                   "Finds files with exactly the same contents, even when their names differ. The extra "
                   "copies go to the Recycle Bin, so nothing is lost for good.").grid(row=0, column=0, sticky="ew")

        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(20, 6))
        self.scan_button = ttk.Button(toolbar, text="Find duplicates", style="Accent.TButton", command=self.scan)
        self.scan_button.pack(side="left")
        self.recursive_var = tk.BooleanVar(value=app.settings.duplicates_recursive)
        ttk.Checkbutton(toolbar, text="Include subfolders", variable=self.recursive_var,
                        command=self._recursive_changed).pack(side="left", padx=(16, 0))
        self.trash_button = ttk.Button(toolbar, text="Recycle marked copies", style="Danger.TButton",
                                       command=self.trash_marked, state="disabled")
        self.trash_button.pack(side="right")
        self.toggle_button = ttk.Button(toolbar, text="Keep / remove", command=self.toggle_selected,
                                        state="disabled")
        self.toggle_button.pack(side="right", padx=(0, 8))

        status = ttk.Frame(self)
        status.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        self.summary_label = ttk.Label(status, style="Muted.TLabel",
                                       text="Double-click a file to switch between Keep and Remove.")
        self.summary_label.pack(side="left")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=140,
                                        style="Accent.Horizontal.TProgressbar")

        self.table = Table(self, [("#0", "FILE", 320, True), ("size", "SIZE", 90, False),
                                  ("action", "ACTION", 90, False), ("where", "FOLDER", 220, True)],
                           show="tree headings", empty_text="Press “Find duplicates” to scan your folder.")
        self.table.grid(row=3, column=0, sticky="nsew")
        tree = self.table.tree
        tree.tag_configure("remove", foreground="#B4432F")
        tree.tag_configure("keep", foreground="#1F5446")
        tree.bind("<Double-1>", self._double_click)
        tree.bind("<space>", lambda _e: self.toggle_selected())
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())

    def _recursive_changed(self):
        self.app.settings.duplicates_recursive = self.recursive_var.get()
        self.app.save_settings(0)

    def scan(self):
        if self.cancel:  # second press = stop
            self.cancel.set()
            return
        root = self.app.folder()
        if not root or not os.path.isdir(root):
            messagebox.showinfo("Choose a folder", "Pick the folder to scan on the Auto sort page first.",
                                parent=self)
            self.app.show_page("sort")
            return
        self.root_folder = os.path.normpath(root)
        self.cancel = threading.Event()
        cancel = self.cancel
        recursive = self.recursive_var.get()
        self.scan_button.configure(text="Stop")
        self.progress.pack(side="right")
        self.progress.start(12)
        self.summary_label.configure(text="Looking for files with the same size…")

        def progress(text):
            self.app.post(lambda: cancel is self.cancel and self.summary_label.configure(text=text))

        def done(groups):
            stopped = cancel.is_set()
            self._finish_scan()
            if stopped:
                self.summary_label.configure(text="Scan stopped.")
                return
            self._fill(groups)

        def failed(e):
            self._finish_scan()
            messagebox.showerror("Couldn't scan", str(e), parent=self)

        self.app.run_async(lambda: find_duplicates(self.root_folder, recursive, progress=progress, cancel=cancel),
                           done, failed)

    def _finish_scan(self):
        self.cancel = None
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_button.configure(text="Scan again")

    def _fill(self, groups):
        tree = self.table.tree
        self.table.clear()
        self.rows.clear()
        self.actions.clear()
        for group in groups:
            try:
                size = human_size(os.path.getsize(group[0]))
            except OSError:
                continue
            parent = tree.insert("", "end", text=f"{os.path.basename(group[0])}   ·   {len(group)} copies",
                                 values=(size, "", ""), open=True, tags=("group",))
            for i, path in enumerate(group):
                action = KEEP if i == 0 else REMOVE
                row = tree.insert(parent, "end", text=os.path.basename(path),
                                  values=(size, action, short_path(os.path.dirname(path), self.root_folder)
                                          or "main folder"),
                                  tags=(action.lower(),))
                self.rows[row] = path
                self.actions[row] = action
        self.table.set_empty_text("No duplicates found. Nice and clean.")
        self.table.refresh_empty()
        self._update_summary(groups)
        self._update_buttons()

    def _update_summary(self, groups=None):
        sets = len(self.table.tree.get_children())
        if not sets:
            self.summary_label.configure(text="No duplicates found.")
            self.app.set_badge("duplicates", "")
            return
        marked = [p for r, p in self.rows.items() if self.actions[r] == REMOVE]
        size = sum(os.path.getsize(p) for p in marked if os.path.exists(p))
        self.summary_label.configure(
            text=f"{plural(sets, 'set')} of duplicates  ·  {plural(len(marked), 'copy', 'copies')} marked  ·  "
                 f"{human_size(size)} can be freed")
        self.app.set_badge("duplicates", str(sets))

    def _double_click(self, event):
        row = self.table.tree.identify_row(event.y)
        if row in self.rows:
            self._toggle([row])
        return "break"

    def toggle_selected(self):
        self._toggle([r for r in self.table.tree.selection() if r in self.rows])

    def _toggle(self, rows):
        tree = self.table.tree
        for row in rows:
            new = KEEP if self.actions[row] == REMOVE else REMOVE
            if new == REMOVE:
                siblings = tree.get_children(tree.parent(row))
                if all(self.actions[s] == REMOVE for s in siblings if s != row):
                    self.app.toast("Keep at least one copy of every file", "neutral")
                    continue
            self.actions[row] = new
            values = list(tree.item(row, "values"))
            values[1] = new
            tree.item(row, values=values, tags=(new.lower(),))
        self._update_summary()
        self._update_buttons()

    def _update_buttons(self):
        any_marked = any(a == REMOVE for a in self.actions.values())
        self.trash_button.configure(state="normal" if any_marked else "disabled")
        selected = any(r in self.rows for r in self.table.tree.selection())
        self.toggle_button.configure(state="normal" if selected else "disabled")

    def trash_marked(self):
        marked = [r for r, a in self.actions.items() if a == REMOVE]
        if not marked:
            return
        paths = [self.rows[r] for r in marked]
        size = human_size(sum(os.path.getsize(p) for p in paths if os.path.exists(p)))
        if not messagebox.askyesno("Recycle copies",
                                   f"Move {plural(len(paths), 'copy', 'copies')} ({size}) to the Recycle Bin?\n\n"
                                   "You can restore them from there if you change your mind.", parent=self):
            return
        self.trash_button.configure(state="disabled")

        def done(failures):
            failed = {p for p, _e in failures}
            tree = self.table.tree
            for row in marked:
                if self.rows[row] not in failed:
                    parent = tree.parent(row)
                    tree.delete(row)
                    del self.rows[row]
                    del self.actions[row]
                    if len(tree.get_children(parent)) < 2:
                        for child in tree.get_children(parent):
                            self.rows.pop(child, None)
                            self.actions.pop(child, None)
                        tree.delete(parent)
            self.table.refresh_empty()
            self._update_summary()
            self._update_buttons()
            removed = len(paths) - len(failed)
            if removed:
                self.app.toast(f"Recycled {plural(removed, 'copy', 'copies')}")
            if failures:
                messagebox.showwarning("Some copies weren't removed",
                                       "\n".join(f"{os.path.basename(p)}: {e}" for p, e in failures[:8]),
                                       parent=self)

        self.app.run_async(lambda: send_to_trash(paths), done)
