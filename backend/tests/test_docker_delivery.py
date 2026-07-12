from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_delivery_declares_persistent_database_and_relative_web_api() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.docker.example").read_text(encoding="utf-8")

    assert "postgres:" in compose
    assert "backend:" in compose
    assert "frontend:" in compose
    assert "postgres_data:" in compose
    assert "VITE_API_BASE_URL: /api/v1" in compose
    assert "DATABASE_URL=postgresql+psycopg://" in env_example


def test_nginx_proxies_api_and_disables_sse_buffering() -> None:
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000/api/;" in nginx
    assert "proxy_buffering off;" in nginx


def test_readme_documents_compose_start_and_data_retention() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docker compose up -d --build" in readme
    assert ".env.docker.example" in readme
    assert "docker compose down -v" in readme
