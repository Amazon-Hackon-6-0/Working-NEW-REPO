from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AttendanceStatus = Literal["safe", "watch", "danger", "critical"]
ClassStatus = Literal["held", "cancelled", "holiday", "teacher_absent"]
SubmissionStatus = Literal["submitted", "pending", "late", "missed", "unknown"]
Weekday = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class SubjectAttendance(BaseModel):
    code: str
    name: str
    faculty: str
    held_classes: int
    attended_classes: int
    missed_classes: int = 0
    planned_classes: int = 0
    class_hours: float = 1.0
    planned_hours: float = 100.0
    missed_hours: float = 0.0
    threshold: float = 75
    attendance_percent: float
    status: AttendanceStatus
    bunk_budget: int
    classes_needed: int
    next_class: str


class AttendanceFeedback(BaseModel):
    subject_code: str
    class_status: ClassStatus
    attended: bool = False
    note: str | None = None


class AttendanceFeedbackResponse(BaseModel):
    message: str
    subject: SubjectAttendance


class AttendanceEvent(BaseModel):
    event_id: str
    subject_code: str
    class_status: ClassStatus
    attended: bool
    note: str | None = None
    source: str
    actor_id: str | None = None
    created_at: str


class TimetableEntry(BaseModel):
    subject_code: str
    subject_name: str
    faculty: str | None = None
    weekday: Weekday
    start_time: str
    end_time: str
    room: str | None = None
    planned_hours: float | None = None


class TimetableUploadResponse(BaseModel):
    source_name: str
    uploaded_at: str | None = None
    entries: list[TimetableEntry]
    message: str


class TimetableResponse(BaseModel):
    has_uploaded_timetable: bool
    source_name: str
    uploaded_at: str | None = None
    timezone: str = "Asia/Kolkata"
    weekdays_with_classes: list[Weekday]
    classes_per_day: dict[str, int]
    today: list[TimetableEntry]
    today_count: int
    next_class: TimetableEntry | None = None
    next_class_starts_at: str | None = None
    entries: list[TimetableEntry]


class TimetableTodayResponse(BaseModel):
    date: str
    weekday: Weekday
    timezone: str = "Asia/Kolkata"
    class_count: int
    classes: list[TimetableEntry]
    next_class: TimetableEntry | None = None
    next_class_starts_at: str | None = None


class ExamReminder(BaseModel):
    subject: str
    exam_date: str
    time: str
    venue: str
    confidence: Literal["high", "medium", "low"]
    source: str
    verified_by_user: bool


class ExamScheduleUpload(BaseModel):
    source_name: str = "manual_exam_schedule.txt"
    schedule_text: str
    confirm_as_latest: bool = False


class ExamScheduleUploadResponse(BaseModel):
    exams: list[ExamReminder]
    outdated_items: list[str]
    message: str


class AssignmentItem(BaseModel):
    title: str
    course: str
    due_at: str
    status: SubmissionStatus
    source: str
    reminder: str


class CampusUpdate(BaseModel):
    title: str
    summary: str
    priority: Literal["high", "medium", "low"]
    source: str


class DailyBriefing(BaseModel):
    headline: str
    alerts: list[str]
    schedule: list[str]
    suggestions: list[str]


class CampusFlowOverview(BaseModel):
    student_name: str
    semester: str
    threshold: float
    last_verified: str
    attendance: list[SubjectAttendance]
    exams: list[ExamReminder]
    assignments: list[AssignmentItem]
    updates: list[CampusUpdate]
    briefing: DailyBriefing


class CampusQuestionRequest(BaseModel):
    question: str = Field(..., min_length=3)


class CampusQuestionResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: Literal["high", "medium", "low"]
