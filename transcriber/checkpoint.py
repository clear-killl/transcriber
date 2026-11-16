"""Transactional checkpoints: a chunk is either fully committed or retried."""
import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from pathlib import Path

from .domain import Settings, TranscriptSegment


def job_identity(path: Path, settings: Settings, track_index: int) -> str:
    stat = path.stat()
    identity = {
        "version": 1, "path": str(path.resolve()), "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns, "settings": asdict(settings),
        "track_index": track_index,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class Checkpoint:
    def __init__(self, directory: Path, identity: str):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{identity}.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                number INTEGER PRIMARY KEY, end REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS segments (
                chunk INTEGER NOT NULL, position INTEGER NOT NULL,
                start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL,
                PRIMARY KEY (chunk, position)
            );
        """)

    def has_chunk(self, number: int) -> bool:
        return self.db.execute("SELECT 1 FROM chunks WHERE number = ?", (number,)).fetchone() is not None

    def commit(self, number: int, end: float, segments: Iterable[TranscriptSegment]):
        with self.db:
            self.db.execute("DELETE FROM segments WHERE chunk = ?", (number,))
            self.db.executemany(
                "INSERT INTO segments VALUES (?, ?, ?, ?, ?)",
                ((number, position, s.start, s.end, s.text) for position, s in enumerate(segments)),
            )
            self.db.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?)", (number, end))

    def segments(self) -> Iterator[TranscriptSegment]:
        for start, end, text in self.db.execute(
            "SELECT start, end, text FROM segments ORDER BY chunk, position"
        ):
            yield TranscriptSegment(start, end, text)

    def completed_seconds(self) -> float:
        return self.db.execute("SELECT COALESCE(MAX(end), 0) FROM chunks").fetchone()[0]

    def close(self):
        self.db.close()
