from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas.campusflow import (
    AttendanceEvent,
    AttendanceFeedback,
    AttendanceFeedbackResponse,
    CampusFlowOverview,
    CampusQuestionRequest,
    CampusQuestionResponse,
    ExamReminder,
    ExamScheduleUpload,
    ExamScheduleUploadResponse,
    ProcessCaseCreateRequest,
    ProcessCaseReplyRequest,
    ProcessCaseResponse,
    ProcessCaseSendRequest,
    ProcessCopilotAskRequest,
    ProcessCopilotAskResponse,
    ProcessInboundReplyRequest,
    ProcessPolicyListResponse,
    ProcessPolicyUploadResponse,
    ProcessTaskUpdateRequest,
    TimetableResponse,
    TimetableTodayResponse,
    TimetableUploadResponse,
)
from app.services.assignment_repository import AssignmentRepository
from app.services.attendance_repository import AttendanceRepository
from app.services.campusflow_service import CampusFlowService
from app.services.exam_repository import ExamRepository
from app.services.exam_schedule_service import ExamScheduleService
from app.services.process_copilot_service import ProcessCopilotService
from app.services.timetable_repository import TimetableRepository
from app.services.timetable_service import TimetableService

router = APIRouter(prefix="/campusflow", tags=["CampusFlow"])
attendance_repository = AttendanceRepository()
assignment_repository = AssignmentRepository()
exam_repository = ExamRepository()
timetable_repository = TimetableRepository()
timetable_service = TimetableService(timetable_repository)
campusflow_service = CampusFlowService(
    attendance_repository,
    assignment_repository,
    exam_repository,
    timetable_service,
)
exam_schedule_service = ExamScheduleService(exam_repository)
process_copilot_service = ProcessCopilotService()


@router.get("/overview", response_model=CampusFlowOverview)
async def get_overview() -> CampusFlowOverview:
    return campusflow_service.get_overview()


@router.get("/attendance/events", response_model=list[AttendanceEvent])
async def get_attendance_events() -> list[AttendanceEvent]:
    return campusflow_service.list_attendance_events()


@router.get("/timetable", response_model=TimetableResponse)
async def get_timetable() -> TimetableResponse:
    return campusflow_service.get_timetable()


@router.get("/timetable/today", response_model=TimetableTodayResponse)
async def get_timetable_today() -> TimetableTodayResponse:
    return campusflow_service.get_timetable_today()


