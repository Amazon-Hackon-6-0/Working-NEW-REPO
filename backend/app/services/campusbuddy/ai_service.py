import json
import logging
import os
import re
from typing import Any

from app.agents.campusbuddy.friend_agent import create_friend_response
from app.agents.campusbuddy.classifier_agent import classify_student_message
from app.agents.campusbuddy.escalation_agent import anonymous_committee_message


DEFAULT_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)
CONNECTOR_CATEGORIES = {
    "academic_help",
    "technical_help",
    "project_help",
    "career_help",
    "campus_guidance",
    "interest_group",
    "peer_support",
    "personal_support",
    "general_help",
}


def get_chat_response(message: str):
    mock_response = _normalize_response(create_friend_response(message), message, source="mock")
    api_key = os.getenv("GEMINI_API_KEY")
    _log_ai_status()

    if not api_key:
        mock_response["fallback_reason"] = "missing_gemini_api_key"
        return mock_response

    try:
        gemini_response = _generate_with_gemini(message, api_key)
        return _normalize_response(gemini_response, message, source="gemini")
    except json.JSONDecodeError as exc:
        safe_error = _safe_gemini_error(exc, forced_category="gemini_parse_error")
        _log_safe_gemini_error("chat", safe_error)
        mock_response["fallback_reason"] = safe_error
        return mock_response
    except Exception as exc:
        safe_error = _safe_gemini_error(exc)
        _log_safe_gemini_error("chat", safe_error)
        mock_response["fallback_reason"] = safe_error
        return mock_response


def get_ai_status() -> dict[str, Any]:
    key_present = bool(os.getenv("GEMINI_API_KEY"))
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return {
        "gemini_key_present": key_present,
        "gemini_model": model,
        "mode": "gemini_possible" if key_present else "mock_only",
    }


def get_gemini_debug_status() -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    if not api_key:
        return {
            "gemini_key_present": False,
            "gemini_model": model,
            "gemini_test_success": False,
            "safe_error": "missing_gemini_api_key",
        }

    try:
        response_text = _generate_gemini_text("Reply with only OK", api_key)
        return {
            "gemini_key_present": True,
            "gemini_model": model,
            "gemini_test_success": response_text.strip().upper() == "OK",
            "safe_error": None if response_text.strip().upper() == "OK" else "gemini_unknown_error: unexpected test response",
        }
    except Exception as exc:
        safe_error = _safe_gemini_error(exc)
        _log_safe_gemini_error("debug", safe_error)
        return {
            "gemini_key_present": True,
            "gemini_model": model,
            "gemini_test_success": False,
            "safe_error": safe_error,
        }


def classify_connector_request(request_text: str) -> dict[str, Any] | None:
    result = classify_connector_request_with_status(request_text)
    return result["classification"]


def classify_connector_request_with_status(request_text: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    _log_ai_status()

    if not api_key:
        return {"classification": None, "fallback_reason": "missing_gemini_api_key"}

    try:
        classification = _generate_connector_classification(request_text, api_key)
        return {
            "classification": _normalize_connector_classification(classification, request_text),
            "fallback_reason": None,
        }
    except json.JSONDecodeError as exc:
        safe_error = _safe_gemini_error(exc, forced_category="gemini_parse_error")
        _log_safe_gemini_error("connector", safe_error)
        return {"classification": None, "fallback_reason": safe_error}
    except Exception as exc:
        safe_error = _safe_gemini_error(exc)
        _log_safe_gemini_error("connector", safe_error)
        return {"classification": None, "fallback_reason": safe_error}


def _log_ai_status() -> None:
    status = get_ai_status()
    logger.info(
        "CampusBuddy AI status: gemini_key_present=%s gemini_model=%s",
        status["gemini_key_present"],
        status["gemini_model"],
    )


def _generate_with_gemini(message: str, api_key: str) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=_build_prompt(message),
    )
    return _parse_json_response(response.text or "")


