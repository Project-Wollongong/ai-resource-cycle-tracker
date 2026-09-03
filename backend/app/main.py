from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import (
    admin,
    announcements,
    backtest,
    config as config_routes,
    health,
    historical_analysis,
    reports,
    signals,
    stocks,
)
from .config import settings
from .database import SessionLocal, init_db
from .services.config_service import ensure_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as session:
        ensure_defaults(session)
    scheduler = None
    if settings.enable_scheduler:
        from .scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AI Resource Cycle Tracker", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    health,
    stocks,
    signals,
    announcements,
    backtest,
    reports,
    historical_analysis,
    config_routes,
    admin,
):
    app.include_router(module.router, prefix="/api")
