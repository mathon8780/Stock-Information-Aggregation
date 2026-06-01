# Repository Guidelines

## Project Structure & Module Organization
This repository is a local securities market monitor with a FastAPI backend and React/Vite frontend.

- `backend/app/` contains the Python application: `api/` routes, `services/` logic, `models/` SQLAlchemy entities, `schemas/` Pydantic types, and `analysis/` indicators.
- `backend/tests/` contains pytest coverage for APIs, indicators, collectors, and project alignment.
- `frontend/src/` contains the dashboard UI. Shared UI is in `components/`, route pages in `pages/`, feature code in `features/`, API calls in `api/`, and theme/types in `theme/` and `types/`.
- `data/` stores migrations, runtime files, local logs, and test database artifacts.
- `tools/` contains one-off operational scripts such as full-market history import.

## Build, Test, and Development Commands
From the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .\backend
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
.\.venv\Scripts\python -m pytest .\backend\tests
```

Frontend commands run in `frontend/`:

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
npm run build
npm run preview
```

`npm run build` type-checks the project before producing the Vite build.

## Coding Style & Naming Conventions
Use Python 3.11+ with 4-space indentation, practical type hints, and `snake_case` modules/functions. Keep route wiring in `api/router.py`, persistence models in `models/entities.py`, and orchestration in `services/`.

Use TypeScript/React with 2-space indentation. Components and pages use `PascalCase` filenames, hooks use `useX` naming, and table/chart helpers stay near their feature folders. Prefer existing Ant Design, ECharts, and API-client patterns.

## Testing Guidelines
Backend tests use pytest and live under `backend/tests/` with `test_*.py` names. Add focused tests when changing API responses, strategy calculations, or collectors. PostgreSQL is the local default; SQLite is reserved for tests. No frontend test runner is configured; validate UI changes with `npm run build`.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects, often Conventional Commit prefixes such as `feat:`. Follow that style: `feat: add settings sync status`, `fix: handle missing quote rows`, or another concise imperative subject.

Pull requests should describe the behavior change, list backend/frontend verification commands, call out `.env` or database migration impacts, and include screenshots for visible UI changes. Never commit real API keys or local runtime logs.
