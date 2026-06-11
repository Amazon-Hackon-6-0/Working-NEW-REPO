from app.agents.planner import PlannerAgent
from app.schemas.agent import AgentPlanRequest, AgentPlanResponse


class AgentService:
    def __init__(self) -> None:
        self.planner_agent = PlannerAgent()

    def create_plan(self, payload: AgentPlanRequest) -> AgentPlanResponse:
        return self.planner_agent.generate_plan(payload)
