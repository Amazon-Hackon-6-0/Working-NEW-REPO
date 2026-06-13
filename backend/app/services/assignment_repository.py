from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.schemas.campusflow import AssignmentItem


class AssignmentRepository:
    """Local durable assignment store for Classroom sync results."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[2] / "data" / "assignments.json"
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def replace_all(self, assignments: list[AssignmentItem], source: str) -> None:
        payload = {
            "source": source,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "assignments": [assignment.model_dump() for assignment in assignments],
        }
        with self._lock:
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_assignments(self) -> list[AssignmentItem]:
        payload = self._read_payload()
        return [AssignmentItem(**item) for item in payload.get("assignments", [])]

    def synced_at(self) -> str | None:
        payload = self._read_payload()
        return payload.get("synced_at")

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
