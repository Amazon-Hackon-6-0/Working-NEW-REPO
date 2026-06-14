from __future__ import annotations

import json
import logging
import re
import smtplib
import ssl
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import httpx
from pypdf import PdfReader

from app.core.config import settings
from app.schemas.campusflow import (
    ProcessCaseCreateRequest,
    ProcessCaseReplyRequest,
    ProcessCaseResponse,
    ProcessCaseSendRequest,
    ProcessInboundReplyRequest,
    ProcessTaskUpdateRequest,
    ProcessCopilotAskResponse,
    ProcessPolicyListResponse,
    ProcessPolicySummary,
    ProcessPolicyUploadResponse,
)

logger = logging.getLogger(__name__)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OFFICE_MAPPINGS = [
    {
        "issue_type": "missed exam / makeup exam",
        "office": "Academic Office + Exam Cell",
        "keywords": ["missed exam", "makeup", "exam", "sick", "illness", "medical"],
        "documents": ["Medical Certificate", "Application Form"],
    },
    {
        "issue_type": "attendance shortage",
        "office": "Academic Office",
        "keywords": ["attendance", "below 75", "shortage", "medical proof"],
        "documents": ["Medical Certificate", "Attendance Proof", "Application Form"],
    },
    {
        "issue_type": "bonafide certificate",
        "office": "Academic Office",
        "keywords": ["bonafide", "certificate", "bank account"],
        "documents": ["Bonafide Application Form", "ID Card"],
    },
    {
        "issue_type": "internship NOC",
        "office": "Placement/Academic Office",
        "keywords": ["internship", "noc", "no objection", "offer letter"],
        "documents": ["Internship Offer Letter", "NOC Application Form"],
    },
    {
        "issue_type": "hostel room change",
        "office": "Hostel Office",
        "keywords": ["hostel", "room change", "warden", "roommate"],
        "documents": ["Hostel Room Change Form", "ID Card"],
    },
    {
        "issue_type": "mess issue",
        "office": "Mess Committee",
        "keywords": ["mess", "food", "meal", "canteen"],
        "documents": ["Written Complaint"],
    },
    {
        "issue_type": "ID card lost",
        "office": "Admin/Security Office",
        "keywords": ["id card", "identity card", "lost card", "security"],
        "documents": ["ID Card Replacement Form", "Fee Receipt"],
    },
]


