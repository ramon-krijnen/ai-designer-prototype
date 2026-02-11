# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: Flask API and image persistence.
- `backend/providers/`: provider abstraction and OpenAI implementation.
- `backend/storage.py`: SQLite-backed metadata/image storage.
- `frontend/`: Vue 3 + Vite client app.
- `frontend/src/`: UI source (`components/`, `assets/`, `main.js`, `App.vue`).
- `frontend/public/`: static assets served as-is.
- `README.md`: setup and API usage overview.

## Build, Test, and Development Commands
- Backend setup:
```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```
- Run backend (dev):
```bash
cd backend && source .venv/bin/activate && flask run --host 127.0.0.1 --port 5000
```
- Frontend setup:
```bash
cd frontend && npm install
```
- Run frontend (dev with HMR):
```bash
cd frontend && npm run dev
```
- Build frontend:
```bash
cd frontend && npm run build
```

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes.
- Vue/JS: 2-space indentation, component files in `PascalCase` (for example `WelcomeItem.vue`), variables/functions in `camelCase`.
- Keep modules focused: provider logic stays in `backend/providers/`, persistence logic in `backend/storage.py`.
- Use clear API names under `/api/images/...` and avoid breaking existing response fields.

## Testing Guidelines
- No automated test suite is committed yet.
- For backend additions, prefer `pytest` with tests under `backend/tests/` named `test_*.py`.
- For frontend additions, prefer Vitest + Vue Test Utils with tests under `frontend/src/**/__tests__/`.
- Minimum expectation for PRs: manual verification of image generation flow and image listing endpoints.

## Commit & Pull Request Guidelines
- Current history uses short, lowercase, imperative messages (for example `add .gitignore`); keep that style.
- Keep commits scoped (backend, frontend, or docs) and avoid mixing unrelated changes.
- PRs should include:
1. What changed and why.
2. Local verification steps you ran.
3. Screenshots or GIFs for UI changes.
4. Related issue/task reference when available.

## Security & Configuration Tips
- Never commit secrets; keep API keys in `backend/.env`.
- Keep `backend/.env.example` updated when adding new required environment variables.
