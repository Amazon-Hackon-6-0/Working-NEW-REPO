from datetime import datetime, timezone
import os
from threading import RLock
from typing import Any

from app.services.campusbuddy.ai_service import (
    DEFAULT_MODEL,
    _log_safe_gemini_error,
    _parse_json_response,
    _safe_gemini_error,
)
from app.services.campusbuddy.complaint_classifier_service import classify_complaint
from app.services.campusbuddy.discord_bridge import send_complaint_escalation_to_discord
from app.services.campusbuddy.memory_service import require_user_id
from app.services.campusbuddy.sqlite_store import create_sequential_record, list_records, upsert_record


COMPLAINT_ESCALATION_THRESHOLD = 3
DISCORD_DESTINATIONS = {
    "mess_committee": "#mess-committee",
    "hostel_committee": "#hostel-committee",
    "maintenance_team": "#maintenance-team",
    "tech_support": "#tech-support",
    "academic_committee": "#academic-committee",
    "transport_committee": "#transport-committee",
    "student_council": "#student-council",
}
COMPLAINT_KIND = "complaint"
ESCALATION_KIND = "complaint_escalation"
COMPLAINT_LOCK = RLock()


def submit_complaint(student_id: str, text: str) -> dict:
    student_id = require_user_id(student_id)
    classification = classify_complaint(text)
    anonymous_student_alias = anonymous_name_for_student(student_id)

    with COMPLAINT_LOCK:
        duplicate_student_topic = has_student_reported_topic(student_id, classification["topic_key"])

        def build_complaint(complaint_id: str) -> dict:
            return {
                "complaint_id": complaint_id,
                "student_id": student_id,
                "anonymous_student_alias": anonymous_student_alias,
                "raw_text": text,
                "category": classification["category"],
                "topic_key": classification["topic_key"],
                "sentiment": classification["sentiment"],
                "urgency": classification["urgency"],
                "target_group": classification["target_group"],
                "normalized_issue": classification["normalized_issue"],
                "generalized_summary": classification["generalized_summary"],
                "source": classification["source"],
                "fallback_reason": classification["fallback_reason"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        complaint = create_sequential_record(COMPLAINT_KIND, "complaint", build_complaint)
        similar_complaint_count = get_unique_student_count_for_topic(complaint["topic_key"])
        ready_for_escalation = similar_complaint_count >= COMPLAINT_ESCALATION_THRESHOLD
        escalation = handle_threshold_escalation(complaint, similar_complaint_count, ready_for_escalation)

    return {
        "complaint_id": complaint["complaint_id"],
        "stored_anonymously": True,
        "source": complaint["source"],
        "fallback_reason": complaint["fallback_reason"],
        "category": complaint["category"],
        "topic_key": complaint["topic_key"],
        "sentiment": complaint["sentiment"],
        "urgency": complaint["urgency"],
        "target_group": complaint["target_group"],
        "similar_complaint_count": similar_complaint_count,
        "threshold": COMPLAINT_ESCALATION_THRESHOLD,
        "ready_for_escalation": ready_for_escalation,
        "duplicate_student_topic": duplicate_student_topic,
        "escalation_created": escalation["created"],
        "escalation_id": escalation["item"]["escalation_id"] if escalation["item"] else None,
        "mock_discord_destination": escalation["item"]["destination"] if escalation["item"] else None,
        "generalized_summary": escalation["item"]["generalized_summary"] if escalation["item"] else None,
        "summary_source": escalation["item"]["summary_source"] if escalation["item"] else None,
        "summary_fallback_reason": escalation["item"]["summary_fallback_reason"] if escalation["item"] else None,
        "message": escalation_message(ready_for_escalation),
    }


def handle_threshold_escalation(complaint: dict, complaint_count: int, ready_for_escalation: bool) -> dict:
    if not ready_for_escalation:
        return {"created": False, "item": None}

    existing_escalation = get_escalation_by_topic_key(complaint["topic_key"])
    if existing_escalation:
        ensure_escalation_discord_delivery(existing_escalation)
        return {"created": False, "item": existing_escalation}

    escalation = create_mock_discord_escalation(complaint, complaint_count)
    ensure_escalation_discord_delivery(escalation)
    save_mock_discord_escalation(escalation)
    return {"created": True, "item": escalation}


def ensure_escalation_discord_delivery(escalation: dict) -> dict:
    if escalation.get("discord_delivery", {}).get("sent"):
        return escalation

    discord_result = send_complaint_escalation_to_discord(escalation)
    escalation["discord_delivery"] = discord_result
    if discord_result.get("sent"):
        escalation["status"] = "sent_to_discord"
        escalation["discord_channel_id"] = discord_result.get("channel_id")
    save_mock_discord_escalation(escalation)
    return escalation


def create_mock_discord_escalation(complaint: dict, complaint_count: int) -> dict:
    target_group = complaint["target_group"]
    summary_result = generate_escalation_summary(
        category=complaint["category"],
        topic_key=complaint["topic_key"],
        target_group=target_group,
        complaint_count=complaint_count,
        normalized_issue=complaint.get("normalized_issue"),
    )
    def build_escalation(escalation_id: str) -> dict:
        return {
            "escalation_id": escalation_id,
            "topic_key": complaint["topic_key"],
            "category": complaint["category"],
            "target_group": target_group,
            "complaint_count": complaint_count,
            "generalized_summary": summary_result["summary"],
            "summary_source": summary_result["source"],
            "summary_fallback_reason": summary_result["fallback_reason"],
            "status": "queued_mock_discord",
            "destination": DISCORD_DESTINATIONS.get(target_group, "#student-council"),
        }

    return create_sequential_record(ESCALATION_KIND, "escalation", build_escalation)


def get_escalation_by_topic_key(topic_key: str) -> dict | None:
    for escalation in list_mock_discord_escalations():
        if escalation["topic_key"] == topic_key:
            return escalation
    return None


def get_topic_complaint_count(topic_key: str) -> int:
    return sum(1 for complaint in list_complaints_internal() if complaint["topic_key"] == topic_key)


def get_unique_student_count_for_topic(topic_key: str) -> int:
    return len(
        {
            complaint["student_id"]
            for complaint in list_complaints_internal()
            if complaint["topic_key"] == topic_key
        }
    )


def has_student_reported_topic(student_id: str, topic_key: str) -> bool:
    return any(
        complaint["student_id"] == student_id and complaint["topic_key"] == topic_key
        for complaint in list_complaints_internal()
    )


def list_mock_discord_escalations() -> list[dict]:
    return list_records(ESCALATION_KIND)


def list_complaints_internal() -> list[dict]:
    return list_records(COMPLAINT_KIND)


def retry_pending_discord_escalations() -> dict:
    retried = []
    for escalation in list_mock_discord_escalations():
        if escalation.get("discord_delivery", {}).get("sent"):
            continue
        retried.append(ensure_escalation_discord_delivery(escalation))
    return {"retried": len(retried), "outbox": list_mock_discord_escalations()}


def save_complaint(complaint: dict) -> None:
    upsert_record(COMPLAINT_KIND, complaint["complaint_id"], complaint)


def save_mock_discord_escalation(escalation: dict) -> None:
    upsert_record(ESCALATION_KIND, escalation["escalation_id"], escalation)


def generate_escalation_summary(
    category: str,
    topic_key: str,
    target_group: str,
    complaint_count: int,
    normalized_issue: str | None = None,
) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "summary": fallback_escalation_summary(category, topic_key),
            "source": "fallback",
            "fallback_reason": "missing_gemini_api_key",
        }

    try:
        gemini_result = generate_gemini_escalation_summary(
            api_key=api_key,
            category=category,
            topic_key=topic_key,
            target_group=target_group,
            complaint_count=complaint_count,
            normalized_issue=normalized_issue,
        )
        summary = str(gemini_result.get("generalized_summary") or "").strip()
        if not summary:
            return {
                "summary": fallback_escalation_summary(category, topic_key),
                "source": "fallback",
                "fallback_reason": "gemini_empty_summary",
            }
        return {
            "summary": summary,
            "source": "gemini",
            "fallback_reason": None,
        }
    except Exception as exc:
        safe_error = _safe_gemini_error(exc)
        _log_safe_gemini_error("complaint_escalation_summary", safe_error)
        return {
            "summary": fallback_escalation_summary(category, topic_key),
            "source": "fallback",
            "fallback_reason": safe_error,
        }


def generate_gemini_escalation_summary(
    api_key: str,
    category: str,
    topic_key: str,
    target_group: str,
    complaint_count: int,
    normalized_issue: str | None = None,
) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_escalation_summary_prompt(
            category=category,
            topic_key=topic_key,
            target_group=target_group,
            complaint_count=complaint_count,
            normalized_issue=normalized_issue,
        ),
    )
    return _parse_json_response(response.text or "")


