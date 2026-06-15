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
from app.services.campusbuddy.discord_bridge import ensure_interest_group_channel
from app.services.campusbuddy.memory_service import get_group_suggestion_memories, require_user_id
from app.services.campusbuddy.sqlite_store import create_sequential_record, list_records, mutate_record, upsert_record


GROUP_THRESHOLD = 3

HOBBY_SUBMISSION_KIND = "hobby_submission"
HOBBY_GROUP_KIND = "hobby_group"
GROUP_INVITE_KIND = "group_invite"
GROUP_CREATION_LOCK = RLock()

HOBBY_PATTERNS = [
    ("badminton", ["badminton"]),
    ("football", ["football", "soccer", "futsal"]),
    ("cricket", ["cricket"]),
    ("chess", ["chess"]),
    ("music", ["music", "singing", "guitar", "piano", "band"]),
    ("coding", ["coding", "programming", "hackathon", "hackathons", "web development"]),
    ("gym", ["gym", "fitness", "workout", "bodybuilding"]),
    ("anime", ["anime", "manga"]),
    ("dance", ["dance", "dancing"]),
    ("photography", ["photography", "camera", "photo"]),
    ("reading", ["reading", "books", "book club"]),
]


def build_groups_from_trust_memories(student_id: str | None = None) -> dict:
    hobby_interests = collect_hobby_interests_from_memories()

    with GROUP_CREATION_LOCK:
        for hobby_key, interest in hobby_interests.items():
            member_interest_count = len(interest["user_ids"])
            if member_interest_count < GROUP_THRESHOLD:
                continue

            group = ensure_group_for_hobby(
                hobby_key=hobby_key,
                hobby_label=interest["hobby_label"],
                member_interest_count=member_interest_count,
            )
            ensure_group_invites_for_interested_students(group, interest["user_ids"])

    return {"groups": list_public_groups(student_id)}


def collect_hobby_interests_from_memories() -> dict:
    hobby_interests = {}
    for memory in get_group_suggestion_memories():
        memory_text = f"{memory.get('label', '')} {memory.get('text', '')}"
        user_id = memory.get("user_id")
        if not user_id:
            continue

        for hobby_key in extract_hobby_keys_from_text(memory_text):
            hobby_interests.setdefault(
                hobby_key,
                {
                    "hobby_key": hobby_key,
                    "hobby_label": hobby_key_to_label(hobby_key),
                    "user_ids": set(),
                },
            )
            hobby_interests[hobby_key]["user_ids"].add(user_id)

    return hobby_interests


def list_group_invites_for_student(student_id: str) -> dict:
    student_id = require_user_id(student_id)
    build_groups_from_trust_memories()
    return {
        "student_id": student_id,
        "invites": [
            public_invite(invite)
            for invite in dedupe_invites_for_student(student_id)
            if invite.get("invite_status") == "ready_to_join"
        ],
    }


def join_group(group_id: str, student_id: str) -> dict:
    student_id = require_user_id(student_id)
    build_groups_from_trust_memories()
    with GROUP_CREATION_LOCK:
        group = find_group_by_id(group_id)
        invite = find_invite(group_id, student_id)
        if invite is None and group is not None:
            invite = create_group_invite(student_id, group)

        if invite is None:
            return {
                "joined": False,
                "group_id": group_id,
                "invite_status": None,
                "message": "No private invite was found for this student and group.",
            }

        def apply_join(current_invite: dict) -> dict:
            current_invite["invite_status"] = "joined"
            current_invite["joined_at"] = now_iso()
            return current_invite

        invite = mutate_record(GROUP_INVITE_KIND, invite["invite_id"], apply_join) or invite
    return {
        "joined": True,
        "group_id": group_id,
        "invite_status": "joined",
        "message": "You joined the group. Discord joining is mocked for now.",
        "invite": public_invite(invite),
    }


