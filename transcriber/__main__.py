import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import re
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Русская расшифровка аудио и видео в Word")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--cli", action="store_true", help="Обработать файлы без графического окна")
    parser.add_argument("--model", default="small", choices=("base", "small", "medium", "large-v3"))
    parser.add_argument("--device", default="cpu", help="cpu, cuda или vulkan:0 (номер Vulkan GPU)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    if args.device not in {"cpu", "cuda"} and not re.fullmatch(r"vulkan:\d+", args.device):
        parser.error("Устройство: cpu, cuda или vulkan:0 (номер GPU)")
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    data_dir = args.data_dir.resolve() if args.data_dir else app_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Keep model caches inside the application directory, and do not send telemetry.
    os.environ.setdefault("HF_HOME", str(data_dir / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[RotatingFileHandler(data_dir / "transcriber.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")],
    )
    if args.cli:
        if not args.files:
            parser.error("Укажите хотя бы один аудио- или видеофайл")
        from .domain import Settings
        from .engine import Transcriber
        logger = logging.getLogger("cli")
        engine = Transcriber(data_dir, Settings(model=args.model, device=args.device), lambda: False, logger.info)
        try:
            for file in args.files:
                result = engine.run_file(
                    Path(file).resolve(), args.output or app_dir / "results",
                    lambda seconds, duration: None, lambda segment: None,
                )
                logger.info("Saved: %s", result)
            return 0
        except Exception:
            logger.exception("Transcription failed")
            return 1
        finally:
            engine.close()
    from .ui import run_gui
    return run_gui(app_dir, data_dir, args.files)


if __name__ == "__main__":
    raise SystemExit(main())
