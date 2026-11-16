import json
from pathlib import Path
import sys
import time

import numpy as np
import pytest

from transcriber.domain import Cancelled
from transcriber import vulkan


def test_timed_words_preserve_russian_and_group_subwords():
    message = {"text": " Проверка русской речи.", "tokens": [
        {"text": " Провер", "start": 0, "end": 0.3},
        {"text": "ка", "start": 0.3, "end": 0.5},
        {"text": " русской", "start": 0.6, "end": 1},
        {"text": " речи.", "start": 1.1, "end": 1.5},
    ]}
    words = vulkan.timed_words(message)
    assert [w.word for w in words] == [" Проверка", " русской", " речи."]
    assert words[0].end == 0.5
    # BPE can split a Unicode codepoint. Never reconstruct damaged Russian text.
    message["tokens"][0]["text"] = "�"
    assert vulkan.timed_words(message) == []


def test_missing_vulkan_component_has_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(vulkan, "worker_path", lambda: tmp_path / "missing.exe")
    with pytest.raises(RuntimeError, match="build-gpu"):
        vulkan.list_devices()


def test_native_worker_protocol_wav_and_cleanup(monkeypatch, tmp_path):
    script = tmp_path / "worker.py"
    script.write_text('''import json, sys, wave
print(json.dumps({"type": "ready"}), flush=True)
for command in sys.stdin:
    path = json.loads(command)["audio"]
    with wave.open(path) as f:
        assert f.getframerate() == 16000 and f.getnchannels() == 1 and f.getsampwidth() == 2
    print(json.dumps({"type":"segment", "start":0, "end":1, "text":"Русская речь", "tokens":[]}), flush=True)
    print(json.dumps({"type":"done"}), flush=True)
''', encoding="utf-8")
    monkeypatch.setattr(vulkan, "worker_path", lambda: Path(sys.executable))
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda audio: [{"start": 0, "end": len(audio)}])
    model = vulkan.VulkanModel(script, 0, tmp_path, lambda: False)
    temporary = Path(model.temp.name)
    process = model.process
    segments, _ = model.transcribe(np.ones(16000, dtype=np.float32))
    assert [s.text for s in segments] == ["Русская речь"]
    assert not (temporary / "chunk.wav").exists()
    model.close()
    model.close()
    assert process.poll() is not None and not temporary.exists()


def test_cancel_terminates_blocked_native_worker(monkeypatch, tmp_path):
    script = tmp_path / "worker.py"
    script.write_text('''import json, sys, time
print(json.dumps({"type":"ready"}), flush=True)
for line in sys.stdin:
    time.sleep(30)
''', encoding="utf-8")
    monkeypatch.setattr(vulkan, "worker_path", lambda: Path(sys.executable))
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda audio: [{"start": 0, "end": len(audio)}])
    model = vulkan.VulkanModel(script, 0, tmp_path, lambda: False)
    process, temporary = model.process, Path(model.temp.name)
    stop_at = time.monotonic() + 0.2
    model.cancelled = lambda: time.monotonic() >= stop_at
    try:
        with pytest.raises(Cancelled):
            list(model.transcribe(np.ones(16000, dtype=np.float32))[0])
        assert process.poll() is not None and not temporary.exists()
    finally:
        model.close()


def test_worker_crash_reports_log_and_cleans_up(monkeypatch, tmp_path):
    script = tmp_path / "worker.py"
    script.write_text('import sys; print("GPU initialization failed", file=sys.stderr); sys.exit(5)', encoding="utf-8")
    monkeypatch.setattr(vulkan, "worker_path", lambda: Path(sys.executable))
    with pytest.raises(RuntimeError, match="GPU initialization failed"):
        vulkan.VulkanModel(script, 0, tmp_path, lambda: False)
    assert not [path for path in tmp_path.glob("vulkan-*") if path.is_dir()]
