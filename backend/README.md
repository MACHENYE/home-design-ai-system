# Home Design AI Backend

This backend powers the graduation-project demo for an interactive home-design AI system. It serves the frontend, stores generation tasks in SQLite, and wraps external image-generation APIs.

It supports:

- Static frontend at `http://127.0.0.1:8000`
- Image uploads exposed through `/uploads`
- Async design generation tasks
- NanoBanana callbacks and manual refresh
- Mock mode for a runnable demo without local model deployment or API keys

## Setup

### Prereq

- Python **3.10+** (this project will not run on Python 2.x).

1) Create a `.env` from the example:

```powershell
cp .env.example .env
```

2) Fill in:

- `AI_PROVIDER` (`auto`, `mock`, or `nanobanana`)
- `NANOBANANA_API_KEY`
- `PUBLIC_BASE_URL` (must be publicly reachable if you want NanoBanana callbacks to hit your server)

> For local dev, use a tunneling tool (e.g. ngrok) and set `PUBLIC_BASE_URL` to the tunnel URL.

3) Install deps and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API

- `GET /` Frontend app
- `GET /api/v1/design/presets` Frontend option presets
- `POST /api/v1/assets/upload` Upload image bytes and expose them at `/uploads`
- `POST /api/v1/design/submit` Submit a task (basic/pro)
- `GET /api/v1/tasks` List recent tasks
- `GET /api/v1/tasks/{task_id}` Get stored status/result
- `POST /api/v1/tasks/{task_id}/refresh` Poll NanoBanana `/record-info` and update stored status
- `POST /api/v1/nanobanana/callback` Callback receiver (the URL sent as `callBackUrl`)