def ignore_group_invite(group_id: str, student_id: str) -> dict:
    student_id = require_user_id(student_id)
    build_groups_from_trust_memories()
    with GROUP_CREATION_LOCK:
        invite = find_invite(group_id, student_id)
        if invite is None:
            return {
                "ignored": False,
                "group_id": group_id,
                "invite_status": None,
                "message": "No private invite was found for this student and group.",
            }

        def apply_ignore(current_invite: dict) -> dict:
            if current_invite.get("invite_status") != "joined":
                current_invite["invite_status"] = "ignored"
                current_invite["ignored_at"] = now_iso()
            return current_invite

        invite = mutate_record(GROUP_INVITE_KIND, invite["invite_id"], apply_ignore) or invite
    return {
        "ignored": True,
        "group_id": group_id,
        "invite_status": "ignored",
        "message": "Invite ignored. You can join later if you change your mind.",
        "invite": public_invite(invite),
    }


def submit_hobby(student_id: str, hobby_text: str) -> dict:
    student_id = require_user_id(student_id)
    hobby_text = (hobby_text or "").strip()
    hobby_key = normalize_hobby_key(hobby_text)
    hobby_label = hobby_key_to_label(hobby_key)
    with GROUP_CREATION_LOCK:
        existing_group = find_group_by_hobby(hobby_key)
        duplicate_student_hobby = has_student_submitted_hobby(student_id, hobby_key)

        store_hobby_submission(student_id, hobby_text, hobby_key, hobby_label, duplicate_student_hobby)

        unique_student_count = get_unique_student_count_for_hobby(hobby_key)

        if duplicate_student_hobby:
            return build_hobby_response(
                hobby_text=hobby_text,
                hobby_key=hobby_key,
                hobby_label=hobby_label,
                unique_student_count=unique_student_count,
                duplicate_student_hobby=True,
                group=existing_group,
                group_created=False,
                invite=None,
                message="You already shared this hobby. It was saved, but it does not increase the group threshold.",
            )

        if existing_group:
            invite = create_group_invite(student_id, existing_group)
            return build_hobby_response(
                hobby_text=hobby_text,
                hobby_key=hobby_key,
                hobby_label=hobby_label,
                unique_student_count=unique_student_count,
                duplicate_student_hobby=False,
                group=existing_group,
                group_created=False,
                invite=invite,
                message="A group already exists for this hobby. You can join it when you feel comfortable.",
            )

        if unique_student_count >= GROUP_THRESHOLD:
            group = create_hobby_group(hobby_key, hobby_label, unique_student_count)
            invite = create_group_invite(student_id, group)
            return build_hobby_response(
                hobby_text=hobby_text,
                hobby_key=hobby_key,
                hobby_label=hobby_label,
                unique_student_count=unique_student_count,
                duplicate_student_hobby=False,
                group=group,
                group_created=True,
                invite=invite,
                message="Multiple students share this hobby. A consent-based group is ready.",
            )

    return build_hobby_response(
        hobby_text=hobby_text,
        hobby_key=hobby_key,
        hobby_label=hobby_label,
        unique_student_count=unique_student_count,
        duplicate_student_hobby=False,
        group=None,
        group_created=False,
        invite=None,
        message="Hobby saved anonymously. CampusBuddy will suggest a group when enough unique students show interest.",
    )


def normalize_hobby_key(hobby_text: str) -> str:
    text = hobby_text.lower()
    for hobby_key, keywords in HOBBY_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return hobby_key

    tokens = [token for token in split_words(text) if token not in hobby_stop_words()]
    if not tokens:
        return "general_hobby"
    return "_".join(tokens[:4])


def hobby_key_to_label(hobby_key: str) -> str:
    return " ".join(word.capitalize() for word in hobby_key.split("_"))


def extract_hobby_keys_from_text(text: str) -> list[str]:
    normalized_text = text.lower()
    hobby_keys = [
        hobby_key
        for hobby_key, keywords in HOBBY_PATTERNS
        if any(keyword in normalized_text for keyword in keywords)
    ]
    if hobby_keys:
        return list(dict.fromkeys(hobby_keys))

    hobby_key = normalize_hobby_key(text)
    if hobby_key == "general_hobby":
        return []
    return [hobby_key]


def store_hobby_submission(
    student_id: str,
    hobby_text: str,
    hobby_key: str,
    hobby_label: str,
    duplicate_student_hobby: bool,
) -> None:
    def build_submission(submission_id: str) -> dict:
        return {
            "submission_id": submission_id,
            "student_id": student_id,
            "hobby_text": hobby_text,
            "hobby_key": hobby_key,
            "hobby_label": hobby_label,
            "duplicate_student_hobby": duplicate_student_hobby,
            "created_at": now_iso(),
        }

    create_sequential_record(HOBBY_SUBMISSION_KIND, "hobby_submission", build_submission)