def build_escalation_summary_prompt(
    category: str,
    topic_key: str,
    target_group: str,
    complaint_count: int,
    normalized_issue: str | None = None,
) -> str:
    return f"""
Generate a short generalized escalation summary for a campus committee.

Privacy rules:
- Do not mention student IDs.
- Do not quote or expose individual raw complaints.
- Do not say "one student".
- Say "Several students" or "Multiple students".
- Use only the safe aggregate fields below.
- Keep the summary 2-3 sentences.
- Return strict JSON only.
- Do not wrap JSON in markdown fences.

Safe aggregate fields:
- category: {category}
- topic_key: {topic_key}
- target_group: {target_group}
- complaint_count: {complaint_count}
- normalized_issue: {normalized_issue or "recurring campus concern"}

Summary requirements:
- Mention the issue category in natural language.
- Mention common concerns generally.
- Mention that students are requesting review or follow-up by the relevant committee or team.

Return exactly:
{{
  "generalized_summary": "..."
}}
""".strip()


def generalized_escalation_summary(complaint: dict) -> str:
    return fallback_escalation_summary(complaint["category"], complaint["topic_key"])


def fallback_escalation_summary(category: str, topic_key: str | None = None) -> str:
    if topic_key == "saturday_dinner_food_quality":
        return (
            "Several students reported dissatisfaction with Saturday night hostel food. "
            "Common concerns include food quality, freshness, and taste. "
            "Students are requesting improvement in weekend dinner quality."
        )
    summaries = {
        "wifi": (
            "Several students reported recurring hostel WiFi connectivity issues. "
            "Common concerns include slow internet speed, unstable connection, and frequent disconnections. "
            "Students are requesting review by the technical support team."
        ),
        "maintenance": (
            "Several students reported hostel maintenance issues. "
            "Common concerns include broken fixtures, electrical issues, or repair delays. "
            "Students are requesting timely follow-up by the maintenance team."
        ),
        "mess_food": (
            "Several students reported concerns about mess food quality. "
            "Common concerns include taste, freshness, and meal quality. "
            "Students are requesting review by the mess committee."
        ),
        "hostel": (
            "Several students reported hostel facility concerns. "
            "Common concerns include room conditions, hygiene, or shared facilities. "
            "Students are requesting review by the hostel committee."
        ),
        "academic": (
            "Several students reported academic coordination concerns. "
            "Common concerns include schedules, classes, exams, or communication gaps. "
            "Students are requesting review by the academic committee."
        ),
        "transport": (
            "Several students reported campus transport concerns. "
            "Common concerns include delays, availability, or route issues. "
            "Students are requesting review by the transport committee."
        ),
        "events": (
            "Several students reported concerns related to campus event coordination. "
            "Common concerns include communication, scheduling, or management. "
            "Students are requesting review by the student council."
        ),
        "general": (
            "Several students reported a recurring campus concern. "
            "Students are requesting review by the student council or relevant campus authority."
        ),
    }
    return summaries.get(category, summaries["general"])


def escalation_message(ready_for_escalation: bool) -> str:
    if ready_for_escalation:
        return "Multiple similar anonymous complaints have been detected. A generalized escalation summary can now be prepared."
    return "Complaint recorded anonymously. It will be escalated only if multiple students report a similar issue."


def anonymous_name_for_student(student_id: str) -> str:
    suffix = student_id.split("_")[-1]
    return f"Anonymous Student {suffix}"
