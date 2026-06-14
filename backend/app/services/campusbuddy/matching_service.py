import json
import os
from typing import Any

from app.agents.campusbuddy.matching_agent import group_matches
from app.services.campusbuddy.ai_service import (
    DEFAULT_MODEL,
    _log_safe_gemini_error,
    _parse_json_response,
    _safe_gemini_error,
    classify_connector_request_with_status,
)
from app.services.campusbuddy.memory_service import (
    get_connector_candidate_memories,
    get_current_user_id,
)


def connect_student(request_text: str, current_user_id: str | None = None):
    current_user_id = current_user_id or get_current_user_id()
    classification_result = classify_connector_request_with_status(request_text)
    classification = classification_result["classification"]
    source = "gemini" if classification else "fallback"
    fallback_reason = classification_result["fallback_reason"]
    if classification is None:
        classification = fallback_classification(request_text)

    topic = classification["topic"]
    category = classification["category"]
    matches = find_helper_matches(request_text, topic, category, current_user_id)

    return {
        "source": source,
        "requester_mode": "anonymous_first",
        "extracted_topic": topic,
        "category": category,
        "helper_type_needed": classification["helper_type_needed"],
        "matches": matches,
        "suggested_request_message": classification["suggested_request_message"],
        "privacy_note": (
            "Raw chats are never shared. Real identities are hidden by default, "
            "and identity reveal requires consent from both requester and helper."
        ),
        "fallback_reason": fallback_reason,
        "no_match_message": "" if matches else "No exact helper found yet. CampusBuddy can keep this anonymous request open for opt-in helpers.",
    }


def fallback_classification(request_text: str):
    topic = extract_topic(request_text)
    category = categorize_request(request_text, topic)
    return {
        "topic": topic,
        "category": category,
        "helper_type_needed": build_helper_type_needed(topic, category),
        "urgency": "normal",
        "suggested_request_message": build_suggested_request(topic, category),
    }


def suggest_groups(interest: str):
    return {
        "classification": "community_group",
        "interest": interest,
        "invite_policy": "Opt-in invites only. No student is exposed without consent.",
        "groups": group_matches(interest),
    }


def find_helper_matches(request_text: str, topic: str, category: str, current_user_id: str):
    memories = get_connector_candidate_memories(
        exclude_user_id=current_user_id,
        include_group_suggestions=category == "interest_group",
    )
    ai_matches = find_ai_ranked_matches(request_text, topic, category, memories)
    if ai_matches:
        return ai_matches

    return find_fallback_matches(request_text, topic, category, memories)


def find_ai_ranked_matches(request_text: str, topic: str, category: str, memories: list[dict]):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not memories:
        return []

    candidates = [safe_candidate_from_memory(memory) for memory in memories]

    try:
        ranked = generate_gemini_match_ranking(api_key, request_text, topic, category, candidates)
        return normalize_ai_ranked_matches(ranked, memories, topic, category)
    except json.JSONDecodeError as exc:
        _log_safe_gemini_error("connector_matching", _safe_gemini_error(exc, forced_category="gemini_parse_error"))
    except Exception as exc:
        _log_safe_gemini_error("connector_matching", _safe_gemini_error(exc))
    return []


def generate_gemini_match_ranking(
    api_key: str,
    request_text: str,
    topic: str,
    category: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_matching_prompt(request_text, topic, category, candidates),
    )
    return _parse_json_response(response.text or "")


def build_matching_prompt(request_text: str, topic: str, category: str, candidates: list[dict[str, Any]]) -> str:
    return f"""
You rank anonymous CampusBuddy connector matches from consented Trust Dashboard memories.

Privacy and safety rules:
- Use only the candidate_id values below.
- Do not reveal student IDs, names, contact details, raw private notes, or identity.
- Match only when the memory clearly indicates the student can help with, guide, play, discuss, or share the requested topic.
- For hobbies/interests like badminton, chess, music, gym, or football, match students with shared interest even if they did not use words like "can help".
- Do not match a memory where the student is asking for help on the same issue rather than offering help or sharing interest.
- Output strict JSON only, no markdown.

Requester:
- request_text: {request_text}
- extracted_topic: {topic}
- category: {category}

Candidates:
{json.dumps(candidates, ensure_ascii=True, indent=2)}

Return exactly this JSON shape:
{{
  "matches": [
    {{
      "candidate_id": "candidate id from the list",
      "score": 0-100,
      "safe_reason": "short privacy-safe reason without revealing raw memory"
    }}
  ]
}}
Only include candidates with score >= 60. Return at most 3 matches.
""".strip()


