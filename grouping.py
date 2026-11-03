"""Finding files that belong together: episodes of a show, a movie and its
subtitles, numbered scans/photos, monthly statements, ...

No UI imports.
"""
import difflib
import os
import re
from dataclasses import dataclass, field

import media
from sorter import (MoveResult, is_sort_folder, move_file, safe_folder_name, should_skip)

KIND_SHOW = "show"
KIND_MOVIE = "movie"
KIND_SIMILAR = "similar"

FUZZY_THRESHOLD = 0.82
FUZZY_SAME_START_THRESHOLD = 0.72  # looser when names start with the same real word ('invoice ...')
FUZZY_LIMIT = 2500  # fuzzy matching is O(n²); skip it on enormous folders


@dataclass
class FileGroup:
    name: str                       # suggested folder name
    kind: str                       # KIND_SHOW / KIND_MOVIE / KIND_SIMILAR
    files: list[str] = field(default_factory=list)
    media: media.MediaInfo | None = None

    @property
    def videos(self) -> list[str]:
        return [f for f in self.files if media.is_video(f)]


def collect_files(root: str, include_sorted: bool = True) -> list[str]:
    """Loose files in root, plus (optionally) files sitting in Tidy's own sort folders
    like root/mkv/ or root/Videos/. Folders the user made themselves are left alone."""
    files = []
    for entry in os.scandir(root):
        if entry.is_file():
            if not should_skip(entry.name):
                files.append(entry.path)
        elif entry.is_dir() and include_sorted:
            try:
                for sub in os.scandir(entry.path):
                    if sub.is_file() and not should_skip(sub.name) and is_sort_folder(entry.name, sub.name):
                        files.append(sub.path)
            except OSError:
                continue
    return files


def skeleton(filename: str) -> str:
    """Name with numbers and release noise taken out: 'IMG_2031.jpg' -> 'img #'."""
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem = re.sub(r"\[[^\]]*\]|\([^)]*\d[^)]*\)", " ", stem)  # '(1)', '[1080p]'
    tokens = re.split(r"[\s._\-–,+]+", stem)
    out = []
    for token in tokens:
        if not token or token in media.JUNK_TOKENS:
            continue
        out.append(re.sub(r"\d+", "#", token))
    text = " ".join(out)
    return re.sub(r"(# ?)+", "# ", text).strip()


def _media_key(info: media.MediaInfo) -> str:
    return re.sub(r"[^a-z0-9]", "", info.title.lower())


def _common_name(paths: list[str]) -> str:
    """Readable shared prefix of the file names, cut at a word boundary."""
    stems = [re.sub(r"[._]+", " ", os.path.splitext(os.path.basename(p))[0]).strip() for p in paths]
    prefix_len = len(os.path.commonprefix([s.lower() for s in stems]))
    prefix = stems[0][:prefix_len]
    if prefix_len < len(stems[0]) and prefix and not prefix[-1].isspace() and stems[0][prefix_len].isalnum():
        prefix = prefix.rsplit(" ", 1)[0] if " " in prefix else ""  # don't cut a word in half
    prefix = re.sub(r"[\s\-–_(\[#]*\d*$", "", prefix).strip(" -–_([")
    if prefix:
        return prefix[0].upper() + prefix[1:]
    # No shared prefix: use the words every name has in common ('invoice')
    word_sets = [set(skeleton(p).split()) for p in paths]
    common = [w for w in skeleton(paths[0]).split() if w != "#" and all(w in ws for ws in word_sets)]
    return " ".join(common).title()


