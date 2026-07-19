# RiseUp — child growth tracking (Flask + Supabase)

Single-file Flask app (`app.py`). Jinja templates + Bootstrap 5; Chart.js via CDN. Auth via flask-login. Chatbot uses Gemini through the OpenAI-compatible endpoint.

## Run

```bash
./.venv1/Scripts/python app.py        # venv is .venv1 (NOT .venv); serves on http://127.0.0.1:8080
./.venv1/Scripts/pip install -r requirements.txt
```

Bare `python` on this machine has no packages installed — always use `.venv1`. Secrets live in `.env` (SUPABASE_URL, SUPABASE_KEY, NEXT_PUBLIC_GEMINI_API_KEY, SECRET_KEY).

## Database (Supabase / PostgREST client)

- `users`: PK `id`, columns `email`, `password_hash`
- `children`: PK `child_id` (NOT `id` — common bug source), FK `user_id`, `name`, `birthday` (text `YYYY-MM-DD`), `gender` (`male`/`female`), `height` (latest)
- `records`: FK `child_id`, `height`, `date` (text — may be `YYYY-MM-DD` or `MM-DD-YYYY`; parse both)
- `chat_history`: `user_id`, `message_id` (autoincrement, used for ordering), `message` (jsonb `{"role": ..., "content": ...}`)

supabase-py quirks: `.maybe_single().execute()` returns a falsy value when no row matches — check `if not row` before `row.data`. Always scope queries by `user_id` for authorization.

## Gotchas

- WHO growth reference tables (`data/*.xlsx`) load once at import time via pandas; percentile columns are labels like `P3`…`P97`. `static/data/` is a stale duplicate of `data/` — edit `data/` only.
- Jinja `{{ ... }}` inside `<script>` blocks triggers false-positive JS errors in IDE diagnostics — ignore them.
- Legacy/scratch files, do not extend: `main.py`, `testdeepseek.py`, `db/` (old sqlite version, superseded by Supabase; commented-out code in `app.py` is the old sqlite implementation).

## Deploy

Docker → Cloud Run (gunicorn, `$PORT`); `vercel.json` also present. Keep `app.py` importable as `app:app`.
