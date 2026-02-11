# AI Designer Prototype

Monorepo for an AI image generation app with:
- `backend`: Flask API for image generation and image history/storage
- `frontend`: Vue + Vite UI that calls the backend API

## Repo Structure

```text
.
├── backend
└── frontend
```

## Prerequisites

- Python 3.10+
- Node.js 20+
- npm
- OpenAI API key

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `backend/.env` with a valid `OPENAI_API_KEY`.

Run the backend:

```bash
cd backend
source .venv/bin/activate
flask run --host 127.0.0.1 --port 5000
```

Health check:

```bash
curl http://127.0.0.1:5000/
```

## Frontend Setup

```bash
cd frontend
npm install
```

Run the frontend in development:

```bash
cd frontend
npm run dev
```

By default, Vite proxies `/api` requests to `http://127.0.0.1:5000`.

## API Endpoints

- `GET /` health check
- `POST /api/images/generate` generate an image
- `POST /api/images/openai` generate an image via OpenAI provider
- `GET /api/images` list generated images
- `GET /api/images/:image_id` get metadata for one image
- `GET /api/images/:image_id/file` get the image file

Example request:

```bash
curl -X POST http://127.0.0.1:5000/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A minimal poster of a mountain at sunrise"}'
```

## Build Frontend

```bash
cd frontend
npm run build
```