def find_groups(files: list[str]) -> tuple[list[FileGroup], list[str]]:
    """Split files into groups of related files. Returns (groups, ungrouped files)."""
    shows: dict[str, FileGroup] = {}
    movies: dict[str, FileGroup] = {}
    rest: list[str] = []

    for path in files:
        info = media.parse(os.path.basename(path))
        if info and info.is_episode:
            group = shows.setdefault(_media_key(info), FileGroup(info.title, KIND_SHOW, media=info))
            group.files.append(path)
        elif info:
            key = f"{_media_key(info)}{info.year or ''}"
            name = f"{info.title} ({info.year})" if info.year else info.title
            group = movies.setdefault(key, FileGroup(name, KIND_MOVIE, media=info))
            group.files.append(path)
        else:
            rest.append(path)

    # Subtitles named after the movie but without the year ('Inception.en.srt') join it
    for key, group in list(movies.items()):
        base = _media_key(group.media)
        for path in list(rest):
            if media.is_subtitle(path) and re.sub(r"[^a-z0-9]", "", skeleton(path)).startswith(base):
                group.files.append(path)
                rest.remove(path)

    # A movie group without a video is just a stray subtitle; let the similarity pass have it
    for key, group in list(movies.items()):
        if not group.videos:
            rest.extend(group.files)
            del movies[key]

    similar = _similar_groups(rest)
    grouped = {p for g in similar for p in g.files}
    leftovers = [p for p in rest if p not in grouped]

    def by_size(groups):
        return sorted(groups, key=lambda g: (-len(g.files), g.name.lower()))

    for group in [*movies.values(), *similar]:
        group.files.sort(key=lambda p: _natural_key(os.path.basename(p)))
    for group in shows.values():
        group.files.sort(key=_episode_order)
    return by_size(shows.values()) + by_size(movies.values()) + by_size(similar), leftovers


def _similar_groups(paths: list[str]) -> list[FileGroup]:
    skeletons = {p: skeleton(p) for p in paths}
    # Ignore names with too little text to compare ('1.jpg', '#.png')
    usable = [p for p in paths if len(re.sub(r"[^a-z]", "", skeletons[p])) >= 3]

    parent = {p: p for p in usable}

    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        parent[find(a)] = find(b)

    # Pass 1: identical skeletons ('IMG_2031', 'IMG_2032')
    by_skeleton: dict[str, str] = {}
    for p in usable:
        first = by_skeleton.setdefault(skeletons[p], p)
        if first is not p:
            union(p, first)

    # Pass 2: nearly identical names ('invoice march', 'invoice april')
    reps = list(by_skeleton.values())
    if len(reps) <= FUZZY_LIMIT:
        for i, a in enumerate(reps):
            matcher = difflib.SequenceMatcher(None, skeletons[a])
            for b in reps[i + 1:]:
                sb = skeletons[b]
                matcher.set_seq2(sb)
                same_start = _shares_first_word(skeletons[a], sb)
                if not same_start:
                    continue
                threshold = FUZZY_SAME_START_THRESHOLD if len(skeletons[a].split(" ", 1)[0]) >= 4                     else FUZZY_THRESHOLD
                if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
                    continue
                if matcher.ratio() >= threshold:
                    union(a, b)

    clusters: dict[str, list[str]] = {}
    for p in usable:
        clusters.setdefault(find(p), []).append(p)

    groups = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        groups.append(FileGroup(_common_name(members) or "Similar files", KIND_SIMILAR, members))
    return groups


def _shares_first_word(a: str, b: str) -> bool:
    return a.split(" ", 1)[0] == b.split(" ", 1)[0]


def _episode_order(path: str):
    info = media.parse(os.path.basename(path))
    season, episode = (info.season or 0, info.episode or 0) if info else (0, 0)
    return season, episode, media.is_subtitle(path), _natural_key(os.path.basename(path))


def _natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def move_group(root: str, files: list[str], folder_name: str, rename_episodes: bool = False,
               history=None) -> list[MoveResult]:
    """Move files into root/<folder_name>/, optionally renaming episodes to 'Show - S01E02.ext'."""
    target = os.path.join(root, safe_folder_name(folder_name))
    results = []
    for path in files:
        new_name = media.tidy_episode_name(os.path.basename(path)) if rename_episodes else None
        results.append(move_file(path, target, new_name))
    moved = [(r.source, r.destination) for r in results if not r.error]
    if history is not None and moved:
        entry = history.record("group", f"{len(moved)} file{'s' if len(moved) != 1 else ''} → "
                                        f"{os.path.basename(target)}/", moved)
        for r in results:
            r.history_id = entry.id
    return results
