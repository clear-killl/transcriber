from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import wave

import av
from docx import Document
import numpy as np
import pytest

from transcriber.checkpoint import Checkpoint, job_identity
from transcriber.domain import Cancelled, Settings, TranscriptSegment
from transcriber.engine import Transcriber, owned_segments
from transcriber.export import available_output, export_docx
from transcriber.media import AudioChunk, SAMPLE_RATE, audio_chunks, choose_track, probe, split_samples


def write_wav(path: Path, seconds=1, rate=22050):
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(np.zeros(int(seconds * rate), dtype=np.int16).tobytes())


def word(start, end, text):
    return SimpleNamespace(start=start, end=end, word=text)


def segment(text=" Проверка русского текста."):
    return SimpleNamespace(start=0, end=0.5, text=text, words=[word(0, 0.5, text)])


def test_streaming_chunks_cover_all_samples_and_bound_memory():
    # Irregular decoder frames and exact-boundary EOF exercise carry and flush.
    source = np.arange(SAMPLE_RATE * 13 + 17, dtype=np.float32)
    settings = Settings(chunk_seconds=3, overlap_seconds=1)
    arrays = (source[i:i + 733] for i in range(0, len(source), 733))
    chunks = list(split_samples(arrays, settings))
    assert all(len(chunk.samples) <= SAMPLE_RATE * 4 for chunk in chunks)
    assert chunks[-1].last and not any(chunk.last for chunk in chunks[:-1])
    reconstructed = np.concatenate([chunk.samples[:3 * SAMPLE_RATE] for chunk in chunks[:-1]] + [chunks[-1].samples])
    np.testing.assert_array_equal(reconstructed, source)
    exact = list(split_samples(iter([source[:4 * SAMPLE_RATE]]), settings))
    assert len(exact) == 1 and exact[0].last


def test_cancel_checked_while_streaming():
    with pytest.raises(Cancelled):
        list(split_samples(iter([np.zeros(100)]), Settings(), lambda: True))


def test_wav_decode_resamples_and_flushes(tmp_path):
    path = tmp_path / "Запись с пробелами.wav"
    write_wav(path, 2.25)
    track = choose_track(probe(path), None)
    chunks = list(audio_chunks(path, track, Settings(), lambda: False))
    assert sum(len(chunk.samples) for chunk in chunks) == 36000
    assert chunks[0].samples.dtype == np.float32


def test_mkv_multi_audio_track_selection_and_no_video_decode(tmp_path):
    path = tmp_path / "Две дорожки.mkv"
    with av.open(str(path), "w", format="matroska") as container:
        video = container.add_stream("mpeg4", rate=1)
        video.width, video.height = 32, 32
        video.pix_fmt = "yuv420p"
        tracks = []
        for language in ("eng", "rus"):
            stream = container.add_stream("pcm_s16le", rate=16000)
            stream.layout = "mono"
            stream.metadata["language"] = language
            tracks.append(stream)
        frame = av.VideoFrame.from_ndarray(np.zeros((32, 32, 3), dtype=np.uint8), format="rgb24")
        for packet in video.encode(frame):
            container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
        for index, stream in enumerate(tracks):
            samples = np.full((1, 16000), 1000 * (index + 1), dtype=np.int16)
            frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
            frame.sample_rate, frame.pts = 16000, 0
            for packet in stream.encode(frame):
                container.mux(packet)
            for packet in stream.encode(None):
                container.mux(packet)
    info = probe(path)
    assert len(info.tracks) == 2
    selected = choose_track(info, None)
    assert selected.ordinal == 1
    chunks = list(audio_chunks(path, selected, Settings(), lambda: False))
    assert len(chunks) == 1
    assert float(np.mean(chunks[0].samples)) == pytest.approx(2000 / 32768)
    with pytest.raises(ValueError, match="нет"):
        choose_track(info, 2)


def test_overlap_words_are_owned_once():
    settings = Settings(chunk_seconds=3, overlap_seconds=2)
    first = AudioChunk(0, np.zeros(SAMPLE_RATE * 5), False)
    second = AudioChunk(3, np.zeros(SAMPLE_RATE * 5), True)
    one = SimpleNamespace(words=[word(3, 3.5, " до"), word(4, 4.5, " после")])
    two = SimpleNamespace(words=[word(0, 0.5, " до"), word(1, 1.5, " после")])
    result = list(owned_segments([one], first, settings)) + list(owned_segments([two], second, settings))
    assert [item.text for item in result] == ["до", "после"]
    assert result[1].start == 4


def test_checkpoint_commit_and_identity_changes(tmp_path):
    source = tmp_path / "file.wav"
    source.write_bytes(b"audio")
    identity = job_identity(source, Settings(), 0)
    assert identity != job_identity(source, replace(Settings(), model="medium"), 0)
    store = Checkpoint(tmp_path / "checkpoints", identity)
    store.commit(0, 300, [TranscriptSegment(1, 2, "Привет")])
    store.close()
    store = Checkpoint(tmp_path / "checkpoints", identity)
    assert store.has_chunk(0) and not store.has_chunk(1)
    assert store.completed_seconds() == 300
    assert list(store.segments()) == [TranscriptSegment(1, 2, "Привет")]
    store.close()


def test_docx_russian_text_timestamps_and_no_overwrite(tmp_path):
    source = tmp_path / "Интервью.mkv"
    target = available_output(tmp_path, source)
    export_docx(target, source, [TranscriptSegment(3661, 3663, "Русская речь\x00.")], model="small", track_label="№ 2 · rus", timestamps=True)
    document = Document(target)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "[01:01:01]" in text and "Русская речь." in text
    assert document.core_properties.language == "ru-RU"
    assert available_output(tmp_path, source) != target
    assert not list(tmp_path.glob("tmp*.docx"))


def test_cancellation_saves_partial_and_retry_skips_recognition(tmp_path):
    source = tmp_path / "Запись.wav"
    write_wav(source, seconds=6)
    settings = Settings(chunk_seconds=2, overlap_seconds=1)
    stop = [False]

    class FakeModel:
        calls = 0

        def transcribe(self, audio, **kwargs):
            assert kwargs["language"] == "ru"
            self.calls += 1
            return iter([segment()]), None

    model = FakeModel()
    engine = Transcriber(tmp_path / "data", settings, lambda: stop[0], lambda text: None)
    engine.model = model

    def cancel_after_commit(_):
        stop[0] = True

    with pytest.raises(Cancelled):
        engine.run_file(source, tmp_path / "output", lambda *args: None, cancel_after_commit)
    partial = list((tmp_path / "output").glob("*частично.docx"))
    assert len(partial) == 1
    assert "Частичная расшифровка" in "\n".join(p.text for p in Document(partial[0]).paragraphs)
    assert model.calls == 1
    stop[0] = False
    result = engine.run_file(source, tmp_path / "output", lambda *args: None, lambda text: None)
    assert result.exists() and model.calls == 3  # Three chunks total; the first is reused.


def test_corrupt_media_fails_with_no_success_document(tmp_path):
    path = tmp_path / "broken.mkv"
    path.write_bytes(b"not a media container")
    engine = Transcriber(tmp_path / "data", Settings(), lambda: False, lambda text: None)
    with pytest.raises(Exception):
        engine.run_file(path, tmp_path / "output", lambda *args: None, lambda text: None)
    assert not list(tmp_path.glob("output/*.docx"))
