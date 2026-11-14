# Free deployment guide (Vercel + Render)

This repository is prepared for a Next.js frontend on Vercel and a Flask API on Render.

## 1. Push to GitHub

Extract this project and push the contents of this folder (`AI_Trip_Planner_Enhanced`) to a GitHub repository. Do not commit `.env` files or API keys. The root `.gitignore` excludes environment files.

## 2. Deploy the backend on Render

1. In Render, choose **New + → Blueprint** and connect this GitHub repository.
2. Render detects `render.yaml` and creates the `ai-travel-planner-api` web service. Alternatively, create a Web Service manually with **Root Directory** `backend`, build command `pip install -r requirements.txt`, and start command `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`.
3. Set the environment variables for the API keys you actually use: `GROQ_API_KEY` (required), `TAVILY_API_KEY`, `OPENWEATHER_API_KEY`, and optional `PEXELS_API_KEY`, `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`.
4. After Vercel is deployed, set `FRONTEND_URL` to the exact Vercel origin, e.g. `https://your-project.vercel.app` (no trailing slash), then redeploy.
5. Check `https://YOUR-RENDER-SERVICE.onrender.com/health`; it should return `{"status":"ok"}`.

## 3. Deploy the frontend on Vercel

1. In Vercel, import the same GitHub repository.
2. Set **Root Directory** to `frontend`. Vercel should detect Next.js automatically.
3. Add the environment variable `NEXT_PUBLIC_API_URL` with the Render service origin, e.g. `https://YOUR-RENDER-SERVICE.onrender.com` (no trailing slash).
4. Deploy. If you change this variable later, redeploy the frontend.

## 4. Important free-tier limitations

- Render free web services spin down after inactivity; the first request after sleeping can take a while.
- The backend currently stores accounts and saved trips in SQLite at `backend/trips.db`. Render's free filesystem is ephemeral, so this data can be lost when the service restarts or redeploys. Use a persistent database (for example, PostgreSQL/Supabase) before relying on saved accounts/trips.
- The APScheduler task runs inside the web process. It will not reliably run every six hours while a free service is asleep. Use an always-on worker or an external scheduled job for dependable alerts.
- Email alerts require valid Gmail credentials and an App Password. SMTP restrictions or provider limits may affect delivery. Set `CHECKS_ADMIN_TOKEN` only if you need to invoke the protected manual check endpoint; send it in the `X-Admin-Token` header.
- Free API plans have quotas and can change.

## 5. Local development

Frontend: `cd frontend && npm install && npm run dev`

Backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python app.py`

The frontend defaults to `http://127.0.0.1:5000` when `NEXT_PUBLIC_API_URL` is not set.

## Authentication and itinerary history

- Users must sign up or sign in before generating or re-optimizing itineraries.
- Generated itineraries are automatically stored against the authenticated account and remain until manually deleted.
- Existing password hashes are upgraded automatically after a successful login; users do not need to reset their passwords.
- Sessions expire after 30 days by default. `SESSION_DAYS` can override this in the backend environment.
- Re-optimizing one day excludes attractions scheduled on other days, while allowing that day's original attractions to remain candidates. The updated day is persisted without changing the other days.
