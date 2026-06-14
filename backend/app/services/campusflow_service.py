from __future__ import annotations

from datetime import datetime, timedelta
from math import floor
import re

import httpx

from app.core.config import settings
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
    default_planned_hours = 100.0

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
                "held_classes": 0,
                "attended_classes": 0,
                "missed_classes": 0,
                "class_hours": 1.0,
                "planned_hours": self.default_planned_hours,
                "next_class": "Monday, 9:00 AM",
            },
            {
                "code": "OS",
                "name": "Operating Systems",
                "faculty": "Dr. Iyer",
                "held_classes": 0,
                "attended_classes": 0,
                "missed_classes": 0,
                "class_hours": 1.0,
                "planned_hours": self.default_planned_hours,
                "next_class": "Monday, 11:00 AM",
            },
            {
                "code": "CN",
                "name": "Computer Networks",
                "faculty": "Prof. Rao",
                "held_classes": 0,
                "attended_classes": 0,
                "missed_classes": 0,
                "class_hours": 1.0,
                "planned_hours": self.default_planned_hours,
                "next_class": "Tuesday, 10:00 AM",
            },
            {
                "code": "AI",
                "name": "Artificial Intelligence",
                "faculty": "Dr. Sen",
                "held_classes": 0,
                "attended_classes": 0,
                "missed_classes": 0,
                "class_hours": 1.0,
                "planned_hours": self.default_planned_hours,
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

    def _apply_saved_events(self, subject: dict[str, int | float | str]) -> dict[str, int | float | str]:
        updated = subject.copy()
        held_classes = int(updated["held_classes"])
        attended_classes = int(updated["attended_classes"])
        missed_classes = int(updated.get("missed_classes", 0))
        missed_hours = float(updated.get("missed_hours", 0.0))
        class_hours = float(updated.get("class_hours", 1.0))

        for event in self.attendance_repository.events_for_subject(str(subject["code"])):
            if event["class_status"] == "held":
                held_classes += 1
                if event["attended"]:
                    attended_classes += 1
                else:
                    missed_classes += 1
                    missed_hours += class_hours

        updated["held_classes"] = held_classes
        updated["attended_classes"] = attended_classes
        updated["missed_classes"] = missed_classes
        updated["missed_hours"] = round(missed_hours, 2)
        return updated

    async def answer_question(self, payload: CampusQuestionRequest) -> CampusQuestionResponse:
        local_response = self._answer_question_locally(payload)
        if not settings.gemini_api_key:
            return local_response

        try:
            gemini_answer = await self._ask_gemini(payload.question, local_response)
        except Exception:
            return local_response

        if not gemini_answer:
            return local_response

        return CampusQuestionResponse(
            answer=gemini_answer,
            sources=[*local_response.sources, "Gemini AI"],
            confidence=local_response.confidence,
        )

    def _answer_question_locally(self, payload: CampusQuestionRequest) -> CampusQuestionResponse:
        question = payload.question.lower()
        overview = self.get_overview()
        timetable = self.get_timetable()
        risky = sorted(overview.attendance, key=lambda item: item.attendance_percent)[0]
        pending = [item for item in overview.assignments if item.status in {"pending", "unknown", "late", "missed"}]
        next_exam = overview.exams[0] if overview.exams else None
        next_class = timetable.next_class
        today_classes = timetable.today
        sources = ["Attendance tracker", "Timetable", "Exam reminders", "Assignments"]
        requested_codes = self._requested_subject_codes(question, overview.attendance)

        if ("how many" in question or "how much" in question) and any(
            word in question for word in {"bunk", "bunks", "miss", "skip"}
        ):
            targets = [
                subject for subject in overview.attendance if not requested_codes or subject.code in requested_codes
            ]
            return CampusQuestionResponse(
                answer=(
                    "Safe bunk budget: "
                    + "; ".join(
                        f"{subject.code}: {subject.bunk_budget} class(es) left at {subject.attendance_percent}%"
                        for subject in targets
                    )
                    + ". Cancelled or teacher-absent classes do not consume this budget."
                ),
                sources=["Smart bunk planner", "Attendance tracker"],
                confidence="high",
            )

        bunk_plan = self._bunk_plan_for_question(question, overview.attendance)

        if bunk_plan:
            risky_after = [
                item for item in bunk_plan["subjects"] if item["projected_percent"] - self.threshold <= 10
            ]
            subject_lines = "; ".join(
                f"{item['code']}: miss {item['missed_classes']} class(es), "
                f"{item['projected_percent']}%, {item['projected_bunks']} bunk(s) left"
                for item in bunk_plan["subjects"]
            )
            if risky_after:
                return CampusQuestionResponse(
                    answer=(
                        f"Do not take this leave. Simulating {bunk_plan['label']} gives: "
                        f"{subject_lines}. Since "
                        + ", ".join(item["code"] for item in risky_after)
                        + " would be within 10% of the 75% threshold, it is safer to attend or take a shorter leave."
                    ),
                    sources=["Smart bunk planner", "Timetable", "Attendance tracker"],
                    confidence="high",
                )
            return CampusQuestionResponse(
                answer=(
                    f"This leave looks possible from attendance only. Simulating {bunk_plan['label']} gives: "
                    f"{subject_lines}. Keep exam dates and pending assignments in mind before finalizing."
                ),
                sources=["Smart bunk planner", "Timetable", "Attendance tracker"],
                confidence="high",
            )

        if requested_codes and any(word in question for word in {"bunk", "skip", "leave", "holiday", "vacation", "absent", "miss"}):
            requested_label = ", ".join(sorted(requested_codes))
            return CampusQuestionResponse(
                answer=(
                    f"There is no {requested_label} class tomorrow in the uploaded timetable, "
                    "so skipping tomorrow has no attendance impact for that subject."
                ),
                sources=["Smart bunk planner", "Timetable"],
                confidence="high",
            )

        if any(word in question for word in {"event", "fest", "workshop", "seminar", "participate", "competition"}):
            blockers = []
            positives = []
            if risky.bunk_budget <= 1:
                blockers.append(
                    f"{risky.code} has only {risky.bunk_budget} safe bunk(s) left at {risky.attendance_percent}%."
                )
            else:
                positives.append(
                    f"attendance is comfortable enough in the riskiest subject ({risky.code}: {risky.bunk_budget} bunks left)"
                )

            if pending:
                blockers.append(
                    f"{len(pending)} pending assignment(s) need attention, including {pending[0].title}."
                )
            else:
                positives.append("no pending assignments are currently detected")

            if next_exam:
                blockers.append(
                    f"the next exam is {next_exam.subject} on {next_exam.exam_date} at {next_exam.time}."
                )
            else:
                positives.append("no upcoming exam schedule is uploaded")

            if today_classes:
                positives.append(
                    "today's classes are "
                    + ", ".join(f"{entry.subject_code} {entry.start_time}-{entry.end_time}" for entry in today_classes)
                )

            if blockers:
                return CampusQuestionResponse(
                    answer=(
                        "You can participate only if the event does not clash with classes and you first handle the risky items: "
                        + " ".join(blockers)
                        + " If the event is optional, prefer attending class or finishing pending work before committing."
                    ),
                    sources=sources,
                    confidence="high",
                )

            return CampusQuestionResponse(
                answer=(
                    "Yes, participation looks reasonable from the current academic context: "
                    + "; ".join(positives)
                    + ". Still check the event timing against your timetable before you commit."
                ),
                sources=sources,
                confidence="medium",
            )

        if "attendance" in question or "bunk" in question:
            return CampusQuestionResponse(
                answer=(
                    f"{risky.code} needs attention at {risky.attendance_percent}%. "
                    f"You can miss {risky.bunk_budget} more class(es) before dropping below "
                    f"{self.threshold:.0f}%, or attend {risky.classes_needed} class(es) to recover."
                ),
                sources=["Attendance tracker", "User-confirmed class feedback"],
                confidence="high",
            )

        if "exam" in question or "test" in question:
            if not overview.exams:
                return CampusQuestionResponse(
                    answer="No upcoming exam schedule is uploaded yet. Upload the latest exam PDF to activate exam reminders.",
                    sources=["Exam reminder store"],
                    confidence="high",
                )
            next_exam = overview.exams[0]
            if any(word in question for word in {"study", "prepare", "tips", "topic", "topics", "important", "revise", "revision"}):
                subject_code = self._requested_subject_codes(question, overview.attendance)
                subject_label = next(iter(subject_code), None) or self._subject_code_for_name(next_exam.subject, overview.attendance) or next_exam.subject
                topics = self._study_topics_for_subject(subject_label)
                return CampusQuestionResponse(
                    answer=(
                        f"For {subject_label}, prioritize: {', '.join(topics)}. "
                        f"Your next exam is {next_exam.subject} on {next_exam.exam_date} at {next_exam.time}. "
                        "Revise definitions first, then solve 2-3 previous-year style problems."
                    ),
                    sources=["Exam reminders", "Study topic knowledge base"],
                    confidence="medium",
                )
            return CampusQuestionResponse(
                answer=(
                    f"Your next verified exam is {next_exam.subject} on {next_exam.exam_date} "
                    f"at {next_exam.time} in {next_exam.venue}."
                ),
                sources=[next_exam.source],
                confidence=next_exam.confidence,
            )

        if "class" in question or "timetable" in question or "schedule" in question:
            if not next_class:
                return CampusQuestionResponse(
                    answer="No upcoming class is currently available in the timetable.",
                    sources=["Timetable"],
                    confidence="high",
                )
            room = f" in {next_class.room}" if next_class.room else ""
            return CampusQuestionResponse(
                answer=(
                    f"Your next class is {next_class.subject_code} "
                    f"({next_class.subject_name}) on {next_class.weekday} from "
                    f"{next_class.start_time} to {next_class.end_time}{room}."
                ),
                sources=["Timetable"],
                confidence="high",
            )

        if "assignment" in question or "pending" in question or "work" in question:
            if not pending:
                return CampusQuestionResponse(
                    answer="No pending assignments are detected right now.",
                    sources=["Google Classroom", "Assignment tracker"],
                    confidence="high",
                )
            return CampusQuestionResponse(
                answer=(
                    f"You have {len(pending)} pending assignment(s). Start with {pending[0].title} "
                    f"for {pending[0].course}, due {pending[0].due_at}."
                ),
                sources=["Google Classroom", "Assignment tracker"],
                confidence="high",
            )

        return CampusQuestionResponse(
            answer=(
                f"Current snapshot: {risky.code} is the tightest attendance subject at "
                f"{risky.attendance_percent}% with {risky.bunk_budget} bunk(s) left; "
                f"{len(pending)} assignment(s) need attention; "
                f"next exam is {next_exam.subject if next_exam else 'not uploaded'}; "
                f"next class is {next_class.subject_code if next_class else 'not available'}."
            ),
            sources=sources,
            confidence="medium" if pending else "high",
        )

    async def _ask_gemini(
        self,
        question: str,
        local_response: CampusQuestionResponse,
    ) -> str | None:
        overview = self.get_overview()
        timetable = self.get_timetable()
        context = {
            "attendance": [
                {
                    "code": item.code,
                    "percent": item.attendance_percent,
                    "bunks_left": item.bunk_budget,
                    "held_classes": item.held_classes,
                    "planned_classes": item.planned_classes,
                    "next_class": item.next_class,
                }
                for item in overview.attendance
            ],
            "pending_assignments": [
                {
                    "title": item.title,
                    "course": item.course,
                    "due_at": item.due_at,
                    "status": item.status,
                }
                for item in overview.assignments
                if item.status in {"pending", "unknown", "late", "missed"}
            ],
            "next_exam": overview.exams[0].model_dump() if overview.exams else None,
            "today_classes": [item.model_dump() for item in timetable.today],
            "next_class": timetable.next_class.model_dump() if timetable.next_class else None,
            "smart_bunk_plan": self._bunk_plan_for_question(question, overview.attendance),
            "study_topic_hint": self._study_hint_for_question(question, overview),
            "local_recommendation": local_response.answer,
        }
        use_google_search = self._needs_web_study_context(question)
        prompt = (
            "You are CampusFlow, a concise student academic assistant. "
            "Answer using only the provided JSON context. Do not invent dates, classes, exams, or assignments. "
            "If the student asks whether they can attend an event, decide based on attendance risk, pending work, "
            "upcoming exams, and class schedule. If smart_bunk_plan is present, use its projected_percent and "
            "projected_bunks exactly, and advise against leave when any projected_percent is within 10 points "
            "of the 75% threshold. For study-tip questions, combine the student's exam context with web-backed "
            "standard syllabus topics and list specific topics to revise. Keep the answer under 120 words and make it actionable.\n\n"
            f"Question: {question}\n\nContext JSON:\n{context}"
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 220,
            },
        }
        if use_google_search:
            payload["tools"] = [{"google_search": {}}]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None

    def _needs_web_study_context(self, question: str) -> bool:
        return any(
            word in question
            for word in {"study", "prepare", "tips", "topic", "topics", "important", "revise", "revision", "syllabus"}
        )

    def _study_hint_for_question(
        self,
        question: str,
        overview: CampusFlowOverview,
    ) -> dict | None:
        if not self._needs_web_study_context(question):
            return None
        requested_codes = self._requested_subject_codes(question, overview.attendance)
        next_exam = overview.exams[0] if overview.exams else None
        subject_code = next(iter(requested_codes), None)
        if not subject_code and next_exam:
            subject_code = self._subject_code_for_name(next_exam.subject, overview.attendance)
        if not subject_code:
            return None
        return {
            "subject_code": subject_code,
            "suggested_topics": self._study_topics_for_subject(subject_code),
            "next_exam": next_exam.model_dump() if next_exam else None,
        }

    def _subject_code_for_name(
        self,
        subject_name: str,
        attendance: list[SubjectAttendance],
    ) -> str | None:
        normalized = subject_name.lower()
        for subject in attendance:
            if subject.code.lower() in normalized or subject.name.lower() in normalized:
                return subject.code
        return None

    def _study_topics_for_subject(self, subject_code: str) -> list[str]:
        topics_by_subject = {
            "DBMS": [
                "ER model and relational model",
                "SQL queries and joins",
                "functional dependencies",
                "1NF, 2NF, 3NF, and BCNF normalization",
                "transactions and ACID",
                "indexing and query optimization basics",
            ],
            "OS": [
                "process scheduling",
                "deadlocks",
                "memory management",
                "paging and segmentation",
                "file systems",
                "synchronization primitives",
            ],
            "CN": [
                "OSI and TCP/IP models",
                "subnetting",
                "routing",
                "TCP vs UDP",
                "congestion control",
                "DNS and HTTP basics",
            ],
            "AI": [
                "search algorithms",
                "heuristics",
                "knowledge representation",
                "probability basics",
                "machine learning fundamentals",
                "evaluation metrics",
            ],
        }
        return topics_by_subject.get(subject_code.upper(), ["core definitions", "important derivations", "previous-year questions"])

    def _bunk_plan_for_question(
        self,
        question: str,
        attendance: list[SubjectAttendance],
    ) -> dict | None:
        wants_leave = any(
            word in question
            for word in {"bunk", "skip", "leave", "holiday", "vacation", "absent"}
        )
        if not wants_leave:
            return None

        days = 1
        label = "tomorrow"
        if "week" in question:
            week_match = re.search(r"(\d+)\s*week", question)
            weeks = int(week_match.group(1)) if week_match else 1
            days = max(1, weeks * 7)
            label = f"{weeks} week leave"
        elif "tomorrow" not in question:
            day_match = re.search(r"(\d+)\s*day", question)
            if day_match:
                days = max(1, int(day_match.group(1)))
                label = f"{days} day leave"

        requested_codes = {
            code for code in self._requested_subject_codes(question, attendance)
        }
        attendance_by_code = {subject.code.upper(): subject for subject in attendance}
        now = datetime.now(self.timetable_service.timezone)
        start_date = now.date() + timedelta(days=1)
        entries_by_code: dict[str, list[TimetableEntry]] = {}

        for offset in range(days):
            class_date = start_date + timedelta(days=offset)
            for entry in self.timetable_service.classes_for_date(class_date):
                code = entry.subject_code.upper()
                if requested_codes and code not in requested_codes:
                    continue
                entries_by_code.setdefault(code, []).append(entry)

        if not entries_by_code:
            return None

        subjects = []
        for code, entries in sorted(entries_by_code.items()):
            subject = attendance_by_code.get(code)
            if not subject:
                continue
            extra_missed_hours = sum(self._class_hours(entry) for entry in entries)
            projected_missed_hours = subject.missed_hours + extra_missed_hours
            attended_planned_hours = max(0.0, subject.planned_hours - projected_missed_hours)
            projected_percent = round((attended_planned_hours / subject.planned_hours) * 100, 1)
            projected_bunks = self._bunk_budget_from_hours(
                projected_missed_hours,
                subject.planned_hours,
                subject.class_hours,
            )
            subjects.append(
                {
                    "code": code,
                    "missed_classes": len(entries),
                    "missed_hours": round(extra_missed_hours, 2),
                    "current_percent": subject.attendance_percent,
                    "projected_percent": projected_percent,
                    "current_bunks": subject.bunk_budget,
                    "projected_bunks": projected_bunks,
                    "within_10_percent_of_threshold": projected_percent - self.threshold <= 10,
                }
            )

        if not subjects:
            return None

        return {
            "label": label,
            "days": days,
            "threshold": self.threshold,
            "rule": "Advise not to take holiday when projected_percent - 75 <= 10 for any subject.",
            "subjects": subjects,
        }

    def _requested_subject_codes(
        self,
        question: str,
        attendance: list[SubjectAttendance],
    ) -> set[str]:
        return {
            subject.code
            for subject in attendance
            if re.search(rf"\b{re.escape(subject.code.lower())}\b", question)
        }

    def _attendance_subjects(self) -> list[dict[str, int | float | str]]:
        entries = self.timetable_service.list_effective_entries()
        if not entries:
            return [subject.copy() for subject in self._demo_subjects]

        subjects: dict[str, dict[str, int | float | str]] = {}
        for entry in entries:
            code = entry.subject_code.upper()
            if code not in subjects:
                subjects[code] = {
                    "code": code,
                    "name": entry.subject_name,
                    "faculty": entry.faculty or "TBA",
                    "held_classes": 0,
                    "attended_classes": 0,
                    "missed_classes": 0,
                    "class_hours": self._class_hours(entry),
                    "planned_hours": entry.planned_hours or self.default_planned_hours,
                    "next_class": self._format_next_class(code, entries),
                }
                continue

            if subjects[code]["faculty"] == "TBA" and entry.faculty:
                subjects[code]["faculty"] = entry.faculty
            if subjects[code]["name"] == code and entry.subject_name:
                subjects[code]["name"] = entry.subject_name
            if subjects[code]["planned_hours"] == self.default_planned_hours and entry.planned_hours:
                subjects[code]["planned_hours"] = entry.planned_hours

        return list(subjects.values())

    def _class_hours(self, entry: TimetableEntry) -> float:
        start = self.timetable_service._parse_clock(entry.start_time)
        end = self.timetable_service._parse_clock(entry.end_time)
        if not start or not end:
            return 1.0
        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            return 1.0
        return round((end_minutes - start_minutes) / 60, 2)

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

    def _build_attendance(self, item: dict[str, int | float | str]) -> SubjectAttendance:
        held = int(item["held_classes"])
        attended = int(item["attended_classes"])
        missed_classes = int(item.get("missed_classes", 0))
        class_hours = float(item.get("class_hours", 1.0))
        planned_hours = float(item.get("planned_hours", self.default_planned_hours))
        planned_classes = max(1, floor(planned_hours / class_hours)) if class_hours else 0
        missed_hours = float(item.get("missed_hours", missed_classes * class_hours))
        attended_planned_hours = max(0.0, planned_hours - missed_hours)
        percent = round((attended_planned_hours / planned_hours) * 100, 1) if planned_hours else 100.0
        gap = abs(percent - self.threshold)

        if percent < self.threshold:
            status = "critical"
        elif gap <= 10:
            status = "danger"
        elif percent < 85:
            status = "watch"
        else:
            status = "safe"

        bunk_budget = self._bunk_budget_from_hours(missed_hours, planned_hours, class_hours)
        classes_needed = self._classes_needed_from_hours(missed_hours, planned_hours)

        return SubjectAttendance(
            code=str(item["code"]),
            name=str(item["name"]),
            faculty=str(item["faculty"]),
            held_classes=held,
            attended_classes=attended,
            missed_classes=missed_classes,
            planned_classes=planned_classes,
            class_hours=class_hours,
            planned_hours=planned_hours,
            missed_hours=round(missed_hours, 2),
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

    def _bunk_budget_from_hours(
        self,
        missed_hours: float,
        planned_hours: float,
        class_hours: float,
    ) -> int:
        allowed_missed_hours = planned_hours * (1 - self.threshold / 100)
        remaining_hours = max(0.0, allowed_missed_hours - missed_hours)
        if class_hours <= 0:
            return 0
        return floor(remaining_hours / class_hours)

    def _classes_needed_from_hours(self, missed_hours: float, planned_hours: float) -> int:
        if planned_hours <= 0:
            return 0
        return 0 if ((planned_hours - missed_hours) / planned_hours) * 100 >= self.threshold else 1

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
