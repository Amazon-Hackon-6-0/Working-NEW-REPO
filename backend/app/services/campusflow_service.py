from __future__ import annotations

from math import floor
from datetime import datetime, timedelta

from app.schemas.campusflow import (
    AssignmentItem,
    AttendanceFeedback,
    AttendanceFeedbackResponse,
    AttendanceEvent,
    CampusFlowOverview,
    CampusQuestionRequest,
    CampusQuestionResponse,
    CampusUpdate,
    DailyBriefing,
    ExamReminder,
    SubjectAttendance,
    TimetableEntry,
    TimetableResponse,
    TimetableTodayResponse,
)
from app.services.assignment_repository import AssignmentRepository
from app.services.attendance_repository import AttendanceRepository
from app.services.exam_repository import ExamRepository
from app.services.timetable_service import TimetableService


class CampusFlowService:
    """Deterministic MVP logic for the CampusFlow hackathon prototype."""

    threshold = 75.0

    def __init__(
        self,
        attendance_repository: AttendanceRepository | None = None,
        assignment_repository: AssignmentRepository | None = None,
        exam_repository: ExamRepository | None = None,
        timetable_service: TimetableService | None = None,
    ) -> None:
        self.attendance_repository = attendance_repository or AttendanceRepository()
        self.assignment_repository = assignment_repository or AssignmentRepository()
        self.exam_repository = exam_repository or ExamRepository()
        self.timetable_service = timetable_service or TimetableService()
        self._demo_subjects = [
            {
                "code": "DBMS",
                "name": "Database Management Systems",
                "faculty": "Prof. Mehra",
                "held_classes": 26,
                "attended_classes": 20,
                "next_class": "Monday, 9:00 AM",
            },
            {
                "code": "OS",
                "name": "Operating Systems",
                "faculty": "Dr. Iyer",
                "held_classes": 28,
                "attended_classes": 22,
                "next_class": "Monday, 11:00 AM",
            },
            {
                "code": "CN",
                "name": "Computer Networks",
                "faculty": "Prof. Rao",
                "held_classes": 24,
                "attended_classes": 21,
                "next_class": "Tuesday, 10:00 AM",
            },
            {
                "code": "AI",
                "name": "Artificial Intelligence",
                "faculty": "Dr. Sen",
                "held_classes": 18,
                "attended_classes": 16,
                "next_class": "Wednesday, 2:00 PM",
            },
        ]

    def get_overview(self) -> CampusFlowOverview:
        subjects = self._attendance_subjects()
        attendance = [self._build_attendance(self._apply_saved_events(item)) for item in subjects]
        exams = self.exam_repository.list_exams()
        assignments = self.assignment_repository.list_assignments() or [
            AssignmentItem(
                title="OS deadlock case study",
                course="Operating Systems",
                due_at="Today, 11:59 PM",
                status="pending",
                source="Google Classroom",
                reminder="Evening reminder scheduled for 8:00 PM",
            ),
            AssignmentItem(
                title="CN subnetting worksheet",
                course="Computer Networks",
                due_at="Tomorrow, 5:00 PM",
                status="submitted",
                source="Google Classroom",
                reminder="No action needed",
            ),
            AssignmentItem(
                title="DBMS ER diagram revision",
                course="Database Management Systems",
                due_at="Jun 16, 9:00 AM",
                status="unknown",
                source="Manual entry",
                reminder="Ask student to confirm submission",
            ),
        ]
        updates = [
            CampusUpdate(
                title="Placement prep session moved",
                summary="The aptitude workshop is now at 4:30 PM in Seminar Hall 2.",
                priority="high",
                source="Campus notice",
            ),
            CampusUpdate(
                title="Library hours extended",
                summary="Central library will stay open until midnight this week.",
                priority="medium",
                source="Email digest",
            ),
            CampusUpdate(
                title="Mess menu change",
                summary="Dinner menu changed to chole rice and curd.",
                priority="low",
                source="Hostel group",
            ),
        ]

        return CampusFlowOverview(
            student_name="Pranjay",
            semester="Semester 5",
            threshold=self.threshold,
            last_verified="2026-06-13 09:00 IST",
            attendance=attendance,
            exams=exams,
            assignments=assignments,
            updates=updates,
            briefing=self._build_briefing(
                attendance,
                exams,
                assignments,
                self.timetable_service.get_timetable(),
            ),
        )

    def get_timetable(self) -> TimetableResponse:
        return self.timetable_service.get_timetable()

    def get_timetable_today(self) -> TimetableTodayResponse:
        return self.timetable_service.get_today()

    def apply_feedback(
        self,
        payload: AttendanceFeedback,
        source: str = "manual",
        actor_id: str | None = None,
    ) -> AttendanceFeedbackResponse:
        subjects = self._attendance_subjects()
        subject = next(
            item for item in subjects if item["code"].lower() == payload.subject_code.lower()
        )
        self.attendance_repository.add_event(payload, source=source, actor_id=actor_id)
        updated = self._apply_saved_events(subject)

        rebuilt = self._build_attendance(updated)
        if payload.class_status == "held" and payload.attended:
            message = f"{rebuilt.code} attendance updated as attended."
        elif payload.class_status == "held":
            message = f"{rebuilt.code} attendance updated as missed."
        else:
            message = f"{rebuilt.code} was marked as {payload.class_status.replace('_', ' ')} and excluded."

        return AttendanceFeedbackResponse(message=message, subject=rebuilt)

    def list_attendance_events(self) -> list[AttendanceEvent]:
        return [
            AttendanceEvent(**event)
            for event in sorted(
                self.attendance_repository.list_events(),
                key=lambda item: item["created_at"],
                reverse=True,
            )
        ]

    def _apply_saved_events(self, subject: dict[str, int | str]) -> dict[str, int | str]:
        updated = subject.copy()
        held_classes = int(updated["held_classes"])
        attended_classes = int(updated["attended_classes"])

        for event in self.attendance_repository.events_for_subject(str(subject["code"])):
            if event["class_status"] == "held":
                held_classes += 1
                if event["attended"]:
                    attended_classes += 1

        updated["held_classes"] = held_classes
        updated["attended_classes"] = attended_classes
        return updated

    def answer_question(self, payload: CampusQuestionRequest) -> CampusQuestionResponse:
        question = payload.question.lower()
        overview = self.get_overview()

        if "attendance" in question or "bunk" in question:
            risky = sorted(overview.attendance, key=lambda item: item.attendance_percent)[0]
            return CampusQuestionResponse(
                answer=(
                    f"{risky.code} needs attention at {risky.attendance_percent}%. "
                    f"You can miss {risky.bunk_budget} more class(es) before dropping below "
                    f"{self.threshold:.0f}%, or attend {risky.classes_needed} class(es) to recover."
                ),
                sources=["Attendance tracker", "User-confirmed class feedback"],
                confidence="high",
            )

        if "exam" in question:
            if not overview.exams:
                return CampusQuestionResponse(
                    answer="No upcoming exam schedule is uploaded yet. Upload the latest exam PDF to activate exam reminders.",
                    sources=["Exam reminder store"],
                    confidence="high",
                )
            next_exam = overview.exams[0]
            return CampusQuestionResponse(
                answer=(
                    f"Your next verified exam is {next_exam.subject} on {next_exam.exam_date} "
                    f"at {next_exam.time} in {next_exam.venue}."
                ),
                sources=[next_exam.source],
                confidence=next_exam.confidence,
            )

        pending = [item for item in overview.assignments if item.status in {"pending", "unknown"}]
        return CampusQuestionResponse(
            answer=(
                "Today you should finish pending assignments and attend the next scheduled class "
                "that is closest to the 75% attendance threshold."
            ),
            sources=["Google Classroom", "Attendance tracker", "Manual assignment entry"],
            confidence="medium" if pending else "high",
        )

    def _attendance_subjects(self) -> list[dict[str, int | str]]:
        entries = self.timetable_service.repository.list_entries()
        if not entries:
            return [subject.copy() for subject in self._demo_subjects]

        subjects: dict[str, dict[str, int | str]] = {}
        for entry in entries:
            code = entry.subject_code.upper()
            if code not in subjects:
                subjects[code] = {
                    "code": code,
                    "name": entry.subject_name,
                    "faculty": entry.faculty or "TBA",
                    "held_classes": 0,
                    "attended_classes": 0,
                    "next_class": self._format_next_class(code, entries),
                }
                continue

            if subjects[code]["faculty"] == "TBA" and entry.faculty:
                subjects[code]["faculty"] = entry.faculty
            if subjects[code]["name"] == code and entry.subject_name:
                subjects[code]["name"] = entry.subject_name

        return list(subjects.values())

    def _format_next_class(self, subject_code: str, entries: list[TimetableEntry]) -> str:
        now = datetime.now(self.timetable_service.timezone)
        subject_entries = [
            entry for entry in entries if entry.subject_code.upper() == subject_code.upper()
        ]
        for offset in range(8):
            class_date = now.date() + timedelta(days=offset)
            weekday = self.timetable_service.weekdays[class_date.weekday()]
            for entry in self.timetable_service._sort_entries(
                [item for item in subject_entries if item.weekday == weekday]
            ):
                starts_at = self.timetable_service.class_start_datetime(entry, class_date)
                if starts_at >= now:
                    return self._format_class_label(entry)
        if subject_entries:
            return self._format_class_label(self.timetable_service._sort_entries(subject_entries)[0])
        return "No upcoming class"

    def _format_class_label(self, entry: TimetableEntry) -> str:
        room = f" in {entry.room}" if entry.room else ""
        return f"{entry.weekday}, {entry.start_time}-{entry.end_time}{room}"

    def _build_attendance(self, item: dict[str, int | str]) -> SubjectAttendance:
        held = int(item["held_classes"])
        attended = int(item["attended_classes"])
        percent = round((attended / held) * 100, 1) if held else 100.0
        gap = abs(percent - self.threshold)

        if percent < self.threshold:
            status = "critical"
        elif gap <= 10:
            status = "danger"
        elif percent < 85:
            status = "watch"
        else:
            status = "safe"

        bunk_budget = self._bunk_budget(attended, held)
        classes_needed = self._classes_needed(attended, held)

        return SubjectAttendance(
            code=str(item["code"]),
            name=str(item["name"]),
            faculty=str(item["faculty"]),
            held_classes=held,
            attended_classes=attended,
            threshold=self.threshold,
            attendance_percent=percent,
            status=status,
            bunk_budget=bunk_budget,
            classes_needed=classes_needed,
            next_class=str(item["next_class"]),
        )

    def _bunk_budget(self, attended: int, held: int) -> int:
        max_total = floor(attended / (self.threshold / 100))
        return max(0, max_total - held)

    def _classes_needed(self, attended: int, held: int) -> int:
        needed = 0
        while held + needed and ((attended + needed) / (held + needed)) * 100 < self.threshold:
            needed += 1
        return needed

    def _build_briefing(
        self,
        attendance: list[SubjectAttendance],
        exams: list[ExamReminder],
        assignments: list[AssignmentItem],
        timetable: TimetableResponse,
    ) -> DailyBriefing:
        risky_subjects = [
            subject for subject in attendance if subject.status in {"danger", "critical"}
        ]
        pending_assignments = [
            assignment for assignment in assignments if assignment.status in {"pending", "unknown"}
        ]

        alerts = [
            f"{subject.code} is at {subject.attendance_percent}% with {subject.bunk_budget} bunk(s) left."
            for subject in risky_subjects
        ]
        alerts.extend(
            f"{assignment.title} is {assignment.status}; {assignment.reminder.lower()}."
            for assignment in pending_assignments
        )

        schedule = [
            f"{entry.subject_code} at {entry.start_time}"
            for entry in timetable.today
        ] or ["No classes scheduled for today"]
        if exams:
            schedule.append(f"Next exam: {exams[0].subject} on {exams[0].exam_date}")
        else:
            schedule.append("No upcoming exam schedule uploaded")

        riskiest = sorted(attendance, key=lambda item: item.attendance_percent)[0]
        suggestions = [
            f"Attend {riskiest.code} next because it is closest to the attendance threshold.",
            "Finish the OS case study before dinner to avoid a late-night crunch.",
        ]
        if exams and not all(exam.verified_by_user for exam in exams):
            suggestions.append("Confirm the uploaded exam schedule source before relying on reminders.")
        elif not exams:
            suggestions.append("Upload the latest exam PDF to activate exam reminders.")

        return DailyBriefing(
            headline="Tonight's CampusFlow briefing is ready for Discord.",
            alerts=alerts,
            schedule=schedule,
            suggestions=suggestions,
        )
