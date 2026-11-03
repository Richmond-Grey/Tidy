"""Colours, fonts, icons and ttk styles for the desktop app."""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

def _palette(**colors):
    """Fill in the keys most themes derive the same way."""
    colors.setdefault("on_accent", "#FFFFFF")
    colors.setdefault("on_accent_disabled", colors["surface"])
    colors.setdefault("side_active_text", "#FFFFFF")
    colors.setdefault("side_brand", "#FFFFFF")
    colors.setdefault("toast_neutral", colors["text"])
    colors.setdefault("toast_text", "#FFFFFF")
    return colors


# Each theme: display name, a one-line description and its colours.
THEMES = {
    "bear": ("Bear", "Warm honey and chocolate", _palette(
        bg="#FAF5EC", surface="#FFFDF8", surface_alt="#FBF7EF", segment="#F3ECE0",
        border="#ECE2D1", border_strong="#DACBB3",
        text="#2A1E16", muted="#7A6857", faint="#B3A491",
        accent="#9A5B2E", accent_active="#7E4823", accent_soft="#F6E8D6", accent_text="#7A431C",
        danger="#B5402C", danger_active="#953222", danger_soft="#F8E5DF",
        warn="#B07414", warn_soft="#FBEFD8", info="#3F6491", info_soft="#E6EDF6",
        watching="#4E9A5B", idle="#C2B5A3", select="#F4E4CE",
        side_bg="#2A1D15", side_hover="#36261C", side_active="#443023",
        side_text="#EADDCB", side_muted="#9C8775", side_accent="#F4B942",
    )),
    "forest": ("Forest", "Calm pine green", _palette(
        bg="#F6F5F1", surface="#FFFFFF", surface_alt="#FAF9F6", segment="#F1EFEA",
        border="#E7E4DD", border_strong="#D6D2C9",
        text="#1B1A18", muted="#77736B", faint="#A7A39A",
        accent="#2F6F5E", accent_active="#255A4C", accent_soft="#E5EFEB", accent_text="#1F5446",
        danger="#B4432F", danger_active="#963624", danger_soft="#F8E7E3",
        warn="#A86A12", warn_soft="#FBF0DC", info="#3A5F95", info_soft="#E6EDF7",
        watching="#36A56E", idle="#B9B5AC", select="#E3EEEA",
        side_bg="#17231F", side_hover="#21312C", side_active="#2A3E37",
        side_text="#D5DDD9", side_muted="#7D8E87", side_accent="#7FD1AE",
    )),
    "ocean": ("Ocean", "Cool sea blue", _palette(
        bg="#F2F6F8", surface="#FFFFFF", surface_alt="#F7FAFB", segment="#E9F0F3",
        border="#DCE6EB", border_strong="#C5D3DA",
        text="#13222B", muted="#5D707B", faint="#9AAAB3",
        accent="#1F6F99", accent_active="#185B7E", accent_soft="#E1EFF6", accent_text="#175877",
        danger="#B8432F", danger_active="#983625", danger_soft="#F8E6E2",
        warn="#A86A12", warn_soft="#FBF0DC", info="#3A5F95", info_soft="#E6EDF7",
        watching="#2E9E77", idle="#AFBCC3", select="#DDEDF5",
        side_bg="#0F2733", side_hover="#173544", side_active="#1E4254",
        side_text="#D3E2EA", side_muted="#7E98A6", side_accent="#6CC5E8",
    )),
    "blossom": ("Blossom", "Soft cherry pink", _palette(
        bg="#FBF4F4", surface="#FFFFFF", surface_alt="#FDF8F8", segment="#F5EAEB",
        border="#EEDDDF", border_strong="#E0C8CB",
        text="#2B1A1E", muted="#7E656A", faint="#B9A2A6",
        accent="#B4486A", accent_active="#963A57", accent_soft="#F8E4EA", accent_text="#943955",
        danger="#B8432F", danger_active="#983625", danger_soft="#F8E6E2",
        warn="#A86A12", warn_soft="#FBF0DC", info="#4A5F95", info_soft="#E8EBF6",
        watching="#3E9E6E", idle="#C6B3B7", select="#F7E1E8",
        side_bg="#3A1E28", side_hover="#482633", side_active="#58313E",
        side_text="#F1DDE3", side_muted="#A88591", side_accent="#F5A3BC",
    )),
    "midnight": ("Midnight", "Dark, easy on the eyes", _palette(
        bg="#14161B", surface="#1C1F26", surface_alt="#21252D", segment="#262A33",
        border="#2D323C", border_strong="#3B414D",
        text="#E8EAED", muted="#9AA1AC", faint="#646B77",
        accent="#7C9CFF", accent_active="#9BB3FF", accent_soft="#262F4A", accent_text="#AFC2FF",
        danger="#F06A5A", danger_active="#F48577", danger_soft="#3A2226",
        warn="#E0A24A", warn_soft="#3A2F1E", info="#6CB4F0", info_soft="#1E2E3E",
        watching="#4CC38A", idle="#565D69", select="#2A3350",
        side_bg="#0E1014", side_hover="#181B21", side_active="#1F232B",
        side_text="#C9CED6", side_muted="#6B7280", side_accent="#7C9CFF",
        on_accent="#0E1014", on_accent_disabled="#9AA1AC", toast_neutral="#E8EAED", toast_text="#14161B",
    )),
}
DEFAULT_THEME = "bear"

