"""User settings, saved as JSON in the per-user config folder. No UI imports."""
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields


def config_dir() -> str:
    """%APPDATA%\\Tidy on Windows, ~/Library/Application Support/Tidy on macOS, ~/.config/tidy elsewhere.
    TIDY_CONFIG_DIR overrides it (handy for testing)."""
    if override := os.environ.get("TIDY_CONFIG_DIR"):
        return override
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Tidy")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Tidy")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "tidy")


@dataclass
class Settings:
    folder: str = ""
    sort_mode: str = "extension"            # "extension" or "category"
    ignore_patterns: list[str] = field(default_factory=lambda: ["*.lnk"])
    start_on_launch: bool = False           # resume watching the last folder when Tidy opens
    group_include_sorted: bool = True       # grouping also looks inside Tidy's own sort folders
    rename_episodes: bool = False           # 'Show - S01E02.mkv' when grouping
    subtitle_language: str = "en"
    opensubtitles_api_key: str = ""
    opensubtitles_username: str = ""
    opensubtitles_password: str = ""
    duplicates_recursive: bool = True

    @classmethod
    def path(cls) -> str:
        return os.path.join(config_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(cls.path(), encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = self.path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, self.path())
