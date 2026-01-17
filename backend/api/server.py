"""
FastAPI server for Stellaris Companion Electron app.

Provides REST endpoints for the Electron renderer to communicate with
the Python backend. All endpoints require Bearer token authentication.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


# Auth configuration
ENV_API_TOKEN = "STELLARIS_API_TOKEN"
security = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
    """Request body for /api/chat endpoint."""

    message: str
    session_key: str = "default"


def get_auth_token() -> str | None:
    """Get the expected auth token from environment."""
    return os.environ.get(ENV_API_TOKEN)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Dependency that verifies the Bearer token on every request.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    expected_token = get_auth_token()

    if not expected_token:
        # No token configured - reject all requests
        raise HTTPException(
            status_code=401,
            detail={"error": "Server not configured with auth token"},
        )

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid or missing authorization token"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid or missing authorization token"},
        )

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid or missing authorization token"},
        )

    return credentials.credentials


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    The app uses dependency injection for auth and backend services.
    Companion and GameDatabase instances should be set on app.state after creation.

    Returns:
        Configured FastAPI application.

    Example:
        app = create_app()
        app.state.companion = Companion(save_path=...)
        app.state.db = GameDatabase()
    """
    app = FastAPI(
        title="Stellaris Companion API",
        description="Backend API for Stellaris Companion Electron app",
        version="1.0.0",
        docs_url=None,  # Disable Swagger UI in production
        redoc_url=None,  # Disable ReDoc in production
    )

    # Register routes with auth dependency
    @app.get("/api/health", dependencies=[Depends(verify_token)])
    async def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint.

        Returns server status and current game state info.
        """
        companion = getattr(request.app.state, "companion", None)

        if companion is None or not companion.is_loaded:
            return {
                "status": "ok",
                "save_loaded": False,
                "empire_name": None,
                "game_date": None,
                "precompute_ready": False,
            }

        precompute_status = companion.get_precompute_status()

        return {
            "status": "ok",
            "save_loaded": True,
            "empire_name": companion.metadata.get("name"),
            "game_date": companion.metadata.get("date"),
            "precompute_ready": precompute_status.get("ready", False),
        }

    @app.post("/api/chat", dependencies=[Depends(verify_token)])
    async def chat(request: Request, body: ChatRequest) -> dict[str, Any]:
        """Chat endpoint for asking questions about the game state.

        Uses the precomputed briefing for fast responses without tool calls.

        Returns 503 if the precompute is not ready yet.
        """
        companion = getattr(request.app.state, "companion", None)

        if companion is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Companion not initialized", "retry_after_ms": 2000},
            )

        if not companion.is_loaded:
            raise HTTPException(
                status_code=503,
                detail={"error": "No save file loaded", "retry_after_ms": 2000},
            )

        # Check if precompute is ready
        precompute_status = companion.get_precompute_status()
        if not precompute_status.get("ready", False):
            raise HTTPException(
                status_code=503,
                detail={"error": "Briefing not ready yet", "retry_after_ms": 2000},
            )

        # Call ask_precomputed to get the response
        start_time = time.time()
        response_text, elapsed = companion.ask_precomputed(
            question=body.message,
            session_key=body.session_key,
        )
        response_time_ms = int((time.time() - start_time) * 1000)

        # Get tools_used from the companion's last call stats
        call_stats = companion.get_call_stats()
        tools_used = call_stats.get("tools_used", [])

        return {
            "text": response_text,
            "game_date": precompute_status.get("game_date"),
            "tools_used": tools_used,
            "response_time_ms": response_time_ms,
        }

    return app