def has_student_submitted_hobby(student_id: str, hobby_key: str) -> bool:
    return any(
        submission["student_id"] == student_id and submission["hobby_key"] == hobby_key
        for submission in list_hobby_submissions()
    )


def get_unique_student_count_for_hobby(hobby_key: str) -> int:
    return len(
        {
            submission["student_id"]
            for submission in list_hobby_submissions()
            if submission["hobby_key"] == hobby_key
        }
    )


def find_group_by_hobby(hobby_key: str) -> dict | None:
    group = next((group for group in dedupe_groups_by_hobby() if group["hobby_key"] == hobby_key), None)
    if group:
        return group
    return None


def find_group_by_id(group_id: str) -> dict | None:
    return next((group for group in dedupe_groups_by_hobby() if group["group_id"] == group_id), None)


def create_hobby_group(hobby_key: str, hobby_label: str, unique_student_count: int) -> dict:
    with GROUP_CREATION_LOCK:
        existing_group = find_group_by_hobby(hobby_key)
        if existing_group:
            update_group_interest_count(existing_group, unique_student_count)
            return existing_group

        group_name = f"{hobby_label} Circle"
        summary_result = generate_group_summary(
            hobby_key=hobby_key,
            hobby_label=hobby_label,
            group_name=group_name,
            member_interest_count=unique_student_count,
            threshold=GROUP_THRESHOLD,
        )
        def build_group(group_id: str) -> dict:
            return {
                "group_id": group_id,
                "hobby_key": hobby_key,
                "hobby_label": hobby_label,
                "group_name": group_name,
                "member_interest_count": unique_student_count,
                "unique_student_count": unique_student_count,
                "threshold": GROUP_THRESHOLD,
                "destination": mock_discord_destination_for_hobby(hobby_key),
                "status": "mock_discord_group_ready",
                "invite_mode": "consent_required",
                "group_summary": summary_result["summary"],
                "summary_source": summary_result["source"],
                "summary_fallback_reason": summary_result["fallback_reason"],
                "created_at": now_iso(),
            }

        group = create_sequential_record(HOBBY_GROUP_KIND, "group", build_group)
        discord_result = ensure_interest_group_channel(group)
        group["discord_channel"] = discord_result
        if discord_result.get("channel_name"):
            group["destination"] = f"#{discord_result['channel_name']}"
            group["discord_channel_id"] = discord_result.get("channel_id")
            group["discord_announcement_channel_id"] = discord_result.get("announcement_channel_id")
            group["discord_invite_url"] = discord_result.get("invite_url")
            group["discord_private"] = bool(discord_result.get("private"))
            group["status"] = "discord_group_ready"
        save_hobby_group(group)
        return group


def ensure_group_for_hobby(hobby_key: str, hobby_label: str, member_interest_count: int) -> dict:
    group = find_group_by_hobby(hobby_key)
    if group is None:
        return create_hobby_group(hobby_key, hobby_label, member_interest_count)

    update_group_interest_count(group, member_interest_count)
    if group.get("discord_private") is True:
        refresh_group_discord_invite(group)
    return group


def refresh_group_discord_invite(group: dict) -> None:
    discord_result = ensure_interest_group_channel(group)
    group["discord_channel"] = discord_result
    if discord_result.get("channel_name"):
        group["destination"] = f"#{discord_result['channel_name']}"
        group["discord_channel_id"] = discord_result.get("channel_id")
        group["discord_announcement_channel_id"] = discord_result.get("announcement_channel_id")
        group["discord_invite_url"] = discord_result.get("invite_url")
        group["discord_private"] = bool(discord_result.get("private"))
        group["status"] = "discord_group_ready"
        save_hobby_group(group)


def ensure_group_invites_for_interested_students(group: dict, user_ids: set[str]) -> None:
    for user_id in sorted(user_ids):
        create_group_invite(user_id, group)


