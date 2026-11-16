import logging
import os
from collections.abc import Callable
from pathlib import Path

from .checkpoint import Checkpoint, job_identity
from .domain import Cancelled, Settings, TranscriptSegment, timestamp
from .export import available_output, export_docx
from .media import AudioChunk, audio_chunks, choose_track, probe

logger = logging.getLogger(__name__)


def owned_segments(segments, chunk: AudioChunk, settings: Settings):
    """Keep each word in one overlap window; retain its absolute audio timestamp."""
    lower = chunk.start + settings.overlap_seconds / 2 if chunk.start else 0
    upper = float("inf") if chunk.last else chunk.start + settings.chunk_seconds + settings.overlap_seconds / 2
    for segment in segments:
        words = getattr(segment, "words", None)
        if words:
            kept = [word for word in words if lower <= chunk.start + (word.start + word.end) / 2 < upper]
            if kept:
                yield TranscriptSegment(
                    chunk.start + kept[0].start, chunk.start + kept[-1].end,
                    "".join(word.word for word in kept).strip(),
                )
        elif lower <= chunk.start + (segment.start + segment.end) / 2 < upper:
            yield TranscriptSegment(chunk.start + segment.start, chunk.start + segment.end, segment.text.strip())


class Transcriber:
    def __init__(self, data_dir: Path, settings: Settings, cancelled: Callable[[], bool],
                 status: Callable[[str], None]):
        self.data_dir, self.settings = data_dir, settings
        self.cancelled, self.status = cancelled, status
        self.model = None

    def load_model(self):
        if self.model is not None:
            return
        if self.cancelled():
            raise Cancelled()
        self.status(f"Подготовка модели {self.settings.model}. При первом запуске идёт загрузка из интернета…")
        if self.settings.device.startswith("vulkan:"):
            from .vulkan import VulkanModel, download_model, list_devices
            index = int(self.settings.device.split(":", 1)[1])
            devices = list_devices()
            if not any(device["index"] == index for device in devices):
                raise RuntimeError("Выбранный Vulkan GPU не найден. Обновите драйвер AMD / Intel или выберите CPU.")
            model_path = download_model(self.data_dir, self.settings.model, self.status)
            if self.cancelled():
                raise Cancelled()
            self.status(f"Подготовка AMD / Intel GPU: {devices[index]['name']}…")
            self.model = VulkanModel(model_path, index, self.data_dir, self.cancelled)
            return
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            self.settings.model, device=self.settings.device,
            compute_type="int8" if self.settings.device == "cpu" else "float16",
            download_root=str(self.data_dir / "models"),
            cpu_threads=max(1, min(8, (os.cpu_count() or 4) - 1)),
            num_workers=1,
        )
        if self.cancelled():
            raise Cancelled()

    def close(self):
        if self.model is not None and hasattr(self.model, "close"):
            self.model.close()
        self.model = None

    def run_file(self, source: Path, output_dir: Path,
                 progress: Callable[[float, float | None], None],
                 preview: Callable[[TranscriptSegment], None]) -> Path:
        self.status("Чтение аудиодорожек…")
        info = probe(source)
        track = choose_track(info, self.settings.audio_track)
        label = f"№ {track.ordinal + 1} · {track.language}"
        if track.title:
            label += f" · {track.title}"
        store = Checkpoint(self.data_dir / "checkpoints", job_identity(source, self.settings, track.index))

        def save(partial: bool) -> Path:
            return export_docx(
                available_output(output_dir, source, partial), source, store.segments(),
                model=self.settings.model, track_label=label, timestamps=self.settings.timestamps,
                partial=partial, completed_seconds=store.completed_seconds(),
            )

        try:
            progress(store.completed_seconds(), track.duration)
            for segment in store.segments():
                preview(segment)
            for number, chunk in enumerate(audio_chunks(source, track, self.settings, self.cancelled)):
                if self.cancelled():
                    raise Cancelled()
                if store.has_chunk(number):
                    progress(chunk.end, track.duration)
                    continue
                self.load_model()
                self.status(f"Распознавание · аудиодорожка {label} · с {timestamp(chunk.start)}")
                segments, _ = self.model.transcribe(
                    chunk.samples, language="ru", task="transcribe", beam_size=5,
                    vad_filter=True, word_timestamps=True, condition_on_previous_text=False,
                )

                def checked_segments():
                    for segment in segments:
                        if self.cancelled():
                            raise Cancelled()
                        progress(min(chunk.end, chunk.start + segment.end), track.duration)
                        yield segment

                committed = list(owned_segments(checked_segments(), chunk, self.settings))
                if self.cancelled():
                    raise Cancelled()
                store.commit(number, chunk.end, committed)
                for segment in committed:
                    preview(segment)
                progress(chunk.end, track.duration)
            if self.cancelled():
                raise Cancelled()
            self.status("Сохранение документа Word…")
            return save(False)
        except Exception:
            # Checkpoints are retained even if Word cannot be written (e.g. disk full).
            if store.completed_seconds() > 0:
                try:
                    partial = save(True)
                    self.status(f"Частичная расшифровка сохранена: {partial.name}")
                except Exception:
                    logger.exception("Could not export partial transcript; SQLite checkpoint is intact")
            raise
        finally:
            store.close()
