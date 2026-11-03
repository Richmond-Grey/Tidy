"""Group similar page: find files that belong together, tweak each group, move it into a folder."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import grouping
import media
from sorter import safe_folder_name
from subtitles import LANGUAGES, OpenSubtitles, SubtitleError, has_subtitle
from ui.widgets import Card, hline, Dialog, PageHeader, Pill, Table, open_in_file_manager, plural, short_path

KIND_LABELS = {
    grouping.KIND_SHOW: ("TV show", "info", "Show"),
    grouping.KIND_MOVIE: ("Movie", "warn", "Movie"),
    grouping.KIND_SIMILAR: ("Similar names", "accent", "Similar"),
}
LANGUAGE_BY_NAME = {name: code for code, name in LANGUAGES.items()}


class GroupsPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(36, 30, 36, 24))
        self.app = app
        self.root_folder: str | None = None
        self.groups: list[grouping.FileGroup] = []
        self.pool: list[str] = []                 # every file found by the last scan
        self.current: grouping.FileGroup | None = None
        self.sub_status: dict[str, str] = {}      # video path -> subtitle status text
        self.busy = False
        self._group_rows: dict[str, grouping.FileGroup] = {}
        self._file_rows: dict[str, str] = {}
        self._loading = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        PageHeader(self, "Group similar files",
                   "Episodes of a show, a movie and its subtitles, numbered scans… "
                   "Check each group, name its folder, and move on to the next."
                   ).grid(row=0, column=0, sticky="ew")

        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(18, 12))
        self.scan_button = ttk.Button(toolbar, text="Find groups", style="Accent.TButton", command=self.scan)
        self.scan_button.pack(side="left")
        self.include_var = tk.BooleanVar(value=app.settings.group_include_sorted)
        ttk.Checkbutton(toolbar, text="Also look inside folders Tidy already sorted (mkv/, Videos/…)",
                        variable=self.include_var, command=self._include_changed).pack(side="left", padx=(16, 0))
        self.summary_label = ttk.Label(toolbar, style="Muted.TLabel")
        self.summary_label.pack(side="right")
        self.progress = ttk.Progressbar(toolbar, mode="indeterminate", length=120,
                                        style="Accent.Horizontal.TProgressbar")

        main = ttk.Frame(self)
        main.grid(row=2, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self.group_table = Table(main, [("name", "GROUP", 130, True), ("kind", "TYPE", 66, False),
                                        ("count", "FILES", 62, False)],
                                 empty_text="Press “Find groups”\nto scan your folder.", selectmode="browse")
        self.group_table.grid(row=0, column=0, sticky="nsew")
        self.group_table.configure(width=270)
        self.group_table.grid_propagate(False)
        self.group_table.tree.bind("<<TreeviewSelect>>", self._group_selected)

        self.detail = Card(main, padding=18)
        self.detail.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self._build_detail(self.detail.body)
        self._show_detail(False, "Groups you find will open here.")

    # ---------- layout ----------

    def _build_detail(self, body):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)

        self.placeholder = ttk.Label(body, style="Card.Muted.TLabel", justify="center")

        top = ttk.Frame(body, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        self.kind_pill = Pill(top, font=self.app.theme.fonts["small_strong"])
        self.kind_pill.pack(side="left")
        self.position_label = ttk.Label(top, style="Card.Small.TLabel")
        self.position_label.pack(side="right")

        self.folder_label = ttk.Label(body, text="Folder name", style="Card.Section.TLabel")
        self.folder_label.grid(row=1, column=0, sticky="w", pady=(12, 6))
        self.name_var = tk.StringVar()
        self.name_var.trace_add("write", self._name_changed)
        self.name_entry = ttk.Entry(body, textvariable=self.name_var, font=self.app.theme.fonts["title"])
        self.name_entry.grid(row=2, column=0, sticky="ew")
        self.name_entry.bind("<Return>", lambda _e: self.move_current())
        self.dest_label = ttk.Label(body, style="Card.Small.TLabel")
        self.dest_label.grid(row=3, column=0, sticky="w", pady=(6, 0))

        files_header = ttk.Frame(body, style="Card.TFrame")
        files_header.grid(row=4, column=0, sticky="ew", pady=(14, 6))
        self.files_label = ttk.Label(files_header, style="Card.Section.TLabel")
        self.files_label.pack(side="left")
        self.remove_button = ttk.Button(files_header, text="Remove selected", style="CardGhost.TButton",
                                        command=self.remove_selected, state="disabled")
        self.remove_button.pack(side="right")
        self.add_button = ttk.Button(files_header, text="Add files…", style="CardGhost.TButton",
                                     command=self.add_files)
        self.add_button.pack(side="right", padx=(0, 4))

        self.file_table = Table(body, [("file", "FILE", 300, True), ("newname", "NEW NAME", 200, True),
                                       ("where", "NOW IN", 100, False), ("subs", "SUBTITLES", 110, False)],
                                empty_text="This group is empty.")
        self.file_table.grid(row=5, column=0, sticky="nsew")
        self.file_table.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        self.file_table.tree.bind("<Delete>", lambda _e: self.remove_selected())
        self.file_table.tree.bind("<Double-1>", self._reveal_file)

        # Options for shows and movies
        self.media_frame = ttk.Frame(body, style="Card.TFrame")
        self.media_frame.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.media_frame.columnconfigure(1, weight=1)
        self.rename_var = tk.BooleanVar(value=self.app.settings.rename_episodes)
        self.rename_check = ttk.Checkbutton(self.media_frame, style="Card.TCheckbutton",
                                            text="Rename to  Show - S01E02",
                                            variable=self.rename_var, command=self._rename_changed)
        self.rename_check.grid(row=0, column=0, sticky="w")
        self.lang_var = tk.StringVar(value=LANGUAGES.get(self.app.settings.subtitle_language, "English"))
        self.lang_combo = ttk.Combobox(self.media_frame, textvariable=self.lang_var, state="readonly", width=11,
                                       values=sorted(LANGUAGES.values()))
        self.lang_combo.grid(row=0, column=2, sticky="e", padx=(12, 8))
        self.lang_combo.bind("<<ComboboxSelected>>", self._lang_changed)
        self.subs_button = ttk.Button(self.media_frame, text="Get subtitles", command=self.get_subtitles)
        self.subs_button.grid(row=0, column=3, sticky="e")

        hline(body).grid(row=7, column=0, sticky="ew", pady=14)
        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=8, column=0, sticky="ew")
        self.skip_button = ttk.Button(actions, text="Skip this group", command=self.skip_current)
        self.skip_button.pack(side="left")
        self.move_button = ttk.Button(actions, style="Accent.TButton", command=self.move_current)
        self.move_button.pack(side="right")
        self.action_label = ttk.Label(actions, style="Card.Small.TLabel")
        self.action_label.pack(side="right", padx=(0, 12))
        self.subs_label = ttk.Label(actions, style="Card.Small.TLabel")  # subtitle progress
        self.subs_label.pack(side="left", padx=(12, 0))

    def _show_detail(self, visible, message=""):
        # grid_slaves() skips hidden widgets, so remember the full list once
        if not hasattr(self, "_detail_widgets"):
            self._detail_widgets = list(self.detail.body.grid_slaves())
        for widget in self._detail_widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()
        if visible:
            self.placeholder.place_forget()
        else:
            self.placeholder.configure(text=message)
            self.placeholder.place(relx=0.5, rely=0.45, anchor="center")

    # ---------- scanning ----------

    def on_show(self):
        if not self.groups and not self.root_folder:
            folder = self.app.folder()
            self.summary_label.configure(text=f"Folder: {folder}" if folder else "Choose a folder on Auto sort first")

    def _include_changed(self):
        self.app.settings.group_include_sorted = self.include_var.get()
        self.app.save_settings(0)

    def scan(self):
        root = self.app.folder()
        if not root or not os.path.isdir(root):
            messagebox.showinfo("Choose a folder", "Pick the folder to scan on the Auto sort page first.",
                                parent=self)
            self.app.show_page("sort")
            return
        root = os.path.normpath(root)
        include = self.include_var.get()
        self.scan_button.configure(state="disabled", text="Scanning…")
        self.summary_label.pack_forget()
        self.progress.pack(side="right")
        self.progress.start(12)

        def work():
            files = grouping.collect_files(root, include)
            groups, leftovers = grouping.find_groups(files)
            return files, groups, leftovers

        def done(result):
            files, groups, _leftovers = result
            self._scan_finished()
            self.root_folder = root
            self.pool = sorted(files, key=lambda p: os.path.basename(p).lower())
            self.groups = groups
            self.sub_status.clear()
            self._refresh_groups()
            if groups:
                self._select(groups[0])
            else:
                self.current = None
                self._show_detail(False, "No similar files found.\nEverything here already looks unique.")
            self._update_summary()

        def failed(error):
            self._scan_finished()
            messagebox.showerror("Couldn't scan", str(error), parent=self)

        self.app.run_async(work, done, failed)

    def _scan_finished(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.summary_label.pack(side="right")
        self.scan_button.configure(state="normal", text="Scan again" if self.root_folder else "Find groups")

    def _update_summary(self):
        files = sum(len(g.files) for g in self.groups)
        text = f"{plural(len(self.groups), 'group')} left  ·  {plural(files, 'file')}" if self.groups else \
            ("All groups done" if self.root_folder else "")
        self.summary_label.configure(text=text)
        self.app.set_badge("group", str(len(self.groups)) if self.groups else "")

    # ---------- group list ----------

    def _refresh_groups(self):
        tree = self.group_table.tree
        tree.delete(*tree.get_children())
        self._group_rows.clear()
        for i, group in enumerate(self.groups):
            row = tree.insert("", "end", values=self._group_values(group), tags=("alt",) if i % 2 else ())
            self._group_rows[row] = group
        self.group_table.set_empty_text("No groups left.\nScan again to look for more." if self.root_folder
                                        else "Press “Find groups”\nto scan your folder.")
        self.group_table.refresh_empty()

    def _group_values(self, group):
        return group.name, KIND_LABELS[group.kind][2], len(group.files)

    def _row_for(self, group):
        return next((row for row, g in self._group_rows.items() if g is group), None)

    def _update_group_row(self, group):
        row = self._row_for(group)
        if row:
            self.group_table.tree.item(row, values=self._group_values(group))

    def _group_selected(self, _event=None):
        selection = self.group_table.tree.selection()
        if selection and selection[0] in self._group_rows:
            group = self._group_rows[selection[0]]
            if group is not self.current:
                self._load(group)

    def _select(self, group):
        row = self._row_for(group)
        if row:
            self.group_table.tree.selection_set(row)
            self.group_table.tree.see(row)
        self._load(group)

    def _load(self, group):
        self.current = group
        self._loading = True
        self.name_var.set(group.name)
        self._loading = False
        label, tone, _short = KIND_LABELS[group.kind]
        self.kind_pill.set(label, tone)
        self.position_label.configure(text=f"Group {self.groups.index(group) + 1} of {len(self.groups)}")
        is_media = group.kind in (grouping.KIND_SHOW, grouping.KIND_MOVIE)
        self.rename_check.configure(state="normal" if group.kind == grouping.KIND_SHOW else "disabled")
        self.subs_label.configure(text="")
        self._show_detail(True)
        if not is_media:
            self.media_frame.grid_remove()
        self._refresh_files()
        self._update_dest()
        self.name_entry.icursor("end")

    # ---------- current group ----------

    def _refresh_files(self):
        group = self.current
        tree = self.file_table.tree
        tree.delete(*tree.get_children())
        self._file_rows.clear()
        if not group:
            return
        renaming = self.rename_var.get() and group.kind == grouping.KIND_SHOW
        columns = ["file"] + (["newname"] if renaming else []) + ["where"]
        if group.kind in (grouping.KIND_SHOW, grouping.KIND_MOVIE):
            columns.append("subs")
        tree.configure(displaycolumns=columns)

        for i, path in enumerate(group.files):
            name = os.path.basename(path)
            new_name = media.tidy_episode_name(name) if renaming else ""
            where = short_path(os.path.dirname(path), self.root_folder) or "main folder"
            subs = ""
            if media.is_video(name):
                subs = self.sub_status.get(path) or ("✓ Has subtitles" if has_subtitle(path, self._lang_code())
                                                     else "—")
            tags = ("alt",) if i % 2 else ()
            if not os.path.exists(path):
                tags += ("muted",)
            row = tree.insert("", "end", values=(name, new_name, where, subs), tags=tags)
            self._file_rows[row] = path
        self.files_label.configure(text=plural(len(group.files), "file"))
        self.file_table.refresh_empty()
        self._update_group_row(group)
        self._update_buttons()

    def _update_dest(self):
        name = self.name_var.get().strip()
        if self.root_folder and name:
            self.dest_label.configure(text=f"Creates  {os.path.join(self.root_folder, safe_folder_name(name))}")
        else:
            self.dest_label.configure(text="Type a name for the folder")
        self._update_buttons()

    def _update_buttons(self):
        group = self.current
        count = len(group.files) if group else 0
        can_act = bool(group) and not self.busy
        self.move_button.configure(text=f"Move {plural(count, 'file')} to folder",
                                   state="normal" if can_act and count and self.name_var.get().strip()
                                   else "disabled")
        self.skip_button.configure(state="normal" if can_act else "disabled")
        self.add_button.configure(state="normal" if can_act else "disabled")
        self.remove_button.configure(state="normal" if can_act and self.file_table.tree.selection()
                                     else "disabled")
        has_videos = bool(group and group.videos)
        self.subs_button.configure(state="normal" if can_act and has_videos else "disabled")

    def _name_changed(self, *_):
        if self._loading or not self.current:
            return
        self.current.name = self.name_var.get()
        self._update_group_row(self.current)
        self._update_dest()

    def _rename_changed(self):
        self.app.settings.rename_episodes = self.rename_var.get()
        self.app.save_settings(0)
        self._refresh_files()

    def _lang_code(self) -> str:
        return LANGUAGE_BY_NAME.get(self.lang_var.get(), self.app.settings.subtitle_language or "en")

    def _lang_changed(self, _event=None):
        self.app.settings.subtitle_language = self._lang_code()
        self.app.save_settings(0)
        self.sub_status.clear()
        self._refresh_files()

    def set_language(self, code):
        """Called when the language is changed on the Settings page."""
        self.lang_var.set(LANGUAGES.get(code, code))
        self.sub_status.clear()
        if self.current:
            self._refresh_files()

    def _reveal_file(self, _event):
        path = self._file_rows.get(self.file_table.tree.focus())
        if path and os.path.exists(path):
            open_in_file_manager(path)

    def remove_selected(self):
        group = self.current
        if not group or self.busy:
            return
        chosen = {self._file_rows[row] for row in self.file_table.tree.selection() if row in self._file_rows}
        if not chosen:
            return
        group.files = [p for p in group.files if p not in chosen]
        if not group.files:
            self._drop_group(group)
            return
        self._refresh_files()
        self._update_summary()

    def add_files(self):
        group = self.current
        if not group or self.busy:
            return
        owner = {p: g for g in self.groups for p in g.files}
        candidates = [p for p in self.pool if p not in set(group.files) and os.path.exists(p)]

        dialog = Dialog(self, "Add files to group", 720, 560)
        body = dialog.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)
        ttk.Label(body, text=f"Add files to “{group.name}”", style="Title.TLabel").grid(row=0, column=0,
                                                                                      sticky="w")
        ttk.Label(body, text="Pick files from the scan. Files already in another group are moved over.",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 12))
        search_var = tk.StringVar()
        search = ttk.Entry(body, textvariable=search_var)
        search.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        table = Table(body, [("file", "FILE", 360, True), ("group", "IN GROUP", 150, False),
                             ("where", "NOW IN", 100, False)], empty_text="No matching files.")
        table.grid(row=3, column=0, sticky="nsew")
        rows: dict[str, str] = {}

        def fill(*_):
            table.tree.delete(*table.tree.get_children())
            rows.clear()
            needle = search_var.get().lower().strip()
            shown = 0
            for path in candidates:
                name = os.path.basename(path)
                if needle and needle not in name.lower():
                    continue
                other = owner.get(path)
                row = table.tree.insert("", "end", values=(
                    name, other.name if other else "—",
                    short_path(os.path.dirname(path), self.root_folder) or "main folder"),
                    tags=("alt",) if shown % 2 else ())
                rows[row] = path
                shown += 1
            table.refresh_empty()

        search_var.trace_add("write", fill)
        fill()

        def add(paths):
            for path in paths:
                other = owner.get(path)
                if other and other is not group:
                    other.files.remove(path)
                    if not other.files:
                        self._drop_group(other, reselect=False)
                    else:
                        self._update_group_row(other)
                if path not in group.files:
                    group.files.append(path)
                if path not in self.pool:
                    self.pool.append(path)
            dialog.destroy()
            self._refresh_files()
            self.position_label.configure(
                text=f"Group {self.groups.index(group) + 1} of {len(self.groups)}")
            self._update_summary()

        def add_selected():
            add([rows[r] for r in table.tree.selection() if r in rows])

        def browse_more():
            paths = filedialog.askopenfilenames(parent=dialog, title="Add files to this group",
                                                initialdir=self.root_folder or os.path.expanduser("~"))
            if paths:
                add([os.path.normpath(p) for p in paths])

        table.tree.bind("<Double-1>", lambda _e: add_selected())
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(buttons, text="Browse other files…", style="Ghost.TButton", command=browse_more).pack(
            side="left")
        ttk.Button(buttons, text="Add selected", style="Accent.TButton", command=add_selected).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 8))
        dialog.show()
        search.focus_set()

    def _drop_group(self, group, reselect=True):
        index = self.groups.index(group)
        self.groups.remove(group)
        self._refresh_groups()
        self._update_summary()
        if group is self.current and reselect:
            self.current = None
            if self.groups:
                self._select(self.groups[min(index, len(self.groups) - 1)])
            else:
                self._show_detail(False, "That's every group done.\nScan again any time.")

    def skip_current(self):
        if self.current and not self.busy:
            self._drop_group(self.current)

    def move_current(self):
        group = self.current
        if not group or self.busy:
            return
        name = self.name_var.get().strip()
        if not name:
            self.name_entry.focus_set()
            return
        files = [p for p in group.files if os.path.exists(p)]
        if not files:
            messagebox.showinfo("Nothing to move", "These files have been moved or deleted since the scan.",
                                parent=self)
            self._drop_group(group)
            return
        root = self.root_folder
        rename = self.rename_var.get() and group.kind == grouping.KIND_SHOW
        self._set_busy(True, "Moving…")

        def done(results):
            self._set_busy(False)
            moved = [r for r in results if not r.error]
            failed = [r for r in results if r.error]
            moved_sources = {r.source for r in moved}
            self.pool = [p for p in self.pool if p not in moved_sources]
            folder = os.path.basename(os.path.dirname(moved[0].destination)) if moved else name
            if failed:
                group.files = [r.source for r in failed]
                self._refresh_files()
                messagebox.showwarning(
                    "Some files weren't moved",
                    "\n".join(f"{os.path.basename(r.source)}: {r.error}" for r in failed[:8]), parent=self)
            else:
                self._drop_group(group)
            if moved:
                self.app.toast(f"Moved {plural(len(moved), 'file')} to {folder}{os.sep}")

        def error(e):
            self._set_busy(False)
            messagebox.showerror("Couldn't move files", str(e), parent=self)

        self.app.run_async(lambda: grouping.move_group(root, files, name, rename, self.app.history), done, error)

    def _set_busy(self, busy, text=""):
        self.busy = busy
        self.action_label.configure(text=text)
        self._update_buttons()

    # ---------- subtitles ----------

    def get_subtitles(self):
        group = self.current
        if not group or self.busy:
            return
        s = self.app.settings
        if not s.opensubtitles_api_key.strip():
            if messagebox.askyesno("API key needed",
                                   "Tidy gets subtitles from OpenSubtitles.com, which needs a free API key.\n\n"
                                   "Open Settings to add one now?", parent=self):
                self.app.show_page("settings")
                self.app.pages["settings"].focus_api_key()
            return
        lang = self._lang_code()
        todo = [v for v in group.videos if os.path.exists(v) and not has_subtitle(v, lang)]
        if not todo:
            self.app.toast("Every video here already has subtitles", "neutral")
            return
        client = OpenSubtitles(s.opensubtitles_api_key, s.opensubtitles_username, s.opensubtitles_password)
        for video in todo:
            self.sub_status[video] = "Waiting…"
        self._refresh_files()
        self._set_busy(True, "")
        self.subs_label.configure(text=f"Getting subtitles for {plural(len(todo), 'video')}…")

        def status(video, text):
            self.sub_status[video] = text
            if self.current is group:
                self._refresh_files()

        def found(video, path):
            status(video, "✓ Downloaded")
            if path not in group.files:
                group.files.append(path)  # the subtitle travels with its video
                self.pool.append(path)
            if self.current is group:
                self._refresh_files()

        def work():
            got, problems = 0, []
            for video in todo:
                self.app.post(lambda v=video: status(v, "Searching…"))
                try:
                    path = client.fetch_best(video, lang)
                    got += 1
                    self.app.post(lambda v=video, p=path: found(v, p))
                except SubtitleError as e:
                    message = str(e)
                    problems.append(message)
                    short = "Not found" if message.startswith("No ") else "Failed"
                    self.app.post(lambda v=video, t=short: status(v, f"✗ {t}"))
                    if not message.startswith("No "):
                        # Key, quota and connection problems will hit every file the same way
                        for rest in todo[todo.index(video) + 1:]:
                            self.app.post(lambda v=rest: status(v, "—"))
                        break
            return got, problems

        def done(result):
            got, problems = result
            self._set_busy(False)
            self.subs_label.configure(text=f"Downloaded {plural(got, 'subtitle')}" if got else "")
            fatal = [p for p in problems if not p.startswith("No ")]
            if fatal:
                messagebox.showerror("Subtitles", fatal[0], parent=self)
            elif got:
                self.app.toast(f"Downloaded {plural(got, 'subtitle')}")
            elif problems:
                self.subs_label.configure(text="No matching subtitles found")

        def failed(e):
            self._set_busy(False)
            self.subs_label.configure(text="")
            messagebox.showerror("Subtitles", str(e), parent=self)

        self.app.run_async(work, done, failed)
