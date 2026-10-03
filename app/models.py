from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoItem:
    title: str
    url: str
    source: str
    duration: int | None = None


@dataclass(frozen=True)
class DownloadedVideo:
    item: VideoItem
    path: Path
    processed_path: Path | None = None

    @property
    def send_path(self) -> Path:
        return self.processed_path or self.path
