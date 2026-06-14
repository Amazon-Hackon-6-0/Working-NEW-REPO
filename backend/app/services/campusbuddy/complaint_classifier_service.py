import os
import re
from typing import Any

from app.services.campusbuddy.ai_service import (
    DEFAULT_MODEL,
    _log_safe_gemini_error,
    _parse_json_response,
    _safe_gemini_error,
)


CATEGORY_TARGET_GROUPS = {
    "mess_food": "mess_committee",
    "hostel": "hostel_committee",
    "maintenance": "maintenance_team",
    "wifi": "tech_support",
    "academic": "academic_committee",
    "transport": "transport_committee",
    "events": "student_council",
    "general": "student_council",
}

KEYWORD_CATEGORIES = [
    ("wifi", ["wifi", "wi-fi", "internet", "network", "speed", "disconnect", "connectivity"]),
    ("maintenance", ["water", "light", "bulb", "electricity", "fan", "tap", "leak", "repair", "broken"]),
    ("mess_food", ["food", "mess", "canteen", "meal", "dinner", "lunch", "breakfast", "paneer", "roti", "rice", "stale", "taste", "quality"]),
    ("hostel", ["hostel", "room", "warden", "roommate", "washroom", "bathroom", "cleaning", "hygiene"]),
    ("academic", ["class", "teacher", "assignment", "exam"]),
    ("transport", ["bus", "transport", "auto", "shuttle"]),
    ("events", ["fest", "event", "club"]),
]


def classify_complaint(text: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return normalize_complaint_topic(
            text,
            _fallback_complaint_classification(text, "missing_gemini_api_key"),
        )

    try:
        gemini_result = _generate_gemini_complaint_classification(text, api_key)
        gemini_category = str(gemini_result.get("category") or "").strip()
        if gemini_category not in CATEGORY_TARGET_GROUPS:
            return normalize_complaint_topic(
                text,
                _fallback_complaint_classification(text, "invalid_gemini_category"),
            )
        normalized = _normalize_complaint_classification(gemini_result, text)
        normalized["source"] = "gemini"
        normalized["fallback_reason"] = None
        return normalize_complaint_topic(text, normalized)
    except Exception as exc:
        safe_error = _safe_gemini_error(exc)
        _log_safe_gemini_error("complaint_classifier", safe_error)
        return normalize_complaint_topic(
            text,
            _fallback_complaint_classification(text, safe_error),
        )


def _generate_gemini_complaint_classification(text: str, api_key: str) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=_build_complaint_prompt(text),
    )
    return _parse_json_response(response.text or "")


def _build_complaint_prompt(text: str) -> str:
    return f"""
You classify private CampusBuddy student complaints for anonymous pattern-based escalation.

Privacy rules:
- Do not include student identity, roll number, email, phone, room number, or personal details.
- Do not quote the raw complaint directly.
- Produce a generalized committee-safe summary.
- Return strict JSON only.
- Do not wrap JSON in markdown fences.
- Use broad, stable topic_key values for clustering. Do not create overly specific keys from dates, single food items, room details, or one-off wording.

Allowed categories and target groups:
- mess_food -> mess_committee
- hostel -> hostel_committee
- maintenance -> maintenance_team
- wifi -> tech_support
- academic -> academic_committee
- transport -> transport_committee
- events -> student_council
- general -> student_council

Return exactly this JSON shape:
{{
  "category": "one allowed category",
  "topic_key": "short_snake_case_issue_key",
  "sentiment": "negative | neutral | positive",
  "urgency": "low | normal | high",
  "target_group": "matching target group",
  "normalized_issue": "short issue title",
  "generalized_summary": "committee-safe summary without raw complaint text"
}}

Topic key guidance:
- Mess food taste, freshness, stale food, dinner/lunch quality -> "mess_food_quality"
- Hostel WiFi slow, internet disconnecting, network not working -> "hostel_wifi_connectivity"
- Fan not working, room fan broken, electrical issue with fan -> "hostel_room_fan_maintenance"
- Broken lights, bulb, electricity in hostel room -> "hostel_room_electrical_maintenance"
- Water/tap/leak repair issues -> "hostel_water_maintenance"
- Washroom, bathroom, hygiene, cleaning issues -> "hostel_facility_hygiene"
- Exam timetable or schedule confusion -> "exam_schedule_confusion"
- Assignment deadline or submission confusion -> "assignment_deadline_confusion"
- Bus/shuttle delays -> "campus_transport_delay"
- Fest/event/club mismanagement -> "event_management_concern"

Bad topic keys:
- saturday_night_paneer_stale_issue_very_bad
- wifi_disconnect_today_student_room
- room_204_fan_broken_specific

Student complaint:
{text}
""".strip()


