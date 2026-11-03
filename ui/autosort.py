"""Auto sort page: pick a folder, sort it once, then keep sorting new arrivals."""
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sorter import (MODE_CATEGORY, MODE_EXTENSION, FolderWatcher, MoveResult, plan_directory,
                    remove_empty_folders, sort_directory)
from ui.theme import COLORS as C
from ui.widgets import Card, hline, Dialog, PageHeader, StatusDot, Table, open_in_file_manager, plural


class AutoSortPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(36, 30, 36, 24))
        self.app = app
        self.watcher = None
        self.moved_count = 0
        self.row_entries: dict[str, int] = {}  # tree row -> history entry id
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        PageHeader(self, "Auto sort",
                   "Moves every file into a folder named after its type, then keeps doing it as new "
                   "files arrive.").grid(row=0, column=0, sticky="ew")

        # Folder card
        card = Card(self)
        card.grid(row=1, column=0, sticky="ew", pady=(22, 0))
        body = card.body
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Folder to keep tidy", style="Card.Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(body, text="Open folder", style="CardGhost.TButton",
                   command=lambda: self.app.folder() and open_in_file_manager(self.app.folder())).grid(
            row=0, column=1, columnspan=2, sticky="e")
        self.path_entry = ttk.Entry(body, textvariable=app.path_var)
        self.path_entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.path_entry.bind("<Return>", lambda _e: self.toggle())
        app.path_var.trace_add("write", lambda *_: app.save_settings())
        self.browse_button = ttk.Button(body, text="Browse…", command=self.browse)
        self.browse_button.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))

        mode_row = ttk.Frame(body, style="Card.TFrame")
        mode_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(16, 0))
        ttk.Label(mode_row, text="Sort into", style="Card.Muted.TLabel").pack(side="left", padx=(0, 12))
        self.mode_var = tk.StringVar(value=app.settings.sort_mode)
        for value, text in ((MODE_EXTENSION, "File type  ·  pdf/, jpg/"),
                            (MODE_CATEGORY, "Category  ·  Documents/, Images/")):
            ttk.Radiobutton(mode_row, text=text, value=value, variable=self.mode_var,
                            style="Segment.TRadiobutton", command=self._mode_changed).pack(side="left")

        hline(body).grid(row=3, column=0, columnspan=3, sticky="ew", pady=16)

        status_row = ttk.Frame(body, style="Card.TFrame")
        status_row.grid(row=4, column=0, sticky="w")
        self.status_dot = StatusDot(status_row, C["surface"])
        self.status_dot.pack(side="left")
        self.status_label = ttk.Label(status_row, style="Card.TLabel")
        self.status_label.pack(side="left", padx=(10, 0))

        self.preview_button = ttk.Button(body, text="Preview", command=self.preview)
        self.preview_button.grid(row=4, column=1, sticky="e", padx=(8, 0))
        self.toggle_button = ttk.Button(body, command=self.toggle, width=15)
        self.toggle_button.grid(row=4, column=2, sticky="e", padx=(8, 0))

        # Activity
        header = ttk.Frame(self)
        header.grid(row=3, column=0, sticky="ew", pady=(26, 10))
        ttk.Label(header, text="Activity", style="Title.TLabel").pack(side="left")
        self.count_label = ttk.Label(header, style="Muted.TLabel")
        self.count_label.pack(side="left", padx=(12, 0), pady=(3, 0))
        ttk.Button(header, text="Clear list", style="Ghost.TButton", command=self.clear_log).pack(side="right")
        self.undo_button = ttk.Button(header, text="Undo selected", command=self.undo_selected, state="disabled")
        self.undo_button.pack(side="right", padx=(0, 6))
        ttk.Button(header, text="Remove empty folders", style="Ghost.TButton",
                   command=self.clean_empty).pack(side="right", padx=(0, 6))

        self.table = Table(self, [("time", "TIME", 90, False), ("file", "FILE", 340, True),
                                  ("folder", "MOVED TO", 180, True)],
                           empty_text="Sorted files will show up here.\nPick a folder and press Start.")
        self.table.grid(row=4, column=0, sticky="nsew")
        self.table.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_undo_button())
        self.table.tree.bind("<Double-1>", self._reveal)

        self._update_count()
        self._set_state("idle")

    # ---------- actions ----------

    def browse(self):
        folder = filedialog.askdirectory(title="Choose a folder to keep tidy",
                                         initialdir=self.app.folder() or os.path.expanduser("~"))
        if folder:
            self.app.path_var.set(os.path.normpath(folder))

    def _valid_folder(self) -> str | None:
        path = self.app.folder()
        if not path:
            messagebox.showinfo("Choose a folder", "Pick a folder to sort first.", parent=self)
            return None
        if not os.path.isdir(path):
            messagebox.showerror("Folder not found", f"Couldn't find a folder at:\n{path}", parent=self)
            return None
        return os.path.normpath(path)

    def maybe_autostart(self):
        folder = self.app.folder()
        if self.app.settings.start_on_launch and folder and os.path.isdir(folder):
            self.toggle()

    def toggle(self):
        if self.watcher:
            self.stop()
            return
        path = self._valid_folder()
        if not path:
            return
        self.app.path_var.set(path)
        self.watcher = FolderWatcher(path, lambda r: self.app.post(lambda: self.add_result(r)),
                                     rules=self.app.rules(), history=self.app.history)
        self._set_state("starting")
        watcher = self.watcher
        threading.Thread(target=self._start_watcher, args=(watcher,), daemon=True).start()

    def _start_watcher(self, watcher):
        # Runs off the UI thread: the initial sort can take a while on big folders
        try:
            watcher.start()
            self.app.post(lambda: self._started(watcher))
        except OSError as e:
            message = str(e)
            self.app.post(lambda: self._failed(watcher, message))

    def _started(self, watcher):
        # Ignore a watcher that was stopped before it finished starting
        if watcher is self.watcher:
            self._set_state("watching")

    def _failed(self, watcher, message):
        if watcher is self.watcher:
            self.watcher = None
            self._set_state("idle")
            messagebox.showerror("Couldn't start sorting", message, parent=self)

    def stop(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self._set_state("idle")

    def shutdown(self):
        if self.watcher:
            self.watcher.stop()

    def _mode_changed(self):
        self.app.settings.sort_mode = self.mode_var.get()
        self.app.save_settings(0)
        if self.watcher:
            self.watcher.rules.mode = self.mode_var.get()
        settings_page = self.app.pages.get("settings")
        if settings_page:
            settings_page.sync_from_settings()

    def apply_rules(self):
        """Settings changed elsewhere: pick them up, including on a running watcher."""
        self.mode_var.set(self.app.settings.sort_mode)
        if self.watcher:
            rules = self.app.rules()
            self.watcher.rules.mode = rules.mode
            self.watcher.rules.ignore_patterns = rules.ignore_patterns

    def preview(self):
        path = self._valid_folder()
        if not path:
            return
        plan = plan_directory(path, self.app.rules())
        dialog = Dialog(self, "Preview", 620, 520)
        body = dialog.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(body, text="What sorting would do", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        folders = {f for _n, f in plan}
        summary = (f"{plural(len(plan), 'file')} would move into {plural(len(folders), 'folder')}. "
                   "Nothing has been moved yet.") if plan else "Nothing to sort: this folder is already tidy."
        ttk.Label(body, text=summary, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 14))
        table = Table(body, [("file", "FILE", 340, True), ("folder", "GOES TO", 160, True)],
                      empty_text="No loose files here.")
        table.grid(row=2, column=0, sticky="nsew")
        for i, (name, folder) in enumerate(plan):
            table.tree.insert("", "end", values=(name, folder + os.sep), tags=("alt",) if i % 2 else ())
        table.refresh_empty()
        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="left")
        if plan and not self.watcher:
            def sort_once():
                dialog.destroy()
                self._sort_once(path)
            ttk.Button(buttons, text="Sort once", command=sort_once).pack(side="left", padx=(8, 0))

            def start():
                dialog.destroy()
                self.toggle()
            ttk.Button(buttons, text="Sort and keep watching", style="Accent.TButton",
                       command=start).pack(side="left", padx=(8, 0))
        dialog.show()

    def _sort_once(self, path):
        rules, history = self.app.rules(), self.app.history

        def work():
            sort_directory(path, lambda r: self.app.post(lambda: self.add_result(r)), rules, history)
        self.app.run_async(work, lambda _r: self.app.toast("Folder sorted"))

    def clean_empty(self):
        path = self._valid_folder()
        if not path:
            return
        removed = remove_empty_folders(path)
        self.app.toast(f"Removed {plural(len(removed), 'empty folder')}" if removed
                       else "No empty folders found", "accent" if removed else "neutral")

    def undo_selected(self):
        ids = sorted({self.row_entries[row] for row in self.table.tree.selection() if row in self.row_entries})
        if ids:
            self.app.undo(ids)

    def on_history_changed(self, entry_ids):
        undone = set(entry_ids)
        for row, entry_id in list(self.row_entries.items()):
            entry = self.app.history.get(entry_id)
            if entry_id in undone and entry and entry.undone and self.table.tree.exists(row):
                values = list(self.table.tree.item(row, "values"))
                values[2] = "Put back"
                self.table.tree.item(row, values=values, tags=("muted",))
                del self.row_entries[row]
        self._update_undo_button()

    def _reveal(self, _event):
        row = self.table.tree.focus()
        entry = self.app.history.get(self.row_entries.get(row, -1))
        if entry and entry.moves and os.path.exists(entry.moves[0][1]):
            open_in_file_manager(entry.moves[0][1])

    def clear_log(self):
        self.table.clear()
        self.row_entries.clear()
        self.moved_count = 0
        self._update_count()
        self._update_undo_button()

    # ---------- UI updates ----------

    def add_result(self, result: MoveResult):
        name = os.path.basename(result.source)
        if result.error:
            folder, tags = f"Failed: {result.error}", ("error",)
        else:
            folder, tags = os.path.basename(os.path.dirname(result.destination)) + os.sep, ()
            self.moved_count += 1
        if len(self.table.tree.get_children()) % 2:
            tags += ("alt",)
        row = self.table.tree.insert("", "end", values=(time.strftime("%H:%M:%S"), name, folder), tags=tags)
        if result.history_id:
            self.row_entries[row] = result.history_id
        self.table.tree.see(row)
        self._update_count()

    def _update_count(self):
        self.count_label.configure(text=f"{plural(self.moved_count, 'file')} sorted")
        self.app.set_badge("sort", str(self.moved_count) if self.moved_count else "")
        self.table.refresh_empty()

    def _update_undo_button(self):
        selected = any(row in self.row_entries for row in self.table.tree.selection())
        self.undo_button.configure(state="normal" if selected else "disabled")

    def _set_state(self, state):
        # One place to keep the status, button and inputs consistent with each other
        folder = os.path.basename(self.app.folder()) or self.app.folder()
        text, dot, button_text, button_style, button_enabled, inputs_enabled = {
            "idle": ("Not running", C["idle"], "Start sorting", "Accent.TButton", True, True),
            "starting": ("Sorting existing files…", C["accent"], "Starting…", "Accent.TButton", False, False),
            "watching": (f"Watching {folder}", C["watching"], "Stop", "Danger.TButton", True, False),
        }[state]
        self.status_label.configure(text=text)
        self.status_dot.set(dot)
        self.toggle_button.configure(text=button_text, style=button_style,
                                     state="normal" if button_enabled else "disabled")
        input_state = "normal" if inputs_enabled else "disabled"
        self.path_entry.configure(state=input_state)
        self.browse_button.configure(state=input_state)
        self.preview_button.configure(state=input_state)
        self.app.set_watch_status(state == "watching", f"Sorting {folder} as files arrive"
                                  if state == "watching" else "")
