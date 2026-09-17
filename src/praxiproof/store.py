import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxiproof.ir.evidence import Evidence

_TABLES = {"manuals": "MAN", "videos": "VID", "runs": "V", "skills": "SK", "pipelines": "PL"}


class NotFound(KeyError):
    pass


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            for table in _TABLES:
                self._db.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, created_at TEXT, data TEXT)"
                )
            self._db.execute("CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, source_id TEXT, data TEXT)")
            self._db.execute("CREATE INDEX IF NOT EXISTS evidence_source ON evidence (source_id)")

    def create(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            cursor = self._db.execute(f"INSERT INTO {table} (created_at, data) VALUES (?, '{{}}')", (_now(),))
            record_id = f"{_TABLES[table]}-{cursor.lastrowid:03d}"
            record = {"id": record_id, "created_at": _now(), **data}
            self._db.execute(f"UPDATE {table} SET id = ?, data = ? WHERE seq = ?", (record_id, json.dumps(record), cursor.lastrowid))
        return record

    def get(self, table: str, record_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute(f"SELECT data FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise NotFound(f"{table} {record_id} not found")
        return json.loads(row[0])

    def update(self, table: str, record_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock, self._db:
            row = self._db.execute(f"SELECT data FROM {table} WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                raise NotFound(f"{table} {record_id} not found")
            record = json.loads(row[0]) | fields
            self._db.execute(f"UPDATE {table} SET data = ? WHERE id = ?", (json.dumps(record), record_id))
        return record

    def list(self, table: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(f"SELECT data FROM {table} ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def put_evidence(self, items: Iterable[Evidence]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO evidence (id, source_id, data) VALUES (?, ?, ?)",
                [(e.evidence_id, e.source_id, e.model_dump_json()) for e in items],
            )

    def evidence(self, ids: Iterable[str] | None = None, source_id: str | None = None) -> dict[str, Evidence]:
        with self._lock:
            if source_id is not None:
                rows = self._db.execute("SELECT data FROM evidence WHERE source_id = ?", (source_id,)).fetchall()
            else:
                wanted = list(dict.fromkeys(ids or []))
                if not wanted:
                    return {}
                marks = ",".join("?" * len(wanted))
                rows = self._db.execute(f"SELECT data FROM evidence WHERE id IN ({marks})", wanted).fetchall()
        items = [Evidence.model_validate_json(r[0]) for r in rows]
        return {e.evidence_id: e for e in items}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