class ProcessCopilotService:
    """Local campus policy retrieval for process/helpdesk questions."""

    def __init__(
        self,
        path: Path | None = None,
        cases_path: Path | None = None,
        office_directory_path: Path | None = None,
    ) -> None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        self.path = path or data_dir / "campus_knowledge.json"
        self.cases_path = cases_path or data_dir / "process_cases.json"
        self.office_directory_path = office_directory_path or data_dir / "office_directory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def upload_policy_pdf(
        self,
        filename: str,
        content: bytes,
        college_id: str = "default",
    ) -> ProcessPolicyUploadResponse:
        clean_college_id = self._clean_college_id(college_id)
        text = self._extract_pdf_text(content)
        if not text.strip():
            raise ValueError(
                "Could not extract readable text from this PDF. Upload a text-based campus policy PDF."
            )

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError(
                "PDF text was extracted, but it did not contain enough policy text to index."
            )

        uploaded_at = datetime.now(timezone.utc).isoformat()
        document = {
            "document_id": str(uuid4()),
            "college_id": clean_college_id,
            "document_name": filename,
            "extracted_text": text,
            "chunks": [
                {
                    "chunk_id": f"{Path(filename).stem or 'policy'}-{index + 1}",
                    "text": chunk,
                }
                for index, chunk in enumerate(chunks)
            ],
            "uploaded_at": uploaded_at,
        }

        with self._lock:
            payload = self._read_payload()
            payload.setdefault("documents", []).append(document)
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return ProcessPolicyUploadResponse(
            document_name=filename,
            college_id=clean_college_id,
            chunks_count=len(chunks),
            message=f"Indexed {len(chunks)} campus policy chunk(s) from {filename}.",
        )

    def list_policies(self, college_id: str | None = None) -> ProcessPolicyListResponse:
        clean_college_id = self._clean_college_id(college_id) if college_id else None
        summaries = []
        for document in self._read_payload().get("documents", []):
            if clean_college_id and document.get("college_id") != clean_college_id:
                continue
            summaries.append(
                ProcessPolicySummary(
                    college_id=document.get("college_id", "default"),
                    document_name=document.get("document_name", "campus_policy.pdf"),
                    chunks_count=len(document.get("chunks", [])),
                    uploaded_at=document.get("uploaded_at", ""),
                )
            )
        return ProcessPolicyListResponse(
            policies=sorted(
                summaries,
                key=lambda item: item.uploaded_at,
                reverse=True,
            )
        )

    async def answer_question(
        self,
        question: str,
        college_id: str = "default",
    ) -> ProcessCopilotAskResponse:
        clean_college_id = self._clean_college_id(college_id)
        matches = self._top_matches(question, clean_college_id)
        if not matches:
            return ProcessCopilotAskResponse(
                answer=(
                    "The uploaded campus policy documents do not contain enough information "
                    "to answer this question."
                ),
                steps=[],
                required_documents=[],
                office_or_contact=None,
                deadline_or_timeline=None,
                email_draft=None,
                sources_used=[],
                llm_used=False,
                llm_provider="fallback",
                llm_error="No relevant policy chunks found",
                fallback_mode=True,
                used_college_id=clean_college_id,
            )

        gemini_key = self._gemini_api_key()
        gemini_model = self._gemini_model()
        self._log_gemini_config(gemini_key, gemini_model)

        if not gemini_key:
            return self._fallback_answer(
                question,
                clean_college_id,
                matches,
                llm_error="GEMINI_API_KEY missing",
            )

        try:
            return await self._answer_with_gemini(
                question,
                clean_college_id,
                matches,
                gemini_key,
                gemini_model,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Process Copilot Gemini response format unexpected")
            return self._fallback_answer(
                question,
                clean_college_id,
                matches,
                llm_error="Gemini response format unexpected",
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            logger.warning(
                "Process Copilot Gemini HTTP failure: status_code=%s",
                status_code,
            )
            return self._fallback_answer(
                question,
                clean_college_id,
                matches,
                llm_error=self._gemini_http_error(status_code),
            )
        except httpx.RequestError as exc:
            logger.warning(
                "Process Copilot Gemini client failure: error_type=%s",
                exc.__class__.__name__,
            )
            return self._fallback_answer(
                question,
                clean_college_id,
                matches,
                llm_error="Gemini request failed: network/client error",
            )
        except Exception as exc:
            logger.warning(
                "Process Copilot Gemini unexpected failure: error_type=%s",
                exc.__class__.__name__,
            )
            return self._fallback_answer(
                question,
                clean_college_id,
                matches,
                llm_error="Gemini request failed: network/client error",
            )

    def list_cases(self, college_id: str | None = None) -> list[ProcessCaseResponse]:
        clean_college_id = self._clean_college_id(college_id) if college_id else None
        cases = []
        for case in self._read_cases_payload().get("cases", []):
            if clean_college_id and case.get("college_id") != clean_college_id:
                continue
            cases.append(self._case_response(case))
        return sorted(cases, key=lambda item: item.updated_at, reverse=True)

    def get_case(self, case_id: str) -> ProcessCaseResponse | None:
        case = self._find_case(case_id)
        return self._case_response(case) if case else None

    async def create_case(
        self,
        payload: ProcessCaseCreateRequest,
    ) -> ProcessCaseResponse:
        clean_college_id = self._clean_college_id(payload.college_id)
        issue_text = " ".join(
            part
            for part in [payload.student_issue, payload.course_or_subject or ""]
            if part.strip()
        )
        matches = self._top_matches(issue_text, clean_college_id)
        mapping = self._issue_mapping(issue_text, clean_college_id)
        gemini_key = self._gemini_api_key()
        gemini_model = self._gemini_model()
        self._log_gemini_config(gemini_key, gemini_model)

        plan: dict[str, Any] | None = None
        llm_used = False
        llm_provider = "fallback"
        fallback_mode = True
        llm_error: str | None = None

        if gemini_key:
            try:
                plan = await self._case_plan_with_gemini(
                    payload,
                    clean_college_id,
                    matches,
                    mapping,
                    gemini_key,
                    gemini_model,
                )
                llm_used = True
                llm_provider = "gemini"
                fallback_mode = False
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("Process Relay Gemini case response format unexpected")
                llm_error = "Gemini response format unexpected"
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                logger.warning(
                    "Process Relay Gemini case HTTP failure: status_code=%s",
                    status_code,
                )
                llm_error = self._gemini_http_error(status_code)
            except httpx.RequestError as exc:
                logger.warning(
                    "Process Relay Gemini case client failure: error_type=%s",
                    exc.__class__.__name__,
                )
                llm_error = "Gemini request failed: network/client error"
            except Exception as exc:
                logger.warning(
                    "Process Relay Gemini case unexpected failure: error_type=%s",
                    exc.__class__.__name__,
                )
                llm_error = "Gemini request failed: network/client error"
        else:
            llm_error = "GEMINI_API_KEY missing"

        if plan is None:
            plan = self._fallback_case_plan(payload, clean_college_id, matches, mapping)

        case = self._build_case(
            payload,
            clean_college_id,
            plan,
            matches,
            mapping,
            llm_used=llm_used,
            llm_provider=llm_provider,
            fallback_mode=fallback_mode,
            llm_error=llm_error,
        )
        self._save_case(case)
        return self._case_response(case)

    def send_case(
        self,
        case_id: str,
        payload: ProcessCaseSendRequest | None = None,
    ) -> ProcessCaseResponse | None:
        case = self._find_case(case_id)
        if not case:
            return None
        if payload and not payload.student_approved:
            case["delivery_mode"] = self._delivery_mode()
            case["action_message"] = "Request was not sent because student approval is required."
            self._save_case(case)
            return self._case_response(case)

        now = self._now()
        subject = self._case_email_subject(case)
        body = self._case_email_body(case)
        email_config = self._smtp_config()
        case["delivery_mode"] = self._delivery_mode()

        if not settings.campus_relay_email_enabled:
            case["delivery_mode"] = "queue"
            case["status"] = "queued"
            case["outbound_message"] = self._outbound_metadata(
                case,
                subject,
                body,
                now,
                demo_mode=True,
                event_key="queued_at",
            )
            case["action_message"] = "Queued because email is not enabled"
            case["last_student_notification"] = "Queued because email is not enabled"
            self._append_timeline(
                case,
                "sent",
                "Queued",
                "Email delivery is disabled, so the request was queued locally.",
                now,
            )
        elif not email_config:
            case["status"] = "send_failed"
            case["action_message"] = "Email sending failed: SMTP configuration is incomplete"
            case["last_student_notification"] = case["action_message"]
            self._append_timeline(
                case,
                "sent",
                "Send failed",
                "SMTP configuration is incomplete.",
                now,
            )
        elif not case.get("routed_to_email"):
            case["status"] = "send_failed"
            case["action_message"] = "Email sending failed: routed office email is missing"
            case["last_student_notification"] = case["action_message"]
            self._append_timeline(
                case,
                "sent",
                "Send failed",
                "No routed office email was found.",
                now,
            )
        else:
            try:
                self._send_email(
                    to_email=case["routed_to_email"],
                    subject=subject,
                    body=body,
                    config=email_config,
                )
                case["delivery_mode"] = "email"
                case["status"] = "sent"
                case["sent_at"] = now
                case["outbound_message"] = self._outbound_metadata(
                    case,
                    subject,
                    body,
                    now,
                    demo_mode=False,
                    event_key="sent_at",
                )
                case["action_message"] = f"Sent to {case.get('routed_to_email')}"
                case["last_student_notification"] = case["action_message"]
                self._append_timeline(
                    case,
                    "sent",
                    "Sent",
                    f"Email sent to {case.get('routed_to_email')}.",
                    now,
                )
            except Exception as exc:
                logger.warning(
                    "Process Relay email send failed: error_type=%s",
                    exc.__class__.__name__,
                )
                case["status"] = "send_failed"
                case["action_message"] = "Email sending failed: check SMTP settings and office email"
                case["last_student_notification"] = case["action_message"]
                self._append_timeline(
                    case,
                    "sent",
                    "Send failed",
                    "SMTP send failed. Case data was kept.",
                    now,
                )
        case["follow_up_due_at"] = self._future_iso(days=3)
        case["updated_at"] = now
        self._save_case(case)
        return self._case_response(case)

    async def add_case_reply(
        self,
        case_id: str,
        payload: ProcessCaseReplyRequest,
    ) -> ProcessCaseResponse | None:
        case = self._find_case(case_id)
        if not case:
            return None

        await self._apply_reply_to_case(
            case,
            reply_message=payload.reply_message,
            reply_from=payload.reply_from,
            from_email=None,
        )
        self._save_case(case)
        return self._case_response(case)

    async def receive_inbound_reply(
        self,
        payload: ProcessInboundReplyRequest,
    ) -> ProcessCaseResponse | None:
        case_id = payload.case_id or self._extract_case_id(
            " ".join(
                part
                for part in [payload.subject or "", payload.reply_message]
                if part.strip()
            )
        )
        if not case_id:
            return None
        case = self._find_case(case_id)
        if not case:
            return None

        await self._apply_reply_to_case(
            case,
            reply_message=payload.reply_message,
            reply_from=payload.from_email or case.get("routed_to_office"),
            from_email=payload.from_email,
        )
        self._save_case(case)
        return self._case_response(case)

    async def follow_up_case(self, case_id: str) -> ProcessCaseResponse | None:
        case = self._find_case(case_id)
        if not case:
            return None

        now = self._now()
        subject, body, llm_used, llm_provider, fallback_mode, llm_error = (
            await self._follow_up_message(case)
        )
        case["llm_used"] = llm_used
        case["llm_provider"] = llm_provider
        case["fallback_mode"] = fallback_mode
        case["llm_error"] = llm_error
        email_config = self._smtp_config()
        reminder_count = int(case.get("reminder_count") or 0) + 1
        case["reminder_count"] = reminder_count

        if not settings.campus_relay_email_enabled:
            case["follow_up_message"] = self._outbound_metadata(
                case,
                subject,
                body,
                now,
                demo_mode=True,
                event_key="queued_at",
            )
            case["action_message"] = "Follow-up queued because email is not enabled"
            case["last_student_notification"] = case["action_message"]
            self._append_timeline(
                case,
                "sent",
                "Follow-up queued",
                "Follow-up email was queued locally.",
                now,
            )
        elif not email_config or not case.get("routed_to_email"):
            case["action_message"] = "Follow-up failed: SMTP config or routed email is missing"
            case["last_student_notification"] = case["action_message"]
            self._append_timeline(
                case,
                "sent",
                "Follow-up failed",
                "Follow-up could not be sent because delivery settings are incomplete.",
                now,
            )
        else:
            try:
                self._send_email(
                    to_email=case["routed_to_email"],
                    subject=subject,
                    body=body,
                    config=email_config,
                )
                case["follow_up_message"] = self._outbound_metadata(
                    case,
                    subject,
                    body,
                    now,
                    demo_mode=False,
                    event_key="sent_at",
                )
                case["action_message"] = f"Follow-up sent to {case.get('routed_to_office')}"
                case["last_student_notification"] = case["action_message"]
                self._append_timeline(
                    case,
                    "sent",
                    "Follow-up sent",
                    f"Follow-up email sent to {case.get('routed_to_office')}.",
                    now,
                )
            except Exception as exc:
                logger.warning(
                    "Process Relay follow-up email failed: error_type=%s",
                    exc.__class__.__name__,
                )
                case["action_message"] = "Follow-up failed: check SMTP settings and office email"
                case["last_student_notification"] = case["action_message"]
                self._append_timeline(
                    case,
                    "sent",
                    "Follow-up failed",
                    "SMTP follow-up send failed. Case data was kept.",
                    now,
                )

        case["follow_up_due_at"] = self._future_iso(days=3)
        case["updated_at"] = now
        self._save_case(case)
        return self._case_response(case)

    def update_case_task(
        self,
        case_id: str,
        task_id: str,
        payload: ProcessTaskUpdateRequest,
    ) -> ProcessCaseResponse | None:
        case = self._find_case(case_id)
        if not case:
            return None

        task_found = False
        for task in case.get("tasks", []):
            if task.get("task_id") == task_id:
                task["done"] = payload.done
                task_found = True
                break
        if not task_found:
            return None

        now = self._now()
        self._append_timeline(
            case,
            "task_updated",
            "Task updated",
            f"Task {task_id} marked {'done' if payload.done else 'pending'}.",
            now,
        )
        tasks = case.get("tasks", [])
        if tasks and all(task.get("done") for task in tasks):
            case["status"] = "completed"
            case["student_next_action"] = "All checklist items are complete."
            case["action_message"] = "Case marked completed."
            case["last_student_notification"] = "Case completed."
            self._append_timeline(
                case,
                "completed",
                "Completed",
                "All checklist tasks are complete.",
                now,
            )
        elif case.get("status") == "completed":
            case["status"] = "replied" if case.get("office_reply") else "queued"
            case["action_message"] = "Case reopened because a task is pending."
            case["last_student_notification"] = case["action_message"]
        else:
            case["action_message"] = "Task updated."
            case["last_student_notification"] = case["action_message"]
        case["updated_at"] = now
        self._save_case(case)
        return self._case_response(case)

    def _read_cases_payload(self) -> dict[str, Any]:
        if not self.cases_path.exists():
            return {"cases": []}
        try:
            payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"cases": []}
        if not isinstance(payload, dict):
            return {"cases": []}
        payload.setdefault("cases", [])
        return payload

    def _save_case(self, case: dict[str, Any]) -> None:
        with self._lock:
            payload = self._read_cases_payload()
            cases = payload.setdefault("cases", [])
            for index, existing in enumerate(cases):
                if existing.get("case_id") == case.get("case_id"):
                    cases[index] = case
                    break
            else:
                cases.append(case)
            self.cases_path.parent.mkdir(parents=True, exist_ok=True)
            self.cases_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _find_case(self, case_id: str) -> dict[str, Any] | None:
        for case in self._read_cases_payload().get("cases", []):
            if case.get("case_id") == case_id:
                return case
        return None

    def _case_response(self, case: dict[str, Any]) -> ProcessCaseResponse:
        return ProcessCaseResponse(
            case_id=case.get("case_id", ""),
            college_id=case.get("college_id", "default"),
            issue_type=case.get("issue_type", "general campus request"),
            status=case.get("status", "draft"),
            routed_to_office=case.get("routed_to_office", "Academic Office"),
            routed_to_email=case.get("routed_to_email"),
            delivery_mode=self._case_delivery_mode(case),
            confidence=case.get("confidence", "low"),
            summary=case.get("summary", ""),
            required_documents=case.get("required_documents", []),
            deadline_or_timeline=case.get("deadline_or_timeline"),
            tasks=case.get("tasks", []),
            generated_message_subject=case.get("generated_message_subject", ""),
            generated_message_body=case.get("generated_message_body", ""),
            sent_at=case.get("sent_at"),
            follow_up_due_at=case.get("follow_up_due_at"),
            reminder_count=int(case.get("reminder_count") or 0),
            office_reply=case.get("office_reply"),
            reply_history=case.get("reply_history", []),
            reply_outcome=case.get("reply_outcome"),
            student_next_action=case.get("student_next_action"),
            last_student_notification=case.get("last_student_notification"),
            notification_channel=case.get("notification_channel", "app"),
            timeline=case.get("timeline", []),
            sources_used=case.get("sources_used", []),
            llm_used=case.get("llm_used", False),
            llm_provider=case.get("llm_provider", "fallback"),
            fallback_mode=case.get("fallback_mode", True),
            llm_error=case.get("llm_error"),
            action_message=case.get("action_message"),
            created_at=case.get("created_at", ""),
            updated_at=case.get("updated_at", ""),
        )

    async def _case_plan_with_gemini(
        self,
        payload: ProcessCaseCreateRequest,
        college_id: str,
        matches: list[dict[str, Any]],
        mapping: dict[str, Any],
        gemini_key: str,
        gemini_model: str,
    ) -> dict[str, Any]:
        policy_context = "\n\n".join(
            (
                f"Document: {match['document_name']}\n"
                f"Snippet: {self._snippet(match['text'], 900)}"
            )
            for match in matches
        ) or "No relevant uploaded policy chunks were found for this issue."
        prompt = (
            "You are Campus Process Relay. Create a campus workflow case from the "
            "student issue. Use only the uploaded campus policy chunks and office "
            "mapping provided below. If policy text lacks documents, deadlines, or "
            "rules, use null/empty values or say not enough information; do not invent. "
            "Do not invent email addresses. Only use an email if it appears in the "
            "office directory. generated_message_subject and generated_message_body "
            "are the formal request email to the routed office or authority, not a "
            "message to the student. The body must begin with Dear <routed office>, "
            "and must include the CampusFlow case ID placeholder if available, student "
            "name, student email, course or subject, issue summary, documents, "
            "policy-based reason, requested action from office, and this reply "
            "instruction: Please reply with the Case ID in the subject/body. "
            "Do not write student-facing guidance in generated_message_body; put that "
            "only in student_next_action. Return strict JSON with keys: issue_type, "
            "routed_to_office, routed_to_email, confidence, summary, "
            "required_documents, deadline_or_timeline, tasks, "
            "generated_message_subject, generated_message_body, student_next_action, "
            "sources_used."
        )
        request_text = {
            "college_id": college_id,
            "student_name": payload.student_name,
            "student_email": payload.student_email,
            "student_issue": payload.student_issue,
            "course_or_subject": payload.course_or_subject,
            "attached_document_names": payload.attached_document_names,
            "fallback_office_mapping": mapping,
            "office_directory": self._office_directory_entries(college_id),
            "uploaded_policy_context": policy_context,
        }
        llm_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt}\n\n"
                                f"Case input JSON:\n{json.dumps(request_text, indent=2)}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{gemini_model}:generateContent"
                ),
                params={"key": gemini_key},
                headers={"Content-Type": "application/json"},
                json=llm_payload,
            )
        response.raise_for_status()
        return self._parse_llm_json(self._gemini_text(response.json()))

    def _fallback_case_plan(
        self,
        payload: ProcessCaseCreateRequest,
        college_id: str,
        matches: list[dict[str, Any]],
        mapping: dict[str, Any],
    ) -> dict[str, Any]:
        matched_texts = [match["text"] for match in matches]
        combined = " ".join(matched_texts)
        office = self._extract_office(matched_texts) or mapping["office"]
        documents = self._extract_required_documents(combined) or mapping.get("documents", [])
        documents = self._dedupe_list(
            [*documents, *[name for name in payload.attached_document_names if name.strip()]]
        )[:8]
        timeline = self._extract_timeline(combined)
        sources = self._source_labels(matches)
        if not sources:
            sources = [f"Default office mapping: {mapping['issue_type']} -> {office}"]
        confidence = "high" if matches and mapping.get("score", 0) >= 2 else "medium"
        if not matches and mapping.get("score", 0) <= 0:
            confidence = "low"
        summary = self._summary_from_issue(payload.student_issue)
        return {
            "issue_type": mapping["issue_type"],
            "routed_to_office": office,
            "routed_to_email": self._office_email_for(
                mapping["issue_type"],
                office,
                college_id,
            ),
            "confidence": confidence,
            "summary": summary,
            "required_documents": documents,
            "deadline_or_timeline": timeline,
            "tasks": self._case_tasks(documents, office),
            "generated_message_subject": self._message_subject(mapping["issue_type"], payload),
            "generated_message_body": self._message_body(payload, office, documents),
            "student_next_action": "Review the generated request and click Send request when ready.",
            "sources_used": sources,
        }

    def _build_case(
        self,
        payload: ProcessCaseCreateRequest,
        college_id: str,
        plan: dict[str, Any],
        matches: list[dict[str, Any]],
        mapping: dict[str, Any],
        llm_used: bool,
        llm_provider: str,
        fallback_mode: bool,
        llm_error: str | None,
    ) -> dict[str, Any]:
        office = self._clean_text(plan.get("routed_to_office")) or mapping["office"]
        issue_type = self._clean_text(plan.get("issue_type")) or mapping["issue_type"]
        documents = self._dedupe_list(self._string_list(plan.get("required_documents")))[:8]
        if not documents:
            documents = mapping.get("documents", [])
        sources = self._dedupe_list(self._string_list(plan.get("sources_used")))[:3]
        if not sources:
            sources = self._source_labels(matches)
        if not sources:
            sources = [f"Default office mapping: {issue_type} -> {office}"]

        now = self._now()
        case_id = str(uuid4())
        summary = self._clean_text(plan.get("summary")) or self._summary_from_issue(
            payload.student_issue
        )
        deadline = self._clean_text(plan.get("deadline_or_timeline"))
        subject = self._clean_text(plan.get("generated_message_subject")) or self._message_subject(
            issue_type,
            payload,
        )
        body = self._office_facing_message_body(
            body=self._clean_text(plan.get("generated_message_body")),
            payload=payload,
            office=office,
            documents=documents,
            summary=summary,
            issue_type=issue_type,
            deadline=deadline,
        )
        return {
            "case_id": case_id,
            "college_id": college_id,
            "student_name": payload.student_name,
            "student_email": payload.student_email,
            "student_issue": payload.student_issue,
            "course_or_subject": payload.course_or_subject,
            "attached_document_names": payload.attached_document_names,
            "issue_type": issue_type,
            "status": "draft",
            "routed_to_office": office,
            "routed_to_email": self._safe_routed_email(
                plan.get("routed_to_email"),
                issue_type,
                office,
                college_id,
            ),
            "delivery_mode": self._delivery_mode(),
            "confidence": self._confidence(plan.get("confidence"), mapping.get("score", 0)),
            "summary": summary,
            "required_documents": documents,
            "deadline_or_timeline": deadline,
            "tasks": self._normalise_tasks(plan.get("tasks"), documents, office),
            "generated_message_subject": subject,
            "generated_message_body": body.replace("{{CASE_ID}}", case_id),
            "office_reply": None,
            "reply_history": [],
            "student_next_action": self._clean_text(plan.get("student_next_action"))
            or "Review the generated request and click Send request when ready.",
            "sent_at": None,
            "follow_up_due_at": None,
            "reminder_count": 0,
            "last_student_notification": "Draft case created. Review before sending.",
            "notification_channel": "app",
            "timeline": [
                self._timeline_event(
                    "created",
                    "Created",
                    "Campus request case created.",
                    now,
                ),
                self._timeline_event(
                    "message_generated",
                    "Message generated",
                    "AI drafted the office request for review.",
                    now,
                ),
            ],
            "sources_used": [self._snippet(source, 180) for source in sources],
            "llm_used": llm_used,
            "llm_provider": llm_provider,
            "fallback_mode": fallback_mode,
            "llm_error": llm_error,
            "action_message": "Draft case created. Review before sending.",
            "created_at": now,
            "updated_at": now,
        }

    async def _next_action_from_reply(
        self,
        case: dict[str, Any],
        reply_text: str,
    ) -> tuple[dict[str, Any], bool, str, bool, str | None]:
        gemini_key = self._gemini_api_key()
        gemini_model = self._gemini_model()
        self._log_gemini_config(gemini_key, gemini_model)
        if not gemini_key:
            return self._fallback_reply_insights(reply_text, case), False, "fallback", True, (
                "GEMINI_API_KEY missing"
            )
        try:
            insights = await self._next_action_with_gemini(
                case,
                reply_text,
                gemini_key,
                gemini_model,
            )
            return insights, True, "gemini", False, None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Process Relay Gemini reply response format unexpected")
            return self._fallback_reply_insights(reply_text, case), False, "fallback", True, (
                "Gemini response format unexpected"
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            logger.warning(
                "Process Relay Gemini reply HTTP failure: status_code=%s",
                status_code,
            )
            return self._fallback_reply_insights(reply_text, case), False, "fallback", True, (
                self._gemini_http_error(status_code)
            )
        except httpx.RequestError as exc:
            logger.warning(
                "Process Relay Gemini reply client failure: error_type=%s",
                exc.__class__.__name__,
            )
            return self._fallback_reply_insights(reply_text, case), False, "fallback", True, (
                "Gemini request failed: network/client error"
            )
        except Exception as exc:
            logger.warning(
                "Process Relay Gemini reply unexpected failure: error_type=%s",
                exc.__class__.__name__,
            )
            return self._fallback_reply_insights(reply_text, case), False, "fallback", True, (
                "Gemini request failed: network/client error"
            )

    async def _next_action_with_gemini(
        self,
        case: dict[str, Any],
        reply_text: str,
        gemini_key: str,
        gemini_model: str,
    ) -> dict[str, Any]:
        prompt = (
            "Read the office reply and return strict JSON with keys: "
            "student_next_action, new_tasks, deadline_or_timeline, case_outcome. "
            "case_outcome must be one of approved, rejected, pending, information. "
            "Keep the next action one concise practical instruction for the student. "
            "Do not invent new deadlines, offices, or documents."
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt}\n\n"
                                f"Case: {json.dumps(case, indent=2)}\n\n"
                                f"Office reply: {reply_text}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{gemini_model}:generateContent"
                ),
                params={"key": gemini_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
        response.raise_for_status()
        parsed = self._parse_llm_json(self._gemini_text(response.json()))
        action = self._clean_text(parsed.get("student_next_action"))
        if not action:
            raise ValueError("Gemini reply action missing.")
        return {
            "student_next_action": action,
            "new_tasks": self._dedupe_list(self._string_list(parsed.get("new_tasks")))[:5],
            "deadline_or_timeline": self._clean_text(parsed.get("deadline_or_timeline")),
            "case_outcome": self._case_outcome(parsed.get("case_outcome")),
        }

    async def _apply_reply_to_case(
        self,
        case: dict[str, Any],
        reply_message: str,
        reply_from: str | None = None,
        from_email: str | None = None,
    ) -> None:
        reply_text = reply_message.strip()
        clean_from = reply_from or case.get("routed_to_office") or "Campus office"
        now = self._now()
        case["office_reply"] = f"{clean_from}: {reply_text}"
        case["reply_history"] = case.get("reply_history", [])
        case["reply_history"].append(
            {
                "reply_id": str(uuid4()),
                "reply_from": clean_from,
                "from_email": self._extract_email(from_email),
                "reply_message": reply_text,
                "received_at": now,
            }
        )
        case["status"] = "replied"

        insights, llm_used, llm_provider, fallback_mode, llm_error = (
            await self._next_action_from_reply(case, reply_text)
        )
        next_action = self._clean_text(insights.get("student_next_action"))
        new_tasks = self._dedupe_list(self._string_list(insights.get("new_tasks")))[:5]
        deadline = self._clean_text(insights.get("deadline_or_timeline"))

        case["student_next_action"] = next_action
        case["reply_outcome"] = self._case_outcome(insights.get("case_outcome"))
        if deadline:
            case["deadline_or_timeline"] = deadline
        case["llm_used"] = llm_used
        case["llm_provider"] = llm_provider
        case["fallback_mode"] = fallback_mode
        case["llm_error"] = llm_error
        if next_action:
            new_tasks.append(next_action)
        for task_title in new_tasks:
            case["tasks"] = self._append_task_if_missing(case.get("tasks", []), task_title)
        case["action_message"] = "Office reply added. Student next action updated."
        case["last_student_notification"] = next_action or case["action_message"]
        case["updated_at"] = now
        self._append_timeline(
            case,
            "reply_received",
            "Reply received",
            "Office reply was attached to the case.",
            now,
        )

    def _fallback_reply_insights(
        self,
        reply_text: str,
        case: dict[str, Any],
    ) -> dict[str, Any]:
        action = self._fallback_next_action(reply_text, case)
        documents = self._extract_required_documents(reply_text)
        deadline = self._extract_timeline(reply_text)
        tasks = []
        if documents:
            tasks.append(f"Submit {', '.join(documents[:3])}.")
        if action:
            tasks.append(action)
        return {
            "student_next_action": action,
            "new_tasks": self._dedupe_list(tasks)[:5],
            "deadline_or_timeline": deadline,
            "case_outcome": self._case_outcome(reply_text),
        }

    def _case_outcome(self, value: Any) -> str:
        text = self._clean_text(value).lower()
        if any(word in text for word in ["approved", "accepted", "granted"]):
            return "approved"
        if any(word in text for word in ["rejected", "denied", "not approved"]):
            return "rejected"
        if any(word in text for word in ["pending", "submit", "provide", "within", "visit"]):
            return "pending"
        return "information"

    def _office_directory_entries(self, college_id: str = "default") -> list[dict[str, Any]]:
        if not self.office_directory_path.exists():
            return []
        try:
            payload = json.loads(self.office_directory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        entries: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            college_directory = payload.get(college_id) or payload.get("default")
            if isinstance(college_directory, dict):
                for office_key, office_value in college_directory.items():
                    if isinstance(office_value, dict):
                        entries.append(
                            {
                                "college_id": college_id,
                                "office_key": office_key,
                                "office": office_value.get("name") or office_key,
                                "name": office_value.get("name") or office_key,
                                "email": self._extract_email(
                                    office_value.get("email")
                                    or office_value.get("office_email")
                                ),
                            }
                        )
            raw_entries = payload.get("offices", [])
            if isinstance(raw_entries, list):
                for item in raw_entries:
                    if isinstance(item, dict):
                        entries.append(
                            {
                                **item,
                                "email": self._extract_email(
                                    item.get("email") or item.get("office_email")
                                ),
                            }
                        )
            for issue_type, value in payload.items():
                if issue_type in {"offices", college_id, "default"}:
                    continue
                if isinstance(value, dict):
                    entries.append(
                        {
                            "issue_type": issue_type,
                            **value,
                            "email": self._extract_email(
                                value.get("email") or value.get("office_email")
                            ),
                        }
                    )
                elif isinstance(value, str):
                    entries.append({"issue_type": issue_type, "office": value})
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    entries.append(
                        {
                            **item,
                            "email": self._extract_email(
                                item.get("email") or item.get("office_email")
                            ),
                        }
                    )
        return entries

    def _issue_mapping(self, issue_text: str, college_id: str) -> dict[str, Any]:
        lower_issue = issue_text.lower()
        best = DEFAULT_OFFICE_MAPPINGS[0]
        best_score = -1
        for mapping in DEFAULT_OFFICE_MAPPINGS:
            score = 0
            for keyword in mapping["keywords"]:
                keyword_lower = keyword.lower()
                if keyword_lower in lower_issue:
                    score += 3
                    continue
                words = [word for word in keyword_lower.split() if len(word) > 2]
                if words and all(word in lower_issue for word in words):
                    score += 2
            if score > best_score:
                best = mapping
                best_score = score

        if best_score <= 0:
            best = {
                "issue_type": "general campus request",
                "office": "Academic Office",
                "keywords": [],
                "documents": ["Application Form"],
            }
        result = dict(best)
        result["score"] = max(best_score, 0)
        directory_email = self._office_email_for(
            result["issue_type"],
            result["office"],
            college_id,
        )
        if directory_email:
            result["email"] = directory_email
        return result

    def _office_email_for(
        self,
        issue_type: str,
        office: str,
        college_id: str = "default",
    ) -> str | None:
        issue_key = issue_type.lower()
        office_key = office.lower()
        for entry in self._office_directory_entries(college_id):
            email = self._extract_email(entry.get("email") or entry.get("office_email"))
            if not email or not self._looks_like_email(email):
                continue
            entry_issue = self._clean_text(entry.get("issue_type")).lower()
            entry_office = self._clean_text(entry.get("office") or entry.get("name")).lower()
            entry_key = self._clean_text(entry.get("office_key")).replace("_", " ").lower()
            if entry_issue and (entry_issue in issue_key or issue_key in entry_issue):
                return email
            if entry_office and (entry_office in office_key or office_key in entry_office):
                return email
            if entry_key and (entry_key in office_key or any(part in office_key for part in entry_key.split())):
                return email
        return None

    def _safe_routed_email(
        self,
        proposed_email: Any,
        issue_type: str,
        office: str,
        college_id: str,
    ) -> str | None:
        directory_email = self._office_email_for(issue_type, office, college_id)
        if not directory_email:
            return None
        proposed = self._extract_email(proposed_email)
        if proposed and proposed.lower() == directory_email.lower():
            return directory_email
        return directory_email

    def _looks_like_email(self, value: str) -> bool:
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))

    def _extract_email(self, value: Any) -> str | None:
        text = self._clean_text(value)
        if not text:
            return None
        mailto = re.search(r"mailto:([^)\]\s]+)", text, flags=re.I)
        if mailto:
            return mailto.group(1).strip()
        match = re.search(r"[^@\s<>()\[\]]+@[^@\s<>()\[\]]+\.[^@\s<>()\[\]]+", text)
        return match.group(0).strip() if match else None

    def _confidence(self, value: Any, mapping_score: int) -> str:
        cleaned = self._clean_text(value).lower()
        if cleaned in {"low", "medium", "high"}:
            return cleaned
        if mapping_score >= 3:
            return "high"
        if mapping_score > 0:
            return "medium"
        return "low"

    def _normalise_tasks(
        self,
        value: Any,
        documents: list[str],
        office: str,
    ) -> list[dict[str, Any]]:
        task_titles: list[str] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    task_titles.append(self._clean_text(item.get("title")))
                else:
                    task_titles.append(self._clean_text(item))
        elif isinstance(value, str):
            task_titles.append(value)

        if not task_titles:
            task_titles = self._case_tasks(documents, office)
        task_titles = self._dedupe_list(task_titles)[:6]
        return [
            {
                "task_id": f"task-{index + 1}-{uuid4().hex[:6]}",
                "title": title,
                "done": False,
            }
            for index, title in enumerate(task_titles)
        ]

    def _case_tasks(self, documents: list[str], office: str) -> list[str]:
        tasks = ["Review generated request message."]
        if documents:
            tasks.append(f"Keep ready: {', '.join(documents[:3])}.")
        tasks.append(f"Send request to {office}.")
        tasks.append("Track the office response and complete the next action.")
        return self._dedupe_list(tasks)

    def _append_task_if_missing(
        self,
        tasks: list[dict[str, Any]],
        title: str,
    ) -> list[dict[str, Any]]:
        existing_titles = {
            self._clean_text(task.get("title")).lower()
            for task in tasks
            if isinstance(task, dict)
        }
        cleaned = self._clean_text(title)
        if cleaned and cleaned.lower() not in existing_titles:
            tasks.append(
                {
                    "task_id": f"task-{len(tasks) + 1}-{uuid4().hex[:6]}",
                    "title": cleaned,
                    "done": False,
                }
            )
        return tasks

    def _summary_from_issue(self, issue: str) -> str:
        cleaned = self._clean_text(issue)
        if len(cleaned) <= 160:
            return cleaned
        return f"{cleaned[:157].rstrip()}..."

    def _message_subject(
        self,
        issue_type: str,
        payload: ProcessCaseCreateRequest,
    ) -> str:
        course = f" - {payload.course_or_subject}" if payload.course_or_subject else ""
        return f"Request regarding {issue_type}{course}"

    def _message_body(
        self,
        payload: ProcessCaseCreateRequest,
        office: str,
        documents: list[str],
        summary: str | None = None,
        issue_type: str | None = None,
        deadline: str | None = None,
    ) -> str:
        name = payload.student_name or "[Student Name]"
        email = payload.student_email or "Not provided"
        course = payload.course_or_subject or "Not provided"
        doc_text = ", ".join(documents) if documents else "To be confirmed"
        attached_text = (
            ", ".join(payload.attached_document_names)
            if payload.attached_document_names
            else "None mentioned"
        )
        issue_summary = summary or self._summary_from_issue(payload.student_issue)
        policy_reason = (
            f"Policy-based reason: {deadline}."
            if deadline
            else "Policy-based reason: Based on the uploaded policy text and office routing."
        )
        return (
            f"Dear {office},\n\n"
            "Campus Process Relay is forwarding this student request for review.\n\n"
            "CampusFlow Case ID: {{CASE_ID}}\n"
            f"Student name: {name}\n"
            f"Student email: {email}\n"
            f"Course/subject: {course}\n"
            f"Issue type: {issue_type or 'Campus process request'}\n"
            f"Issue summary: {issue_summary}\n"
            f"Documents attached/mentioned: {attached_text}\n"
            f"Documents required/expected: {doc_text}\n"
            f"{policy_reason}\n\n"
            "Requested action from office: Please review this request, confirm the "
            "required documents and timeline, and share the next action for the student.\n\n"
            "Please reply with the Case ID in the subject/body.\n\n"
            f"Regards,\n{name}"
        )

    def _office_facing_message_body(
        self,
        body: str,
        payload: ProcessCaseCreateRequest,
        office: str,
        documents: list[str],
        summary: str,
        issue_type: str,
        deadline: str | None,
    ) -> str:
        if not body or self._looks_student_facing(body, payload.student_name):
            return self._message_body(
                payload,
                office,
                documents,
                summary=summary,
                issue_type=issue_type,
                deadline=deadline,
            )
        if not re.search(rf"Dear\s+{re.escape(office)}", body, flags=re.I):
            return self._message_body(
                payload,
                office,
                documents,
                summary=summary,
                issue_type=issue_type,
                deadline=deadline,
            )
        if "case id" not in body.lower() or "reply with the case id" not in body.lower():
            return self._message_body(
                payload,
                office,
                documents,
                summary=summary,
                issue_type=issue_type,
                deadline=deadline,
            )
        return body

    def _looks_student_facing(self, body: str, student_name: str | None) -> bool:
        lowered = body.lower()
        if student_name and re.search(rf"dear\s+{re.escape(student_name.lower())}\b", lowered):
            return True
        student_patterns = [
            r"\bwe understand you\b",
            r"\byou missed\b",
            r"\bplease follow these steps\b",
            r"\byour next step\b",
            r"\byou should\b",
        ]
        return any(re.search(pattern, lowered) for pattern in student_patterns)

    def _fallback_next_action(self, reply_text: str, case: dict[str, Any]) -> str:
        documents = self._extract_required_documents(reply_text)
        timeline = self._extract_timeline(reply_text)
        office = case.get("routed_to_office") or "the campus office"
        for sentence in self._sentences(reply_text):
            cleaned = self._clean_step(sentence)
            if re.search(r"\b(submit|upload|provide|visit|contact|pay|collect|send)\b", cleaned, flags=re.I):
                return cleaned
        if documents and timeline:
            return f"Submit {', '.join(documents[:3])} to {office} {timeline}."
        if documents:
            return f"Submit {', '.join(documents[:3])} to {office}."
        if timeline:
            return f"Follow up with {office} {timeline}."
        return f"Read the office reply and follow up with {office} if anything is unclear."

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _future_iso(self, days: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    def _delivery_mode(self) -> str:
        return "email" if settings.campus_relay_email_enabled else "queue"

    def _case_delivery_mode(self, case: dict[str, Any]) -> str:
        if case.get("status") in {"draft", "send_failed"}:
            return self._delivery_mode()
        return case.get("delivery_mode") or self._delivery_mode()

    def _timeline_event(
        self,
        event_type: str,
        title: str,
        message: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, str | None]:
        return {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "title": title,
            "message": message,
            "created_at": created_at or self._now(),
        }

    def _append_timeline(
        self,
        case: dict[str, Any],
        event_type: str,
        title: str,
        message: str | None = None,
        created_at: str | None = None,
    ) -> None:
        case["timeline"] = case.get("timeline", [])
        case["timeline"].append(self._timeline_event(event_type, title, message, created_at))

    def _smtp_config(self) -> dict[str, Any] | None:
        host = self._clean_text(settings.campus_relay_smtp_host)
        port_text = self._clean_text(settings.campus_relay_smtp_port)
        username = self._clean_text(settings.campus_relay_smtp_username)
        password = self._clean_text(settings.campus_relay_smtp_password)
        from_email = self._extract_email(settings.campus_relay_from_email)
        from_name = self._clean_text(settings.campus_relay_from_name) or "Campus Process Relay"
        if not all([host, port_text, username, password, from_email]):
            return None
        try:
            port = int(port_text)
        except ValueError:
            return None
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "from_email": from_email,
            "from_name": from_name,
        }

    def _send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        config: dict[str, Any],
    ) -> None:
        message = EmailMessage()
        message["From"] = f"{config['from_name']} <{config['from_email']}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        if config["port"] == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config["host"], config["port"], context=context) as smtp:
                smtp.login(config["username"], config["password"])
                smtp.send_message(message)
            return

        with smtplib.SMTP(config["host"], config["port"], timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)

    def _case_email_subject(self, case: dict[str, Any]) -> str:
        subject = self._clean_text(case.get("generated_message_subject"))
        case_id = case.get("case_id")
        if case_id and case_id not in subject:
            return f"[CampusFlow Case {case_id}] {subject}"
        return subject or f"[CampusFlow Case {case_id}] Campus process request"

    def _case_email_body(self, case: dict[str, Any]) -> str:
        body = self._clean_text(case.get("generated_message_body"))
        case_id = case.get("case_id")
        footer = (
            f"\n\nCampusFlow case ID: {case_id}\n"
            "Please keep this case ID in your reply so the response can be matched."
        )
        if case_id and case_id in body:
            return body
        return f"{body}{footer}"

    def _outbound_metadata(
        self,
        case: dict[str, Any],
        subject: str,
        body: str,
        timestamp: str,
        demo_mode: bool,
        event_key: str,
    ) -> dict[str, Any]:
        return {
            "demo_mode": demo_mode,
            event_key: timestamp,
            "to_office": case.get("routed_to_office"),
            "to_email": case.get("routed_to_email"),
            "subject": subject,
            "body": body,
        }

    def _extract_case_id(self, text: str) -> str | None:
        match = re.search(
            r"(?:CampusFlow\s+Case|case\s+ID|case)\s*[:#-]?\s*([0-9a-fA-F-]{32,36})",
            text,
            flags=re.I,
        )
        if match:
            return match.group(1)
        uuid_match = re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
            text,
        )
        return uuid_match.group(0) if uuid_match else None

    async def _follow_up_message(
        self,
        case: dict[str, Any],
    ) -> tuple[str, str, bool, str, bool, str | None]:
        gemini_key = self._gemini_api_key()
        gemini_model = self._gemini_model()
        self._log_gemini_config(gemini_key, gemini_model)
        if not gemini_key:
            subject, body = self._fallback_follow_up_message(case)
            return subject, body, False, "fallback", True, "GEMINI_API_KEY missing"
        try:
            subject, body = await self._follow_up_with_gemini(case, gemini_key, gemini_model)
            return subject, body, True, "gemini", False, None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Process Relay Gemini follow-up response format unexpected")
            subject, body = self._fallback_follow_up_message(case)
            return subject, body, False, "fallback", True, "Gemini response format unexpected"
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            logger.warning(
                "Process Relay Gemini follow-up HTTP failure: status_code=%s",
                status_code,
            )
            subject, body = self._fallback_follow_up_message(case)
            return subject, body, False, "fallback", True, self._gemini_http_error(status_code)
        except httpx.RequestError as exc:
            logger.warning(
                "Process Relay Gemini follow-up client failure: error_type=%s",
                exc.__class__.__name__,
            )
            subject, body = self._fallback_follow_up_message(case)
            return subject, body, False, "fallback", True, (
                "Gemini request failed: network/client error"
            )
        except Exception as exc:
            logger.warning(
                "Process Relay Gemini follow-up unexpected failure: error_type=%s",
                exc.__class__.__name__,
            )
            subject, body = self._fallback_follow_up_message(case)
            return subject, body, False, "fallback", True, (
                "Gemini request failed: network/client error"
            )

    async def _follow_up_with_gemini(
        self,
        case: dict[str, Any],
        gemini_key: str,
        gemini_model: str,
    ) -> tuple[str, str]:
        prompt = (
            "Draft a concise office-facing follow-up email for this campus case. "
            "Return strict JSON with keys subject and body. Subject format must be: "
            "Follow-up: [CampusFlow Case CASE_ID] <issue type>. Body must begin with "
            "Dear <routed office>, mention the student, the original request, and ask "
            "the office to provide an update or next action. Include the case ID. "
            "Do not write student-facing guidance and do not invent new facts."
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"{prompt}\n\nCase JSON:\n{json.dumps(case, indent=2)}"
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{gemini_model}:generateContent"
                ),
                params={"key": gemini_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
        response.raise_for_status()
        parsed = self._parse_llm_json(self._gemini_text(response.json()))
        subject = self._clean_text(parsed.get("subject"))
        body = self._clean_text(parsed.get("body"))
        if not subject or not body:
            raise ValueError("Gemini follow-up missing subject or body.")
        if self._looks_student_facing(body, case.get("student_name")):
            return self._fallback_follow_up_message(case)
        return subject, body

    def _fallback_follow_up_message(self, case: dict[str, Any]) -> tuple[str, str]:
        case_id = case.get("case_id")
        issue_type = case.get("issue_type") or "campus process request"
        subject = f"Follow-up: [CampusFlow Case {case_id}] {issue_type}"
        student = case.get("student_name") or "[Student Name]"
        body = (
            f"Dear {case.get('routed_to_office', 'Campus office')},\n\n"
            f"This is a follow-up regarding the request sent for student {student}.\n\n"
            f"Case ID: {case_id}\n"
            f"Original request: {case.get('summary', '')}\n\n"
            "Kindly provide an update or the next action required from the student.\n\n"
            "Please reply with the Case ID in the subject/body.\n\n"
            "Regards,\n"
            f"{student}"
        )
        return subject, body

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"documents": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"documents": []}
        if not isinstance(payload, dict):
            return {"documents": []}
        payload.setdefault("documents", [])
        return payload

    def _extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return self._normalize_text("\n".join(pages))

    def _chunk_text(self, text: str, max_chars: int = 1100) -> list[str]:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n{2,}|(?<=\.)\s+(?=[A-Z0-9])", text)
            if paragraph.strip()
        ]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 1 <= max_chars:
                current = f"{current} {paragraph}".strip()
                continue
            if current:
                chunks.append(current)
            current = paragraph[:max_chars]
        if current:
            chunks.append(current)
        return chunks

    def _top_matches(self, question: str, college_id: str) -> list[dict[str, Any]]:
        query_terms = self._terms(question)
        if not query_terms:
            return []

        matches = []
        for document in self._read_payload().get("documents", []):
            if document.get("college_id") != college_id:
                continue
            for chunk in document.get("chunks", []):
                text = chunk.get("text", "")
                score = self._score(query_terms, text)
                if score <= 0:
                    continue
                matches.append(
                    {
                        "score": score,
                        "document_name": document.get("document_name", "campus_policy.pdf"),
                        "chunk_id": chunk.get("chunk_id", ""),
                        "text": text,
                    }
                )
        return sorted(matches, key=lambda item: item["score"], reverse=True)[:4]

    def _score(self, query_terms: list[str], text: str) -> float:
        text_terms = Counter(self._terms(text))
        if not text_terms:
            return 0

        score = 0.0
        for term in query_terms:
            score += text_terms.get(term, 0) * 2
            if len(term) >= 5:
                score += sum(1 for word in text_terms if term in word or word in term)
        return score

    async def _answer_with_gemini(
        self,
        question: str,
        college_id: str,
        matches: list[dict[str, Any]],
        gemini_key: str,
        gemini_model: str,
    ) -> ProcessCopilotAskResponse:
        context = "\n\n".join(
            (
                f"Document: {match['document_name']}\n"
                f"Snippet: {self._snippet(match['text'], 900)}"
            )
            for match in matches
        )
        prompt = (
            "Answer only from uploaded campus policy text when possible. "
            "If the answer is not present, say the document does not contain enough information. "
            "Do not invent offices, deadlines, or rules. "
            "Return practical student-friendly steps. Keep the answer concise. "
            "Return valid JSON with keys: answer, steps, required_documents, "
            "office_or_contact, deadline_or_timeline, email_draft."
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt}\n\n"
                                f"College ID: {college_id}\n"
                                f"Question: {question}\n\n"
                                f"Uploaded campus policy text:\n{context}"
                            )
                        }
                    ],
                },
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{gemini_model}:generateContent"
                ),
                params={"key": gemini_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
        response.raise_for_status()
        content = self._gemini_text(response.json())
        parsed = self._parse_llm_json(content)
        return ProcessCopilotAskResponse(
            answer=str(parsed.get("answer") or ""),
            steps=self._dedupe_list(self._string_list(parsed.get("steps")))[:5],
            required_documents=self._dedupe_list(
                self._string_list(parsed.get("required_documents"))
            )[:8],
            office_or_contact=parsed.get("office_or_contact"),
            deadline_or_timeline=parsed.get("deadline_or_timeline"),
            email_draft=parsed.get("email_draft"),
            sources_used=self._source_labels(matches),
            llm_used=True,
            llm_provider="gemini",
            llm_error=None,
            fallback_mode=False,
            used_college_id=college_id,
        )

    def _fallback_answer(
        self,
        question: str,
        college_id: str,
        matches: list[dict[str, Any]],
        llm_error: str | None = None,
    ) -> ProcessCopilotAskResponse:
        matched_texts = [match["text"] for match in matches]
        combined = " ".join(matched_texts)
        office = self._extract_office(matched_texts)
        documents = self._extract_required_documents(combined)
        timeline = self._extract_timeline(combined)
        steps = self._extract_steps(matched_texts, documents, office)
        email_draft = self._email_draft(question, office)

        return ProcessCopilotAskResponse(
            answer=(
                "Based on the uploaded policy text, here is the likely process. "
                "Verify with your college office before acting."
            ),
            steps=steps,
            required_documents=documents,
            office_or_contact=office,
            deadline_or_timeline=timeline,
            email_draft=email_draft,
            sources_used=self._source_labels(matches),
            llm_used=False,
            llm_provider="fallback",
            llm_error=llm_error,
            fallback_mode=True,
            used_college_id=college_id,
        )

    def _extract_steps(
        self,
        matched_texts: list[str],
        documents: list[str],
        office: str | None,
    ) -> list[str]:
        action_words = (
            "apply",
            "submit",
            "inform",
            "contact",
            "attach",
            "fill",
            "obtain",
            "report",
            "request",
            "meet",
        )
        steps: list[str] = []
        candidates = []
        for text in matched_texts:
            candidates.extend(self._sentences(text))

        for sentence in candidates:
            cleaned = self._clean_step(sentence)
            if not cleaned:
                continue
            if any(word in cleaned.lower() for word in action_words):
                steps.append(cleaned)
            if len(steps) == 5:
                break
        steps = self._dedupe_list(steps)

        if not steps:
            steps = ["Review the uploaded policy snippet that matched your question."]
        if documents and len(steps) < 5:
            steps.append(f"Keep ready: {', '.join(documents[:3])}.")
        if office and len(steps) < 5:
            steps.append(f"Contact {office} for submission and confirmation.")
        if len(steps) < 3:
            steps.append("Ask your department office to confirm the exact form and timeline.")

        return self._dedupe_list(steps)[:5]

    def _extract_required_documents(self, text: str) -> list[str]:
        patterns = [
            r"\b(medical certificate)\b",
            r"\b(application form)\b",
            r"\b(parent consent(?: application)?)\b",
            r"\b(fee receipt)\b",
            r"\b(identity card|id card)\b",
            r"\b(doctor certificate)\b",
            r"\b(bonafide application(?: form)?)\b",
            r"\b(internship offer letter)\b",
            r"\b(noc application(?: form)?)\b",
            r"\b(no objection certificate|noc)\b",
            r"\b(hostel room change form)\b",
        ]
        found = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.I):
                value = self._title_case_document(match.group(1))
                if value not in found:
                    found.append(value)
        return found[:8]

    def _extract_office(self, matched_texts: list[str]) -> str | None:
        office_names = [
            "Academic Office",
            "Examination Office",
            "Controller of Examinations",
            "Department Office",
            "Student Section",
            "Hostel Office",
            "Training and Placement Office",
            "Placement Cell",
            "Dean Academics",
            "Registrar",
            "HOD",
            "Warden",
            "Administrative Office",
            "Accounts Office",
        ]
        combined = "\n".join(matched_texts)
        for name in office_names:
            if re.search(rf"\b{re.escape(name)}\b", combined, flags=re.I):
                return name

        for line in self._source_lines(matched_texts):
            if "office mapping" in line.lower():
                for name in office_names:
                    if re.search(rf"\b{re.escape(name)}\b", line, flags=re.I):
                        return name
                continue

            match = re.search(
                r"\b(?:submit(?:ted)? to|contact|approach|report to|office|section|cell)\s*[:\-]?\s*([A-Z][A-Za-z &/-]{2,50})",
                line,
            )
            if match:
                value = match.group(1).strip(" .,:;-")
                if value.lower() not in {"mapping", "office mapping"}:
                    return value
        return None

    def _extract_timeline(self, text: str) -> str | None:
        match = re.search(
            r"\b(?:within|before|after|by)\s+\d{1,2}\s+(?:day|days|working days|hours|weeks)\b",
            text,
            flags=re.I,
        )
        if match:
            return match.group(0)
        return None

    def _email_draft(self, question: str, office: str | None) -> str | None:
        if not office:
            return None
        return (
            f"Subject: Request for guidance regarding {question[:60]}\n\n"
            f"Dear {office},\n\n"
            "I am writing to request guidance on the required campus process. "
            "Please let me know the correct form, documents, and timeline I should follow.\n\n"
            "Regards,\n"
            "[Your Name]"
        )

    def _source_labels(self, matches: list[dict[str, Any]]) -> list[str]:
        labels = []
        for match in matches:
            snippet = self._snippet(match["text"], 120)
            label = f"{match['document_name']}: {snippet}"
            if label not in labels:
                labels.append(label[:180])
            if len(labels) == 3:
                break
        return labels

    def _normalize_text(self, text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    def _terms(self, text: str) -> list[str]:
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "what",
            "how",
            "should",
            "college",
            "campus",
            "student",
            "students",
            "apply",
            "application",
        }
        return [
            word
            for word in re.findall(r"[a-z0-9]{2,}", text.lower())
            if word not in stopwords
        ]

    def _clean_college_id(self, college_id: str | None) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", (college_id or "default").strip())
        return cleaned.strip("-") or "default"

    def _snippet(self, text: str, limit: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."

    def _sentences(self, text: str) -> list[str]:
        chunks = re.split(r"(?:\n|[•·]|\b\d+\.\s+|(?<=[.;])\s+)", text)
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def _source_lines(self, matched_texts: list[str]) -> list[str]:
        lines = []
        for text in matched_texts:
            lines.extend(self._sentences(text))
        return lines

    def _clean_step(self, sentence: str) -> str:
        cleaned = re.sub(r"\s+", " ", sentence).strip(" -•\n\t")
        cleaned = re.sub(r"^(process|steps?|procedure|office mapping)\s*[:\-]\s*", "", cleaned, flags=re.I)
        if len(cleaned) > 150:
            cleaned = f"{cleaned[:147].rstrip()}..."
        return cleaned

    def _title_case_document(self, value: str) -> str:
        replacements = {"id": "ID", "noc": "NOC"}
        words = []
        for word in value.lower().split():
            words.append(replacements.get(word, word.capitalize()))
        return " ".join(words)

    def _dedupe_list(self, values: list[str]) -> list[str]:
        seen = set()
        deduped = []
        for value in values:
            cleaned = re.sub(r"\s+", " ", str(value)).strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    def _gemini_api_key(self) -> str | None:
        key = (settings.gemini_api_key or "").strip()
        return key or None

    def _gemini_model(self) -> str:
        return (settings.gemini_model or "").strip() or DEFAULT_GEMINI_MODEL

    def _log_gemini_config(self, gemini_key: str | None, gemini_model: str) -> None:
        logger.info(
            (
                "Process Copilot Gemini config: GEMINI_API_KEY loaded=%s "
                "length=%s model=%s"
            ),
            bool(gemini_key),
            len(gemini_key or ""),
            gemini_model,
        )

    def _gemini_http_error(self, status_code: int | None) -> str:
        if status_code == 400:
            return "Gemini HTTP 400: invalid request"
        if status_code == 403:
            return "Gemini HTTP 403: API key rejected or API not enabled"
        if status_code == 429:
            return (
                "Gemini HTTP 429: quota or rate limit. "
                "Try again later or use another Gemini project/key/model."
            )
        if status_code is not None:
            return f"Gemini HTTP {status_code}: request failed"
        return "Gemini request failed: network/client error"

    def _parse_llm_json(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        return json.loads(cleaned)

    def _gemini_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if part.get("text")]
        if not text_parts:
            raise ValueError("Gemini returned no text.")
        return "\n".join(text_parts)

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
