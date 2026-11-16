"""Decode only the chosen audio stream, with memory independent of file size."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np

from .domain import AudioTrack, Cancelled, MediaInfo, Settings

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioChunk:
    start: float
    samples: np.ndarray
    last: bool

    @property
    def end(self) -> float:
        return self.start + len(self.samples) / SAMPLE_RATE


def probe(path: Path) -> MediaInfo:
    with av.open(str(path)) as container:
        duration = container.duration / av.time_base if container.duration else None
        tracks = []
        for ordinal, stream in enumerate(container.streams.audio):
            track_duration = (
                float(stream.duration * stream.time_base)
                if stream.duration is not None and stream.time_base else duration
            )
            tracks.append(AudioTrack(
                ordinal, stream.index, stream.metadata.get("language", "und"),
                stream.metadata.get("title", ""), stream.codec_context.channels,
                track_duration,
            ))
    if not tracks:
        raise ValueError("В файле нет аудиодорожек. Выберите запись со звуком.")
    return MediaInfo(path, tuple(tracks), duration)


def choose_track(info: MediaInfo, ordinal: int | None) -> AudioTrack:
    if ordinal is not None:
        if not 0 <= ordinal < len(info.tracks):
            raise ValueError(
                f"Аудиодорожки № {ordinal + 1} нет. В файле дорожек: {len(info.tracks)}."
            )
        return info.tracks[ordinal]
    return next(
        (track for track in info.tracks if track.language.lower() in {"ru", "rus"}),
        info.tracks[0],
    )


def split_samples(
    arrays: Iterator[np.ndarray], settings: Settings,
    cancelled: Callable[[], bool] = lambda: False,
) -> Iterator[AudioChunk]:
    """Bounded buffer; the overlap protects words at five-minute boundaries."""
    stride = settings.chunk_seconds * SAMPLE_RATE
    overlap = settings.overlap_seconds * SAMPLE_RATE
    if stride <= 0 or not 0 <= overlap < stride:
        raise ValueError("Некорректная длительность фрагмента.")
    capacity = stride + overlap
    buffer = np.empty(capacity, dtype=np.float32)
    used = 0
    start_sample = 0
    for array in arrays:
        if cancelled():
            raise Cancelled()
        array = np.asarray(array, dtype=np.float32).reshape(-1)
        position = 0
        while position < len(array):
            if cancelled():
                raise Cancelled()
            if used == capacity:
                yield AudioChunk(start_sample / SAMPLE_RATE, buffer.copy(), False)
                if overlap:
                    buffer[:overlap] = buffer[stride:capacity]
                used = overlap
                start_sample += stride
            take = min(capacity - used, len(array) - position)
            buffer[used:used + take] = array[position:position + take]
            used += take
            position += take
    if used:
        yield AudioChunk(start_sample / SAMPLE_RATE, buffer[:used].copy(), True)


def audio_chunks(
    path: Path, track: AudioTrack, settings: Settings,
    cancelled: Callable[[], bool],
) -> Iterator[AudioChunk]:
    with av.open(str(path)) as container:
        stream = container.streams.audio[track.ordinal]
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)

        def arrays():
            # Demuxing the chosen stream never decodes the video, including in MKV.
            for packet in container.demux(stream):
                if cancelled():
                    raise Cancelled()
                for frame in packet.decode():
                    frame.pts = None
                    for converted in resampler.resample(frame):
                        yield converted.to_ndarray().reshape(-1)
            for converted in resampler.resample(None):
                yield converted.to_ndarray().reshape(-1)

        yield from split_samples(arrays(), settings, cancelled)
