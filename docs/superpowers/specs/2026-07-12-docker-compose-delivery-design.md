# Docker Compose Delivery Design

## Goal

Provide a reproducible local delivery package that starts the React web application, FastAPI service, and PostgreSQL with one `docker compose up -d --build` command.

## Scope

- Add a root Compose file with `frontend`, `backend`, and `postgres` services.
- Keep PostgreSQL data in a named Docker volume rather than an image layer or the repository.
- Add `.dockerignore` files so source control metadata, local dependencies, logs, and environment files are excluded from image build contexts.
- Serve the API through the frontend origin at `/api/`, including SSE, so the frontend does not bake a host-specific API URL into its build.
- Provide a production-oriented environment template and concise Chinese run, reset, backup, and shutdown instructions.

## Runtime Design

`frontend` is built from the existing Vite application and served by Nginx on host port `3000`. Nginx serves client-side routes and proxies `/api/` to `backend:8000`, including the event stream.

`backend` receives all runtime configuration through Compose environment variables. It waits for the PostgreSQL health check before starting. The application continues to create missing tables at startup through its existing `init_db()` behavior.

`postgres` uses the official PostgreSQL 16 image. Its data directory is attached to the named `postgres_data` volume. The database image contains no application data; a fresh deployment creates an empty database, while an existing local volume is retained across `up`, `down`, and image rebuilds.

## Configuration and Security

- Runtime secrets are read from an untracked `.env` file created from `.env.docker.example`.
- The Compose file has safe, non-secret defaults only for local service names and ports.
- The Docker frontend uses `/api/v1` as its build-time base URL; browser requests are same-origin and Nginx proxies them to the backend.
- The existing administrator hash is not changed by this packaging task. The delivery guide explicitly calls out that fixed demonstration credentials are unsuitable for public deployment.

## Acceptance Criteria

1. `docker compose config` validates with the environment template loaded.
2. `docker compose up -d --build` builds the frontend and backend images and starts all three services.
3. PostgreSQL reports healthy, the backend health endpoint returns HTTP 200, and the frontend returns HTTP 200.
4. The frontend API proxy returns the backend health payload through the browser-facing origin.
5. `docker compose down` retains the named database volume; the documentation describes the explicit destructive reset command.
