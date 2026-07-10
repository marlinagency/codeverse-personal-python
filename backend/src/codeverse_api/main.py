from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codeverse_api.config import get_settings
from codeverse_api.routers import auth as auth_router
from codeverse_api.routers import compile as compile_router
from codeverse_api.routers import execute as execute_router
from codeverse_api.routers import learning as learning_router
from codeverse_api.routers import projects as projects_router
from codeverse_api.routers import themes as themes_router
from codeverse_api.routers import ws as ws_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeVerse API",
        description=(
            "AI-personalized Python learning layer compiled to real, runnable code. "
            "Includes Personal Python mapping, lessons, practice, and execution proof."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in get_settings().cors_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router)
    app.include_router(themes_router.router)
    app.include_router(learning_router.router)
    app.include_router(projects_router.router)
    app.include_router(compile_router.router)
    app.include_router(execute_router.router)
    app.include_router(ws_router.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