def generate_group_summary(
    hobby_key: str,
    hobby_label: str,
    group_name: str,
    member_interest_count: int,
    threshold: int,
) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "summary": fallback_group_summary(hobby_label),
            "source": "fallback",
            "fallback_reason": "missing_gemini_api_key",
        }

    try:
        gemini_result = generate_gemini_group_summary(
            api_key=api_key,
            hobby_key=hobby_key,
            hobby_label=hobby_label,
            group_name=group_name,
            member_interest_count=member_interest_count,
            threshold=threshold,
        )
        summary = str(gemini_result.get("group_summary") or "").strip()
        if not summary:
            return {
                "summary": fallback_group_summary(hobby_label),
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
        _log_safe_gemini_error("group_summary", safe_error)
        return {
            "summary": fallback_group_summary(hobby_label),
            "source": "fallback",
            "fallback_reason": safe_error,
        }


def generate_gemini_group_summary(
    api_key: str,
    hobby_key: str,
    hobby_label: str,
    group_name: str,
    member_interest_count: int,
    threshold: int,
) -> dict[str, Any]:
    from google import genai

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_group_summary_prompt(
            hobby_key=hobby_key,
            hobby_label=hobby_label,
            group_name=group_name,
            member_interest_count=member_interest_count,
            threshold=threshold,
        ),
    )
    return _parse_json_response(response.text or "")


def build_group_summary_prompt(
    hobby_key: str,
    hobby_label: str,
    group_name: str,
    member_interest_count: int,
    threshold: int,
) -> str:
    return f"""
Generate a short friendly summary for a campus interest group.
The group formed because multiple students share the same hobby.
Do not mention student names or IDs.
Do not reveal individual memories.
Mention that joining is optional and consent-based.
Keep it 1-2 sentences.

Safe aggregate fields:
- hobby_key: {hobby_key}
- hobby_label: {hobby_label}
- group_name: {group_name}
- member_interest_count: {member_interest_count}
- threshold: {threshold}

Return strict JSON only:
{{
  "group_summary": "..."
}}
""".strip()


def fallback_group_summary(hobby_label: str) -> str:
    return (
        f"A {hobby_label} group is ready because multiple students share this interest. "
        "Students can choose to join when they feel comfortable."
    )


def update_group_interest_count(group: dict, member_interest_count: int) -> None:
    group["member_interest_count"] = member_interest_count
    group["unique_student_count"] = member_interest_count
    save_hobby_group(group)


def create_group_invite(student_id: str, group: dict) -> dict:
    existing_invite = find_existing_invite_for_group(student_id, group)
    if existing_invite:
        sync_invite_group_fields(existing_invite, group)
        save_group_invite(existing_invite)
        return existing_invite

    def build_invite(invite_id: str) -> dict:
        return {
            "invite_id": invite_id,
            "group_id": group["group_id"],
            "hobby_key": group["hobby_key"],
            "hobby_label": group["hobby_label"],
            "group_name": group["group_name"],
            "student_id_internal": student_id,
            "invite_status": "ready_to_join",
            "invite_mode": "consent_required",
            "destination": group["destination"],
            "message": f"A {group['hobby_label']} group is ready. Join when you feel comfortable.",
            "created_at": now_iso(),
        }

    return create_sequential_record(GROUP_INVITE_KIND, "invite", build_invite)


def find_existing_invite_for_group(student_id: str, group: dict) -> dict | None:
    return next(
        (
            invite
            for invite in list_group_invites()
            if invite["student_id_internal"] == student_id
            and (
                invite["group_id"] == group["group_id"]
                or invite.get("hobby_key") == group["hobby_key"]
            )
        ),
        None,
    )


def sync_invite_group_fields(invite: dict, group: dict) -> None:
    invite["group_id"] = group["group_id"]
    invite["hobby_key"] = group["hobby_key"]
    invite["hobby_label"] = group["hobby_label"]
    invite["group_name"] = group["group_name"]
    invite["invite_mode"] = "consent_required"
    invite["destination"] = group["destination"]
    invite["message"] = f"A {group['hobby_label']} group is ready. Join when you feel comfortable."


def find_invite(group_id: str, student_id: str) -> dict | None:
    return next(
        (
            invite
            for invite in list_group_invites()
            if invite["group_id"] == group_id and invite["student_id_internal"] == student_id
        ),
        None,
    )


