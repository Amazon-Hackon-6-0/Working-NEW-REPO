from fastapi import APIRouter

from app.schemas.agent import AgentPlanRequest, AgentPlanResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["AI Agent"])
agent_service = AgentService()


@router.post("/plan", response_model=AgentPlanResponse)
async def create_agent_plan(payload: AgentPlanRequest) -> AgentPlanResponse:
    return agent_service.create_plan(payload)
