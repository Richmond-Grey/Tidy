"""Reading show/movie information out of messy file names.

'Breaking.Bad.S01E02.720p.WEB-DL.x264.mkv' -> title 'Breaking Bad', season 1, episode 2.
No UI imports.
"""
import os
import re
from dataclasses import dataclass

VIDEO_EXTENSIONS = {"mkv", "mp4", "avi", "mov", "wmv", "m4v", "webm", "flv", "mpg", "mpeg", "ts", "3gp"}
SUBTITLE_EXTENSIONS = {"srt", "ass", "ssa", "sub", "vtt", "idx"}

# Release-group noise that never belongs to a title
JUNK_TOKENS = {
    "480p", "576p", "720p", "1080p", "1080i", "2160p", "4k", "uhd", "hd", "fhd", "sd",
    "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "divx", "10bit", "8bit", "hdr", "hdr10", "dv",
    "web", "webrip", "webdl", "web-dl", "bluray", "blu-ray", "bdrip", "brrip", "dvdrip", "hdtv", "hdrip",
    "camrip", "cam", "ts", "remux", "proper", "repack", "extended", "unrated", "internal", "limited",
    "aac", "aac2", "ac3", "dts", "ddp", "ddp5", "dd5", "eac3", "atmos", "mp3", "flac", "opus",
    "nf", "amzn", "dsnp", "hmax", "atvp", "hulu", "multi", "dual", "subs", "eng", "english", "esub",
    "yify", "yts", "rarbg", "eztv", "ettv", "psa", "galaxytv", "tgx", "mkvcage", "pahe", "ion10",
}

_EPISODE_PATTERNS = [
    # S01E02, s1e2, S01E02E03, S01.E02, S01_E02
    re.compile(r"\bs(?P<season>\d{1,2})[ ._-]?e(?P<episode>\d{1,3})", re.I),
    # 1x02
    re.compile(r"\b(?P<season>\d{1,2})x(?P<episode>\d{2,3})\b", re.I),
    # Season 1 Episode 2
    re.compile(r"\bseason[ ._-]?(?P<season>\d{1,2})[ ._-]*(?:episode|ep)[ ._-]?(?P<episode>\d{1,3})", re.I),
    # Episode 12 / Ep 12 / E12 (no season, typical for anime)
    re.compile(r"\b(?:episode|ep|e)[ ._-]?(?P<episode>\d{1,4})\b", re.I),
    # 'Show Name - 12' (anime-style absolute numbering)
    re.compile(r"\s-\s(?P<episode>\d{1,4})(?:v\d)?(?:\s|$)"),
]
_YEAR = re.compile(r"(?:^|[ ._(\[-])(?P<year>19[3-9]\d|20[0-4]\d)(?:$|[ ._)\]-])")
_BRACKETS = re.compile(r"\[[^\]]*\]|\{[^}]*\}")


@dataclass
class MediaInfo:
    title: str
    season: int | None = None
    episode: int | None = None
    year: int | None = None

    @property
    def is_episode(self) -> bool:
        return self.episode is not None

    def episode_tag(self) -> str:
        """'S01E02', or 'E12' when there's no season."""
        if self.episode is None:
            return ""
        if self.season is None:
            return f"E{self.episode:02d}"
        return f"S{self.season:02d}E{self.episode:02d}"


def extension(filename: str) -> str:
    return os.path.splitext(filename)[1][1:].lower()


def is_video(filename: str) -> bool:
    return extension(filename) in VIDEO_EXTENSIONS


def is_subtitle(filename: str) -> bool:
    return extension(filename) in SUBTITLE_EXTENSIONS


def clean_title(text: str) -> str:
    """'breaking.bad_' -> 'Breaking Bad'."""
    text = _BRACKETS.sub(" ", text)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s*[-–(]+\s*$", "", text.strip())
    words = []
    for word in text.split():
        if word.lower().strip("()") in JUNK_TOKENS:
            break  # everything after the first junk token is release noise
        words.append(word)
    text = " ".join(words).strip(" -–()")
    if text and (text.islower() or text.isupper()):
        text = text.title()
    return text


def parse(filename: str) -> MediaInfo | None:
    """Show/movie info for a video/subtitle file name, or None when it doesn't look like one."""
    if not (is_video(filename) or is_subtitle(filename)):
        return None  # 'Invoice - 2023.pdf' is not episode 2023 of anything
    stem =os.path.splitext(os.path.basename(filename))[0]
    # Subtitles are often named 'video.en.srt'; drop the language part
    if is_subtitle(filename):
        stem = re.sub(r"\.[a-z]{2,3}(?:[-_][a-z]{2})?$", "", stem, flags=re.I)
    unbracketed = _BRACKETS.sub(" ", stem)
    spaced = re.sub(r"[._]+", " ", unbracketed)

    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(spaced)
        if not match:
            continue
        title = clean_title(spaced[:match.start()])
        if not title:
            continue
        groups = match.groupdict()
        season = int(groups["season"]) if groups.get("season") else None
        episode = int(groups["episode"])
        year_match = _YEAR.search(spaced[:match.start()])
        year = int(year_match.group("year")) if year_match else None
        if year_match:
            title = clean_title(spaced[:year_match.start()]) or title
        return MediaInfo(title=title, season=season, episode=episode, year=year)

    # Movies: 'Inception.2010.1080p.BluRay' -> title before the year
    year_match = _YEAR.search(spaced)
    if year_match and year_match.start() > 0:
        title = clean_title(spaced[:year_match.start()])
        if title:
            return MediaInfo(title=title, year=int(year_match.group("year")))
    return None


def tidy_episode_name(filename: str, info: MediaInfo | None = None) -> str:
    """'breaking.bad.s01e02.720p.mkv' -> 'Breaking Bad - S01E02.mkv'. Unchanged if not an episode."""
    info = info or parse(filename)
    if not info or not info.is_episode:
        return filename
    ext = os.path.splitext(filename)[1]
    if is_subtitle(filename):
        # Keep the language suffix ('.en') so players still pair it with the video
        lang = re.search(r"(\.[a-z]{2,3}(?:[-_][a-z]{2})?)$", os.path.splitext(filename)[0], re.I)
        ext = (lang.group(1) if lang else "") + ext
    return f"{info.title} - {info.episode_tag()}{ext}"
