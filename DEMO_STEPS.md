# CampusFlow Demo Steps

Use these commands from the project root:

```bash
cd /Users/piyushkant/Documents/GitHub/HackOn-6.0
```

## Required Env

Create the backend env file:

```bash
cp backend/.env.example backend/.env
```

For a safe local demo without automatic Discord sends, keep:

```env
APP_NAME=AmazonHackon Backend
APP_ENV=development
API_V1_PREFIX=/api/v1
PUBLIC_BASE_URL=http://127.0.0.1:8000

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/v1/integrations/google/callback

DISCORD_WEBHOOK_URL=
DISCORD_PUBLIC_KEY=
DISCORD_BOT_TOKEN=
DISCORD_CHANNEL_ID=
DISCORD_SCHEDULER_ENABLED=false
```

For the Discord part of the demo, set one of these:

```env
# Native Discord buttons
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=your-discord-channel-id
PUBLIC_BASE_URL=https://your-public-tunnel.example.com

# Optional, for Discord interaction signature verification
DISCORD_PUBLIC_KEY=your-discord-application-public-key
```

Or use webhook fallback links:

```env
DISCORD_WEBHOOK_URL=your-discord-webhook-url
PUBLIC_BASE_URL=https://your-public-tunnel.example.com
```

Keep automatic class-end sends disabled unless you intentionally want real scheduled sends:

```env
DISCORD_SCHEDULER_ENABLED=false
```

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Start the backend:

```bash
cd /Users/piyushkant/Documents/GitHub/HackOn-6.0/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Backend docs:

```text
http://127.0.0.1:8000/docs
```

## Frontend Setup

```bash
cd /Users/piyushkant/Documents/GitHub/HackOn-6.0/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## API Test Commands

Set your PDF path:

```bash
export TIMETABLE_PDF="/absolute/path/to/semester-timetable.pdf"
```

Upload timetable PDF:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/campusflow/timetable/upload-pdf \
  -F "file=@${TIMETABLE_PDF}"
```

Get parsed timetable:

```bash
curl http://127.0.0.1:8000/api/v1/campusflow/timetable | python -m json.tool
```

Get CampusFlow overview:

```bash
curl http://127.0.0.1:8000/api/v1/campusflow/overview | python -m json.tool
```

Manually trigger today's Discord scheduled prompts:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/integrations/discord/scheduled-feedback/run-today | python -m json.tool
```

## Demo Flow

1. Open the dashboard at `http://localhost:3000`.
2. Show the default demo timetable and attendance fallback.
3. Upload the semester timetable PDF in the **Semester timetable** section.
4. Show the parsed weekly timetable cards.
5. Show that the attendance tracker now uses parsed timetable subjects.
6. Click **Run today's prompts** in the Google Classroom + Discord panel.
7. Show the Discord attendance message with:
   - Held + attended
   - Held + missed
   - Cancelled
   - Teacher absent

## Common Errors

### Discord Message Not Sent

Check that either bot credentials or webhook fallback is configured:

```env
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
```

or:

```env
DISCORD_WEBHOOK_URL=...
```

Then restart the backend after editing `backend/.env`.

### PDF Not Parsed

Use a text-based PDF, not a scanned image PDF. The parser expects readable text with weekday, time, and subject details, for example:

```text
Monday | 09:00-10:00 | CS101 Data Structures | Room A101
Tue 9:00 AM - 10:00 AM MA102 Discrete Math Faculty: Dr Rao
M 9-10 CS101 Data Structures
```

If the frontend says no rows matched, try exporting the timetable as a text-based PDF again.

### Backend Not Connecting To Frontend

Confirm the backend is running:

```text
http://127.0.0.1:8000/docs
```

Confirm the frontend uses the default API base:

```text
http://127.0.0.1:8000/api/v1
```

If you changed it, set this in `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Restart `npm run dev` after changing frontend env values.

### CORS Or Localhost Issue

Use these URLs exactly for local demo:

```text
Frontend: http://localhost:3000
Backend:  http://127.0.0.1:8000
```

The backend already allows both `localhost:3000` and `127.0.0.1:3000`.

### Ngrok Or PUBLIC_BASE_URL Issue

Discord must reach your backend for interaction callbacks and feedback links. If using ngrok or another tunnel, set:

```env
PUBLIC_BASE_URL=https://your-public-tunnel.example.com
```

For native Discord buttons, set the Discord Interactions Endpoint URL to:

```text
https://your-public-tunnel.example.com/api/v1/integrations/discord/interactions
```

Restart the backend after changing `PUBLIC_BASE_URL`.

## Demo Reset

Runtime demo data is local and ignored by git:

```text
backend/app/data/timetable.json
backend/app/data/attendance_events.json
backend/app/data/discord_notification_log.json
```

Delete those files only when you intentionally want to reset the local demo state.
