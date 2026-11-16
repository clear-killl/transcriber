from dataclasses import dataclass
from pathlib import Path


class Cancelled(Exception):
    """A cooperative cancellation; already committed chunks remain available."""


@dataclass(frozen=True)
class Settings:
    model: str = "small"
    device: str = "cpu"
    audio_track: int | None = None
    timestamps: bool = True
    chunk_seconds: int = 300
    overlap_seconds: int = 2


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class AudioTrack:
    ordinal: int
    index: int
    language: str
    title: str
    channels: int
    duration: float | None


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    tracks: tuple[AudioTrack, ...]
    duration: float | None


def timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def file_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}"
        value /= 1024
    return ""
