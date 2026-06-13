# Backend Template

Owner: Pranjay Singh

This is the FastAPI backend starter for the HackOn project. It includes a small AI agent planning flow that can be connected to Bedrock, OpenAI, or another LLM provider later.
It now also includes the CampusFlow MVP API for attendance tracking, deadline reminders, exam verification, and grounded campus Q&A.

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
GET  /api/v1/campusflow/overview
POST /api/v1/campusflow/attendance/feedback
POST /api/v1/campusflow/ask
GET  /api/v1/integrations/status
GET  /api/v1/integrations/google/auth-url
GET  /api/v1/integrations/google/login
GET  /api/v1/integrations/google/callback
POST /api/v1/integrations/google/classroom/sync
POST /api/v1/integrations/discord/daily-feedback
POST /api/v1/integrations/discord/interactions
GET  /api/v1/integrations/discord/feedback-link
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

## CampusFlow Example

```bash
curl http://localhost:8000/api/v1/campusflow/overview
```

The overview response contains subject-wise attendance status, bunk budget, exam reminders, assignment state, campus updates, and the daily Discord briefing payload.

## Real Integration Setup

### Google Classroom

Create an OAuth client in Google Cloud Console and enable the Google Classroom API. Add this redirect URI:

```text
http://127.0.0.1:8000/api/v1/integrations/google/callback
```

Set these values in `backend/.env`:

```text
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/v1/integrations/google/callback
```

Then open:

```text
http://127.0.0.1:8000/api/v1/integrations/google/login
```

After consent, call:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/integrations/google/classroom/sync
```

### Discord Feedback

Create a Discord incoming webhook for your private student channel and set:

```text
DISCORD_WEBHOOK_URL=...
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
PUBLIC_BASE_URL=https://your-public-tunnel.example.com
```

If `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` are present, CampusFlow sends native Discord button prompts through the Bot API.

If only `DISCORD_WEBHOOK_URL` is present, the daily feedback prompt falls back to normal webhook links for:

- Held + attended
- Held + missed
- Cancelled
- Teacher absent

For those links to be clickable from Discord, expose the backend publicly with ngrok or Cloudflare Tunnel and set:

```text
PUBLIC_BASE_URL=https://your-public-tunnel.example.com
```

If you later want native Discord buttons instead of links, set the Discord Interactions Endpoint URL to:

```text
https://your-public-tunnel.example.com/api/v1/integrations/discord/interactions
```

Copy your Discord application public key into:

```text
DISCORD_PUBLIC_KEY=...
```

Then send a daily feedback prompt:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/integrations/discord/daily-feedback \
  -H "Content-Type: application/json" \
  -d '{"subject_code":"DBMS"}'
```

## Next Backend Tasks

- Finalize product idea after the kickoff webinar
- Add real LLM provider integration
- Add persistence layer if the app needs saved sessions
- Coordinate API contracts with frontend
- Add deployment settings with Sarthak
