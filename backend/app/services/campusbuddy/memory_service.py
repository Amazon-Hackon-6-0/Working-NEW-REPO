from fastapi import HTTPException

from app.services.campusbuddy.sqlite_store import create_sequential_record, delete_record, list_records, upsert_record

MEMORY_KIND = "memory"


def require_user_id(user_id: str | None) -> str:
    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id:
        raise HTTPException(status_code=401, detail="CampusBuddy user identity is required.")
    return normalized_user_id


def get_trust_dashboard(user_id: str):
    user_id = require_user_id(user_id)
    return {
        "student_alias": anonymous_name_for_student(user_id),
        "memory_paused": False,
        "privacy_mode": "Anonymous by default",
        "memories": get_user_memories(user_id),
    }


def get_user_memories(user_id: str):
    return [memory for memory in list_records(MEMORY_KIND) if memory["user_id"] == user_id]


def get_matchable_memories(exclude_user_id: str):
    return get_connector_candidate_memories(exclude_user_id)


def get_connector_candidate_memories(
    exclude_user_id: str,
    include_group_suggestions: bool = False,
):
    return [
        memory
        for memory in list_records(MEMORY_KIND)
        if memory["user_id"] != exclude_user_id
        and not is_seeded_or_demo_profile(memory)
        and (
            memory.get("can_be_used_for_matching") is True
            or memory.get("used_for", {}).get("peer_matching") is True
            or (
                include_group_suggestions
                and memory.get("used_for", {}).get("group_suggestions") is True
            )
        )
    ]


def is_seeded_or_demo_profile(memory: dict):
    profile_text = " ".join(
        str(memory.get(field, "")).lower()
        for field in ["memory_type", "type", "reason", "source", "consent_status"]
    )
    blocked_markers = [
        "consented_demo_user_profile",
        "demo profile",
        "seeded profile",
        "hardcoded helper",
    ]
    return any(marker in profile_text for marker in blocked_markers)


def get_group_suggestion_memories():
    return [
        memory
        for memory in list_records(MEMORY_KIND)
        if memory.get("used_for", {}).get("group_suggestions") is True
    ]


def remember_memory(
    label: str,
    student_id: str,
    memory_type: str = "Student-approved memory",
    used_for: dict | None = None,
):
    student_id = require_user_id(student_id)
    used_for = used_for or {
        "personalization": True,
        "peer_matching": False,
        "group_suggestions": False,
        "anonymous_campus_insight": False,
    }
    def build_memory(record_id: str) -> dict:
        next_id = int(record_id.rsplit("_", 1)[-1])
        return {
            "id": next_id,
            "memory_id": record_id,
            "user_id": student_id,
            "label": label,
            "text": label,
            "reason": "Saved only after the student clicked Remember.",
            "memory_type": memory_type,
            "type": memory_type,
            "visibility": "private_to_student",
            "can_be_used_for_matching": bool(used_for.get("peer_matching")),
            "used_for": used_for,
        }

    return create_sequential_record(MEMORY_KIND, "memory", build_memory)


def delete_memory(memory_id: int, user_id: str):
    user_id = require_user_id(user_id)
    memory = next(
        (
            item
            for item in list_records(MEMORY_KIND)
            if item["id"] == memory_id and item["user_id"] == user_id
        ),
        None,
    )
    record_id = memory.get("memory_id", str(memory_id)) if memory else str(memory_id)
    deleted = bool(memory and delete_record(MEMORY_KIND, record_id))
    return {"deleted": deleted, "id": memory_id}


def anonymous_name_for_student(user_id: str) -> str:
    suffix = user_id.split("_")[-1]
    return f"Anonymous Student {suffix}"