# The live palette. Modules import this dict, so switching themes updates it in place.
COLORS = dict(THEMES[DEFAULT_THEME][2])


def use_theme(key: str) -> str:
    """Make `key` the live palette. Returns the key actually used."""
    key = key if key in THEMES else DEFAULT_THEME
    COLORS.clear()
    COLORS.update(THEMES[key][2])
    return key

# Segoe Fluent Icons / MDL2 code points (Windows). Missing font -> no icons, text still works.
ICONS = {
    "sort": "\uE8CB",
    "group": "\uE8F1",
    "duplicates": "\uE8C8",
    "share": "\uE72D",
    "history": "\uE81C",
    "settings": "\uE713",
}


class Theme:
    def __init__(self, root: tk.Misc):
        families = set(tkfont.families(root))

        def pick(*names, default=None):
            return next((n for n in names if n in families), default)

        base = pick("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu",
                    default=tkfont.nametofont("TkDefaultFont").actual("family"))
        strong = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold", default=base)
        display = pick("Segoe UI Variable Display Semib", "Segoe UI Semibold", default=base)
        strong_weight = "normal" if strong != base else "bold"
        display_weight = "normal" if display != base else "bold"
        self.icon_family = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")

        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=base, size=10)

        self.fonts = {
            "display": tkfont.Font(root, family=display, size=22, weight=display_weight),
            "brand": tkfont.Font(root, family=display, size=17, weight=display_weight),
            "title": tkfont.Font(root, family=display, size=13, weight=display_weight),
            "section": tkfont.Font(root, family=strong, size=10, weight=strong_weight),
            "body": tkfont.Font(root, family=base, size=10),
            "small": tkfont.Font(root, family=base, size=9),
            "small_strong": tkfont.Font(root, family=strong, size=9, weight=strong_weight),
            "stat": tkfont.Font(root, family=display, size=18, weight=display_weight),
            "icon": tkfont.Font(root, family=self.icon_family or base, size=12),
        }

    def icon(self, name: str) -> str:
        return ICONS.get(name, "") if self.icon_family else ""


