"""Who made a track and what it's called, from messy SoundCloud uploads.

A SoundCloud stream in rekordbox looks like  artist="Solid Grooves Raw", title="SGRAW052 Beltran - Smack Yo'".
To find it in DJ tracklists we need the real artist (Beltran) and title (Smack Yo'), and we have to match
both: matching on title alone links "Cloonee - XTC" to "Dan Molinari - XTC".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

from .models import Track

# bracket contents that describe the version, not the song
_GENERIC_VERSION = re.compile(
    r"^(extended|original|radio|club|main|vip|clean|dirty|instrumental)?\s*(mix|edit|version|cut)?$"
    r"|free\s*d(ow)?n?l(oa)?d|premiere|out now|unreleased|\bdl\b|\bmlkl\d+|\d{4}", re.IGNORECASE)
_CATALOG = re.compile(r"^(?:[A-Z]{2,}\d{2,}|\[[^\]]*\]|PREMIERE:?|FREE DL:?)\s*", re.IGNORECASE)
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+[^()\[\]]*?(?=\s+-\s+|\s*[(\[]|\s*$)", re.IGNORECASE)
_BRACKETS = re.compile(r"[(\[]([^)\]]*)[)\]]")
_VERSION_WORD = re.compile(r"\b(remix|edit|rework|bootleg|dub|flip|refix|mix)\b", re.IGNORECASE)
_LEADING = re.compile(r"^\s*(?:#|\*)*\s*(?:\[[^\]]*\]\s*)*(?:\d{1,2}:\d{2}(?::\d{2})?\s*-?\s*)?(?:\d{1,3}[.)]\s+)?")
_STOP = {"the", "and", "a", "of", "x", "vs", "feat", "ft", "with", "records", "recordings", "music", "official",
         "remix", "edit", "mix", "extended", "original", "rework", "dub", "version"}


def words(text: str) -> Tuple[str, ...]:
    """Lower-case, accent-free word list ('ROB MÂRK' -> ('rob', 'mark'))."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return tuple(re.findall(r"[a-z0-9]+", text.lower().replace("'", "")))


@dataclass(frozen=True)
class Name:
    artists: Tuple[str, ...]  # each artist as one normalised phrase, e.g. ("max styler", "chris lake")
    title: Tuple[str, ...]  # title words without version info, e.g. ("smack", "yo")
    version: Tuple[str, ...]  # remixer words, e.g. ("max", "styler") for "(Max Styler Remix)"
    swapped: Tuple[str, ...] = ()  # the part before " - " as words: some uploads put "Title - Artist"

    @property
    def title_text(self) -> str:
        return " ".join(self.title)

    @property
    def main_artist(self) -> str:
        return self.artists[0] if self.artists else ""

    def artist_words(self) -> FrozenSet[str]:
        out = set()
        for a in self.artists + (" ".join(self.version),):
            out.update(w for w in a.split() if len(w) >= 3 and w not in _STOP)
        return frozenset(out)


def _split_artists(text: str) -> Tuple[str, ...]:
    parts = re.split(r",|&|\band\b|\bx\b|\bvs\.?\b|\bb2b\b|\bwith\b|\bfeat\.?|\bft\.?", text, flags=re.IGNORECASE)
    return tuple(" ".join(words(p)) for p in parts if words(p))


def parse(artist: str, title: str) -> Name:
    """Real artists, title and remixer from a rekordbox/SoundCloud artist + title."""
    title = title.strip()
    title = _CATALOG.sub("", title).strip()
    version: Tuple[str, ...] = ()
    for inner in _BRACKETS.findall(title):
        if _VERSION_WORD.search(inner) and not _GENERIC_VERSION.search(inner.strip()):
            version = tuple(w for w in words(_VERSION_WORD.sub("", inner)) if w not in _STOP)
    feats = [m.group(0) for m in _FEAT.finditer(title)]
    core = _FEAT.sub("", _BRACKETS.sub("", title))
    artists: Tuple[str, ...] = ()
    swapped: Tuple[str, ...] = ()
    if " - " in core:  # "Beltran - Smack Yo'" inside the title: the uploader is usually a label/channel
        left, core = core.split(" - ", 1)
        if " - " in core:  # "Label - Artist - Title"
            mid, core = core.rsplit(" - ", 1)
            left = mid
        artists = _split_artists(_CATALOG.sub("", left.strip()))
        swapped = words(_CATALOG.sub("", left.strip()))
    # the uploader is usually a label/channel when the artist is in the title: keep it as one name then
    uploader = ((" ".join(words(artist)),) if words(artist or "") else ()) if artists else _split_artists(artist or "")
    artists = artists + tuple(a for a in uploader if a not in artists)
    for f in feats:
        artists += _split_artists(re.sub(r"^\s*(feat\.?|ft\.?|featuring)\s+", "", f.strip(), flags=re.IGNORECASE))
    return Name(artists=artists, title=words(core), version=version, swapped=swapped)


def of(track: Track) -> Name:
    return parse(track.artist, track.title)


def display(track: Track) -> Tuple[str, str]:
    """(artist, title) as written in the upload, for the screen: 'SGRAW052 Beltran - Smack Yo'' -> ('Beltran', "Smack Yo'")."""
    title = track.title.strip()
    if " - " in title:
        left, right = title.rsplit(" - ", 1) if title.count(" - ") > 1 else title.split(" - ", 1)
        left = left.split(" - ")[-1]
        return _CATALOG.sub("", left).strip() or track.artist, right.strip()
    return track.artist, title


def clean_line(line: str) -> Optional[Tuple[str, str]]:
    """'# [12] Beltran - Smack Yo' [Solid Grooves Raw]' -> ('Beltran', "Smack Yo' [Solid Grooves Raw]').
    None when the line isn't 'Artist - Title'."""
    line = _LEADING.sub("", line.strip()).strip()
    if " - " not in line or line.startswith("?"):
        return None
    artist, title = line.split(" - ", 1)
    return artist.strip(), title.strip()


def matches(name: Name, line_artist: str, line_title: str) -> bool:
    """Is this tracklist line the same song? The title words must all be there, and at least one artist
    (or the remixer) must be named somewhere on the line. 'Fake ID - Chris Lorenzo' also matches
    'Chris Lorenzo - Fake ID'."""
    if _matches(name, line_artist, line_title):
        return True
    if name.swapped and name.title:
        flipped = Name(artists=(" ".join(name.title),) + name.artists[len(_split_artists(" ".join(name.swapped))):],
                       title=name.swapped, version=name.version)
        return _matches(flipped, line_artist, line_title)
    return False


def _matches(name: Name, line_artist: str, line_title: str) -> bool:
    if not name.title:
        return False
    t_words = set(words(line_title))
    if not set(name.title) <= t_words:
        return False
    if len(name.title) == 1 and len(words(_BRACKETS.sub("", line_title))) > 3:
        return False  # a one-word title ("Body") inside a long, different title
    every = set(words(line_artist)) | t_words
    aw = name.artist_words()
    return bool(aw & every) if aw else True
