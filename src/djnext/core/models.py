from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .structure import TrackStructure


@dataclass
class Track:
    id: str
    title: str
    artist: str = ""
    bpm: float = 0.0
    key: Optional[str] = None  # Camelot notation, e.g. "8A"
    genre: str = ""
    rating: int = 0  # 0-5 stars
    duration: float = 0.0  # seconds
    path: str = ""
    comments: str = ""
    energy: Optional[float] = None  # 0-10
    energy_source: str = ""  # "comment", "rating" or "bpm" (how energy was obtained)
    source: str = ""  # "soundcloud", "apple-music", "local" ...
    mood_fit: float = 0.0  # 0..1 how well it fits the chosen mood (set when building a mood set)
    analysis_path: str = ""  # rekordbox analysis file (phrases, beat grid)
    structure: Optional["TrackStructure"] = field(default=None, repr=False, compare=False)

    @property
    def is_stream(self) -> bool:
        return self.source not in ("", "local")

    @property
    def soundcloud_id(self) -> Optional[str]:
        prefix = "soundcloud:tracks:"
        return self.path[len(prefix):] if self.path.startswith(prefix) else None

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title
