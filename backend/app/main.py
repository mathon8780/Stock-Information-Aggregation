from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.config import settings
from app.database import init_db
from app.services.news_auto_sync_service import start_news_auto_sync, stop_news_auto_sync
from app.services.startup_sync_service import start_startup_sync, stop_startup_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    startup_sync_started = start_startup_sync()
    start_news_auto_sync(run_immediately=not (startup_sync_started and settings.startup_sync_news_enabled))
    try:
        yield
    finally:
        await stop_startup_sync()
        await stop_news_auto_sync()


app = FastAPI(title="Market Agent API", description="Local A-share market monitor, alert and rule-based strategy API.", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Market Agent API", "docs": "/docs", "health": "/api/v1/health"}
