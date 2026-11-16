"""Real-model smoke test; downloads the selected model into the project cache."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

root = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(root / "data" / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from transcriber.domain import Settings
from transcriber.engine import Transcriber

source = Path(sys.argv[1]).resolve()
engine = Transcriber(root / "data", Settings(model=sys.argv[2] if len(sys.argv) > 2 else "small", device=sys.argv[3] if len(sys.argv) > 3 else "cpu"), lambda: False, print)
try:
    target = engine.run_file(source, root / "data" / "smoke-output", lambda seconds, duration: print(f"progress={seconds:.1f}/{duration}"), lambda segment: print(segment.text))
    print(f"SAVED: {target}")
finally:
    engine.close()