def _fallback_complaint_classification(text: str, fallback_reason: str) -> dict[str, Any]:
    category = _fallback_category(text)
    topic_key = _fallback_topic_key(text, category)
    target_group = CATEGORY_TARGET_GROUPS[category]
    sentiment = _fallback_sentiment(text)
    urgency = _fallback_urgency(text)
    normalized_issue = _fallback_normalized_issue(topic_key, category)

    return {
        "source": "fallback",
        "fallback_reason": fallback_reason,
        "category": category,
        "topic_key": topic_key,
        "sentiment": sentiment,
        "urgency": urgency,
        "target_group": target_group,
        "normalized_issue": normalized_issue,
        "generalized_summary": _fallback_generalized_summary(topic_key, category),
    }


def _normalize_complaint_classification(classification: dict[str, Any], text: str) -> dict[str, Any]:
    category = str(classification.get("category") or _fallback_category(text)).strip()
    if category not in CATEGORY_TARGET_GROUPS:
        category = _fallback_category(text)

    topic_key = _safe_topic_key(classification.get("topic_key") or _fallback_topic_key(text, category))
    if _topic_key_is_too_specific(topic_key):
        topic_key = _safe_topic_key(classification.get("normalized_issue") or _fallback_topic_key(text, category))
    target_group = str(classification.get("target_group") or CATEGORY_TARGET_GROUPS[category]).strip()
    if target_group != CATEGORY_TARGET_GROUPS[category]:
        target_group = CATEGORY_TARGET_GROUPS[category]

    sentiment = str(classification.get("sentiment") or _fallback_sentiment(text)).strip().lower()
    if sentiment not in {"negative", "neutral", "positive"}:
        sentiment = "negative"

    urgency = str(classification.get("urgency") or _fallback_urgency(text)).strip().lower()
    if urgency not in {"low", "normal", "high"}:
        urgency = "normal"

    normalized_issue = str(
        classification.get("normalized_issue") or _fallback_normalized_issue(topic_key, category)
    ).strip()
    generalized_summary = str(
        classification.get("generalized_summary") or _fallback_generalized_summary(topic_key, category)
    ).strip()

    return {
        "category": category,
        "topic_key": topic_key,
        "sentiment": sentiment,
        "urgency": urgency,
        "target_group": target_group,
        "normalized_issue": normalized_issue,
        "generalized_summary": generalized_summary,
    }