def dedupe_invites_for_student(student_id: str) -> list[dict]:
    selected_invites = {}
    for invite in list_group_invites():
        if invite["student_id_internal"] != student_id:
            continue

        uniqueness_key = invite.get("hobby_key") or invite["group_id"]
        current = selected_invites.get(uniqueness_key)
        if current is None or invite_status_priority(invite) > invite_status_priority(current):
            selected_invites[uniqueness_key] = invite

    return list(selected_invites.values())


def invite_status_priority(invite: dict) -> int:
    status_priority = {
        "ready_to_join": 1,
        "ignored": 2,
        "joined": 3,
    }
    return status_priority.get(invite.get("invite_status"), 0)


def build_hobby_response(
    hobby_text: str,
    hobby_key: str,
    hobby_label: str,
    unique_student_count: int,
    duplicate_student_hobby: bool,
    group: dict | None,
    group_created: bool,
    invite: dict | None,
    message: str,
) -> dict:
    group_ready = group is not None
    invite_created = invite is not None and not duplicate_student_hobby
    response = {
        "classification": "community_group",
        "interest": hobby_text,
        "hobby_key": hobby_key,
        "hobby_label": hobby_label,
        "threshold": GROUP_THRESHOLD,
        "unique_student_count": unique_student_count,
        "duplicate_student_hobby": duplicate_student_hobby,
        "group_ready": group_ready,
        "group_created": group_created,
        "invite_created": invite_created,
        "invite_status": invite["invite_status"] if invite else None,
        "invite_mode": invite["invite_mode"] if invite else None,
        "group_id": group["group_id"] if group else None,
        "group_name": group["group_name"] if group else None,
        "mock_discord_destination": group["destination"] if group else None,
        "message": message,
        "invite_policy": "Opt-in invites only. No student is exposed without consent.",
        "groups": build_public_group_cards(hobby_label, unique_student_count, group),
    }
    if invite:
        response["invite"] = {
            "invite_id": invite["invite_id"],
            "group_id": invite["group_id"],
            "hobby_key": invite["hobby_key"],
            "hobby_label": invite["hobby_label"],
            "group_name": invite["group_name"],
            "invite_status": invite["invite_status"],
            "invite_mode": invite["invite_mode"],
            "destination": invite["destination"],
            "message": invite["message"],
        }
    return response


def build_public_group_cards(hobby_label: str, unique_student_count: int, group: dict | None) -> list[dict]:
    if group:
        return [
            {
                "name": group["group_name"],
                "members_waiting": unique_student_count,
                "invite_preview": (
                    f"CampusBuddy found students interested in {hobby_label}. "
                    "Join anonymously first and reveal your profile only if you choose."
                ),
            }
        ]

    remaining = max(GROUP_THRESHOLD - unique_student_count, 0)
    return [
        {
            "name": f"{hobby_label} Circle",
            "members_waiting": unique_student_count,
            "invite_preview": (
                f"{remaining} more unique student interest signal"
                f"{'' if remaining == 1 else 's'} needed before CampusBuddy creates an opt-in group."
            ),
        }
    ]


def mock_discord_destination_for_hobby(hobby_key: str) -> str:
    return f"#{hobby_key.replace('_', '-')}-club"


def list_public_groups(student_id: str | None = None) -> list[dict]:
    return [public_group(group, student_id) for group in dedupe_groups_by_hobby()]


def dedupe_groups_by_hobby() -> list[dict]:
    groups_by_hobby = {}
    for group in list_hobby_groups():
        hobby_key = group["hobby_key"]
        existing = groups_by_hobby.get(hobby_key)
        if existing is None:
            groups_by_hobby[hobby_key] = group
            continue

        if group.get("member_interest_count", 0) > existing.get("member_interest_count", 0):
            sync_group_identity(existing, group)

    return list(groups_by_hobby.values())


