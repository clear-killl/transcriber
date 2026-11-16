"""AMD / Intel acceleration through an isolated whisper.cpp Vulkan worker."""
from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import wave

import numpy as np

from .domain import Cancelled

logger = logging.getLogger(__name__)


def worker_path() -> Path:
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "runtime" / "vulkan" / "GpuWorker.exe"


def process_options() -> dict:
    # PyInstaller changes DLL search paths. Children use their own native runtime.
    environment = os.environ.copy()
    windows = Path(environment.get("SystemRoot", "C:/Windows"))
    paths = [worker_path().parent, windows / "System32", windows]
    if getattr(sys, "frozen", False):
        paths += [Path(sys._MEIPASS), Path(sys._MEIPASS) / "PySide6"]
    environment["PATH"] = os.pathsep.join(map(str, paths))
    environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    return {"env": environment, "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0}


def list_devices() -> list[dict]:
    executable = worker_path()
    if not executable.is_file():
        raise RuntimeError("Компонент Vulkan отсутствует. Запустите build-gpu.ps1 или используйте полную переносимую сборку.")
    result = subprocess.run([str(executable), "--list-devices"], capture_output=True,
                            encoding="utf-8", errors="replace", timeout=30, **process_options())
    if result.returncode:
        raise RuntimeError("Не удалось обнаружить Vulkan GPU. Обновите драйвер AMD / Intel.\n" + result.stderr[-3000:])
    devices = json.loads(result.stdout)
    if not isinstance(devices, list):
        raise RuntimeError("Некорректный ответ компонента Vulkan.")
    return devices


def download_model(data_dir: Path, model: str, status: Callable[[str], None]) -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    options = dict(repo_id="ggerganov/whisper.cpp", filename=f"ggml-{model}.bin",
                   cache_dir=str(data_dir / "models-vulkan"))
    try:
        return Path(hf_hub_download(**options, local_files_only=True))
    except LocalEntryNotFoundError:
        status(f"Загрузка модели {model} для AMD / Intel. Она сохранится для работы без интернета…")
        return Path(hf_hub_download(**options))


def timed_words(message: dict) -> list:
    """Use native token timing only when it reproduces the complete Unicode text."""
    tokens = message.get("tokens", [])
    if not tokens or "".join(token["text"] for token in tokens).strip() != message["text"].strip():
        return []
    words = []
    for token in tokens:
        text, start, end = token["text"], token["start"], token["end"]
        if start < 0 or end < start:
            return []
        if not words or (text and text[0].isspace()):
            words.append(SimpleNamespace(word=text, start=start, end=end))
        else:
            words[-1].word += text
            words[-1].end = end
    return words


class VulkanModel:
    def __init__(self, model: Path, device: int, data_dir: Path, cancelled: Callable[[], bool]):
        self.cancelled = cancelled
        self.process = None
        self.log = None
        self.reader = None
        self.messages = queue.Queue()
        self.temp = tempfile.TemporaryDirectory(prefix="vulkan-", dir=data_dir)
        try:
            self.log = (data_dir / "vulkan-worker.log").open("w+", encoding="utf-8")
            self.process = subprocess.Popen(
                [str(worker_path()), str(model), str(device)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.log, text=True, encoding="utf-8", bufsize=1,
                **process_options(),
            )
            self.reader = threading.Thread(target=self.read_messages, daemon=True)
            self.reader.start()
            if self.receive().get("type") != "ready":
                raise RuntimeError("Компонент Vulkan не подтвердил готовность.")
        except BaseException:
            self.close()
            raise

    def read_messages(self):
        try:
            for line in self.process.stdout:
                self.messages.put(line)
        finally:
            self.messages.put(None)

    def receive(self) -> dict:
        while True:
            if self.cancelled():
                self.close()
                raise Cancelled()
            try:
                line = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                self.log.flush()
                self.log.seek(0)
                details = self.log.read()[-5000:]
                raise RuntimeError("Vulkan: не удалось запустить или продолжить распознавание на GPU.\n" + details)
            try:
                return json.loads(line)
            except ValueError as exc:
                raise RuntimeError("Некорректный ответ компонента Vulkan.") from exc

    def transcribe(self, audio, **kwargs):
        return self.iter_segments(audio), None

    def iter_segments(self, audio):
        from faster_whisper.vad import get_speech_timestamps
        if self.cancelled():
            raise Cancelled()
        # Silence-only chunks must not produce Whisper's common silence hallucinations.
        if not get_speech_timestamps(audio):
            return
        path = Path(self.temp.name) / "chunk.wav"
        try:
            with wave.open(str(path), "wb") as file:
                file.setnchannels(1)
                file.setsampwidth(2)
                file.setframerate(16000)
                file.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
            self.process.stdin.write(json.dumps({"audio": str(path)}) + "\n")
            self.process.stdin.flush()
            while True:
                message = self.receive()
                if message.get("type") == "done":
                    break
                if message.get("type") != "segment":
                    raise RuntimeError("Неизвестный ответ компонента Vulkan.")
                yield SimpleNamespace(start=message["start"], end=message["end"],
                                      text=message["text"], words=timed_words(message))
        finally:
            path.unlink(missing_ok=True)

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            if self.reader:
                self.reader.join(timeout=2)
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None
        self.temp.cleanup()
