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
- OpenAI API key (for OpenAI provider)
- Krea API key (for Krea provider)

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `backend/.env` with provider keys you use (`OPENAI_API_KEY` and/or `KREA_API_KEY`).
For Krea async jobs you can tune `KREA_POLL_INTERVAL_SECONDS` and `KREA_JOB_TIMEOUT_SECONDS`.
If Krea returns image URLs on additional hosts/CDNs, set `KREA_IMAGE_HOST_ALLOWLIST` as a comma-separated host list.

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
- `POST /api/images/krea` generate an image via Krea provider
- `GET /api/providers` list provider capabilities (models/sizes/qualities) for frontend configuration
- `GET /api/images` list generated images
- `GET /api/runs` list grouped generation runs (one run can contain multiple model outputs)
- `GET /api/images/:image_id` get metadata for one image
- `GET /api/images/:image_id/file` get the image file

Example request:

```bash
curl -X POST http://127.0.0.1:5000/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A minimal poster of a mountain at sunrise"}'
```

Multi-model single-run request:

```bash
curl -X POST http://127.0.0.1:5000/api/images/generate \
  -H "Content-Type: application/json" \
  -d '{"provider":"krea","prompt":"a serene mountain landscape at sunset","models":["qwen_2512","z_image","flux_1_dev"],"size":"1024x1024","steps":28}'
```

Krea examples:

```bash
# Qwen 2512
curl -X POST http://127.0.0.1:5000/api/images/krea \
  -H "Content-Type: application/json" \
  -d '{"prompt":"An arctic village, with auroras illuminating igloos and snow-laden pines.","model":"qwen_2512"}'

# Z Image
curl -X POST http://127.0.0.1:5000/api/images/krea \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Balinese temples, where stone and spirits commune.","model":"z_image","size":"1024x1024"}'

# Flux 1 Dev (async job under the hood)
curl -X POST http://127.0.0.1:5000/api/images/krea \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a serene mountain landscape at sunset","model":"flux_1_dev","size":"1024x576","steps":28}'
```

## Build Frontend

```bash
cd frontend
npm run build
```
