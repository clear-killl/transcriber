"""Build a portable release using an allowlist, without user transcripts or settings."""
import argparse
import hashlib
import re
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def collect_files(include_models: bool) -> dict[str, Path]:
    app = ROOT / "dist" / "Transcriber"
    files: dict[str, Path] = {}

    def add_tree(source: Path, target: str):
        if not source.is_dir():
            raise FileNotFoundError(source)
        for path in source.rglob("*"):
            if path.is_file() and not path.name.endswith((".lock", ".incomplete")):
                files[f"Transcriber/{target}/{path.relative_to(source).as_posix()}"] = path

    if not (app / "Transcriber.exe").is_file():
        raise FileNotFoundError("Build the app with build.ps1 first")
    files["Transcriber/Transcriber.exe"] = app / "Transcriber.exe"
    add_tree(app / "_internal", "_internal")
    add_tree(app / "runtime", "runtime")
    for name in ("README.md", "THIRD_PARTY_NOTICES.md"):
        files[f"Transcriber/{name}"] = ROOT / name
    add_tree(ROOT / "docs", "docs")
    if include_models:
        for cache, namespace in (
            ("models", "models--Systran--faster-whisper-small"),
            ("models-vulkan", "models--ggerganov--whisper.cpp"),
        ):
            add_tree(app / "data" / cache / namespace, f"data/{cache}/{namespace}")

    site_packages = ROOT / ".venv" / "Lib" / "site-packages"
    for metadata in site_packages.glob("*.dist-info"):
        for path in metadata.rglob("*"):
            if path.is_file() and ("licenses" in path.relative_to(metadata).parts or
                    any(word in path.name.lower() for word in ("license", "copying", "copyright", "notice"))):
                files[f"Transcriber/licenses/python-packages/{metadata.name}/{path.relative_to(metadata).as_posix()}"] = path
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-models", action="store_true")
    parser.add_argument("--version", default="1.1.0")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("Version must use the format 1.1.0")
    files = collect_files(args.include_models)
    forbidden = ("/data/checkpoints/", "/data/settings.json", "/results/", ".sqlite3", ".log")
    assert not any(any(marker in name for marker in forbidden) for name in files)
    output = ROOT / "releases"
    output.mkdir(exist_ok=True)
    suffix = "" if args.include_models else "-no-models"
    target = output / f"Transcriber-{args.version}-Windows-x64{suffix}.zip"
    print(f"Packaging {len(files)} files", flush=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for index, (name, source) in enumerate(sorted(files.items()), 1):
            archive.write(source, name)
            if index % 250 == 0:
                print(f"{index}/{len(files)}", flush=True)
    with target.open("rb") as file:
        checksum = hashlib.file_digest(file, "sha256").hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
    print(f"Created: {target.name} ({target.stat().st_size / 1024**2:.1f} MiB)", flush=True)
    print(f"SHA256: {checksum}", flush=True)


if __name__ == "__main__":
    main()
