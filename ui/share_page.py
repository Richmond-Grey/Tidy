"""Share page: host files from this computer and hand out download links."""
import os
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from duplicates import human_size
from sharing import Tunnel, lan_ip
from ui.theme import COLORS as C
from ui.widgets import Card, hline, Dialog, PageHeader, StatusDot, Table, plural

EXPIRY_CHOICES = {"Never": None, "1 hour": 3600, "1 day": 86400, "7 days": 7 * 86400}
LIMIT_CHOICES = {"Unlimited": None, "1 download": 1, "5 downloads": 5, "10 downloads": 10}


class SharePage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(36, 30, 36, 24))
        self.app = app
        self.store = app.share_store
        self.server = app.share_server
        self.tunnel: Tunnel | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        PageHeader(self, "Share files",
                   "Send anyone a link to a file on this computer. They download it straight from you, "
                   "no uploading, as long as Tidy is open and you're both online.").grid(row=0, column=0,
                                                                                       sticky="ew")

        card = Card(self)
        card.grid(row=1, column=0, sticky="ew", pady=(22, 0))
        body = card.body
        body.columnconfigure(1, weight=1)

        self.server_dot = StatusDot(body, C["surface"])
        self.server_dot.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.server_label = ttk.Label(body, style="Card.Section.TLabel")
        self.server_label.grid(row=0, column=1, sticky="w")
        self.server_detail = ttk.Label(body, style="Card.Small.TLabel")
        self.server_detail.grid(row=1, column=1, sticky="w", pady=(2, 0))

        hline(body).grid(row=2, column=0, columnspan=3, sticky="ew", pady=14)
        self.tunnel_dot = StatusDot(body, C["surface"])
        self.tunnel_dot.grid(row=3, column=0, sticky="w", padx=(0, 10))
        self.tunnel_label = ttk.Label(body, text="Internet link: off", style="Card.Section.TLabel")
        self.tunnel_label.grid(row=3, column=1, sticky="w")
        self.tunnel_detail = ttk.Label(body, style="Card.Small.TLabel", wraplength=560, justify="left",
                                       text="Links work on your Wi-Fi now. Turn this on to share with people "
                                            "anywhere through a free, temporary public address.")
        self.tunnel_detail.grid(row=4, column=1, sticky="w", pady=(2, 0))
        self.tunnel_button = ttk.Button(body, text="Turn on", command=self.toggle_tunnel)
        self.tunnel_button.grid(row=3, column=2, rowspan=2, sticky="e")

        toolbar = ttk.Frame(self)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(24, 10))
        ttk.Label(toolbar, text="Shared files", style="Title.TLabel").pack(side="left")
        ttk.Button(toolbar, text="Share a file…", style="Accent.TButton", command=self.add_share).pack(
            side="right")
        self.stop_button = ttk.Button(toolbar, text="Stop sharing", command=self.remove_selected, state="disabled")
        self.stop_button.pack(side="right", padx=(0, 8))
        self.open_button = ttk.Button(toolbar, text="Open page", style="Ghost.TButton", command=self.open_selected,
                                      state="disabled")
        self.open_button.pack(side="right", padx=(0, 4))
        self.copy_button = ttk.Button(toolbar, text="Copy link", command=self.copy_selected, state="disabled")
        self.copy_button.pack(side="right", padx=(0, 8))

        self.table = Table(self, [("file", "FILE", 300, True), ("size", "SIZE", 80, False),
                                  ("downloads", "DOWNLOADS", 120, False), ("expires", "EXPIRES", 120, False),
                                  ("status", "STATUS", 90, False)],
                           empty_text="Nothing shared yet.\nPress “Share a file…” to get a link.")
        self.table.grid(row=3, column=0, sticky="nsew")
        self.table.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        self.table.tree.bind("<Double-1>", lambda _e: self.copy_selected())

        if any(s.is_live() for s in self.store.all()):
            self._ensure_server()
        self.refresh()
        self._update_server_status()
        self.after(30_000, self._tick)

    # ---------- server ----------

    def _ensure_server(self) -> bool:
        if self.server.running:
            return True
        try:
            self.server.start()
        except OSError as e:
            messagebox.showerror("Couldn't start sharing", str(e), parent=self)
            return False
        self._update_server_status()
        return True

    def on_server_event(self, kind, share):
        """Called on the UI thread when someone downloads a shared file."""
        self.refresh()
        if kind == "download_started":
            self.app.toast(f"Someone is downloading {share.name}", "neutral")

    def _update_server_status(self):
        if self.server.running:
            self.server_dot.set(C["watching"])
            self.server_label.configure(text="Sharing is on")
            self.server_detail.configure(text=f"Reachable on your network at {lan_ip()}:{self.server.port}. "
                                              "Windows may ask to allow Tidy through the firewall: say yes "
                                              "for private networks.")
        else:
            self.server_dot.set(C["idle"])
            self.server_label.configure(text="Sharing is off")
            self.server_detail.configure(text="It starts by itself when you share a file.")
        live = sum(1 for s in self.store.all() if s.is_live())
        self.app.set_badge("share", str(live) if live else "")

    def toggle_tunnel(self):
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None
            self._tunnel_off()
            return
        tool = Tunnel.available()
        if not tool:
            messagebox.showinfo("Internet link", "To share outside your network, install cloudflared "
                                "(free from Cloudflare) or the OpenSSH client, then try again.", parent=self)
            return
        if not messagebox.askyesno(
                "Turn on internet link?",
                f"Tidy will open a public address through {tool}. Anyone with a file's link can download "
                "that file (and only that file) while this is on.\n\nTurn it on?", parent=self):
            return
        if not self._ensure_server():
            return
        tunnel = Tunnel(self.server.port,
                        on_url=lambda url: self.app.post(lambda: self._tunnel_ready(tunnel, url)),
                        on_closed=lambda why: self.app.post(lambda: self._tunnel_closed(tunnel, why)))
        try:
            tunnel.start()
        except OSError as e:
            messagebox.showerror("Internet link", str(e), parent=self)
            return
        self.tunnel = tunnel
        self.tunnel_dot.set(C["warn"])
        self.tunnel_label.configure(text="Internet link: connecting…")
        self.tunnel_detail.configure(text=f"Opening a public address through {tool}…")
        self.tunnel_button.configure(text="Cancel")

    def _tunnel_ready(self, tunnel, url):
        if tunnel is not self.tunnel:
            return
        self.tunnel_dot.set(C["watching"])
        self.tunnel_label.configure(text="Internet link: on")
        self.tunnel_detail.configure(text=f"Public address {url}. It changes each time you turn this on, so "
                                          "copy links again afterwards.")
        self.tunnel_button.configure(text="Turn off")
        self.app.toast("Internet link is ready. Copied links now work anywhere.")
        self.refresh()

    def _tunnel_closed(self, tunnel, why):
        if tunnel is not self.tunnel:
            return
        self.tunnel = None
        self._tunnel_off()
        messagebox.showwarning("Internet link closed", why, parent=self)

    def _tunnel_off(self):
        self.tunnel_dot.set(C["idle"])
        self.tunnel_label.configure(text="Internet link: off")
        self.tunnel_detail.configure(text="Links work on your Wi-Fi now. Turn this on to share with people "
                                          "anywhere through a free, temporary public address.")
        self.tunnel_button.configure(text="Turn on")

    # ---------- shares ----------

    def add_share(self, path=None):
        if not path:
            path = filedialog.askopenfilename(parent=self, title="Choose a file to share",
                                              initialdir=self.app.folder() or os.path.expanduser("~"))
        if not path:
            return
        path = os.path.normpath(path)

        dialog = Dialog(self, "Share a file", 520, 330)
        body = dialog.body
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text=os.path.basename(path), style="Title.TLabel", wraplength=460).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=os.path.dirname(path), style="Small.TLabel", wraplength=460).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 18))
        expiry = tk.StringVar(value="Never")
        limit = tk.StringVar(value="Unlimited")
        for row, (label, var, choices) in enumerate((("Link expires", expiry, EXPIRY_CHOICES),
                                                     ("Downloads allowed", limit, LIMIT_CHOICES)), 2):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 16))
            ttk.Combobox(body, textvariable=var, values=list(choices), state="readonly", width=16).grid(
                row=row, column=1, sticky="w", pady=6)

        def create():
            share = self.store.add(path, EXPIRY_CHOICES[expiry.get()], LIMIT_CHOICES[limit.get()])
            dialog.destroy()
            if not self._ensure_server():
                return
            self.refresh(select=share.token)
            self._copy(share)

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(24, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(buttons, text="Create link", style="Accent.TButton", command=create).pack(side="left",
                                                                                             padx=(8, 0))
        dialog.show()

    def refresh(self, select=None):
        tree = self.table.tree
        selected = set(tree.selection()) | ({select} if select else set())
        tree.delete(*tree.get_children())
        for i, share in enumerate(self.store.all()):
            try:
                size = human_size(os.path.getsize(share.path))
            except OSError:
                size = "—"
            downloads = str(share.downloads) + (f" / {share.max_downloads}" if share.max_downloads else "")
            expires = "Never" if share.expires is None else _when(share.expires)
            status = share.status()
            tags = ("alt",) if i % 2 else ()
            if status != "Live":
                tags += ("muted",)
            tree.insert("", "end", iid=share.token, values=(share.name, size, downloads, expires, status),
                        tags=tags)
        for iid in selected:
            if tree.exists(iid):
                tree.selection_add(iid)
                tree.see(iid)
        self.table.refresh_empty()
        self._update_buttons()
        self._update_server_status()

    def _selected(self):
        return [s for s in (self.store.get(t) for t in self.table.tree.selection()) if s]

    def _update_buttons(self):
        selected = self._selected()
        live = [s for s in selected if s.is_live()]
        self.copy_button.configure(state="normal" if len(live) == 1 else "disabled")
        self.open_button.configure(state="normal" if len(live) == 1 else "disabled")
        self.stop_button.configure(state="normal" if selected else "disabled")

    def _link(self, share):
        if self.tunnel and self.tunnel.url:
            return self.tunnel.public_url(share)
        return self.server.local_url(share)

    def _copy(self, share):
        link = self._link(share)
        self.clipboard_clear()
        self.clipboard_append(link)
        where = "anywhere" if self.tunnel and self.tunnel.url else "on your network"
        self.app.toast(f"Link copied. Works {where} while Tidy is open.")

    def copy_selected(self):
        live = [s for s in self._selected() if s.is_live()]
        if live and self._ensure_server():
            self._copy(live[0])

    def open_selected(self):
        live = [s for s in self._selected() if s.is_live()]
        if live and self._ensure_server():
            webbrowser.open(self._link(live[0]))

    def remove_selected(self):
        shares = self._selected()
        if not shares:
            return
        for share in shares:
            self.store.remove(share.token)
        self.app.toast(f"Stopped sharing {plural(len(shares), 'file')}", "neutral")
        self.refresh()
        if not any(s.is_live() for s in self.store.all()):
            if self.tunnel:
                self.tunnel.stop()
                self.tunnel = None
                self._tunnel_off()
            self.server.stop()
            self._update_server_status()

    def _tick(self):
        # Keep "Expired" and "Expires in" fresh
        if not self.winfo_exists():
            return  # page was rebuilt for a theme change
        self.refresh()
        self.after(30_000, self._tick)

    def detach(self):
        """Page is going away (theme change or quit). The server lives on the app; the tunnel doesn't."""
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None


def _when(timestamp: float) -> str:
    left = timestamp - time.time()
    if left <= 0:
        return "Expired"
    if left < 3600:
        return f"in {max(int(left // 60), 1)} min"
    if left < 86400:
        return f"in {int(left // 3600)} h"
    return f"in {int(left // 86400)} days"
