from fastapi import APIRouter, HTTPException
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.campusbuddy.ai_service import get_ai_status, get_chat_response, get_gemini_debug_status
from app.services.campusbuddy.complaint_service import (
    list_mock_discord_escalations,
    retry_pending_discord_escalations,
    submit_complaint,
)
from app.services.campusbuddy.connection_request_service import (
    create_connection_request,
    give_reveal_consent,
    get_incoming_connection_requests,
    respond_to_connection_request,
)
from app.services.campusbuddy.escalation_service import committee_dashboard, prepare_escalation
from app.services.campusbuddy.hobby_group_service import (
    build_groups_from_trust_memories,
    ignore_group_invite,
    join_group,
    list_group_invites_for_student,
    submit_hobby,
)
from app.services.campusbuddy.matching_service import connect_student
from app.services.campusbuddy.memory_service import delete_memory, get_trust_dashboard, remember_memory
from app.services.campusbuddy.memory_service import require_user_id

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    student_id: str


class ChatResponse(BaseModel):
    source: Literal["gemini", "mock"]
    reply: str
    reply_text: str
    intent: str
    detected_intent: str
    actions: list[Any] = Field(default_factory=list)
    suggested_actions: list[Any] = Field(default_factory=list)
    memory_candidate: dict[str, Any] = Field(default_factory=dict)
    memory_suggestions: list[Any] = Field(default_factory=list)
    privacy_note: str
    escalation_preview: dict[str, Any] | None = None
    matching_query: dict[str, Any] | None = None
    fallback_reason: str | None = None


class AIStatusResponse(BaseModel):
    gemini_key_present: bool
    gemini_model: str
    mode: Literal["gemini_possible", "mock_only"]


class GeminiDebugResponse(BaseModel):
    gemini_key_present: bool
    gemini_model: str
    gemini_test_success: bool
    safe_error: str | None = None


class MemoryRequest(BaseModel):
    label: str
    memory_type: str = "Student-approved memory"
    used_for: dict = Field(default_factory=dict)
    student_id: str


class ConnectRequest(BaseModel):
    need: str | None = None
    query: str | None = None
    message: str | None = None
    request_text: str | None = None
    student_id: str


class ConnectionRequestCreate(BaseModel):
    connection_id: str
    request_message: str
    topic: str
    category: str
    requester_user_id: str | None = None
    student_id: str | None = None


class ConnectionRequestResponse(BaseModel):
    user_id: str
    action: Literal["accepted", "denied"]


class RevealConsentRequest(BaseModel):
    user_id: str


class ComplaintRequest(BaseModel):
    student_id: str
    complaint_text: str | None = None
    text: str | None = None


class GroupRequest(BaseModel):
    interest: str | None = None
    hobby: str | None = None
    hobby_text: str | None = None
    student_id: str


class GroupJoinRequest(BaseModel):
    student_id: str


class EscalationRequest(BaseModel):
    category: str
    description: str


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    require_user_id(request.student_id)
    return get_chat_response(request.message, request.student_id)


@router.get("/ai-status", response_model=AIStatusResponse)
def ai_status():
    return get_ai_status()


@router.get("/gemini-debug", response_model=GeminiDebugResponse)
def gemini_debug():
    return get_gemini_debug_status()


@router.get("/trust-dashboard")
def trust_dashboard(student_id: str):
    return get_trust_dashboard(student_id)


@router.post("/memory")
def memory(request: MemoryRequest):
    return remember_memory(request.label, request.student_id, request.memory_type, request.used_for or None)


@router.delete("/memory/{memory_id}")
def remove_memory(memory_id: int, student_id: str):
    return delete_memory(memory_id, student_id)


@router.post("/connect")
def connect(request: ConnectRequest):
    request_text = request.query or request.message or request.request_text or request.need or ""
    return connect_student(request_text, request.student_id)


@router.post("/complaints")
def submit_student_complaint(request: ComplaintRequest):
    complaint_text = request.complaint_text or request.text or ""
    complaint_text = complaint_text.strip()
    if not complaint_text:
        raise HTTPException(status_code=400, detail="Complaint text is required.")
    return submit_complaint(request.student_id, complaint_text)


@router.get("/complaints/escalations")
def get_complaint_escalations():
    return {"outbox": list_mock_discord_escalations()}


@router.post("/complaints/escalations/retry-discord")
def retry_complaint_escalation_discord_delivery():
    return retry_pending_discord_escalations()


@router.post("/connection-requests")
def create_connector_request(request: ConnectionRequestCreate):
    return create_connection_request(
        request.connection_id,
        request.request_message,
        request.topic,
        request.category,
        request.requester_user_id or request.student_id,
    )


@router.get("/connection-requests")
def incoming_connection_requests(user_id: str):
    return get_incoming_connection_requests(user_id)


@router.post("/connection-requests/{request_id}/respond")
def respond_connector_request(request_id: str, request: ConnectionRequestResponse):
    return respond_to_connection_request(request_id, request.user_id, request.action)


@router.post("/connection-requests/{request_id}/reveal-consent")
def reveal_consent(request_id: str, request: RevealConsentRequest):
    return give_reveal_consent(request_id, request.user_id)


@router.post("/groups")
def groups(request: GroupRequest):
    hobby_text = request.hobby_text or request.hobby or request.interest or ""
    hobby_text = hobby_text.strip()
    if not hobby_text:
        raise HTTPException(status_code=400, detail="Hobby or interest text is required.")
    return submit_hobby(request.student_id, hobby_text)


@router.get("/groups")
def get_groups(student_id: str | None = None):
    return build_groups_from_trust_memories(student_id)


@router.get("/groups/invites")
def get_group_invites(student_id: str):
    return list_group_invites_for_student(student_id)


@router.post("/groups/{group_id}/join")
def join_campus_group(group_id: str, request: GroupJoinRequest):
    return join_group(group_id, request.student_id)


@router.post("/groups/{group_id}/ignore")
def ignore_campus_group(group_id: str, request: GroupJoinRequest):
    return ignore_group_invite(group_id, request.student_id)


@router.post("/committee-escalation")
def committee_escalation(request: EscalationRequest):
    return prepare_escalation(request.category, request.description)


@router.get("/committee-dashboard")
def get_committee_dashboard():
    return committee_dashboard()
