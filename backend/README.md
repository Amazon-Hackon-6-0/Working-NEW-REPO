# Backend Template

Owner: Pranjay Singh

This is the FastAPI backend starter for the HackOn project. It includes a small AI agent planning flow that can be connected to Bedrock, OpenAI, or another LLM provider later.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs will be available at:

```text
http://localhost:8000/docs
```

## Endpoints

```text
GET  /health
POST /api/v1/agent/plan
```

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/agent/plan \
  -H "Content-Type: application/json" \
  -d '{
    "problem_statement": "Help customers compare products faster",
    "target_user": "Online shoppers",
    "constraints": ["48 hour hackathon", "must have demo"]
  }'
```

## Next Backend Tasks

- Finalize product idea after the kickoff webinar
- Add real LLM provider integration
- Add persistence layer if the app needs saved sessions
- Coordinate API contracts with frontend
- Add deployment settings with Sarthak