def sync_group_identity(target: dict, source: dict) -> None:
    target["member_interest_count"] = source.get("member_interest_count", target["member_interest_count"])
    target["unique_student_count"] = source.get("unique_student_count", target.get("unique_student_count"))
    target["threshold"] = source.get("threshold", target["threshold"])
    target["destination"] = source.get("destination", target["destination"])
    target["status"] = source.get("status", target["status"])
    target["invite_mode"] = source.get("invite_mode", target["invite_mode"])
    target["discord_channel"] = source.get("discord_channel", target.get("discord_channel"))
    target["discord_channel_id"] = source.get("discord_channel_id", target.get("discord_channel_id"))
    target["discord_announcement_channel_id"] = source.get(
        "discord_announcement_channel_id",
        target.get("discord_announcement_channel_id"),
    )
    target["discord_invite_url"] = source.get("discord_invite_url", target.get("discord_invite_url"))
    target["discord_private"] = source.get("discord_private", target.get("discord_private"))
    save_hobby_group(target)


def public_group(group: dict, student_id: str | None = None) -> dict:
    student_status = current_student_group_status(student_id, group) if student_id else None
    consensus_interest_count = min(int(group["member_interest_count"]), int(group["threshold"]))
    return {
        "group_id": group["group_id"],
        "hobby_key": group["hobby_key"],
        "hobby_label": group["hobby_label"],
        "group_name": group["group_name"],
        "member_interest_count": group["member_interest_count"],
        "consensus_interest_count": consensus_interest_count,
        "threshold": group["threshold"],
        "destination": group["destination"],
        "status": group["status"],
        "invite_mode": group["invite_mode"],
        "group_summary": group["group_summary"],
        "summary_source": group.get("summary_source"),
        "summary_fallback_reason": group.get("summary_fallback_reason"),
        "discord_channel_id": group.get("discord_channel_id"),
        "discord_announcement_channel_id": group.get("discord_announcement_channel_id"),
        "discord_invite_url": group.get("discord_invite_url"),
        "discord_private": bool(group.get("discord_private")),
        "discord_delivery": group.get("discord_channel"),
        "current_student_status": student_status or "not_joined",
    }


def current_student_group_status(student_id: str | None, group: dict) -> str:
    if not student_id:
        return "not_joined"

    invite = find_existing_invite_for_group(student_id, group)
    if invite and invite.get("invite_status") == "joined":
        return "joined"
    return "not_joined"


def public_invite(invite: dict) -> dict:
    return {
        "invite_id": invite["invite_id"],
        "group_id": invite["group_id"],
        "hobby_key": invite["hobby_key"],
        "hobby_label": invite["hobby_label"],
        "group_name": invite["group_name"],
        "invite_status": invite["invite_status"],
        "invite_mode": invite["invite_mode"],
        "destination": invite["destination"],
        "message": invite["message"],
        "group_summary": find_group_summary(invite["group_id"]),
        "summary_source": find_group_summary_source(invite["group_id"]),
    }


def find_group_summary(group_id: str) -> str | None:
    group = next((item for item in list_hobby_groups() if item["group_id"] == group_id), None)
    return group.get("group_summary") if group else None


def find_group_summary_source(group_id: str) -> str | None:
    group = next((item for item in list_hobby_groups() if item["group_id"] == group_id), None)
    return group.get("summary_source") if group else None


def split_words(text: str) -> list[str]:
    word = ""
    words = []
    for char in text.lower():
        if char.isalnum():
            word += char
        elif word:
            words.append(word)
            word = ""
    if word:
        words.append(word)
    return words


def hobby_stop_words() -> set[str]:
    return {
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
        "want",
        "wanted",
        "like",
        "likes",
        "interested",
        "interest",
        "hobby",
        "hobbies",
        "start",
        "join",
        "play",
        "group",
        "club",
        "circle",
        "someone",
        "students",
        "student",
        "college",
        "campus",
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_hobby_submissions() -> list[dict]:
    return list_records(HOBBY_SUBMISSION_KIND)


def save_hobby_submission(submission: dict) -> None:
    upsert_record(HOBBY_SUBMISSION_KIND, submission["submission_id"], submission)


def list_hobby_groups() -> list[dict]:
    return list_records(HOBBY_GROUP_KIND)


def save_hobby_group(group: dict) -> None:
    upsert_record(HOBBY_GROUP_KIND, group["group_id"], group)


def list_group_invites() -> list[dict]:
    return list_records(GROUP_INVITE_KIND)


def save_group_invite(invite: dict) -> None:
    upsert_record(GROUP_INVITE_KIND, invite["invite_id"], invite)
