from datetime import datetime, timezone

from app.services.campusbuddy.memory_service import get_current_user_id, get_matchable_memories
from app.services.campusbuddy.sqlite_store import count_records, list_records, upsert_record


CONNECTION_REQUEST_KIND = "connection_request"


def create_connection_request(
    connection_id: str,
    request_message: str,
    topic: str,
    category: str,
    requester_user_id: str | None = None,
):
    requester_user_id = requester_user_id or get_current_user_id()
    helper_user_id = resolve_helper_user_id(connection_id, requester_user_id)
    if helper_user_id is None:
        return {
            "error": "invalid_connection",
            "message": "Could not create request because the anonymous connection is no longer available.",
        }

    request_id = f"request_{count_records(CONNECTION_REQUEST_KIND) + 1:03d}"
    connection_request = {
        "request_id": request_id,
        "requester_user_id": requester_user_id,
        "helper_user_id": helper_user_id,
        "requester_alias": anonymous_name_for_user(requester_user_id),
        "helper_alias": anonymous_name_for_user(helper_user_id),
        "topic": topic,
        "category": category,
        "request_message": request_message,
        "status": "pending",
        "requester_reveal_consent": False,
        "helper_reveal_consent": False,
        "identity_revealed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_connection_request(connection_request)

    return {
        "request_id": request_id,
        "status": "pending",
        "requester_alias": connection_request["requester_alias"],
        "helper_alias": connection_request["helper_alias"],
        "topic": topic,
        "message": "Anonymous request sent. The helper can accept or deny from their inbox.",
    }


def get_incoming_connection_requests(user_id: str):
    return {
        "user_alias": anonymous_name_for_user(user_id),
        "incoming_requests": [
            public_incoming_request(connection_request)
            for connection_request in list_connection_requests()
            if connection_request["helper_user_id"] == user_id
        ],
        "outgoing_requests": [
            public_incoming_request(connection_request)
            for connection_request in list_connection_requests()
            if connection_request["requester_user_id"] == user_id
        ],
    }


def respond_to_connection_request(request_id: str, user_id: str, action: str):
    connection_request = find_connection_request(request_id)
    if connection_request is None:
        return {
            "error": "request_not_found",
            "message": "Connection request was not found.",
        }

    if connection_request["helper_user_id"] != user_id:
        return {
            "error": "not_allowed",
            "message": "Only the anonymous helper for this request can accept or deny it.",
        }

    if action not in {"accepted", "denied"}:
        return {
            "error": "invalid_action",
            "message": "Action must be accepted or denied.",
        }

    connection_request["status"] = action
    save_connection_request(connection_request)
    return public_incoming_request(connection_request)


def give_reveal_consent(request_id: str, user_id: str):
    connection_request = find_connection_request(request_id)
    if connection_request is None:
        return {
            "error": "request_not_found",
            "message": "Connection request was not found.",
        }

    if user_id == connection_request["requester_user_id"]:
        connection_request["requester_reveal_consent"] = True
    elif user_id == connection_request["helper_user_id"]:
        connection_request["helper_reveal_consent"] = True
    else:
        return {
            "error": "not_allowed",
            "message": "Only the requester or helper can give reveal consent for this request.",
        }

    connection_request["identity_revealed"] = (
        connection_request["requester_reveal_consent"]
        and connection_request["helper_reveal_consent"]
    )
    save_connection_request(connection_request)
    return public_reveal_status(connection_request)


def find_connection_request(request_id: str):
    for connection_request in list_connection_requests():
        if connection_request["request_id"] == request_id:
            return connection_request
    return None


def list_connection_requests() -> list[dict]:
    return list_records(CONNECTION_REQUEST_KIND)


def save_connection_request(connection_request: dict) -> None:
    upsert_record(
        CONNECTION_REQUEST_KIND,
        connection_request["request_id"],
        connection_request,
    )


def resolve_helper_user_id(connection_id: str, requester_user_id: str):
    parsed = parse_connection_id(connection_id)
    if parsed is None:
        return None

    helper_user_id, memory_id = parsed
    if helper_user_id == requester_user_id:
        return None

    for memory in get_matchable_memories(exclude_user_id=requester_user_id):
        if memory["user_id"] == helper_user_id and memory["id"] == memory_id:
            return helper_user_id
    return None


def parse_connection_id(connection_id: str):
    prefix = "connection_"
    if not connection_id.startswith(prefix):
        return None

    connection_body = connection_id[len(prefix):]
    if "_" not in connection_body:
        return None

    helper_user_id, memory_id_text = connection_body.rsplit("_", 1)
    try:
        memory_id = int(memory_id_text)
    except ValueError:
        return None
    return helper_user_id, memory_id


def public_incoming_request(connection_request: dict):
    identity_revealed = connection_request["identity_revealed"]
    return {
        "request_id": connection_request["request_id"],
        "requester_alias": connection_request["requester_alias"],
        "helper_alias": connection_request["helper_alias"],
        "topic": connection_request["topic"],
        "category": connection_request["category"],
        "request_message": connection_request["request_message"],
        "status": connection_request["status"],
        "requester_reveal_consent": connection_request["requester_reveal_consent"],
        "helper_reveal_consent": connection_request["helper_reveal_consent"],
        "identity_revealed": identity_revealed,
        "visible_requester_name": visible_name_for_user(
            connection_request["requester_user_id"],
            connection_request["requester_alias"],
            identity_revealed,
        ),
        "visible_helper_name": visible_name_for_user(
            connection_request["helper_user_id"],
            connection_request["helper_alias"],
            identity_revealed,
        ),
        "created_at": connection_request["created_at"],
    }


def public_reveal_status(connection_request: dict):
    identity_revealed = connection_request["identity_revealed"]
    return {
        "request_id": connection_request["request_id"],
        "reveal_status": reveal_status(connection_request),
        "requester_reveal_consent": connection_request["requester_reveal_consent"],
        "helper_reveal_consent": connection_request["helper_reveal_consent"],
        "identity_revealed": identity_revealed,
        "visible_requester_name": visible_name_for_user(
            connection_request["requester_user_id"],
            connection_request["requester_alias"],
            identity_revealed,
        ),
        "visible_helper_name": visible_name_for_user(
            connection_request["helper_user_id"],
            connection_request["helper_alias"],
            identity_revealed,
        ),
    }


def reveal_status(connection_request: dict):
    if connection_request["identity_revealed"]:
        return "identity_revealed"
    if connection_request["requester_reveal_consent"] and not connection_request["helper_reveal_consent"]:
        return "waiting_for_helper_consent"
    if connection_request["helper_reveal_consent"] and not connection_request["requester_reveal_consent"]:
        return "waiting_for_requester_consent"
    return "waiting_for_both_consents"


def visible_name_for_user(user_id: str, alias: str, identity_revealed: bool):
    if not identity_revealed:
        return alias
    return demo_name_for_user(user_id)


def demo_name_for_user(user_id: str):
    demo_names = {
        "student_001": "Current Student",
        "student_002": "Demo DSA Helper",
        "student_003": "Demo React Helper",
        "student_004": "Demo Sports Buddy",
        "student_005": "Demo Campus Guide",
        "student_006": "Demo Career Mentor",
    }
    return demo_names.get(user_id, anonymous_name_for_user(user_id))


def anonymous_name_for_user(user_id: str):
    suffix = user_id.split("_")[-1]
    return f"Anonymous Student {suffix}"
