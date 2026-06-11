from app.schemas.agent import AgentPlanRequest, AgentPlanResponse, AgentStep


class PlannerAgent:
    """Rule-based placeholder until the real LLM provider is finalized."""

    def generate_plan(self, payload: AgentPlanRequest) -> AgentPlanResponse:
        constraints = ", ".join(payload.constraints) if payload.constraints else "none"

        return AgentPlanResponse(
            summary=(
                f"Build a customer-focused solution for {payload.target_user}. "
                f"Core problem: {payload.problem_statement}. Constraints: {constraints}."
            ),
            recommended_flow=[
                AgentStep(
                    title="Understand user intent",
                    description=(
                        "Collect the user's goal, context, and constraints through a simple UI flow."
                    ),
                    owner_hint="Frontend + Backend",
                ),
                AgentStep(
                    title="Generate an AI-assisted recommendation",
                    description=(
                        "Use an agent layer to reason over the user input and produce a structured result."
                    ),
                    owner_hint="Backend / AI",
                ),
                AgentStep(
                    title="Show an actionable result",
                    description=(
                        "Return a concise response with next steps, confidence, and useful explanation."
                    ),
                    owner_hint="Frontend",
                ),
            ],
            demo_angle=(
                "Start with a relatable customer problem, show the live AI-assisted flow, "
                "then end with measurable impact."
            ),
            next_questions=[
                "What exact theme is announced in the kickoff webinar?",
                "What data source or API can make the demo feel real?",
                "What is the one metric judges should remember?",
            ],
        )
