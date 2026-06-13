from typing import Literal

from pydantic import BaseModel, Field


AttendanceStatus = Literal["safe", "watch", "danger", "critical"]
ClassStatus = Literal["held", "cancelled", "holiday", "teacher_absent"]
SubmissionStatus = Literal["submitted", "pending", "late", "missed", "unknown"]


class SubjectAttendance(BaseModel):
    code: str
    name: str
    faculty: str
    held_classes: int
    attended_classes: int
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
