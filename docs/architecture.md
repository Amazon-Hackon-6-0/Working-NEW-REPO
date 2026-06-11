# Backend and AI Agent Architecture

Owner: Pranjay Singh

## Goal

Create a backend template that lets the team plug in the final hackathon idea quickly after the kickoff webinar.

## Current Flow

```text
Frontend
  -> FastAPI route
  -> Agent service
  -> Planner agent
  -> Structured JSON response
```

## Initial API Contract

```text
POST /api/v1/agent/plan
```

Input:

```json
{
  "problem_statement": "Help customers compare products faster",
  "target_user": "Online shoppers",
  "constraints": ["48 hour hackathon", "must have demo"]
}
```

Output:

```json
{
  "summary": "...",
  "recommended_flow": [
    {
      "title": "...",
      "description": "...",
      "owner_hint": "..."
    }
  ],
  "demo_angle": "...",
  "next_questions": ["..."]
}
```

## LLM Integration Plan

The current `PlannerAgent` is rule-based. Once the final idea is decided, replace its internals with:

- Bedrock model call, or
- OpenAI model call, or
- a hybrid retrieval + generation flow

Keep the route and response schema stable so the frontend does not break.