@router.post("/timetable/upload-pdf", response_model=TimetableUploadResponse)
async def upload_timetable_pdf(file: UploadFile = File(...)) -> TimetableUploadResponse:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Upload a PDF file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

    try:
        return timetable_service.upload_pdf_timetable(
            filename=file.filename or "semester_timetable.pdf",
            content=content,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process PDF: {exc}") from exc


@router.post("/process-copilot/upload-policy", response_model=ProcessPolicyUploadResponse)
async def upload_process_policy_pdf(
    file: UploadFile = File(...),
    college_id: str = Form("default"),
) -> ProcessPolicyUploadResponse:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Upload a PDF file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

    try:
        return process_copilot_service.upload_policy_pdf(
            filename=file.filename or "campus_policy.pdf",
            content=content,
            college_id=college_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process PDF: {exc}") from exc


@router.get("/process-copilot/policies", response_model=ProcessPolicyListResponse)
async def get_process_policies(
    college_id: str | None = Query(None),
) -> ProcessPolicyListResponse:
    return process_copilot_service.list_policies(college_id)


@router.post("/process-copilot/ask", response_model=ProcessCopilotAskResponse)
async def ask_process_copilot(
    payload: ProcessCopilotAskRequest,
) -> ProcessCopilotAskResponse:
    return await process_copilot_service.answer_question(
        question=payload.question,
        college_id=payload.college_id,
    )


@router.post("/process-copilot/cases", response_model=ProcessCaseResponse)
async def create_process_case(
    payload: ProcessCaseCreateRequest,
) -> ProcessCaseResponse:
    return await process_copilot_service.create_case(payload)


@router.get("/process-copilot/cases", response_model=list[ProcessCaseResponse])
async def list_process_cases(
    college_id: str | None = Query(None),
) -> list[ProcessCaseResponse]:
    return process_copilot_service.list_cases(college_id)


@router.get("/process-copilot/cases/{case_id}", response_model=ProcessCaseResponse)
async def get_process_case(case_id: str) -> ProcessCaseResponse:
    case = process_copilot_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Process case not found.")
    return case


@router.post("/process-copilot/cases/{case_id}/send", response_model=ProcessCaseResponse)
async def send_process_case(
    case_id: str,
    payload: ProcessCaseSendRequest | None = None,
) -> ProcessCaseResponse:
    case = process_copilot_service.send_case(case_id, payload)
    if not case:
        raise HTTPException(status_code=404, detail="Process case not found.")
    return case


@router.post("/process-copilot/cases/{case_id}/reply", response_model=ProcessCaseResponse)
async def reply_process_case(
    case_id: str,
    payload: ProcessCaseReplyRequest,
) -> ProcessCaseResponse:
    case = await process_copilot_service.add_case_reply(case_id, payload)
    if not case:
        raise HTTPException(status_code=404, detail="Process case not found.")
    return case


@router.post("/process-copilot/inbound-reply", response_model=ProcessCaseResponse)
async def inbound_process_reply(
    payload: ProcessInboundReplyRequest,
) -> ProcessCaseResponse:
    case = await process_copilot_service.receive_inbound_reply(payload)
    if not case:
        raise HTTPException(status_code=404, detail="Matching process case not found.")
    return case


@router.post(
    "/process-copilot/cases/{case_id}/follow-up",
    response_model=ProcessCaseResponse,
)
async def follow_up_process_case(case_id: str) -> ProcessCaseResponse:
    case = await process_copilot_service.follow_up_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Process case not found.")
    return case


@router.patch(
    "/process-copilot/cases/{case_id}/tasks/{task_id}",
    response_model=ProcessCaseResponse,
)
async def update_process_case_task(
    case_id: str,
    task_id: str,
    payload: ProcessTaskUpdateRequest,
) -> ProcessCaseResponse:
    case = process_copilot_service.update_case_task(case_id, task_id, payload)
    if not case:
        raise HTTPException(status_code=404, detail="Process case or task not found.")
    return case


@router.get("/exams", response_model=list[ExamReminder])
async def get_exams() -> list[ExamReminder]:
    return exam_repository.list_exams()


@router.post("/exams/upload", response_model=ExamScheduleUploadResponse)
async def upload_exam_schedule(payload: ExamScheduleUpload) -> ExamScheduleUploadResponse:
    return exam_schedule_service.upload_schedule(payload)


@router.post("/exams/upload-pdf", response_model=ExamScheduleUploadResponse)
async def upload_exam_schedule_pdf(
    file: UploadFile = File(...),
    confirm_as_latest: bool = Form(False),
) -> ExamScheduleUploadResponse:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Upload a PDF file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

    try:
        return exam_schedule_service.upload_pdf_schedule(
            filename=file.filename or "exam_schedule.pdf",
            content=content,
            confirm_as_latest=confirm_as_latest,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process PDF: {exc}") from exc


@router.post("/attendance/feedback", response_model=AttendanceFeedbackResponse)
async def submit_attendance_feedback(
    payload: AttendanceFeedback,
) -> AttendanceFeedbackResponse:
    try:
        return campusflow_service.apply_feedback(payload)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Subject code not found") from exc


@router.post("/ask", response_model=CampusQuestionResponse)
async def ask_campus_question(payload: CampusQuestionRequest) -> CampusQuestionResponse:
    return await campusflow_service.answer_question(payload)
