# Repository Guidelines

## Project Structure & Module Organization
This repository is a local securities market monitor. The backend is FastAPI and lives in `backend/app/`: API routes in `api/`, business logic in `services/`, SQLAlchemy models in `models/`, Pydantic schemas in `schemas/`, and technical indicators in `analysis/`. Backend tests are in `backend/tests/`.

The frontend is a React/Vite/TypeScript app in `frontend/src/`. Route pages are in `pages/`, reusable UI in `components/`, feature-specific tables, charts, and controls in `features/`, and HTTP access in `api/`. Database migrations live in `data/migrations/`; operational scripts live in `tools/`.

## Build, Test, and Development Commands
Run backend commands from the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .\backend
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
.\.venv\Scripts\python -m pytest .\backend\tests
```

Run frontend commands from `frontend/`:

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
npm run build
npm run preview
```

`npm run build` runs TypeScript project checks before producing the Vite build.

## Coding Style & Naming Conventions
Use Python 3.11+, 4-space indentation, `snake_case` modules/functions, and practical type hints. Keep route wiring thin; put orchestration and external data handling in services.

Use TypeScript with 2-space indentation. React components and pages use `PascalCase` filenames, hooks use `useX` naming, and table/chart helpers should stay inside their feature folder. Prefer existing Ant Design, ECharts, and API client patterns.

## Testing Guidelines
Backend tests use pytest and `test_*.py` naming under `backend/tests/`. Add focused tests for API response changes, strategy/indicator calculations, collectors, and persistence behavior. No frontend test runner is configured; validate frontend changes with `npm run build` and manual checks for affected screens.

## Commit & Pull Request Guidelines
Git history uses concise Conventional Commit-style subjects, such as `feat: add push message output workflow` and `fix: add market data source fallbacks`. Keep subjects imperative and scoped.

Pull requests should include a behavior summary, verification commands, migration or `.env` impacts, and screenshots for visible UI changes. Do not commit real API keys, local database files, generated runtime logs, or personal output paths.
