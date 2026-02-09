"""FastAPI application entry point for knowItAll."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import pathlib

from knowitall.api.routes import router
from knowitall.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background scheduler on startup, stop on shutdown."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="knowItAll",
    description="Interactive daily intelligence assistant for founder-relevant signals.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)

# Mount static files
_STATIC_DIR = pathlib.Path(__file__).resolve().parent / "../../static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR.resolve())), name="static")
