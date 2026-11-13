# AI Travel Planner

AI-powered travel planner with a Next.js frontend and a Flask/LangGraph backend. It generates travel plans with attractions, restaurants, hotels, weather information, and a day-by-day itinerary.

## Project structure

- `frontend/` — Next.js application
- `backend/` — Flask API, LangGraph workflow, agents, SQLite persistence
- `render.yaml` — Render Blueprint for the backend
- `DEPLOYMENT_GUIDE.md` — step-by-step free deployment instructions

## API keys

Create `backend/.env` locally using `backend/.env.example` as a reference. The main key for itinerary generation is `GROQ_API_KEY`. `TAVILY_API_KEY` and `OPENWEATHER_API_KEY` enable search and weather features. Pexels and Gmail credentials are optional.

Never commit `.env` or publish API keys. Add the same values as environment variables in Render when deploying.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

The API runs at `http://127.0.0.1:5000`.

### Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. By default, the frontend connects to the local API. To override it, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.

## Free deployment

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for the Vercel + Render setup. In brief:

- Deploy `frontend/` to Vercel with `NEXT_PUBLIC_API_URL` set to the Render API URL.
- Deploy `backend/` to Render using the included `render.yaml` Blueprint.
- Set `FRONTEND_URL` on Render to the deployed Vercel origin.

## Important hosting limitation

The backend currently stores user accounts and saved trips in SQLite (`backend/trips.db`). Render's free filesystem is ephemeral, so SQLite data may be lost after a restart or redeploy. Move to a persistent PostgreSQL database before relying on long-term user data. The in-process six-hour scheduler also cannot reliably run while a free Render service is asleep.
