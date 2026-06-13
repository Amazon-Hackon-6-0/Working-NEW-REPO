from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.schemas.campusflow import AssignmentItem
from app.schemas.integrations import (
    ClassroomSyncResponse,
    GoogleAuthUrlResponse,
    GoogleCallbackResponse,
)
from app.services.assignment_repository import AssignmentRepository


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CLASSROOM_BASE_URL = "https://classroom.googleapis.com/v1"

CLASSROOM_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
]


class GoogleClassroomService:
    def __init__(self, assignment_repository: AssignmentRepository | None = None) -> None:
        self._token: dict[str, Any] | None = None
        self.assignment_repository = assignment_repository or AssignmentRepository()

    @property
    def is_connected(self) -> bool:
        return bool(self._token and self._token.get("access_token"))

    def build_auth_url(self) -> GoogleAuthUrlResponse:
        self._ensure_configured()
        query = urlencode(
            {
                "client_id": settings.google_client_id,
                "redirect_uri": settings.google_redirect_uri,
                "response_type": "code",
                "scope": " ".join(CLASSROOM_SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": "campusflow-local-demo",
            }
        )
        return GoogleAuthUrlResponse(auth_url=f"{GOOGLE_AUTH_URL}?{query}", scopes=CLASSROOM_SCOPES)

    async def handle_callback(self, code: str) -> GoogleCallbackResponse:
        self._ensure_configured()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        response.raise_for_status()
        self._token = response.json()
        return GoogleCallbackResponse(
            connected=True,
            message="Google Classroom connected. You can now sync assignments.",
        )

    async def sync_assignments(self) -> ClassroomSyncResponse:
        if not self.is_connected:
            return ClassroomSyncResponse(
                source="Google Classroom",
                assignments=[],
                courses_scanned=0,
                message="Google Classroom is not connected. Open the auth URL first.",
            )

        courses = await self._get("/courses", params={"studentId": "me", "courseStates": "ACTIVE"})
        assignments: list[AssignmentItem] = []
        scanned = 0

        for course in courses.get("courses", [])[:8]:
            scanned += 1
            course_id = course["id"]
            course_name = course.get("name", "Google Classroom course")
            work_items = await self._get(
                f"/courses/{course_id}/courseWork",
                params={"courseWorkStates": "PUBLISHED", "orderBy": "dueDate desc"},
            )

            for work in work_items.get("courseWork", [])[:10]:
                submissions = await self._get(
                    f"/courses/{course_id}/courseWork/{work['id']}/studentSubmissions",
                    params={"userId": "me"},
                )
                submission_state = "unknown"
                if submissions.get("studentSubmissions"):
                    submission_state = self._map_submission_state(
                        submissions["studentSubmissions"][0].get("state", "UNKNOWN")
                    )

                assignments.append(
                    AssignmentItem(
                        title=work.get("title", "Untitled assignment"),
                        course=course_name,
                        due_at=self._format_due(work),
                        status=submission_state,
                        source="Google Classroom",
                        reminder=self._reminder_text(submission_state),
                    )
                )

        synced_assignments = assignments[:20]
        self.assignment_repository.replace_all(synced_assignments, source="Google Classroom")

        return ClassroomSyncResponse(
            source="Google Classroom",
            assignments=synced_assignments,
            courses_scanned=scanned,
            message=f"Synced {len(synced_assignments)} assignment(s) from Google Classroom.",
        )

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token['access_token']}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{CLASSROOM_BASE_URL}{path}",
                headers=headers,
                params=params or {},
            )
        response.raise_for_status()
        return response.json()

    def _ensure_configured(self) -> None:
        if not settings.google_client_id or not settings.google_client_secret:
            raise RuntimeError("Google Classroom OAuth is not configured.")

    def _format_due(self, work: dict[str, Any]) -> str:
        due = work.get("dueDate")
        time = work.get("dueTime")
        if not due:
            return "No due date"

        due_date = date(due["year"], due["month"], due["day"]).strftime("%b %d, %Y")
        if not time:
            return due_date

        hour = time.get("hours", 23)
        minute = time.get("minutes", 59)
        return f"{due_date}, {hour:02d}:{minute:02d}"

    def _map_submission_state(self, state: str) -> str:
        if state in {"TURNED_IN", "RETURNED"}:
            return "submitted"
        if state == "RECLAIMED_BY_STUDENT":
            return "pending"
        if state == "CREATED":
            return "pending"
        return "unknown"

    def _reminder_text(self, state: str) -> str:
        if state == "submitted":
            return "No action needed"
        if state == "pending":
            return "Evening reminder scheduled"
        return "Ask student to confirm submission"
