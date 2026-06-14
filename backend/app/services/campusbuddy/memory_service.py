CURRENT_USER_ID = "student_001"

from app.services.campusbuddy.sqlite_store import delete_record, list_records, upsert_record

MEMORY_KIND = "memory"


def get_current_user_id() -> str:
    return CURRENT_USER_ID


def get_trust_dashboard(user_id: str = CURRENT_USER_ID):
    user_id = (user_id or CURRENT_USER_ID).strip() or CURRENT_USER_ID
    return {
        "student_alias": anonymous_name_for_student(user_id),
        "memory_paused": False,
        "privacy_mode": "Anonymous by default",
        "memories": get_user_memories(user_id),
    }


def get_user_memories(user_id: str):
    return [memory for memory in list_records(MEMORY_KIND) if memory["user_id"] == user_id]


def get_matchable_memories(exclude_user_id: str = CURRENT_USER_ID):
    return get_connector_candidate_memories(exclude_user_id)


def get_connector_candidate_memories(
    exclude_user_id: str = CURRENT_USER_ID,
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
    memory_type: str = "Student-approved memory",
    used_for: dict | None = None,
    student_id: str = CURRENT_USER_ID,
):
    memories = list_records(MEMORY_KIND)
    next_id = max([memory["id"] for memory in memories], default=0) + 1
    student_id = (student_id or CURRENT_USER_ID).strip() or CURRENT_USER_ID
    used_for = used_for or {
        "personalization": True,
        "peer_matching": False,
        "group_suggestions": False,
        "anonymous_campus_insight": False,
    }
    memory = {
        "id": next_id,
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
    upsert_record(MEMORY_KIND, str(memory["id"]), memory)
    return memory


def delete_memory(memory_id: int, user_id: str = CURRENT_USER_ID):
    user_id = (user_id or CURRENT_USER_ID).strip() or CURRENT_USER_ID
    memory = next(
        (
            item
            for item in list_records(MEMORY_KIND)
            if item["id"] == memory_id and item["user_id"] == user_id
        ),
        None,
    )
    deleted = bool(memory and delete_record(MEMORY_KIND, str(memory_id)))
    return {"deleted": deleted, "id": memory_id}


def anonymous_name_for_student(user_id: str) -> str:
    if user_id == CURRENT_USER_ID:
        return "Anonymous Student 001"
    suffix = user_id.split("_")[-1]
    return f"Anonymous Student {suffix}"