def setup_styles(root: tk.Misc, theme: Theme) -> None:
    c, f = COLORS, theme.fonts
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=c["bg"], foreground=c["text"], font=f["body"],
                    bordercolor=c["border"], focuscolor=c["accent"], troughcolor=c["bg"],
                    selectbackground=c["select"], selectforeground=c["text"])

    # Frames & labels. "Card" variants sit on white surfaces.
    style.configure("TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["surface"])
    for prefix, bg in (("", c["bg"]), ("Card.", c["surface"])):
        style.configure(f"{prefix}TLabel", background=bg, foreground=c["text"])
        style.configure(f"{prefix}Muted.TLabel", background=bg, foreground=c["muted"])
        style.configure(f"{prefix}Small.TLabel", background=bg, foreground=c["muted"], font=f["small"])
        style.configure(f"{prefix}Section.TLabel", background=bg, font=f["section"])
        style.configure(f"{prefix}Title.TLabel", background=bg, font=f["title"])
        style.configure(f"{prefix}Error.TLabel", background=bg, foreground=c["danger"], font=f["small"])
        style.configure(f"{prefix}Success.TLabel", background=bg, foreground=c["accent"], font=f["small"])
    style.configure("Display.TLabel", font=f["display"])
    style.configure("Stat.Card.TLabel", background=c["surface"], font=f["stat"])

    # Inputs
    field = dict(fieldbackground=c["surface"], bordercolor=c["border_strong"], lightcolor=c["surface"],
                 darkcolor=c["surface"], padding=(9, 6), insertcolor=c["text"])
    style.configure("TEntry", **field)
    style.map("TEntry",
              bordercolor=[("focus", c["accent"])],
              lightcolor=[("focus", c["accent_soft"])],
              fieldbackground=[("disabled", c["bg"]), ("readonly", c["bg"])],
              foreground=[("disabled", c["muted"])])
    style.configure("TCombobox", arrowcolor=c["muted"], background=c["surface"], arrowsize=12, **field)
    style.map("TCombobox",
              bordercolor=[("focus", c["accent"])],
              fieldbackground=[("readonly", c["surface"]), ("disabled", c["bg"])],
              selectbackground=[("readonly", c["surface"])],
              selectforeground=[("readonly", c["text"])],
              background=[("active", c["surface_alt"])])
    root.option_add("*TCombobox*Listbox.background", c["surface"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["text"])
    root.option_add("*TCombobox*Listbox.font", f["body"])
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    for name, bg in (("TCheckbutton", c["bg"]), ("Card.TCheckbutton", c["surface"])):
        style.configure(name, background=bg, foreground=c["text"], indicatorbackground=c["surface"],
                        indicatorforeground=c["surface"], indicatorrelief="flat", indicatormargin=(0, 0, 8, 0), indicatorsize=15,
                        padding=(0, 2), focusthickness=0, upperbordercolor=c["border_strong"],
                        lowerbordercolor=c["border_strong"])
        style.map(name,
                  background=[("active", bg)],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["accent_soft"])],
                  upperbordercolor=[("selected", c["accent"])],
                  lowerbordercolor=[("selected", c["accent"])],
                  foreground=[("disabled", c["faint"])])
        radio = name.replace("Checkbutton", "Radiobutton")
        style.configure(radio, background=bg, foreground=c["text"], indicatorbackground=c["surface"],
                        indicatormargin=(0, 0, 8, 0), indicatorsize=15, padding=(0, 2), focusthickness=0,
                        upperbordercolor=c["border_strong"], lowerbordercolor=c["border_strong"])
        style.map(radio,
                  background=[("active", bg)],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["accent_soft"])],
                  upperbordercolor=[("selected", c["accent"])],
                  lowerbordercolor=[("selected", c["accent"])])

    # Buttons
    common = dict(padding=(14, 7), borderwidth=1, focusthickness=0, relief="solid", anchor="center")
    style.configure("TButton", background=c["surface"], foreground=c["text"], bordercolor=c["border_strong"],
                    lightcolor=c["surface"], darkcolor=c["surface"], **common)
    style.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["border"]), ("active", c["surface_alt"])],
              bordercolor=[("active", c["faint"])],
              lightcolor=[("active", c["surface_alt"])], darkcolor=[("active", c["surface_alt"])],
              foreground=[("disabled", c["faint"])])
    for name, base, active in (("Accent", c["accent"], c["accent_active"]),
                               ("Danger", c["danger"], c["danger_active"])):
        style.configure(f"{name}.TButton", background=base, foreground=c["on_accent"], bordercolor=base,
                        lightcolor=base, darkcolor=base, font=f["section"], **common)
        style.map(f"{name}.TButton",
                  background=[("disabled", c["idle"]), ("pressed", active), ("active", active)],
                  bordercolor=[("disabled", c["idle"]), ("active", active)],
                  lightcolor=[("disabled", c["idle"]), ("active", active)],
                  darkcolor=[("disabled", c["idle"]), ("active", active)],
                  foreground=[("disabled", c["on_accent_disabled"])])
    for name, bg in (("Ghost.TButton", c["bg"]), ("CardGhost.TButton", c["surface"])):
        style.configure(name, background=bg, foreground=c["accent_text"], bordercolor=bg, lightcolor=bg,
                        darkcolor=bg, padding=(8, 5), relief="flat", focusthickness=0)
        style.map(name, background=[("active", c["accent_soft"]), ("pressed", c["accent_soft"])],
                  bordercolor=[("active", c["accent_soft"])],
                  lightcolor=[("active", c["accent_soft"])], darkcolor=[("active", c["accent_soft"])],
                  foreground=[("disabled", c["faint"])])

    # Segmented control (two radio buttons that look like a switch)
    style.configure("Segment.TRadiobutton", background=c["segment"], foreground=c["muted"], padding=(14, 6),
                    borderwidth=1, relief="solid", bordercolor=c["segment"], lightcolor=c["segment"],
                    darkcolor=c["segment"], focusthickness=0, anchor="center")
    style.layout("Segment.TRadiobutton", [
        ("Radiobutton.border", {"sticky": "nswe", "children": [
            ("Radiobutton.padding", {"sticky": "nswe", "children": [
                ("Radiobutton.label", {"sticky": "nswe"})]})]})])
    style.map("Segment.TRadiobutton",
              background=[("selected", c["accent_soft"]), ("active", c["border"])],
              foreground=[("selected", c["accent_text"]), ("disabled", c["faint"])],
              bordercolor=[("selected", c["accent"])],
              lightcolor=[("selected", c["accent_soft"])], darkcolor=[("selected", c["accent_soft"])],
              font=[("selected", f["section"])])

    # Tables
    row_height = f["body"].metrics("linespace") + 14
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["text"],
                    bordercolor=c["surface"], lightcolor=c["surface"], darkcolor=c["surface"], borderwidth=0,
                    rowheight=row_height, padding=0)
    style.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", background=c["surface"], foreground=c["muted"], font=f["small_strong"],
                    relief="flat", borderwidth=0, padding=(10, 8), bordercolor=c["border"],
                    lightcolor=c["surface"], darkcolor=c["border"])
    style.map("Treeview.Heading", background=[("active", c["surface_alt"])])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no inner border

    style.configure("Vertical.TScrollbar", background=c["border"], troughcolor=c["surface"],
                    bordercolor=c["surface"], arrowcolor=c["muted"], lightcolor=c["border"],
                    darkcolor=c["border"], gripcount=0, arrowsize=11)
    style.map("Vertical.TScrollbar", background=[("active", c["border_strong"])])

    style.configure("Accent.Horizontal.TProgressbar", background=c["accent"], troughcolor=c["accent_soft"],
                    bordercolor=c["accent_soft"], lightcolor=c["accent"], darkcolor=c["accent"], thickness=4)
    style.configure("TSeparator", background=c["border"])
