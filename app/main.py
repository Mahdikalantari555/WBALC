"""RSAL FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import datasets, inference, labels, projects, query, scenes, som, training
from .config import Settings, settings as default_settings
from .db import Database
from .storage import ensure_dirs


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_dirs(settings)
        db = Database(settings)
        await db.init_db()
        app.state.settings = settings
        app.state.db = db
        yield
        await db.dispose()

    app = FastAPI(
        title="WBALC Backend",
        description=(
            "Water-body monitoring foundation with multi-temporal Sentinel-1/2 "
            "scene registration, native-grid metadata, and inherited RSAL "
            "single-scene research workflows. Scene registration does not align "
            "or resample source imagery."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(projects.router)
    app.include_router(scenes.router)
    app.include_router(datasets.router)
    app.include_router(labels.router)
    app.include_router(query.router)
    app.include_router(som.router)
    app.include_router(training.router)
    app.include_router(inference.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/", tags=["health"])
    async def root():
        return {
            "name": "WBALC Backend",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
