import re
from io import BytesIO
from datetime import date, datetime

from pypdf import PdfReader

from app.schemas.campusflow import (
    ExamReminder,
    ExamScheduleUpload,
    ExamScheduleUploadResponse,
)
from app.services.exam_repository import ExamRepository


class ExamScheduleService:
    """Parses and verifies simple exam schedule text uploads."""

    def __init__(self, exam_repository: ExamRepository | None = None) -> None:
        self.exam_repository = exam_repository or ExamRepository()

    def upload_schedule(self, payload: ExamScheduleUpload) -> ExamScheduleUploadResponse:
        exams = self._parse_schedule(payload)
        outdated = [
            f"{exam.subject} on {exam.exam_date}"
            for exam in exams
            if datetime.strptime(exam.exam_date, "%Y-%m-%d").date() < date.today()
        ]

        if outdated:
            removed = self.exam_repository.prune_past_exams()
            prune_message = (
                f" Removed {removed} previously saved past exam(s)." if removed else ""
            )
            return ExamScheduleUploadResponse(
                exams=exams,
                outdated_items=outdated,
                message=(
                    "Schedule contains past exam dates and was not saved. "
                    "Upload the latest schedule with future exam dates."
                    f"{prune_message}"
                ),
            )

        verified_exams = [
            exam.model_copy(update={"verified_by_user": payload.confirm_as_latest})
            for exam in exams
        ]
        self.exam_repository.replace_all(verified_exams, payload.source_name)
        return ExamScheduleUploadResponse(
            exams=verified_exams,
            outdated_items=outdated,
            message=f"Saved {len(verified_exams)} exam reminder(s) from {payload.source_name}.",
        )

    def upload_pdf_schedule(
        self,
        filename: str,
        content: bytes,
        confirm_as_latest: bool,
    ) -> ExamScheduleUploadResponse:
        text = self._extract_pdf_text(content)
        if not text.strip():
            return ExamScheduleUploadResponse(
                exams=[],
                outdated_items=[],
                message=(
                    "Could not extract readable text from this PDF. Try uploading a text-based PDF "
                    "or paste the schedule manually."
                ),
            )

        response = self.upload_schedule(
            ExamScheduleUpload(
                source_name=filename,
                schedule_text=text,
                confirm_as_latest=confirm_as_latest,
            )
        )
        if not response.exams:
            return response.model_copy(
                update={
                    "message": (
                        "PDF text was extracted, but no exam rows matched the expected pattern. "
                        "Use lines like: Subject | YYYY-MM-DD | Time | Venue."
                    )
                }
            )
        return response

    def _parse_schedule(self, payload: ExamScheduleUpload) -> list[ExamReminder]:
        exams: list[ExamReminder] = []
        for line in self._normalize_lines(payload.schedule_text):
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue

            parts = [part.strip() for part in re.split(r"\s*[|,]\s*", cleaned) if part.strip()]
            if len(parts) < 2:
                continue

            subject = parts[0]
            exam_date = self._parse_date(parts[1])
            if not exam_date:
                continue

            time = parts[2] if len(parts) >= 3 else "TBA"
            venue = parts[3] if len(parts) >= 4 else "TBA"
            exams.append(
                ExamReminder(
                    subject=subject,
                    exam_date=exam_date.isoformat(),
                    time=time,
                    venue=venue,
                    confidence="high" if len(parts) >= 4 else "medium",
                    source=payload.source_name,
                    verified_by_user=False,
                )
            )

        return sorted(exams, key=lambda item: item.exam_date)

    def _extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    def _normalize_lines(self, text: str) -> list[str]:
        lines = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line.strip())
            if line:
                lines.append(line)
        return lines

    def _parse_date(self, value: str) -> date | None:
        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d %Y",
            "%B %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