def normalize_complaint_topic(text: str, classification: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(classification)
    lowered = text.lower()

    if _is_saturday_dinner_mess_complaint(lowered) and _safe_topic_key(classification.get("topic_key")) == "saturday_dinner_food_quality":
        return _override_topic(
            normalized,
            category="mess_food",
            topic_key="saturday_dinner_food_quality",
            target_group="mess_committee",
        )

    if _has_any(lowered, ["wifi", "wi-fi", "internet", "network", "speed", "disconnect", "connection", "connectivity"]):
        return _override_topic(
            normalized,
            category="wifi",
            topic_key="hostel_wifi_connectivity",
            target_group="tech_support",
        )

    if _has_any(lowered, ["fan"]):
        return _override_topic(
            normalized,
            category="maintenance",
            topic_key="hostel_room_fan_maintenance",
            target_group="maintenance_team",
        )

    if _has_any(lowered, ["light", "bulb", "electricity"]):
        return _override_topic(
            normalized,
            category="maintenance",
            topic_key="hostel_room_electrical_maintenance",
            target_group="maintenance_team",
        )

    if _has_any(lowered, ["water", "tap", "leak", "repair", "broken"]):
        return _override_topic(
            normalized,
            category="maintenance",
            topic_key="hostel_water_maintenance",
            target_group="maintenance_team",
        )

    if _has_any(lowered, ["mess", "food", "canteen", "meal", "lunch", "dinner", "breakfast", "paneer", "stale", "taste", "quality"]):
        return _override_topic(
            normalized,
            category="mess_food",
            topic_key="mess_food_quality",
            target_group="mess_committee",
        )

    if _has_any(lowered, ["hostel", "room", "washroom", "bathroom", "cleaning", "hygiene"]):
        topic_key = "hostel_facility_hygiene" if _has_any(lowered, ["washroom", "bathroom", "cleaning", "hygiene"]) else "hostel_facility_issue"
        return _override_topic(
            normalized,
            category="hostel",
            topic_key=topic_key,
            target_group="hostel_committee",
        )

    if _has_any(lowered, ["exam", "timetable", "schedule"]):
        return _override_topic(
            normalized,
            category="academic",
            topic_key="exam_schedule_confusion",
            target_group="academic_committee",
        )

    if _has_any(lowered, ["assignment", "deadline", "submission"]):
        return _override_topic(
            normalized,
            category="academic",
            topic_key="assignment_deadline_confusion",
            target_group="academic_committee",
        )

    if _has_any(lowered, ["bus", "transport", "auto", "shuttle", "delay", "late"]):
        return _override_topic(
            normalized,
            category="transport",
            topic_key="campus_transport_delay",
            target_group="transport_committee",
        )

    if _has_any(lowered, ["fest", "event", "club"]):
        return _override_topic(
            normalized,
            category="events",
            topic_key="event_management_concern",
            target_group="student_council",
        )

    return normalized


def _override_topic(classification: dict[str, Any], category: str, topic_key: str, target_group: str) -> dict[str, Any]:
    classification["category"] = category
    classification["topic_key"] = topic_key
    classification["target_group"] = target_group
    classification["normalized_issue"] = _fallback_normalized_issue(topic_key, category)
    classification["generalized_summary"] = _fallback_generalized_summary(topic_key, category)
    return classification


def _is_saturday_dinner_mess_complaint(text: str) -> bool:
    saturday_context = _has_any(text, ["saturday", "sat night", "weekend"])
    mess_context = _has_any(text, ["mess", "food", "dinner", "paneer", "stale", "quality", "taste"])
    return saturday_context and mess_context


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _fallback_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in KEYWORD_CATEGORIES:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "general"


def _fallback_topic_key(text: str, category: str) -> str:
    lowered = text.lower()
    saturday_terms = ["saturday", "sat night", "weekend"]
    dinner_terms = ["dinner", "night food", "night mess"]
    food_quality_terms = ["food", "mess", "paneer", "stale", "quality", "taste", "bad"]
    if (
        category == "mess_food"
        and any(term in lowered for term in saturday_terms)
        and (any(term in lowered for term in dinner_terms) or any(term in lowered for term in food_quality_terms))
    ):
        return "saturday_dinner_food_quality"

    if category == "mess_food":
        return "mess_food_quality"
    if category == "wifi":
        return "hostel_wifi_connectivity"
    if category == "maintenance":
        if "fan" in lowered:
            return "hostel_room_fan_maintenance"
        if any(term in lowered for term in ["light", "bulb", "electricity"]):
            return "hostel_room_electrical_maintenance"
        if any(term in lowered for term in ["water", "tap", "leak"]):
            return "hostel_water_maintenance"
        return "hostel_maintenance_issue"
    if category == "hostel":
        if any(term in lowered for term in ["washroom", "bathroom", "cleaning", "hygiene"]):
            return "hostel_facility_hygiene"
        return "hostel_facility_issue"
    if category == "academic":
        if any(term in lowered for term in ["exam", "timetable", "schedule"]):
            return "exam_schedule_confusion"
        if any(term in lowered for term in ["assignment", "deadline", "submission"]):
            return "assignment_deadline_confusion"
        return "academic_concern"
    if category == "transport":
        return "campus_transport_delay"
    if category == "events":
        return "event_management_concern"
    return "general_student_concern"


def _fallback_sentiment(text: str) -> str:
    lowered = text.lower()
    negative_terms = ["bad", "poor", "stale", "broken", "not working", "problem", "issue", "complaint"]
    positive_terms = ["good", "great", "resolved", "better"]
    if any(term in lowered for term in negative_terms):
        return "negative"
    if any(term in lowered for term in positive_terms):
        return "positive"
    return "neutral"


def _fallback_urgency(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["urgent", "unsafe", "emergency", "sick", "danger"]):
        return "high"
    if any(term in lowered for term in ["minor", "small", "sometimes"]):
        return "low"
    return "normal"


def _fallback_normalized_issue(topic_key: str, category: str) -> str:
    issue_titles = {
        "saturday_dinner_food_quality": "Saturday dinner food quality concern",
        "mess_food_quality": "Mess food quality concern",
        "hostel_wifi_connectivity": "Hostel Wi-Fi connectivity concern",
        "wifi_connectivity": "Wi-Fi connectivity concern",
        "hostel_room_fan_maintenance": "Hostel room fan maintenance issue",
        "hostel_room_electrical_maintenance": "Hostel room electrical maintenance issue",
        "hostel_water_maintenance": "Hostel water maintenance issue",
        "hostel_maintenance_issue": "Hostel maintenance issue",
        "campus_maintenance": "Campus maintenance concern",
        "hostel_facility_hygiene": "Hostel facility hygiene concern",
        "hostel_facility_issue": "Hostel facility issue",
        "hostel_concern": "Hostel concern",
        "exam_schedule_confusion": "Exam schedule confusion",
        "assignment_deadline_confusion": "Assignment deadline confusion",
        "campus_transport_delay": "Campus transport delay concern",
        "event_management_concern": "Event management concern",
        "academic_concern": "Academic concern",
        "transport_concern": "Transport concern",
        "events_concern": "Events concern",
        "general_student_concern": "General student concern",
    }
    return issue_titles.get(topic_key, f"{category.replace('_', ' ').title()} concern")


def _fallback_generalized_summary(topic_key: str, category: str) -> str:
    if topic_key == "saturday_dinner_food_quality":
        return "Students are reporting dissatisfaction with Saturday night hostel food quality, including freshness and taste concerns."
    if topic_key == "hostel_wifi_connectivity":
        return "Students are reporting hostel Wi-Fi connectivity issues, including slow internet speed and frequent disconnections."
    if topic_key == "hostel_room_fan_maintenance":
        return "Students are reporting hostel room fan maintenance issues and are requesting repair support."
    if topic_key == "hostel_room_electrical_maintenance":
        return "Students are reporting hostel room electrical maintenance issues involving lights, bulbs, or electricity."
    if topic_key == "hostel_water_maintenance":
        return "Students are reporting hostel water or tap maintenance issues that need repair attention."
    if topic_key == "hostel_maintenance_issue":
        return "Students are reporting hostel maintenance issues that need repair or facilities team attention."
    if topic_key == "hostel_facility_hygiene":
        return "Students are reporting hostel facility hygiene concerns involving washrooms, bathrooms, cleaning, or shared spaces."
    if topic_key == "hostel_facility_issue":
        return "Students are reporting hostel facility concerns related to rooms, washrooms, cleaning, or hygiene."
    if topic_key == "exam_schedule_confusion":
        return "Students are reporting confusion about exam schedules or timetables and are requesting clearer academic communication."
    if topic_key == "assignment_deadline_confusion":
        return "Students are reporting confusion about assignment deadlines or submissions and are requesting clearer academic guidance."
    if topic_key == "campus_transport_delay":
        return "Students are reporting campus transport delays or availability concerns and are requesting review."
    if topic_key == "event_management_concern":
        return "Students are reporting concerns about event, fest, or club management and are requesting student council review."
    summaries = {
        "mess_food": "Students are reporting concerns about mess food quality and are requesting improvement.",
        "hostel": "Students are reporting hostel-related concerns that need review by the hostel committee.",
        "maintenance": "Students are reporting campus maintenance issues that need attention.",
        "wifi": "Students are reporting Wi-Fi or internet connectivity issues that need technical support.",
        "academic": "Students are reporting academic concerns that may need committee review.",
        "transport": "Students are reporting transport-related concerns that need review.",
        "events": "Students are reporting concerns related to events or clubs.",
        "general": "Students are reporting a general campus concern that needs review.",
    }
    return summaries.get(category, summaries["general"])


def _safe_topic_key(value: Any) -> str:
    topic_key = str(value or "general_student_concern").strip().lower()
    topic_key = re.sub(r"[^a-z0-9]+", "_", topic_key)
    topic_key = re.sub(r"_+", "_", topic_key).strip("_")
    return topic_key or "general_student_concern"


def _topic_key_is_too_specific(topic_key: str) -> bool:
    if len(topic_key) > 48:
        return True
    tokens = topic_key.split("_")
    noisy_tokens = {"today", "yesterday", "specific", "student", "room", "very", "bad", "properly"}
    return len(tokens) > 6 or any(token.isdigit() for token in tokens) or bool(set(tokens) & noisy_tokens)
