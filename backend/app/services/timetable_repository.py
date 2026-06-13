from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.schemas.campusflow import TimetableEntry


class TimetableRepository:
    """Local durable timetable store for uploaded semester PDFs."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[1] / "data" / "timetable.json"
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def replace_all(self, entries: list[TimetableEntry], source_name: str) -> dict:
        payload = {
            "source_name": source_name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "entries": [entry.model_dump() for entry in entries],
        }
        with self._lock:
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def read_payload(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def list_entries(self) -> list[TimetableEntry]:
        payload = self.read_payload()
        entries = []
        for item in payload.get("entries", []):
            try:
                entries.append(TimetableEntry(**item))
            except ValueError:
                continue
        return entries

    def has_uploaded_timetable(self) -> bool:
        return bool(self.list_entries())
