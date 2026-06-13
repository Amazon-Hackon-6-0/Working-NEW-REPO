from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from app.schemas.campusflow import (
    TimetableEntry,
    TimetableResponse,
    TimetableTodayResponse,
    TimetableUploadResponse,
)
from app.services.timetable_repository import TimetableRepository


class TimetableService:
    """Extracts and summarizes semester timetable uploads."""

    timezone_name = "Asia/Kolkata"
    timezone = ZoneInfo(timezone_name)
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    weekday_aliases = {
        "m": "Monday",
        "mon": "Monday",
        "monday": "Monday",
        "t": "Tuesday",
        "tue": "Tuesday",
        "tues": "Tuesday",
        "tuesday": "Tuesday",
        "w": "Wednesday",
        "wed": "Wednesday",
        "wednesday": "Wednesday",
        "th": "Thursday",
        "r": "Thursday",
        "thu": "Thursday",
        "thur": "Thursday",
        "thurs": "Thursday",
        "thursday": "Thursday",
        "f": "Friday",
        "fri": "Friday",
        "friday": "Friday",
        "sa": "Saturday",
        "sat": "Saturday",
        "saturday": "Saturday",
        "su": "Sunday",
        "sun": "Sunday",
        "sunday": "Sunday",
    }
    free_slot_words = {"break", "free", "holiday", "lunch", "recess", "library"}

    def __init__(self, repository: TimetableRepository | None = None) -> None:
        self.repository = repository or TimetableRepository()

    def upload_pdf_timetable(self, filename: str, content: bytes) -> TimetableUploadResponse:
        text = self._extract_pdf_text(content)
        if not text.strip():
            return TimetableUploadResponse(
                source_name=filename,
                uploaded_at=None,
                entries=[],
                message=(
                    "Could not extract readable text from this PDF. Try uploading a text-based "
                    "semester timetable PDF."
                ),
            )

        entries = self._parse_timetable_text(text)
        if not entries:
            return TimetableUploadResponse(
                source_name=filename,
                uploaded_at=None,
                entries=[],
                message=(
                    "PDF text was extracted, but no timetable rows matched. Use rows with a "
                    "weekday, time range, subject code, and subject name where possible."
                ),
            )

        entries = self._class_entries(entries)
        payload = self.repository.replace_all(entries, filename)
        return TimetableUploadResponse(
            source_name=filename,
            uploaded_at=payload.get("uploaded_at"),
            entries=entries,
            message=f"Saved {len(entries)} timetable class slot(s) from {filename}.",
        )

    def get_timetable(self) -> TimetableResponse:
        payload = self.repository.read_payload()
        uploaded_entries = self._class_entries(self.repository.list_entries())
        has_uploaded_timetable = bool(uploaded_entries)
        entries = uploaded_entries or self.demo_entries()
        return self._build_response(
            entries=entries,
            has_uploaded_timetable=has_uploaded_timetable,
            source_name=payload.get("source_name") or "demo_fallback",
            uploaded_at=payload.get("uploaded_at"),
        )

    def get_today(self) -> TimetableTodayResponse:
        timetable = self.get_timetable()
        now = datetime.now(self.timezone)
        return TimetableTodayResponse(
            date=now.date().isoformat(),
            weekday=self.weekdays[now.weekday()],
            class_count=timetable.today_count,
            classes=timetable.today,
            next_class=timetable.next_class,
            next_class_starts_at=timetable.next_class_starts_at,
        )

    def list_effective_entries(self) -> list[TimetableEntry]:
        return self._class_entries(self.repository.list_entries()) or self.demo_entries()

    def classes_for_date(self, class_date: date) -> list[TimetableEntry]:
        weekday = self.weekdays[class_date.weekday()]
        return self._sort_entries(
            [entry for entry in self.list_effective_entries() if entry.weekday == weekday]
        )

    def class_end_datetime(self, entry: TimetableEntry, class_date: date) -> datetime:
        return datetime.combine(
            class_date,
            self._parse_clock(entry.end_time) or time(23, 59),
            tzinfo=self.timezone,
        )

    def class_start_datetime(self, entry: TimetableEntry, class_date: date) -> datetime:
        return datetime.combine(
            class_date,
            self._parse_clock(entry.start_time) or time(0, 0),
            tzinfo=self.timezone,
        )

    def demo_entries(self) -> list[TimetableEntry]:
        return [
            TimetableEntry(
                subject_code="DBMS",
                subject_name="Database Management Systems",
                faculty="Prof. Mehra",
                weekday="Monday",
                start_time="09:00",
                end_time="10:00",
                room=None,
            ),
            TimetableEntry(
                subject_code="OS",
                subject_name="Operating Systems",
                faculty="Dr. Iyer",
                weekday="Monday",
                start_time="11:00",
                end_time="12:00",
                room=None,
            ),
            TimetableEntry(
                subject_code="CN",
                subject_name="Computer Networks",
                faculty="Prof. Rao",
                weekday="Tuesday",
                start_time="10:00",
                end_time="11:00",
                room=None,
            ),
            TimetableEntry(
                subject_code="AI",
                subject_name="Artificial Intelligence",
                faculty="Dr. Sen",
                weekday="Wednesday",
                start_time="14:00",
                end_time="15:00",
                room=None,
            ),
        ]

    def _build_response(
        self,
        entries: list[TimetableEntry],
        has_uploaded_timetable: bool,
        source_name: str,
        uploaded_at: str | None,
    ) -> TimetableResponse:
        sorted_entries = self._sort_entries(entries)
        classes_per_day_counter = Counter(entry.weekday for entry in sorted_entries)
        classes_per_day = {
            weekday: classes_per_day_counter[weekday]
            for weekday in self.weekdays
            if classes_per_day_counter[weekday]
        }
        weekdays_with_classes = list(classes_per_day.keys())

        now = datetime.now(self.timezone)
        today_weekday = self.weekdays[now.weekday()]
        today = [entry for entry in sorted_entries if entry.weekday == today_weekday]
        next_class, next_class_starts_at = self._next_class(sorted_entries, now)

        return TimetableResponse(
            has_uploaded_timetable=has_uploaded_timetable,
            source_name=source_name,
            uploaded_at=uploaded_at,
            weekdays_with_classes=weekdays_with_classes,
            classes_per_day=classes_per_day,
            today=today,
            today_count=len(today),
            next_class=next_class,
            next_class_starts_at=next_class_starts_at.isoformat()
            if next_class_starts_at
            else None,
            entries=sorted_entries,
        )

    def _next_class(
        self,
        entries: list[TimetableEntry],
        now: datetime,
    ) -> tuple[TimetableEntry | None, datetime | None]:
        for offset in range(8):
            class_date = now.date() + timedelta(days=offset)
            weekday = self.weekdays[class_date.weekday()]
            candidates = [entry for entry in entries if entry.weekday == weekday]
            for entry in self._sort_entries(candidates):
                starts_at = self.class_start_datetime(entry, class_date)
                if starts_at >= now:
                    return entry, starts_at
        return None, None

    def _extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    def _parse_timetable_text(self, text: str) -> list[TimetableEntry]:
        entries: list[TimetableEntry] = []
        current_weekday: str | None = None
        header_weekdays: list[str] = []
        planned_hours_by_subject = self._planned_hours_by_subject(text)

        for line in self._normalize_lines(text):
            weekdays_in_line = self._weekdays_in(line)
            time_range = self._find_time_range(line)

            if len(weekdays_in_line) >= 2 and not time_range:
                header_weekdays = weekdays_in_line
                continue

            if len(weekdays_in_line) == 1 and self._line_is_only_day(line):
                current_weekday = weekdays_in_line[0]
                continue

            if not time_range:
                if weekdays_in_line:
                    current_weekday = weekdays_in_line[0]
                continue

            weekday = weekdays_in_line[0] if weekdays_in_line else current_weekday
            if weekday:
                entry = self._entry_from_text(line, weekday, time_range)
                if entry:
                    entries.append(entry)
                continue

            if header_weekdays:
                entries.extend(self._entries_from_header_row(line, header_weekdays, time_range))

        entries = self._dedupe_entries(entries)
        for entry in entries:
            planned_hours = planned_hours_by_subject.get(entry.subject_code.upper())
            if planned_hours:
                entry.planned_hours = planned_hours
        return entries

    def _entries_from_header_row(
        self,
        line: str,
        header_weekdays: list[str],
        time_range: dict,
    ) -> list[TimetableEntry]:
        remaining = line.replace(time_range["text"], " ")
        chunks = [chunk.strip() for chunk in re.split(r"\s{2,}|\s*[|]\s*", remaining) if chunk.strip()]
        entries = []
        for index, chunk in enumerate(chunks[: len(header_weekdays)]):
            if self._is_free_slot(chunk):
                continue
            entry = self._entry_from_text(
                f"{header_weekdays[index]} {time_range['text']} {chunk}",
                header_weekdays[index],
                time_range,
            )
            if entry:
                entries.append(entry)
        return entries

    def _entry_from_text(
        self,
        line: str,
        weekday: str,
        time_range: dict,
    ) -> TimetableEntry | None:
        subject_text = self._subject_text(line, weekday, time_range["text"])
        if self._is_free_slot(subject_text):
            return None

        faculty = self._extract_faculty(subject_text)
        room = self._extract_room(subject_text)
        subject_code = self._extract_subject_code(subject_text)
        subject_name = self._extract_subject_name(subject_text, subject_code, faculty, room)

        if not subject_name:
            return None
        if not subject_code:
            subject_code = self._derive_subject_code(subject_name)

        return TimetableEntry(
            subject_code=subject_code.upper(),
            subject_name=subject_name,
            faculty=faculty,
            weekday=weekday,
            start_time=time_range["start"],
            end_time=time_range["end"],
            room=room,
        )

    def _planned_hours_by_subject(self, text: str) -> dict[str, float]:
        totals: dict[str, float] = {}
        patterns = [
            re.compile(
                r"\b(?P<code>[A-Z]{2,6}(?:\s*-?\s*\d{2,4}[A-Z]?)?)\b[^\n]{0,80}?"
                r"(?:total\s*(?:semester\s*)?hours?|planned\s*hours?|credits?\s*hours?)"
                r"\s*[:=-]?\s*(?P<hours>\d{1,3}(?:\.\d+)?)",
                re.I,
            ),
            re.compile(
                r"(?:total\s*(?:semester\s*)?hours?|planned\s*hours?|credits?\s*hours?)"
                r"\s*[:=-]?\s*(?P<hours>\d{1,3}(?:\.\d+)?)[^\n]{0,80}?"
                r"\b(?P<code>[A-Z]{2,6}(?:\s*-?\s*\d{2,4}[A-Z]?)?)\b",
                re.I,
            ),
        ]

        for line in self._normalize_lines(text):
            for pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                hours = float(match.group("hours"))
                if hours <= 0:
                    continue
                code = re.sub(r"\s+", "", match.group("code")).replace("-", "").upper()
                totals[code] = hours
        return totals

    def _subject_text(self, line: str, weekday: str, time_text: str) -> str:
        cleaned = line.replace(time_text, " ")
        cleaned = re.sub(rf"\b{weekday}\b", " ", cleaned, flags=re.IGNORECASE)
        for alias, canonical in self.weekday_aliases.items():
            if canonical == weekday:
                cleaned = re.sub(rf"\b{alias}\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(period|lecture|tutorial|practical|slot)\b", " ", cleaned, flags=re.I)
        cleaned = cleaned.replace("\t", " | ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" |-:,")

    def _extract_subject_code(self, text: str) -> str | None:
        code = re.search(r"\b[A-Z]{2,5}\s*-?\s*\d{2,4}[A-Z]?\b", text)
        if code:
            return re.sub(r"\s+", "", code.group(0)).replace("-", "").upper()

        ignored = {
            "AM",
            "PM",
            "LAB",
            "ROOM",
            "HALL",
            "BLOCK",
            "PROF",
            "DR",
            "MR",
            "MRS",
            "MS",
        }
        for match in re.finditer(r"\b[A-Z]{2,6}\b", text):
            value = match.group(0)
            if value not in ignored and value.lower() not in self.weekday_aliases:
                return value
        return None

    def _extract_subject_name(
        self,
        text: str,
        subject_code: str | None,
        faculty: str | None,
        room: str | None,
    ) -> str:
        cleaned = text
        for value in [faculty, room]:
            if value:
                cleaned = cleaned.replace(value, " ")
        cleaned = re.sub(
            r"\b(Faculty|Fac|Teacher|Instructor|Room|Venue|Location)\s*[:\-]\s*",
            " ",
            cleaned,
            flags=re.I,
        )
        if subject_code:
            flexible_code = r"\s*-?\s*".join(re.escape(part) for part in re.findall(r"[A-Z]+|\d+", subject_code))
            cleaned = re.sub(rf"\b{flexible_code}\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*[|,;/]\s*", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:,")
        cleaned = re.sub(r"\s+\d{1,4}$", "", cleaned).strip(" -:,")

        if not cleaned and subject_code:
            return subject_code.upper()
        return cleaned[:120]

    def _class_entries(self, entries: list[TimetableEntry]) -> list[TimetableEntry]:
        return [
            self._clean_entry_for_display(entry)
            for entry in entries
            if not self._is_lab_entry(entry)
        ]

    def _is_lab_entry(self, entry: TimetableEntry) -> bool:
        subject_words = {word.lower() for word in re.findall(r"[A-Za-z]+", entry.subject_name)}
        return bool(subject_words & {"lab", "labs", "practical", "practicals"})

    def _clean_entry_for_display(self, entry: TimetableEntry) -> TimetableEntry:
        subject_name = re.sub(r"\s+\d{1,4}$", "", entry.subject_name).strip(" -:,")
        return entry.model_copy(update={"subject_name": subject_name or entry.subject_name})

    def _extract_faculty(self, text: str) -> str | None:
        labeled = re.search(
            r"\b(?:Faculty|Fac\.?|Teacher|Instructor)\s*[:\-]\s*([^|,;/]+)",
            text,
            flags=re.I,
        )
        if labeled:
            return labeled.group(1).strip(" -:")

        titled = re.search(
            r"\b(?:Prof|Dr|Mr|Mrs|Ms)\.?\s+[A-Z][A-Za-z. ]{1,40}",
            text,
        )
        if titled:
            return titled.group(0).strip()
        return None

    def _extract_room(self, text: str) -> str | None:
        labeled = re.search(
            r"\b(?:Room|Venue|Location)\s*[:\-]\s*([^|,;/]+)",
            text,
            flags=re.I,
        )
        if labeled:
            return labeled.group(1).strip(" -:")

        room = re.search(r"\b(?:Room|Lab|Hall|Block)\s*[-:]?\s*[A-Z0-9 -]{1,20}\b", text, flags=re.I)
        if room:
            return room.group(0).strip()
        return None

    def _derive_subject_code(self, subject_name: str) -> str:
        words = re.findall(r"[A-Za-z]+", subject_name)
        if not words:
            return "SUBJECT"
        initials = "".join(word[0] for word in words[:4]).upper()
        return initials or words[0][:6].upper()

    def _find_time_range(self, line: str) -> dict | None:
        normalized = line.replace("–", "-").replace("—", "-")
        time_token = r"\d{1,2}(?:(?:[:.])\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)?"
        pattern = re.compile(rf"({time_token})\s*(?:-|to)\s*({time_token})", re.I)
        for match in pattern.finditer(normalized):
            start_token = match.group(1).strip()
            end_token = match.group(2).strip()
            end_meridiem = self._meridiem(end_token)
            start_meridiem = self._meridiem(start_token) or end_meridiem
            start = self._parse_time_token(start_token, start_meridiem)
            end = self._parse_time_token(end_token, end_meridiem or start_meridiem)
            if start and end:
                return {
                    "text": match.group(0),
                    "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M"),
                }
        return None

    def _parse_time_token(self, value: str, fallback_meridiem: str | None = None) -> time | None:
        cleaned = value.upper().replace(".", "").replace(" ", "")
        meridiem = self._meridiem(cleaned) or fallback_meridiem
        cleaned = re.sub(r"(AM|PM)$", "", cleaned)

        if ":" in cleaned:
            hour_text, minute_text = cleaned.split(":", 1)
        elif len(cleaned) == 4 and cleaned.isdigit():
            hour_text, minute_text = cleaned[:2], cleaned[2:]
        else:
            hour_text, minute_text = cleaned, "0"

        if not hour_text.isdigit() or not minute_text.isdigit():
            return None

        hour = int(hour_text)
        minute = int(minute_text)
        if meridiem == "PM" and hour != 12:
            hour += 12
        if meridiem == "AM" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return time(hour, minute)

    def _meridiem(self, value: str) -> str | None:
        cleaned = value.upper().replace(".", "")
        if "AM" in cleaned:
            return "AM"
        if "PM" in cleaned:
            return "PM"
        return None

    def _parse_clock(self, value: str) -> time | None:
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return None

    def _weekdays_in(self, line: str) -> list[str]:
        found = []
        for alias, weekday in self.weekday_aliases.items():
            if re.search(rf"\b{alias}\b", line, flags=re.I) and weekday not in found:
                found.append(weekday)
        return sorted(found, key=self.weekdays.index)

    def _line_is_only_day(self, line: str) -> bool:
        cleaned = re.sub(r"[^A-Za-z]", "", line).lower()
        return cleaned in self.weekday_aliases

    def _normalize_lines(self, text: str) -> list[str]:
        lines = []
        for raw_line in text.splitlines():
            line = raw_line.replace("\u00a0", " ").strip()
            line = re.sub(r"[ ]{3,}", "  ", line)
            line = re.sub(r"\s+", " ", line) if "|" in line else line
            if line:
                lines.append(line)
        return lines

    def _is_free_slot(self, value: str) -> bool:
        words = {word.lower() for word in re.findall(r"[A-Za-z]+", value)}
        return bool(words & self.free_slot_words)

    def _dedupe_entries(self, entries: list[TimetableEntry]) -> list[TimetableEntry]:
        deduped = {}
        for entry in entries:
            key = (
                entry.weekday,
                entry.start_time,
                entry.end_time,
                entry.subject_code.upper(),
                entry.room or "",
            )
            deduped[key] = entry
        return self._sort_entries(list(deduped.values()))

    def _sort_entries(self, entries: list[TimetableEntry]) -> list[TimetableEntry]:
        return sorted(
            entries,
            key=lambda entry: (
                self.weekdays.index(entry.weekday),
                entry.start_time,
                entry.subject_code,
            ),
        )
