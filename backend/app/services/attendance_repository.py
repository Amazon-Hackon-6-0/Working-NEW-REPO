from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.schemas.campusflow import AttendanceFeedback


class AttendanceRepository:
    """Local durable event store for the hackathon demo.

    The data shape mirrors what we would later persist in DynamoDB.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[2] / "data" / "attendance_events.json"
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add_event(
        self,
        feedback: AttendanceFeedback,
        source: str,
        actor_id: str | None = None,
    ) -> dict:
        event = {
            "event_id": str(uuid4()),
            "subject_code": feedback.subject_code.upper(),
            "class_status": feedback.class_status,
            "attended": feedback.attended,
            "note": feedback.note,
            "source": source,
            "actor_id": actor_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            events = self.list_events()
            events.append(event)
            self.path.write_text(json.dumps(events, indent=2), encoding="utf-8")
        return event

    def list_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def events_for_subject(self, subject_code: str) -> list[dict]:
        code = subject_code.upper()
        return [event for event in self.list_events() if event["subject_code"] == code]