def _generate_gemini_text(message: str, api_key: str) -> str:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=message,
    )
    return response.text or ""


def _generate_connector_classification(request_text: str, api_key: str) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=_build_connector_prompt(request_text),
    )
    return _parse_json_response(response.text or "")


def _safe_gemini_error(exc: Exception, forced_category: str | None = None) -> str:
    category = forced_category or _gemini_error_category(exc)
    message = _sanitize_error_message(str(exc))
    if not message:
        message = exc.__class__.__name__
    return f"{category}: {message[:260]}"


def _gemini_error_category(exc: Exception) -> str:
    if isinstance(exc, ImportError):
        return "gemini_import_error"
    if isinstance(exc, TimeoutError):
        return "gemini_timeout"

    class_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "timeout" in class_name or "timeout" in message or "deadline" in message:
        return "gemini_timeout"

    status_code = _extract_status_code(exc)
    if status_code in {400, 401, 403, 429}:
        return f"gemini_http_{status_code}"
    if status_code:
        return f"gemini_http_{status_code}"

    for code in (400, 401, 403, 429):
        if re.search(rf"\b{code}\b", message):
            return f"gemini_http_{code}"

    return "gemini_unknown_error"


def _extract_status_code(exc: Exception) -> int | None:
    candidates = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ]
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _sanitize_error_message(message: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    sanitized = message.replace("\n", " ").replace("\r", " ")
    if api_key:
        sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
    sanitized = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[REDACTED_API_KEY]", sanitized)
    sanitized = re.sub(r"key=([^&\s]+)", "key=[REDACTED_API_KEY]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[^,'\"\s]+", "api_key=[REDACTED_API_KEY]", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def _log_safe_gemini_error(context: str, safe_error: str) -> None:
    logger.warning("CampusBuddy Gemini %s failed safely: %s", context, safe_error)


def _build_connector_prompt(request_text: str) -> str:
    return f"""
You classify CampusBuddy People Connector requests.

Your task:
- Only classify and summarize the request.
- Do not invent real students.
- Do not reveal identity.
- Do not include roll number, email, phone number, or personal details.
- Matching and identity policy are handled by the backend.
- Output strict JSON only.
- Do not wrap the JSON in markdown fences.
- Do not add explanation before or after the JSON.
- Use double quotes for all keys and string values.
- Do not include trailing commas.

Allowed categories:
- academic_help
- technical_help
- project_help
- career_help
- campus_guidance
- interest_group
- peer_support
- personal_support
- general_help

Return exactly this JSON shape:
{{
  "requester_mode": "anonymous_first",
  "extracted_topic": "specific topic from the user request",
  "category": "one allowed category",
  "helper_type_needed": "short description of the anonymous helper needed",
  "suggested_request_message": "short anonymous-first message the requester could send"
}}

For the sample request "I need help in DSA graphs but I feel awkward asking in the group.", return:
{{
  "requester_mode": "anonymous_first",
  "extracted_topic": "DSA graphs",
  "category": "academic_help",
  "helper_type_needed": "student or senior comfortable with DSA graphs",
  "suggested_request_message": "Hi, I am looking for anonymous help with DSA graphs. I would like to stay anonymous first and reveal identity only by mutual consent."
}}

Examples:
- "I need help in DSA graphs" -> topic "DSA graphs", category "academic_help"
- "I want someone good at React" -> topic "React", category "technical_help"
- "I am confused about course registration" -> topic "course registration", category "campus_guidance"
- "I want someone to play badminton with" -> topic "badminton", category "interest_group"
- "I am new and want to talk to a senior" -> topic "senior guidance", category "peer_support"
- "I need help with public speaking" -> topic "public speaking", category "career_help"
- "I need help with quantum physics" -> topic "quantum physics", category "academic_help"
- "I am scared to ask seniors about internships" -> topic "internships", category "career_help"

User request:
{request_text}
""".strip()


def _build_prompt(message: str) -> str:
    return f"""
You are CampusBuddy AI, a privacy-first personal AI friend for students.

Identity and core behavior:
- You are not just a tutor, helpdesk, or generic campus bot.
- You are a warm personal AI friend first.
- Start by emotionally acknowledging the student in a calm, friendly way.
- Then suggest CampusBuddy-specific next steps.
- Keep the tone supportive, non-judgmental, and confidence-building.
- Be privacy-first and consent-first.
- Never say anything is saved automatically.
- Any memory suggestion must require explicit consent.
- Explain that anonymity is a confidence bridge, not the destination.
- Never mention a specific interest unless the student mentioned it.
- Extract the actual interest from the student message.
- For group_interest, base reply_text, suggested_actions, memory_suggestions, and matching_query on the actual interest.
- Distinguish students asking for help from students offering help.
- If the student says they are good at, know, can help, can teach, can mentor, are strong in, or have experience in a topic, classify it as offer_help, not academic_help.
- Use this exact privacy note unless there is a very strong reason not to:
  "Raw chats are not shared. Anything remembered or sent needs your consent."

Intent labels:
- personal_support
- academic_help
- group_interest
- campus_issue
- lost_and_found
- career_help
- offer_help
- general

Behavior by intent:
- personal_support: comfort the student first; suggest low-pressure connection options.
- academic_help: do not become only a subject tutor. Acknowledge hesitation, suggest an anonymous peer/senior helper, mention mutual anonymity, suggest memory only with consent, and make matching_query useful for helper matching.
- offer_help: acknowledge the skill positively. Do not suggest finding a helper. Suggest remembering the skill only with consent so CampusBuddy can suggest the student as an anonymous helper for matching. Keep identity hidden unless mutual reveal consent happens later.
- group_interest: suggest an opt-in group invite, mention similar-interest matching, and do not reveal anyone directly.
- campus_issue: create escalation_preview, mention WhatsApp committee escalation, say raw chats are never shared, and ask confirmation before send.
- lost_and_found: create escalation_preview for Student Affairs or Lost and Found, ask confirmation before send, and do not expose identity.
- career_help: acknowledge uncertainty, suggest anonymous senior/mentor matching, and suggest memory only with consent.

Return only valid JSON with this exact shape:
{{
  "source": "gemini",
  "reply": "same value as reply_text",
  "reply_text": "warm student-facing response",
  "intent": "personal_support | academic_help | group_interest | campus_issue | lost_and_found | career_help | offer_help | general",
  "detected_intent": "personal_support | academic_help | group_interest | campus_issue | lost_and_found | career_help | offer_help | general",
  "actions": ["same values as suggested_actions"],
  "suggested_actions": ["short CampusBuddy-specific action 1", "short CampusBuddy-specific action 2"],
  "memory_candidate": {{}},
  "memory_suggestions": [
    {{
      "label": "thing to remember only if student clicks Remember",
      "reason": "why it helps",
      "requires_consent": true,
      "used_for": {{
        "personalization": true,
        "peer_matching": false,
        "group_suggestions": false,
        "anonymous_campus_insight": false
      }}
    }}
  ],
  "privacy_note": "Raw chats are not shared. Anything remembered or sent needs your consent.",
  "escalation_preview": null,
  "matching_query": null,
  "fallback_reason": null
}}

For academic_help, matching_query must be:
{{
  "type": "peer_help",
  "query": "topic, difficulty, and preferred anonymous helper type"
}}

For offer_help, memory_suggestions must include a helper-side skill/profile memory like:
{{
  "label": "Student can help with DSA",
  "reason": "This lets CampusBuddy suggest you as an anonymous helper for DSA-related requests only if you click Remember.",
  "requires_consent": true,
  "used_for": {{
    "personalization": true,
    "peer_matching": true,
    "group_suggestions": false,
    "anonymous_campus_insight": false
  }}
}}

For offer_help, suggested_actions must include:
- "Remember this skill so CampusBuddy can suggest you as a helper with consent."
- "Keep your identity anonymous unless both students later agree to reveal."

For group_interest, matching_query must be:
{{
  "type": "group",
  "query": "interest and opt-in group invite target"
}}

For campus_issue or lost_and_found, include escalation_preview as:
{{
  "committee": "committee name",
  "summary": "anonymous summary",
  "requires_confirmation": true
}}

Student message:
{message}
""".strip()


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned_text = _strip_markdown_json_fence(text).strip()
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        json_text = _extract_balanced_json_object(cleaned_text)
        if not json_text:
            raise
        json_text = re.sub(r",\s*([}\]])", r"\1", json_text)
        return json.loads(json_text)


def _strip_markdown_json_fence(text: str) -> str:
    stripped = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1)
    return stripped


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


def _normalize_connector_classification(classification: dict[str, Any], request_text: str) -> dict[str, Any]:
    topic = str(
        classification.get("extracted_topic")
        or classification.get("topic")
        or request_text
        or "general support"
    ).strip()
    category = str(classification.get("category") or "general_help").strip()
    if category not in CONNECTOR_CATEGORIES:
        category = "general_help"

    urgency = str(classification.get("urgency") or "normal").strip().lower()
    if urgency not in {"low", "normal", "high"}:
        urgency = "normal"

    helper_type_needed = str(
        classification.get("helper_type_needed")
        or f"anonymous helper familiar with {topic}"
    ).strip()
    suggested_request_message = str(
        classification.get("suggested_request_message")
        or f"Hi, I need help with {topic}. Could you help me anonymously first?"
    ).strip()

    return {
        "topic": topic,
        "category": category,
        "helper_type_needed": helper_type_needed,
        "urgency": urgency,
        "suggested_request_message": suggested_request_message,
    }


def _normalize_response(response: dict[str, Any], message: str, source: str) -> dict[str, Any]:
    intent = response.get("detected_intent") or response.get("intent") or classify_student_message(message)
    intent = _canonical_intent(intent)
    if _is_offer_help_message(message):
        intent = "offer_help"
    interest = _extract_interest(message)
    reply_text = response.get("reply_text") or response.get("reply") or "I am listening. You control what I remember or share."
    suggested_actions = response.get("suggested_actions") or response.get("actions") or []
    memory_suggestions = response.get("memory_suggestions")

    if memory_suggestions is None:
        candidate = response.get("memory_candidate") or response.get("suggested_memory")
        memory_suggestions = [candidate] if candidate else []

    escalation_preview = response.get("escalation_preview")
    if escalation_preview is None and intent in {"campus_issue", "lost_and_found"}:
        report = anonymous_committee_message("Campus Issue", message)
        escalation_preview = {
            "committee": report["committee"],
            "summary": report["summary"],
            "requires_confirmation": True,
        }

    matching_query = response.get("matching_query")
    if matching_query is None and intent in {"academic_help", "group_interest", "career_help", "offer_help"}:
        matching_query = {
            "type": "helper_profile" if intent == "offer_help" else "group" if intent == "group_interest" else "peer_help",
            "query": f"{interest} helper profile" if intent == "offer_help" else f"{interest} opt-in group invite" if intent == "group_interest" else message,
        }

    privacy_note = "Raw chats are not shared. Anything remembered or sent needs your consent."

    if not isinstance(suggested_actions, list):
        suggested_actions = [str(suggested_actions)]

    if not isinstance(memory_suggestions, list):
        memory_suggestions = [memory_suggestions] if memory_suggestions else []

    suggested_actions = _campusbuddy_actions(intent, suggested_actions, interest)
    memory_suggestions = _consent_memory_suggestions(intent, message, memory_suggestions, interest)
    reply_text = _friend_first_reply(intent, reply_text, interest)

    primary_memory = memory_suggestions[0] if memory_suggestions else {}

    return {
        "source": source,
        "reply_text": reply_text,
        "detected_intent": intent,
        "suggested_actions": suggested_actions,
        "memory_suggestions": memory_suggestions,
        "privacy_note": privacy_note,
        "escalation_preview": escalation_preview,
        "matching_query": matching_query,
        "fallback_reason": response.get("fallback_reason"),
        # Backward-compatible fields used by the current frontend.
        "reply": reply_text,
        "intent": intent,
        "memory_candidate": primary_memory,
        "actions": suggested_actions,
    }


def _canonical_intent(intent: str) -> str:
    intent_map = {
        "emotional_support": "personal_support",
        "hobbies_groups": "group_interest",
        "community_group": "group_interest",
        "people_connection": "academic_help",
        "placement": "career_help",
        "career": "career_help",
        "helper_profile": "offer_help",
        "skill_offer": "offer_help",
        "offering_help": "offer_help",
    }
    return intent_map.get(intent, intent)


def _campusbuddy_actions(intent: str, actions: list[Any], interest: str) -> list[Any]:
    if intent == "academic_help":
        return [
            "Find an anonymous peer or senior helper for this topic.",
            "Start with mutual anonymity, then reveal identity later only if both sides agree.",
            "Remember this academic need only if the student clicks Remember.",
        ]
    if intent == "offer_help":
        return [
            "Remember this skill so CampusBuddy can suggest you as a helper with consent.",
            "Keep your identity anonymous unless both students later agree to reveal.",
            "Use this only for peer matching after you click Remember.",
        ]
    if intent == "group_interest":
        return [
            f"Create an opt-in {interest} group invite.",
            f"Match with students who consented to {interest} or similar interests.",
            "Let students join anonymously first.",
        ]
    if intent == "campus_issue":
        return [
            "Prepare an anonymous WhatsApp committee summary.",
            "Show the preview before sending.",
            "Send only after student confirmation.",
        ]
    if intent == "lost_and_found":
        return [
            "Prepare an anonymous Lost and Found summary.",
            "Share only confirmed details with the right committee.",
            "Keep student identity hidden unless they choose otherwise.",
        ]
    if intent == "career_help":
        return [
            "Find an anonymous senior or mentor for career guidance.",
            "Use limited profile details only with consent.",
            "Remember goals only if the student clicks Remember.",
        ]
    return actions


def _consent_memory_suggestions(intent: str, message: str, suggestions: list[Any], interest: str) -> list[Any]:
    if suggestions:
        cleaned = []
        for suggestion in suggestions:
            if isinstance(suggestion, dict):
                suggestion["requires_consent"] = True
                if intent == "offer_help":
                    suggestion["label"] = suggestion.get("label") or _helper_skill_label(interest)
                    suggestion["reason"] = (
                        suggestion.get("reason")
                        or f"This lets CampusBuddy suggest you as an anonymous helper for {interest}-related requests only if you click Remember."
                    )
                    suggestion["used_for"] = {
                        "personalization": True,
                        "peer_matching": True,
                        "group_suggestions": False,
                        "anonymous_campus_insight": False,
                    }
                if intent == "group_interest":
                    label = str(suggestion.get("label", "")).lower()
                    if interest not in label:
                        suggestion["label"] = f"Interested in {interest}"
                cleaned.append(suggestion)
        if cleaned:
            return cleaned

    if intent == "offer_help":
        return [
            {
                "label": _helper_skill_label(interest),
                "reason": f"This lets CampusBuddy suggest you as an anonymous helper for {interest}-related requests only if you click Remember.",
                "requires_consent": True,
                "used_for": {
                    "personalization": True,
                    "peer_matching": True,
                    "group_suggestions": False,
                    "anonymous_campus_insight": False,
                },
            }
        ]

    if intent in {"academic_help", "group_interest", "career_help", "personal_support"}:
        return [
            {
                "label": f"Interested in {interest}" if intent == "group_interest" else message,
                "reason": "This can help CampusBuddy personalize support or suggest safer connections only if you allow it.",
                "requires_consent": True,
            }
        ]
    return []


def _friend_first_reply(intent: str, reply_text: str, interest: str) -> str:
    if intent == "offer_help":
        return (
            f"That is useful. CampusBuddy can remember this as a skill only if you choose, "
            f"so you may be suggested as an anonymous helper for {interest}-related requests. "
            "Your identity stays hidden unless both sides later agree to reveal."
        )
    if intent == "academic_help" and not _mentions_any(reply_text, ["anonymous", "peer", "senior", "mutual"]):
        return (
            "I get why asking this in a group can feel awkward. You do not have to jump straight into a public chat. "
            f"{reply_text} CampusBuddy can help you find an anonymous peer or senior helper, keep both sides in control of identity, and remember this need only if you choose."
        )
    if intent == "group_interest" and "opt-in" not in reply_text.lower():
        return (
            f"{reply_text} I can help turn this into an opt-in {interest} group invite and match similar-interest students without revealing anyone directly."
        )
    if intent == "group_interest":
        reply_text = _replace_wrong_interests(reply_text, interest)
    if intent == "campus_issue" and "raw chat" not in reply_text.lower():
        return (
            f"{reply_text} I can prepare an anonymous WhatsApp committee preview. Raw chats are never shared, and you confirm before anything is sent."
        )
    return reply_text


def _mentions_any(text: str, words: list[str]) -> bool:
    lower_text = text.lower()
    return any(word in lower_text for word in words)


def _extract_interest(message: str) -> str:
    text = message.lower()
    known_interests = [
        "dynamic programming",
        "machine learning",
        "football",
        "chess",
        "gym",
        "music",
        "anime",
        "coding",
        "cricket",
        "basketball",
        "badminton",
        "dance",
        "art",
        "photography",
        "dsa",
        "graphs",
        "graph",
        "java",
        "coding",
    ]
    for interest in known_interests:
        if interest in text:
            return interest
    for marker in [
        "i am very good at ",
        "i am good at ",
        "i can help people with ",
        "i can help with ",
        "i can help in ",
        "i can teach ",
        "i can mentor juniors in ",
        "i can mentor ",
        "i am strong in ",
        "i have experience in ",
        "i know ",
        "play ",
        "start a ",
        "join a ",
        "interested in ",
    ]:
        if marker in text:
            after_marker = text.split(marker, 1)[1]
            words = [word.strip(".,!?") for word in after_marker.split()]
            if words:
                return words[0]
    return "this interest"


def _is_offer_help_message(message: str) -> bool:
    text = message.lower()
    need_help_phrases = [
        "i need help",
        "need help",
        "struggling",
        "don't understand",
        "dont understand",
        "can someone teach",
        "asking for help",
        "help me",
    ]
    if any(phrase in text for phrase in need_help_phrases):
        return False

    offer_help_phrases = [
        "i am good at",
        "i am very good at",
        "i know",
        "i can help",
        "i can teach",
        "i can mentor",
        "i am strong in",
        "i have experience in",
    ]
    return any(phrase in text for phrase in offer_help_phrases)


def _helper_skill_label(interest: str) -> str:
    if not interest or interest == "this interest":
        return "Student can help others"
    display_interest = interest.upper() if interest in {"dsa", "dp"} else interest
    return f"Student can help with {display_interest}"


def _replace_wrong_interests(reply_text: str, interest: str) -> str:
    wrong_interests = ["chess", "football", "gym", "music", "anime", "coding", "cricket", "basketball", "badminton"]
    corrected = reply_text
    for wrong_interest in wrong_interests:
        if wrong_interest != interest:
            corrected = re.sub(rf"\b{re.escape(wrong_interest)}\b", interest, corrected, flags=re.IGNORECASE)
    return corrected
