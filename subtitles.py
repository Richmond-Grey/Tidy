"""Searching and downloading subtitles from OpenSubtitles.com. No UI imports.

Needs a free API key from https://www.opensubtitles.com/en/consumers
(and, optionally, a username and password, which raises the daily download limit).
"""
import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import media

API = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "Tidy v0.1.0"
TIMEOUT = 20

LANGUAGES = {
    "en": "English", "fr": "French", "es": "Spanish", "pt-pt": "Portuguese", "pt-br": "Portuguese (Brazil)",
    "de": "German", "it": "Italian", "nl": "Dutch", "pl": "Polish", "ru": "Russian", "tr": "Turkish",
    "ar": "Arabic", "zh-cn": "Chinese (simplified)", "ja": "Japanese", "ko": "Korean", "hi": "Hindi",
    "sw": "Swahili", "yo": "Yoruba", "ha": "Hausa", "ig": "Igbo", "sv": "Swedish", "no": "Norwegian",
    "da": "Danish", "fi": "Finnish", "el": "Greek", "he": "Hebrew", "id": "Indonesian", "vi": "Vietnamese",
}


class SubtitleError(Exception):
    """Something the user should be told about, in plain words."""


@dataclass
class SubtitleResult:
    file_id: int
    release: str
    language: str
    downloads: int
    hash_match: bool
    hearing_impaired: bool
    ai_translated: bool
    season: int | None
    episode: int | None


def movie_hash(path: str) -> str | None:
    """OpenSubtitles' file hash: size + checksum of the first and last 64 KB."""
    block = 64 * 1024
    try:
        size = os.path.getsize(path)
        if size < block * 2:
            return None
        total = size
        with open(path, "rb") as f:
            for offset in (0, size - block):
                f.seek(offset)
                data = f.read(block)
                total += sum(struct.unpack(f"<{block // 8}Q", data))
        return f"{total & 0xFFFFFFFFFFFFFFFF:016x}"
    except (OSError, struct.error):
        return None


def subtitle_path(video_path: str, language: str) -> str:
    """'Show - S01E02.mkv' -> 'Show - S01E02.en.srt', which players load automatically."""
    stem = os.path.splitext(video_path)[0]
    return f"{stem}.{language}.srt"


def has_subtitle(video_path: str, language: str) -> bool:
    stem = os.path.splitext(video_path)[0]
    return any(os.path.exists(f"{stem}{suffix}") for suffix in (f".{language}.srt", ".srt"))


class OpenSubtitles:
    def __init__(self, api_key: str = "", username: str = "", password: str = ""):
        self.api_key = api_key.strip()
        self.username = username.strip()
        self.password = password
        self._token: str | None = None
        self._base = API

    # ---------- HTTP ----------

    def _request(self, method: str, url: str, body: dict | None = None, auth: bool = False) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            headers["Api-Key"] = self.api_key
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise SubtitleError(self._explain(e)) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SubtitleError("Couldn't reach OpenSubtitles. Check your internet connection.") from e
        except ValueError as e:
            raise SubtitleError("OpenSubtitles sent back something unexpected. Try again later.") from e

    def _explain(self, error: urllib.error.HTTPError) -> str:
        try:
            message = json.loads(error.read().decode("utf-8")).get("message", "")
        except (ValueError, OSError, AttributeError):
            message = ""
        if error.code == 401 or error.code == 403:
            return "OpenSubtitles rejected the API key or login. Check them in Settings."
        if error.code == 406 or "quota" in message.lower() or "allowed" in message.lower():
            return message or "You've hit today's OpenSubtitles download limit."
        if error.code == 429:
            return "OpenSubtitles says we're going too fast. Wait a few seconds and try again."
        if error.code >= 500:
            return "OpenSubtitles is having trouble right now. Try again later."
        return message or f"OpenSubtitles error ({error.code})."

    def _login(self):
        if self._token or not (self.username and self.password):
            return
        result = self._request("POST", f"{API}/login",
                               {"username": self.username, "password": self.password})
        self._token = result.get("token")
        if base := result.get("base_url"):
            self._base = f"https://{base}/api/v1" if not base.startswith("http") else f"{base}/api/v1"

    # ---------- public ----------

    def _require_key(self):
        if not self.api_key:
            raise SubtitleError("Add a free OpenSubtitles API key in Settings to get subtitles.")

    def search(self, video_path: str, language: str = "en", info: media.MediaInfo | None = None
               ) -> list[SubtitleResult]:
        """Best matches first. Tries the file hash (exact release) and the parsed title."""
        self._require_key()
        info = info or media.parse(os.path.basename(video_path))
        params = {"languages": language.lower()}
        if info:
            params["query"] = info.title.lower()
            if info.is_episode:
                params["type"] = "episode"
                params["episode_number"] = str(info.episode)
                if info.season is not None:
                    params["season_number"] = str(info.season)
            else:
                params["type"] = "movie"
                if info.year:
                    params["year"] = str(info.year)
        else:
            params["query"] = os.path.splitext(os.path.basename(video_path))[0].lower()

        file_hash = movie_hash(video_path)
        results = self._search(dict(params, moviehash=file_hash)) if file_hash else []
        if not results:
            results = self._search(params)
        if info and info.is_episode:
            # Drop results for other episodes that loose searches sometimes return
            results = [r for r in results if r.episode in (None, info.episode)
                       and (info.season is None or r.season in (None, info.season))]
        results.sort(key=lambda r: (not r.hash_match, r.ai_translated, r.hearing_impaired, -r.downloads))
        return results

    def _search(self, params: dict) -> list[SubtitleResult]:
        # The API redirects unless parameters are sorted and lower-case
        query = urllib.parse.urlencode(sorted(params.items()))
        data = self._request("GET", f"{API}/subtitles?{query}")
        results = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            files = attrs.get("files") or []
            if not files:
                continue
            feature = attrs.get("feature_details") or {}
            results.append(SubtitleResult(
                file_id=files[0]["file_id"],
                release=attrs.get("release") or files[0].get("file_name") or "",
                language=attrs.get("language") or params.get("languages", ""),
                downloads=attrs.get("download_count") or 0,
                hash_match=bool(attrs.get("moviehash_match")),
                hearing_impaired=bool(attrs.get("hearing_impaired")),
                ai_translated=bool(attrs.get("ai_translated") or attrs.get("machine_translated")),
                season=feature.get("season_number"),
                episode=feature.get("episode_number"),
            ))
        return results

    def download(self, result: SubtitleResult, video_path: str, language: str = "en") -> str:
        """Save the subtitle next to the video. Returns the saved path."""
        self._require_key()
        self._login()
        info = self._request("POST", f"{self._base}/download",
                             {"file_id": result.file_id, "sub_format": "srt"}, auth=True)
        link = info.get("link")
        if not link:
            raise SubtitleError(info.get("message") or "OpenSubtitles didn't return a download link.")
        try:
            request = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                content = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SubtitleError("The subtitle download failed. Try again.") from e

        target = subtitle_path(video_path, language)
        with open(target, "wb") as f:
            f.write(content)
        return target

    def fetch_best(self, video_path: str, language: str = "en") -> str:
        """Search and download the best match in one go. Returns the saved path."""
        results = self.search(video_path, language)
        if not results:
            name = os.path.basename(video_path)
            raise SubtitleError(f"No {LANGUAGES.get(language, language)} subtitles found for {name}.")
        return self.download(results[0], video_path, language)
