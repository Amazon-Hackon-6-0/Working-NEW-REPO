from pydantic import BaseModel, Field


class AgentPlanRequest(BaseModel):
    problem_statement: str = Field(
        ...,
        min_length=10,
        description="The customer problem the team wants to solve.",
    )
    target_user: str = Field(
        ...,
        min_length=2,
        description="Primary user or customer segment.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Hackathon, technical, business, or demo constraints.",
    )


class AgentStep(BaseModel):
    title: str
    description: str
    owner_hint: str


class AgentPlanResponse(BaseModel):
    summary: str
    recommended_flow: list[AgentStep]
    demo_angle: str
    next_questions: list[str]