def safe_candidate_from_memory(memory: dict) -> dict[str, Any]:
    return {
        "candidate_id": str(memory["id"]),
        "anonymous_alias": anonymous_name_for_user(memory["user_id"]),
        "memory_label": str(memory.get("label", ""))[:180],
        "memory_type": memory.get("memory_type") or memory.get("type"),
        "allowed_uses": {
            "peer_matching": bool(memory.get("used_for", {}).get("peer_matching")),
            "group_suggestions": bool(memory.get("used_for", {}).get("group_suggestions")),
        },
    }


def normalize_ai_ranked_matches(ranked: dict[str, Any], memories: list[dict], topic: str, category: str):
    memories_by_id = {str(memory["id"]): memory for memory in memories}
    matches = []
    seen_ids = set()

    for item in ranked.get("matches", []):
        candidate_id = str(item.get("candidate_id", "")).strip()
        if candidate_id in seen_ids or candidate_id not in memories_by_id:
            continue

        try:
            score = int(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        if score < 60:
            continue

        memory = memories_by_id[candidate_id]
        matches.append(
            format_match(
                memory,
                [topic],
                topic,
                category,
                match_reason=safe_ai_reason(item.get("safe_reason"), topic, category),
                match_source="gemini",
            )
        )
        seen_ids.add(candidate_id)

        if len(matches) == 3:
            break

    return matches


def safe_ai_reason(reason: Any, topic: str, category: str) -> str:
    reason_text = str(reason or "").strip()
    if not reason_text:
        return build_safe_match_reason(topic, category)
    blocked_fragments = ["student_", "@", "phone", "email", "roll"]
    if any(fragment in reason_text.lower() for fragment in blocked_fragments):
        return build_safe_match_reason(topic, category)
    return reason_text[:180]


def find_fallback_matches(request_text: str, topic: str, category: str, memories: list[dict]):
    text = request_text.lower()
    scored_memories = []

    for memory in memories:
        memory_text = f"{memory['label']} {memory['text']} {memory['reason']}".lower()
        if not is_eligible_helper_memory(memory_text, category):
            continue

        topic_hits, topic_score = score_topic_overlap(f"{text} {topic.lower()}", topic, [memory_text])
        category_hit = category_memory_overlap(category, memory_text) and is_broad_request(text, topic)
        interest_hit = category == "interest_group" and has_interest_overlap(text, topic, memory_text)
        score = topic_score + (5 if category_hit else 0) + (10 if interest_hit else 0)

        if score >= 5:
            scored_memories.append((score, topic_hits, memory))

    scored_memories.sort(key=lambda item: item[0], reverse=True)
    return [
        format_match(memory, topic_hits, topic, category)
        for _, topic_hits, memory in scored_memories[:3]
    ]


def format_match(
    memory: dict,
    topic_hits: list[str],
    topic: str,
    category: str,
    match_reason: str | None = None,
    match_source: str = "fallback",
):
    connection_id = f"connection_{memory['user_id']}_{memory['id']}"
    return {
        "connection_id": connection_id,
        "anonymous_name": anonymous_name_for_user(memory["user_id"]),
        "matched_memory_label": build_safe_match_label(topic, category),
        "match_reason": match_reason or build_safe_match_reason(topic, category),
        "match_source": match_source,
        "contact_mode": "anonymous_first",
        "consent_status": memory["memory_type"],
        "reveal_policy": "mutual_consent_required",
        "actions": ["Send anonymous request", "Request identity reveal later"],
    }


def anonymous_name_for_user(user_id: str):
    suffix = user_id.split("_")[-1]
    return f"Anonymous Student {suffix}"


def extract_topic(request_text: str):
    text = request_text.lower()
    known_topics = [
        "dsa graphs",
        "graphs",
        "dsa",
        "react",
        "frontend",
        "javascript",
        "web development",
        "course registration",
        "hostel rules",
        "clubs",
        "societies",
        "badminton",
        "football",
        "cricket",
        "chess",
        "gym",
        "music",
        "resume",
        "internships",
        "interviews",
        "public speaking",
        "loneliness",
        "making friends",
        "first year adjustment",
        "senior guidance",
    ]
    for topic in known_topics:
        if topic in text:
            return topic
    if "senior" in text:
        return "senior guidance"
    for marker in ["help in ", "help with ", "good at ", "play ", "talk to a ", "confused about "]:
        if marker in text:
            after_marker = text.split(marker, 1)[1]
            words = [word.strip(".,!?") for word in after_marker.split()]
            if words:
                return " ".join(words[:3])
    return "general support"


def score_topic_overlap(text: str, extracted_topic: str, profile_topics: list[str]):
    request_tokens = meaningful_tokens(f"{text} {extracted_topic}")
    topic_hits = []
    score = 0

    for profile_topic in profile_topics:
        normalized_topic = profile_topic.lower()
        profile_tokens = meaningful_tokens(normalized_topic)

        if normalized_topic in text or normalized_topic == extracted_topic.lower():
            topic_hits.append(profile_topic)
            score += 10
            continue

        overlap = request_tokens.intersection(profile_tokens)
        if overlap:
            topic_hits.append(profile_topic)
            score += 5 * len(overlap)

    return topic_hits, score


def category_memory_overlap(category: str, memory_text: str):
    category_terms = {
        "academic_help": ["dsa", "graphs", "algorithms", "physics", "course", "subject"],
        "technical_help": ["react", "frontend", "javascript", "web development"],
        "project_help": ["project", "hackathon", "prototype", "app"],
        "career_help": ["resume", "internship", "interview", "placement", "public speaking"],
        "campus_guidance": ["course registration", "hostel rules", "clubs", "societies", "campus processes"],
        "interest_group": ["badminton", "football", "cricket", "chess", "gym", "music", "sports"],
        "peer_support": ["loneliness", "making friends", "first year", "senior guidance"],
        "personal_support": ["loneliness", "making friends", "first year", "senior guidance"],
    }
    return any(term in memory_text for term in category_terms.get(category, []))


def meaningful_tokens(text: str):
    stop_words = {
        "i",
        "am",
        "a",
        "an",
        "the",
        "to",
        "in",
        "with",
        "for",
        "and",
        "or",
        "need",
        "help",
        "want",
        "someone",
        "good",
        "at",
        "about",
        "confused",
        "new",
        "talk",
    }
    tokens = re_split_words(text)
    return {token for token in tokens if len(token) > 2 and token not in stop_words}


def is_eligible_helper_memory(memory_text: str, category: str):
    if has_need_help_phrase(memory_text):
        return False

    if has_offer_help_phrase(memory_text):
        return True

    return category == "interest_group" and is_interest_memory(memory_text)


def is_interest_memory(memory_text: str):
    interest_phrases = [
        "interested in",
        "interest in",
        "i like",
        "likes",
        "love",
        "loves",
        "want to play",
        "wants to play",
        "play",
        "plays",
        "looking for",
        "group",
        "club",
    ]
    interest_terms = [
        "badminton",
        "football",
        "cricket",
        "chess",
        "gym",
        "music",
        "guitar",
        "coding",
        "anime",
        "dance",
        "photography",
    ]
    return any(phrase in memory_text for phrase in interest_phrases) and any(
        term in memory_text for term in interest_terms
    )


def has_interest_overlap(request_text: str, topic: str, memory_text: str):
    interest_terms = {
        "badminton",
        "football",
        "cricket",
        "chess",
        "gym",
        "music",
        "guitar",
        "coding",
        "anime",
        "dance",
        "photography",
    }
    request_tokens = meaningful_tokens(f"{request_text} {topic}")
    memory_tokens = meaningful_tokens(memory_text)
    return bool(request_tokens.intersection(memory_tokens).intersection(interest_terms))


def has_offer_help_phrase(memory_text: str):
    offer_help_phrases = [
        "can help",
        "good at",
        "strong in",
        "can teach",
        "mentor",
        "experience in",
        "skilled in",
        "knows",
        "know ",
    ]
    return any(phrase in memory_text for phrase in offer_help_phrases)


def has_need_help_phrase(memory_text: str):
    need_help_phrases = [
        "need help",
        "needs help",
        "struggling",
        "do not understand",
        "don't understand",
        "looking for help",
        "awkward asking",
    ]
    return any(phrase in memory_text for phrase in need_help_phrases)


def build_safe_match_label(topic: str, category: str):
    display_topic = format_topic_label(topic)
    if category == "interest_group":
        return f"Shared interest: {display_topic}"
    return f"Can help with {display_topic}"


def build_safe_match_reason(topic: str, category: str):
    if category == "interest_group":
        return "This student consented to anonymous matching for a similar interest."
    return "This student consented to be suggested anonymously for this skill area."


def format_topic_label(topic: str):
    if not topic or topic == "general support":
        return "this topic"

    acronym_words = {
        "dsa": "DSA",
        "dp": "DP",
        "ui": "UI",
        "ux": "UX",
        "ai": "AI",
        "ml": "ML",
    }
    return " ".join(
        acronym_words.get(word.lower(), word.capitalize())
        for word in topic.strip().split()
    )


def re_split_words(text: str):
    word = ""
    words = []
    for char in text.lower():
        if char.isalnum() or char in {"#", "+"}:
            word += char
        elif word:
            words.append(word)
            word = ""
    if word:
        words.append(word)
    return words


def is_broad_request(text: str, topic: str):
    broad_phrases = [
        "need help",
        "want help",
        "talk to someone",
        "talk to a senior",
        "new",
        "confused",
    ]
    return topic == "general support" or any(phrase in text for phrase in broad_phrases)


def categorize_request(request_text: str, topic: str):
    text = request_text.lower()
    if any(word in text for word in ["react", "frontend", "javascript", "web development"]):
        return "technical_help"
    if any(word in text for word in ["project", "hackathon", "prototype", "app"]):
        return "project_help"
    if any(word in text for word in ["dsa", "graphs", "algorithm", "quantum physics", "physics"]):
        return "academic_help"
    if any(word in text for word in ["resume", "internship", "interview", "placement", "public speaking"]):
        return "career_help"
    if any(word in text for word in ["course registration", "hostel", "clubs", "societies", "rules"]):
        return "campus_guidance"
    if any(word in text for word in ["badminton", "football", "cricket", "chess", "gym", "music", "play"]):
        return "interest_group"
    if any(word in text for word in ["new", "lonely", "friends", "senior", "first year"]):
        return "peer_support"
    if topic != "general support":
        return "general_help"
    return "general_help"


def build_suggested_request(topic: str, category: str):
    return (
        f"Hi, I am looking for anonymous help with {topic}. "
        f"I would like to stay anonymous first and reveal identity only by mutual consent."
    )


def build_helper_type_needed(topic: str, category: str):
    helper_types = {
        "academic_help": f"student or senior comfortable with {topic}",
        "technical_help": f"student good at {topic} and related technical work",
        "project_help": f"project teammate or mentor familiar with {topic}",
        "career_help": f"senior or mentor who can guide {topic}",
        "campus_guidance": f"campus guide familiar with {topic}",
        "interest_group": f"student interested in {topic}",
        "peer_support": f"friendly senior or peer for {topic}",
        "personal_support": f"supportive peer for {topic}",
        "general_help": f"anonymous helper familiar with {topic}",
    }
    return helper_types.get(category, f"anonymous helper familiar with {topic}")
