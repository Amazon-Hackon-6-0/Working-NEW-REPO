import json
from typing import Any

import httpx
from fastapi import HTTPException, Request

from app.core.config import settings
from app.schemas.campusflow import AttendanceFeedback
from app.schemas.integrations import DiscordPromptResponse
from app.services.campusflow_service import CampusFlowService


class DiscordService:
    def __init__(self, campusflow_service: CampusFlowService) -> None:
        self.campusflow_service = campusflow_service

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

    async def _send_bot_button_prompt(self, subject: Any) -> DiscordPromptResponse:
        feedback_url = f"{settings.public_base_url}/api/v1/integrations/discord/interactions"
        payload = {
            "allowed_mentions": {"parse": []},
            "content": (
                f"Daily class feedback needed for **{subject.code}** "
                f"({subject.next_class}). Was the class actually held?"
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
            message=f"Discord button prompt sent for {subject.code}.",
            feedback_url=feedback_url,
        )

    async def _send_webhook_link_prompt(self, subject: Any) -> DiscordPromptResponse:
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

        payload = {
            "username": "CampusFlow",
            "allowed_mentions": {"parse": []},
            "content": (
                f"Daily class feedback needed for **{subject.code}** "
                f"({subject.next_class}). Was the class actually held?\n\n"
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
            message=f"Discord feedback prompt sent for {subject.code}.",
            feedback_url=feedback_base_url,
        )

    def _apply_attendance_interaction(self, custom_id: str, actor_id: str | None = None) -> str:
        _, subject_code, class_status, attended_value = custom_id.split(":")
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
