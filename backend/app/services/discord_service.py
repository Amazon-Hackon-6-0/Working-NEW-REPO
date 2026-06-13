from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
from fastapi import HTTPException, Request

from app.core.config import settings
from app.schemas.campusflow import AttendanceFeedback, SubjectAttendance, TimetableEntry
from app.schemas.integrations import DiscordPromptResponse, DiscordScheduledPromptResponse
from app.services.campusflow_service import CampusFlowService


class DiscordService:
    def __init__(self, campusflow_service: CampusFlowService) -> None:
        self.campusflow_service = campusflow_service
        self.notification_log_path = (
            Path(__file__).resolve().parents[1] / "data" / "discord_notification_log.json"
        )
        self.notification_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._notification_log_lock = Lock()

    @property
    def is_configured(self) -> bool:
        return bool(settings.discord_webhook_url or self.bot_configured)

    @property
    def bot_configured(self) -> bool:
        return bool(settings.discord_bot_token and settings.discord_channel_id)

    @property
    def interactions_configured(self) -> bool:
        return bool(settings.discord_public_key)

    async def send_daily_feedback_prompt(
        self,
        subject_code: str | None = None,
    ) -> DiscordPromptResponse:
        overview = self.campusflow_service.get_overview()
        subject = next(
            (item for item in overview.attendance if item.code == (subject_code or "DBMS")),
            overview.attendance[0],
        )

        if self.bot_configured:
            return await self._send_bot_button_prompt(subject)

        if not settings.discord_webhook_url:
            raise RuntimeError(
                "Configure DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID for native buttons, "
                "or DISCORD_WEBHOOK_URL for link-based fallback."
            )

        return await self._send_webhook_link_prompt(subject)

    async def send_scheduled_class_prompts(
        self,
        include_future_today: bool = False,
    ) -> DiscordScheduledPromptResponse:
        timetable_service = self.campusflow_service.timetable_service
        now = datetime.now(timetable_service.timezone)
        class_date = now.date()
        today_classes = timetable_service.classes_for_date(class_date)
        messages: list[str] = []

        if not self.is_configured:
            return DiscordScheduledPromptResponse(
                sent=0,
                skipped=0,
                attempted=0,
                date=class_date.isoformat(),
                messages=[
                    "Discord is not configured. Add DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID or DISCORD_WEBHOOK_URL."
                ],
            )

        due_classes = [
            class_entry
            for class_entry in today_classes
            if include_future_today
            or timetable_service.class_end_datetime(class_entry, class_date) <= now
        ]
        attempted = len(due_classes)

        if not due_classes:
            messages.append("No classes found for today's timetable.")
            return DiscordScheduledPromptResponse(
                sent=0,
                skipped=0,
                attempted=0,
                date=class_date.isoformat(),
                messages=messages,
            )

        try:
            if self.bot_configured:
                response = await self._send_bot_today_prompt(due_classes, class_date)
            else:
                response = await self._send_webhook_today_prompt(due_classes, class_date)
        except Exception as exc:
            messages.append(f"Failed to send today's class prompt: {exc}")
            return DiscordScheduledPromptResponse(
                sent=0,
                skipped=0,
                attempted=attempted,
                date=class_date.isoformat(),
                messages=messages,
            )

        self._record_daily_notification(due_classes, class_date, response.message)
        messages.append(response.message)

        return DiscordScheduledPromptResponse(
            sent=1,
            skipped=0,
            attempted=attempted,
            date=class_date.isoformat(),
            messages=messages,
        )

    async def handle_interaction(self, request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        self._verify_signature(request, raw_body)
        payload = json.loads(raw_body.decode("utf-8"))

        if payload.get("type") == 1:
            return {"type": 1}

        custom_id = payload.get("data", {}).get("custom_id", "")
        if custom_id.startswith("attendance:"):
            actor_id = payload.get("member", {}).get("user", {}).get("id") or payload.get("user", {}).get("id")
            result = self._apply_attendance_interaction(custom_id, actor_id)
            return {
                "type": 4,
                "data": {
                    "content": result,
                    "flags": 64,
                    "allowed_mentions": {"parse": []},
                },
            }

        return {
            "type": 4,
            "data": {
                "content": "CampusFlow received the interaction, but it did not match a feedback action.",
                "flags": 64,
            },
        }

    async def _send_bot_button_prompt(
        self,
        subject: SubjectAttendance,
        class_entry: TimetableEntry | None = None,
    ) -> DiscordPromptResponse:
        feedback_url = f"{settings.public_base_url}/api/v1/integrations/discord/interactions"
        class_label = self._class_label(subject, class_entry)
        payload = {
            "allowed_mentions": {"parse": []},
            "content": (
                f"Class feedback needed for **{subject.code}** "
                f"({class_label}). Was this class actually held?"
            ),
            "embeds": [
                {
                    "title": "CampusFlow attendance check",
                    "description": (
                        f"{subject.name} is at **{subject.attendance_percent}%**. "
                        f"Bunk budget: **{subject.bunk_budget}**."
                    ),
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "Human-in-the-loop rule",
                            "value": "Cancelled, holiday, and teacher-absent classes are excluded from attendance count.",
                        }
                    ],
                }
            ],
            "components": [
                {
                    "type": 1,
                    "components": [
                        self._button(f"attendance:{subject.code}:held:attended", "Held + attended", 3),
                        self._button(f"attendance:{subject.code}:held:missed", "Held + missed", 4),
                        self._button(f"attendance:{subject.code}:cancelled:false", "Cancelled", 2),
                        self._button(f"attendance:{subject.code}:teacher_absent:false", "Teacher absent", 2),
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{settings.discord_channel_id}/messages",
                headers={
                    "Authorization": f"Bot {settings.discord_bot_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        return DiscordPromptResponse(
            sent=True,
            message=f"Discord button prompt sent for {subject.code} ({class_label}).",
            feedback_url=feedback_url,
        )

    async def _send_webhook_link_prompt(
        self,
        subject: SubjectAttendance,
        class_entry: TimetableEntry | None = None,
    ) -> DiscordPromptResponse:
        feedback_base_url = f"{settings.public_base_url}/api/v1/integrations/discord/feedback-link"
        attended_url = (
            f"{feedback_base_url}?subject_code={subject.code}&class_status=held&attended=true"
        )
        missed_url = (
            f"{feedback_base_url}?subject_code={subject.code}&class_status=held&attended=false"
        )
        cancelled_url = (
            f"{feedback_base_url}?subject_code={subject.code}&class_status=cancelled&attended=false"
        )
        teacher_absent_url = (
            f"{feedback_base_url}?subject_code={subject.code}&class_status=teacher_absent&attended=false"
        )
        class_label = self._class_label(subject, class_entry)

        payload = {
            "username": "CampusFlow",
            "allowed_mentions": {"parse": []},
            "content": (
                f"Class feedback needed for **{subject.code}** "
                f"({class_label}). Was this class actually held?\n\n"
                f"[Held + attended]({attended_url}) · "
                f"[Held + missed]({missed_url}) · "
                f"[Cancelled]({cancelled_url}) · "
                f"[Teacher absent]({teacher_absent_url})"
            ),
            "embeds": [
                {
                    "title": "Attendance check",
                    "description": (
                        f"{subject.name} is at **{subject.attendance_percent}%**. "
                        f"Bunk budget: **{subject.bunk_budget}**."
                    ),
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "Why this matters",
                            "value": "Cancelled, holiday, and teacher-absent classes are excluded from the denominator.",
                        }
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.discord_webhook_url}?wait=true",
                json=payload,
            )
        response.raise_for_status()

        return DiscordPromptResponse(
            sent=True,
            message=f"Discord feedback prompt sent for {subject.code} ({class_label}).",
            feedback_url=feedback_base_url,
        )

    async def _send_bot_today_prompt(
        self,
        classes: list[TimetableEntry],
        class_date: date,
    ) -> DiscordPromptResponse:
        feedback_url = f"{settings.public_base_url}/api/v1/integrations/discord/interactions"
        overview_by_code = {
            subject.code.upper(): subject for subject in self.campusflow_service.get_overview().attendance
        }
        weekday = self.campusflow_service.timetable_service.weekdays[class_date.weekday()]
        lines = [
            f"**{index}. {entry.subject_code}** · {entry.start_time}-{entry.end_time}"
            f"{f' · {entry.room}' if entry.room else ''}"
            for index, entry in enumerate(classes, start=1)
        ]
        components = []
        for entry in classes[:5]:
            code = entry.subject_code.upper()
            slot = self._class_slot_token(class_date, entry)
            components.append(
                {
                    "type": 1,
                    "components": [
                        self._button(f"attendance:{code}:held:attended:{slot}", f"{code} attended", 3),
                        self._button(f"attendance:{code}:held:missed:{slot}", f"{code} missed", 4),
                        self._button(f"attendance:{code}:cancelled:false:{slot}", f"{code} cancelled", 2),
                        self._button(f"attendance:{code}:teacher_absent:false:{slot}", f"{code} absent", 2),
                    ],
                }
            )

        payload = {
            "allowed_mentions": {"parse": []},
            "content": (
                f"**CampusFlow daily class check** for **{weekday}, {class_date.isoformat()}**\n"
                "Use these once you know the reality of today's classes, even before class time."
            ),
            "embeds": [
                {
                    "title": "Today's classes",
                    "description": "\n".join(lines),
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "Attendance rule",
                            "value": "Cancelled and teacher-absent classes do not change attendance. Missed classes subtract their class duration from the 100-hour plan.",
                        },
                        {
                            "name": "Current attendance",
                            "value": "\n".join(
                                f"{entry.subject_code}: "
                                f"{overview_by_code.get(entry.subject_code.upper()).attendance_percent if overview_by_code.get(entry.subject_code.upper()) else 100}%"
                                for entry in classes
                            ),
                        },
                    ],
                }
            ],
            "components": components,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{settings.discord_channel_id}/messages",
                headers={
                    "Authorization": f"Bot {settings.discord_bot_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        return DiscordPromptResponse(
            sent=True,
            message=f"Discord daily prompt sent with {len(classes)} class(es).",
            feedback_url=feedback_url,
        )

    async def _send_webhook_today_prompt(
        self,
        classes: list[TimetableEntry],
        class_date: date,
    ) -> DiscordPromptResponse:
        feedback_base_url = f"{settings.public_base_url}/api/v1/integrations/discord/feedback-link"
        weekday = self.campusflow_service.timetable_service.weekdays[class_date.weekday()]
        class_blocks = []
        for entry in classes:
            code = entry.subject_code.upper()
            label = self._class_label_for_entry(entry)
            attended_url = f"{feedback_base_url}?subject_code={code}&class_status=held&attended=true"
            missed_url = f"{feedback_base_url}?subject_code={code}&class_status=held&attended=false"
            cancelled_url = f"{feedback_base_url}?subject_code={code}&class_status=cancelled&attended=false"
            teacher_absent_url = f"{feedback_base_url}?subject_code={code}&class_status=teacher_absent&attended=false"
            class_blocks.append(
                f"**{code}** · {label}\n"
                f"[Attended]({attended_url}) · [Missed]({missed_url}) · "
                f"[Cancelled]({cancelled_url}) · [Teacher absent]({teacher_absent_url})"
            )

        payload = {
            "username": "CampusFlow",
            "allowed_mentions": {"parse": []},
            "content": (
                f"**CampusFlow daily class check** for **{weekday}, {class_date.isoformat()}**\n\n"
                + "\n\n".join(class_blocks)
            ),
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{settings.discord_webhook_url}?wait=true", json=payload)
        response.raise_for_status()
        return DiscordPromptResponse(
            sent=True,
            message=f"Discord daily link prompt sent with {len(classes)} class(es).",
            feedback_url=feedback_base_url,
        )

    def _apply_attendance_interaction(self, custom_id: str, actor_id: str | None = None) -> str:
        _, subject_code, class_status, attended_value, *_ = custom_id.split(":")
        response = self.campusflow_service.apply_feedback(
            AttendanceFeedback(
                subject_code=subject_code,
                class_status=class_status,
                attended=attended_value == "attended",
                note="Submitted from Discord feedback button",
            ),
            source="discord_button",
            actor_id=actor_id,
        )
        subject = response.subject
        return (
            f"{response.message} New preview: {subject.attendance_percent}% attendance, "
            f"{subject.bunk_budget} bunk(s) left."
        )

    def _verify_signature(self, request: Request, raw_body: bytes) -> None:
        if not settings.discord_public_key:
            return

        try:
            from nacl.signing import VerifyKey
            from nacl.exceptions import BadSignatureError
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="PyNaCl is required to verify Discord interactions.",
            ) from exc

        signature = request.headers.get("x-signature-ed25519")
        timestamp = request.headers.get("x-signature-timestamp")
        if not signature or not timestamp:
            raise HTTPException(status_code=401, detail="Missing Discord signature headers")

        verify_key = VerifyKey(bytes.fromhex(settings.discord_public_key))
        try:
            verify_key.verify(timestamp.encode("utf-8") + raw_body, bytes.fromhex(signature))
        except BadSignatureError as exc:
            raise HTTPException(status_code=401, detail="Invalid Discord request signature") from exc

    def _button(self, custom_id: str, label: str, style: int) -> dict[str, Any]:
        return {
            "type": 2,
            "style": style,
            "label": label,
            "custom_id": custom_id,
        }

    def _subject_for_timetable_entry(self, class_entry: TimetableEntry) -> SubjectAttendance:
        overview = self.campusflow_service.get_overview()
        return next(
            (
                subject
                for subject in overview.attendance
                if subject.code.upper() == class_entry.subject_code.upper()
            ),
            overview.attendance[0],
        )

    def _class_label(
        self,
        subject: SubjectAttendance,
        class_entry: TimetableEntry | None,
    ) -> str:
        if not class_entry:
            return subject.next_class
        return self._class_label_for_entry(class_entry)

    def _class_label_for_entry(self, class_entry: TimetableEntry) -> str:
        room = f" in {class_entry.room}" if class_entry.room else ""
        return f"{class_entry.weekday}, {class_entry.start_time}-{class_entry.end_time}{room}"

    def _class_slot_token(self, class_date: date, class_entry: TimetableEntry) -> str:
        return (
            f"{class_date.isoformat()}_"
            f"{class_entry.start_time.replace(':', '')}_"
            f"{class_entry.end_time.replace(':', '')}"
        )

    def _notification_key(self, class_entry: TimetableEntry, class_date: date) -> str:
        room = (class_entry.room or "no-room").lower().replace(" ", "-")
        return (
            f"{class_date.isoformat()}:{class_entry.subject_code.upper()}:"
            f"{class_entry.start_time}:{class_entry.end_time}:{room}"
        )

    def _notification_already_sent(self, notification_key: str) -> bool:
        return any(
            item.get("notification_key") == notification_key
            for item in self._read_notification_log()
        )

    def _record_notification(
        self,
        notification_key: str,
        class_entry: TimetableEntry,
        class_date: date,
        message: str,
    ) -> None:
        with self._notification_log_lock:
            log_items = self._read_notification_log()
            log_items.append(
                {
                    "notification_key": notification_key,
                    "class_date": class_date.isoformat(),
                    "subject_code": class_entry.subject_code.upper(),
                    "weekday": class_entry.weekday,
                    "start_time": class_entry.start_time,
                    "end_time": class_entry.end_time,
                    "room": class_entry.room,
                    "sent_at": datetime.now(
                        self.campusflow_service.timetable_service.timezone
                    ).isoformat(),
                    "message": message,
                }
            )
            self.notification_log_path.write_text(
                json.dumps(log_items, indent=2),
                encoding="utf-8",
            )

    def _record_daily_notification(
        self,
        classes: list[TimetableEntry],
        class_date: date,
        message: str,
    ) -> None:
        with self._notification_log_lock:
            log_items = self._read_notification_log()
            log_items.append(
                {
                    "notification_key": f"{class_date.isoformat()}:daily-run",
                    "class_date": class_date.isoformat(),
                    "subject_code": ",".join(entry.subject_code.upper() for entry in classes),
                    "sent_at": datetime.now(
                        self.campusflow_service.timetable_service.timezone
                    ).isoformat(),
                    "message": message,
                }
            )
            self.notification_log_path.write_text(
                json.dumps(log_items, indent=2),
                encoding="utf-8",
            )

    def _read_notification_log(self) -> list[dict[str, Any]]:
        if not self.notification_log_path.exists():
            return []
        try:
            payload = json.loads(self.notification_log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if isinstance(payload, list):
            return payload
        return []
