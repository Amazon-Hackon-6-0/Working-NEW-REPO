from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AttendanceStatus = Literal["safe", "watch", "danger", "critical"]
ClassStatus = Literal["held", "cancelled", "holiday", "teacher_absent"]
ProcessCaseStatus = Literal["draft", "queued", "sent", "send_failed", "replied", "completed"]
ProcessConfidence = Literal["low", "medium", "high"]
ProcessDeliveryMode = Literal["queue", "email"]
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


class ProcessPolicyUploadResponse(BaseModel):
    document_name: str
    college_id: str
    chunks_count: int
    message: str


class ProcessPolicySummary(BaseModel):
    college_id: str
    document_name: str
    chunks_count: int
    uploaded_at: str


class ProcessPolicyListResponse(BaseModel):
    policies: list[ProcessPolicySummary]


class ProcessCopilotAskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    college_id: str = "default"


class ProcessCopilotAskResponse(BaseModel):
    answer: str
    steps: list[str]
    required_documents: list[str]
    office_or_contact: str | None = None
    deadline_or_timeline: str | None = None
    email_draft: str | None = None
    sources_used: list[str]
    llm_used: bool
    llm_provider: Literal["gemini", "fallback"]
    llm_error: str | None = None
    fallback_mode: bool
    used_college_id: str


class ProcessTask(BaseModel):
    task_id: str
    title: str
    done: bool = False


class ProcessCaseCreateRequest(BaseModel):
    college_id: str = "default"
    student_name: str | None = None
    student_email: str | None = None
    student_issue: str = Field(..., min_length=3)
    course_or_subject: str | None = None
    attached_document_names: list[str] = Field(default_factory=list)


class ProcessCaseSendRequest(BaseModel):
    student_approved: bool = True


class ProcessCaseReplyRequest(BaseModel):
    reply_from: str | None = None
    reply_message: str = Field(..., min_length=2)


class ProcessTaskUpdateRequest(BaseModel):
    done: bool


class ProcessInboundReplyRequest(BaseModel):
    case_id: str | None = None
    subject: str | None = None
    from_email: str | None = None
    reply_message: str = Field(..., min_length=2)


class ProcessTimelineEvent(BaseModel):
    event_id: str
    event_type: str
    title: str
    message: str | None = None
    created_at: str


class ProcessReplyHistoryItem(BaseModel):
    reply_id: str
    reply_from: str | None = None
    from_email: str | None = None
    reply_message: str
    received_at: str


class ProcessCaseResponse(BaseModel):
    case_id: str
    college_id: str
    issue_type: str
    status: ProcessCaseStatus
    routed_to_office: str
    routed_to_email: str | None = None
    delivery_mode: ProcessDeliveryMode
    confidence: ProcessConfidence
    summary: str
    required_documents: list[str]
    deadline_or_timeline: str | None = None
    tasks: list[ProcessTask]
    generated_message_subject: str
    generated_message_body: str
    sent_at: str | None = None
    follow_up_due_at: str | None = None
    reminder_count: int = 0
    office_reply: str | None = None
    reply_history: list[ProcessReplyHistoryItem] = Field(default_factory=list)
    reply_outcome: str | None = None
    student_next_action: str | None = None
    last_student_notification: str | None = None
    notification_channel: Literal["app", "email", "discord_optional"] = "app"
    timeline: list[ProcessTimelineEvent] = Field(default_factory=list)
    sources_used: list[str]
    llm_used: bool
    llm_provider: Literal["gemini", "fallback"]
    fallback_mode: bool
    llm_error: str | None = None
    action_message: str | None = None
    created_at: str
    updated_at: str
