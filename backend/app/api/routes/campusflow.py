from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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
    TimetableResponse,
    TimetableTodayResponse,
    TimetableUploadResponse,
)
from app.services.assignment_repository import AssignmentRepository
from app.services.attendance_repository import AttendanceRepository
from app.services.campusflow_service import CampusFlowService
from app.services.exam_repository import ExamRepository
from app.services.exam_schedule_service import ExamScheduleService
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
    return campusflow_service.answer_question(payload)
