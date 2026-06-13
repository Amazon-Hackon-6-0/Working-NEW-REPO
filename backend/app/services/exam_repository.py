import json
import re
from datetime import datetime, time, timezone
from pathlib import Path
from threading import Lock

from app.schemas.campusflow import ExamReminder


class ExamRepository:
    """Local durable exam schedule store for verified uploads."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[2] / "data" / "exams.json"
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def replace_all(self, exams: list[ExamReminder], source: str) -> None:
        future_exams = [exam for exam in exams if self._is_upcoming(exam)]
        payload = {
            "source": source,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "exams": [exam.model_dump() for exam in future_exams],
        }
        with self._lock:
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_exams(self) -> list[ExamReminder]:
        payload = self._read_payload()
        return [
            exam
            for exam in [ExamReminder(**item) for item in payload.get("exams", [])]
            if self._is_upcoming(exam)
        ]

    def prune_past_exams(self) -> int:
        payload = self._read_payload()
        current = [ExamReminder(**item) for item in payload.get("exams", [])]
        upcoming = [exam for exam in current if self._is_upcoming(exam)]
        removed = len(current) - len(upcoming)
        if removed:
            payload["exams"] = [exam.model_dump() for exam in upcoming]
            payload["synced_at"] = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return removed

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _is_upcoming(self, exam: ExamReminder) -> bool:
        exam_datetime = self._exam_datetime(exam)
        if not exam_datetime:
            return False
        return exam_datetime >= datetime.now()

    def _exam_datetime(self, exam: ExamReminder) -> datetime | None:
        try:
            exam_date = datetime.strptime(exam.exam_date, "%Y-%m-%d").date()
        except ValueError:
            return None

        parsed_time = self._parse_time(exam.time) or time(23, 59)
        return datetime.combine(exam_date, parsed_time)

    def _parse_time(self, value: str) -> time | None:
        cleaned = value.strip().upper().replace(".", "")
        if cleaned in {"", "TBA", "TBD"}:
            return None

        formats = ["%I:%M %p", "%I %p", "%H:%M", "%H"]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt).time()
            except ValueError:
                continue

        compact = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", cleaned)
        if compact:
            hour = int(compact.group(1))
            minute = int(compact.group(2) or 0)
            meridiem = compact.group(3)
            if meridiem == "PM" and hour != 12:
                hour += 12
            if meridiem == "AM" and hour == 12:
                hour = 0
            return time(hour, minute)

        return None
