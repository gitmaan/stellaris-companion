"""
FastAPI server for Stellaris Companion Electron app.

Provides REST endpoints for the Electron renderer to communicate with
the Python backend. All endpoints require Bearer token authentication.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

_chronicle_in_flight: set[str] = set()
_chronicle_in_flight_lock = threading.Lock()


# Auth configuration
ENV_API_TOKEN = "STELLARIS_API_TOKEN"
security = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
    """Request body for /api/chat endpoint."""

    message: str
    session_key: str = "default"


class RecapRequest(BaseModel):
    """Request body for /api/recap endpoint."""

    session_id: str
    style: str = "summary"  # "summary" (deterministic) or "dramatic" (LLM-powered)


class ChronicleRequest(BaseModel):
    """Request body for /api/chronicle endpoint."""

    session_id: str
    force_refresh: bool = False
    chapter_only: bool = False


class RegenerateChapterRequest(BaseModel):
    """Request body for /api/chronicle/regenerate-chapter endpoint."""

    session_id: str
    chapter_number: int
    confirm: bool = False
    regeneration_instructions: str | None = None


class AdvisorCustomRequest(BaseModel):
    """Request body for /api/session-advisor-custom endpoint."""

    custom_instructions: str | None = None


class ChronicleCustomRequest(BaseModel):
    """Request body for /api/chronicle-custom-instructions endpoint."""

    custom_instructions: str | None = None


def _parse_game_date(value: Any) -> tuple[int, int, int] | None:
    """Parse a Stellaris game date string (YYYY.MM.DD with optional zero padding)."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return None
    if year < 0 or month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return (year, month, day)


def _pick_latest_game_date(*values: Any) -> str | None:
    """Pick the latest valid game date from candidate values.

    Falls back to the first non-empty string when no values parse cleanly.
    """
    latest_parsed: tuple[int, int, int] | None = None
    latest_raw: str | None = None
    fallback_raw: str | None = None

    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and fallback_raw is None:
                fallback_raw = stripped
            parsed = _parse_game_date(stripped)
            if parsed is not None and (latest_parsed is None or parsed > latest_parsed):
                latest_parsed = parsed
                latest_raw = stripped

    return latest_raw if latest_raw is not None else fallback_raw


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
        ingestion = getattr(request.app.state, "ingestion", None)
        if ingestion is not None:
            payload = ingestion.get_health_payload()
            return {"status": "ok", **payload}

        companion = getattr(request.app.state, "companion", None)
        if companion is None or not getattr(companion, "is_loaded", False):
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

    @app.get("/api/ingestion-status", dependencies=[Depends(verify_token)])
    async def ingestion_status(request: Request) -> dict[str, Any]:
        """Detailed ingestion status (staged progress, cancellation, timestamps)."""
        ingestion = getattr(request.app.state, "ingestion", None)
        if ingestion is None:
            return {"enabled": False}
        return {"enabled": True, "status": ingestion.get_status()}

    @app.get("/api/diagnostics", dependencies=[Depends(verify_token)])
    async def get_diagnostics(request: Request) -> dict[str, Any]:
        """Get comprehensive diagnostic info for bug reports.

        Returns DLCs, Stellaris version, empire type, save file size, etc.
        Used by the Report Issue modal to capture context.
        """
        diagnostics: dict[str, Any] = {
            "stellarisVersion": None,
            "dlcs": [],
            "empireType": None,
            "empireName": None,
            "empireEthics": [],
            "empireCivics": [],
            "empireOrigin": None,
            "gameYear": None,
            "saveFileSizeMb": None,
            "galaxySize": None,
            "ingestionStage": None,
            "ingestionStageDetail": None,
            "ingestionLastError": None,
            "precomputeReady": None,
            "t2Ready": None,
        }

        ingestion = getattr(request.app.state, "ingestion", None)
        companion = getattr(request.app.state, "companion", None)

        # Try to get metadata from ingestion manager first
        if ingestion is not None:
            status = ingestion.get_status()
            t2_meta = status.get("t2_meta") if isinstance(status.get("t2_meta"), dict) else {}
            t0_meta = status.get("t0_meta") if isinstance(status.get("t0_meta"), dict) else {}

            # Prefer t2 (full) metadata, fall back to t0 (basic)
            meta = t2_meta if t2_meta else t0_meta

            diagnostics["stellarisVersion"] = meta.get("version")
            diagnostics["dlcs"] = meta.get("required_dlcs", [])
            diagnostics["empireName"] = meta.get("empire_name") or meta.get("name")
            diagnostics["gameYear"] = meta.get("date") or status.get("t2_game_date")
            diagnostics["saveFileSizeMb"] = meta.get("file_size_mb")

            # Empire identity from t2 metadata
            diagnostics["empireEthics"] = meta.get("ethics", [])
            diagnostics["empireCivics"] = meta.get("civics", [])
            diagnostics["empireOrigin"] = meta.get("origin")
            diagnostics["empireType"] = meta.get("empire_type")
            diagnostics["galaxySize"] = meta.get("galaxy_size")
            diagnostics["ingestionStage"] = status.get("stage")
            diagnostics["ingestionStageDetail"] = status.get("stage_detail")
            diagnostics["ingestionLastError"] = status.get("last_error")
            diagnostics["t2Ready"] = bool(status.get("t2_ready"))
            diagnostics["precomputeReady"] = bool(
                status.get("precompute_ready", status.get("t2_ready", False))
            )

        # Fall back to companion if ingestion not available
        elif companion is not None and getattr(companion, "is_loaded", False):
            meta = getattr(companion, "metadata", {}) or {}
            precompute_status = companion.get_precompute_status()
            diagnostics["stellarisVersion"] = meta.get("version")
            diagnostics["dlcs"] = meta.get("required_dlcs", [])
            diagnostics["empireName"] = meta.get("name")
            diagnostics["gameYear"] = meta.get("date")
            diagnostics["saveFileSizeMb"] = meta.get("file_size_mb")
            diagnostics["precomputeReady"] = bool(precompute_status.get("ready", False))

            # Try to get empire identity from extractor
            extractor = getattr(companion, "extractor", None)
            if extractor is not None:
                with contextlib.suppress(Exception):
                    identity = extractor.get_empire_identity()
                    diagnostics["empireEthics"] = identity.get("ethics", [])
                    diagnostics["empireCivics"] = identity.get("civics", [])
                    diagnostics["empireOrigin"] = identity.get("origin")
                    diagnostics["empireType"] = identity.get("authority")

        return diagnostics

    def _resolve_current_save_id(request: Request) -> tuple[str | None, str | None]:
        """Return (save_id, error) for the currently loaded playthrough."""
        from backend.core.history import compute_save_id

        companion = getattr(request.app.state, "companion", None)
        ingestion = getattr(request.app.state, "ingestion", None)

        save_path: Path | None = None
        campaign_id: str | None = None
        player_id: int | None = None
        empire_name: str | None = None

        if ingestion is not None:
            status = ingestion.get_status()
            if not status.get("save_loaded", False):
                return None, "No save file loaded"

            t2_meta = status.get("t2_meta") if isinstance(status.get("t2_meta"), dict) else {}
            t0_meta = status.get("t0_meta") if isinstance(status.get("t0_meta"), dict) else {}
            meta = t2_meta if t2_meta else t0_meta

            campaign_id = meta.get("campaign_id")
            player_id = meta.get("player_id")
            empire_name = meta.get("empire_name") or meta.get("name")
            sp = status.get("current_save_path")
            if isinstance(sp, str) and sp:
                save_path = Path(sp)

        elif companion is not None and getattr(companion, "is_loaded", False):
            extractor = getattr(companion, "extractor", None)
            player_id = extractor.get_player_empire_id() if extractor else None
            empire_name = (companion.metadata or {}).get("name")
            save_path = getattr(companion, "save_path", None)

        if not save_path:
            return None, "No save file loaded"

        save_id = compute_save_id(
            campaign_id=campaign_id,
            player_id=player_id,
            empire_name=empire_name,
            save_path=save_path,
        )
        return save_id, None

    def _scope_chat_session_key(*, save_id: str | None, client_key: str | None) -> str:
        """Build a hidden backend thread key scoped to the active save."""
        raw = str(client_key or "default").strip()
        if not raw:
            raw = "default"
        raw = raw.replace("\n", " ").replace("\r", " ")
        if len(raw) > 200:
            raw = raw[:200]
        if save_id:
            return f"save:{save_id}|thread:{raw}"
        return f"thread:{raw}"

    @app.get("/api/session-advisor-custom", dependencies=[Depends(verify_token)])
    async def get_session_advisor_custom(request: Request) -> dict[str, Any]:
        """Get advisor custom instructions for the current playthrough (active session)."""
        db = getattr(request.app.state, "db", None)
        if db is None:
            raise HTTPException(status_code=503, detail={"error": "Database not initialized"})

        save_id, err = _resolve_current_save_id(request)
        if err or not save_id:
            return {"custom_instructions": None, "persisted": False, "error": err}

        session_id = db.get_active_session_id(save_id)
        if session_id:
            return {
                "custom_instructions": db.get_session_advisor_custom(session_id=session_id),
                "persisted": True,
            }

        # If a session row doesn't exist yet (e.g., Tier 2 not persisted),
        # return the in-memory value so the UI can show what the user typed.
        companion = getattr(request.app.state, "companion", None)
        pending = getattr(companion, "custom_instructions", None) if companion is not None else None
        return {
            "custom_instructions": pending
            if isinstance(pending, str) and pending.strip()
            else None,
            "persisted": False,
        }

    @app.post("/api/session-advisor-custom", dependencies=[Depends(verify_token)])
    async def set_session_advisor_custom(
        request: Request,
        body: AdvisorCustomRequest,
    ) -> dict[str, Any]:
        """Set advisor custom instructions for the current playthrough (active session)."""
        db = getattr(request.app.state, "db", None)
        if db is None:
            raise HTTPException(status_code=503, detail={"error": "Database not initialized"})

        companion = getattr(request.app.state, "companion", None)
        if companion is None:
            raise HTTPException(status_code=503, detail={"error": "Companion not initialized"})

        custom = (body.custom_instructions or "").strip()
        custom = custom[:300]

        # Apply immediately in-memory so the very next chat uses the new personality,
        # even if the session row hasn't been persisted yet.
        with contextlib.suppress(Exception):
            companion.set_custom_instructions(custom or None)

        save_id, err = _resolve_current_save_id(request)
        if err or not save_id:
            return {"custom_instructions": custom or None, "persisted": False, "error": err}

        session_id = db.get_active_session_id(save_id)
        if not session_id:
            # Persist later when the ingestion pipeline creates the session row.
            return {"custom_instructions": custom or None, "persisted": False}

        db.update_session_advisor_custom(session_id=session_id, text=custom or None)
        return {"custom_instructions": custom or None, "persisted": True}

    @app.get("/api/chronicle-custom-instructions", dependencies=[Depends(verify_token)])
    async def get_chronicle_custom_instructions(request: Request) -> dict[str, Any]:
        """Get chronicle custom instructions for the current playthrough."""
        db = getattr(request.app.state, "db", None)
        if db is None:
            raise HTTPException(status_code=503, detail={"error": "Database not initialized"})

        save_id, err = _resolve_current_save_id(request)
        if err or not save_id:
            return {"custom_instructions": None, "persisted": False, "error": err}

        return {
            "custom_instructions": db.get_chronicle_custom_instructions(save_id),
            "persisted": True,
        }

    @app.post("/api/chronicle-custom-instructions", dependencies=[Depends(verify_token)])
    async def set_chronicle_custom_instructions(
        request: Request,
        body: ChronicleCustomRequest,
    ) -> dict[str, Any]:
        """Set chronicle custom instructions for the current playthrough."""
        db = getattr(request.app.state, "db", None)
        if db is None:
            raise HTTPException(status_code=503, detail={"error": "Database not initialized"})

        save_id, err = _resolve_current_save_id(request)
        if err or not save_id:
            return {"custom_instructions": None, "persisted": False, "error": err}

        custom = (body.custom_instructions or "").strip()
        custom = custom[:500]

        db.update_chronicle_custom_instructions(save_id, custom or None)
        return {"custom_instructions": custom or None, "persisted": True}

    @app.post("/api/chat", dependencies=[Depends(verify_token)])
    def chat(request: Request, body: ChatRequest) -> dict[str, Any]:
        """Chat endpoint for asking questions about the game state.

        Uses the precomputed briefing for fast responses without tool calls.

        Returns 503 if the precompute is not ready yet.
        """
        companion = getattr(request.app.state, "companion", None)
        ingestion = getattr(request.app.state, "ingestion", None)

        if companion is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Companion not initialized",
                    "code": "COMPANION_NOT_INITIALIZED",
                    "retry_after_ms": 2000,
                },
            )

        if ingestion is not None:
            health = ingestion.get_health_payload()
            if not health.get("save_loaded", False):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "No save file loaded",
                        "code": "NO_SAVE_LOADED",
                        "retry_after_ms": 2000,
                    },
                )
            if not health.get("precompute_ready", False):
                with contextlib.suppress(Exception):
                    ingestion.request_t2_on_demand()
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Briefing not ready yet",
                        "code": "BRIEFING_NOT_READY",
                        "retry_after_ms": 2000,
                    },
                )
        else:
            if not companion.is_loaded:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "No save file loaded",
                        "code": "NO_SAVE_LOADED",
                        "retry_after_ms": 2000,
                    },
                )

            precompute_status = companion.get_precompute_status()
            if not precompute_status.get("ready", False):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Briefing not ready yet",
                        "code": "BRIEFING_NOT_READY",
                        "retry_after_ms": 2000,
                    },
                )

        precompute_status = companion.get_precompute_status()

        if not precompute_status.get("ready", False):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Briefing not ready yet",
                    "code": "BRIEFING_NOT_READY",
                    "retry_after_ms": 2000,
                },
            )

        # Call ask_precomputed to get the response
        start_time = time.time()
        save_id, _ = _resolve_current_save_id(request)
        scoped_session_key = _scope_chat_session_key(save_id=save_id, client_key=body.session_key)
        response_text, elapsed = companion.ask_precomputed(
            question=body.message,
            session_key=scoped_session_key,
            save_id=save_id,
        )
        response_time_ms = int((time.time() - start_time) * 1000)

        return {
            "text": response_text,
            "game_date": precompute_status.get("game_date"),
            "response_time_ms": response_time_ms,
        }

    @app.get("/api/status", dependencies=[Depends(verify_token)])
    async def get_status(request: Request) -> dict[str, Any]:
        """Get empire status summary.

        Returns key metrics: military power, economy, colonies, population, active wars.
        This is a fast endpoint that doesn't require LLM processing.
        """
        companion = getattr(request.app.state, "companion", None)

        if companion is None or not companion.is_loaded:
            raise HTTPException(
                status_code=503,
                detail={"error": "No save file loaded"},
            )

        # Get status data from companion (uses get_status_data internally)
        status_data = companion.get_status_data()

        if "error" in status_data:
            raise HTTPException(
                status_code=503,
                detail={"error": status_data["error"]},
            )

        # Get active wars from the extractor
        wars_data = companion.extractor.get_wars()
        active_wars = wars_data.get("wars", [])

        # Extract key metrics per API-004 criteria
        colonies_data = status_data.get("colonies", {})
        net_resources = status_data.get("net_resources", {})

        return {
            "empire_name": status_data.get("empire_name"),
            "game_date": status_data.get("date"),
            "military_power": status_data.get("military_power", 0),
            "economy": {
                "energy": net_resources.get("energy", 0),
                "minerals": net_resources.get("minerals", 0),
                "alloys": net_resources.get("alloys", 0),
                "food": net_resources.get("food", 0),
                "consumer_goods": net_resources.get("consumer_goods", 0),
                "tech_power": status_data.get("tech_power", 0),
                "economy_power": status_data.get("economy_power", 0),
            },
            "colonies": (
                colonies_data.get("total_count", 0) if isinstance(colonies_data, dict) else 0
            ),
            "pops": (
                colonies_data.get("total_population", 0) if isinstance(colonies_data, dict) else 0
            ),
            "active_wars": [
                {
                    "name": war.get("name"),
                    "attackers": war.get("attackers", []),
                    "defenders": war.get("defenders", []),
                }
                for war in active_wars
            ],
        }

    @app.get("/api/sessions", dependencies=[Depends(verify_token)])
    async def get_sessions(request: Request) -> dict[str, Any]:
        """Get list of all sessions with snapshot stats.

        Returns sessions ordered by started_at DESC with empire name, dates, and snapshot counts.
        """
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        sessions_data = db.get_sessions(limit=50)

        # Format response according to API spec
        sessions = []
        for session in sessions_data:
            latest_game_date = _pick_latest_game_date(
                session.get("last_game_date_computed"),
                session.get("last_game_date"),
            )
            sessions.append(
                {
                    "id": session["id"],
                    "save_id": session["save_id"],
                    "empire_name": session["empire_name"],
                    "started_at": session["started_at"],
                    "ended_at": session["ended_at"],
                    "first_game_date": session["first_game_date"],
                    "last_game_date": latest_game_date,
                    "snapshot_count": session["snapshot_count"],
                    "is_active": session["ended_at"] is None,
                }
            )

        return {"sessions": sessions}

    @app.get("/api/sessions/{session_id}/events", dependencies=[Depends(verify_token)])
    async def get_session_events(
        request: Request,
        session_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get events for a specific session.

        Returns events ordered by captured_at DESC with game_date, event_type, summary, and data.
        """
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        # Check if session exists
        session = db.get_session_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "Session not found"},
            )

        # Get events for the session
        import json as json_module

        events_data = db.get_recent_events(session_id=session_id, limit=limit)

        # Format response according to API spec
        events = []
        for event in events_data:
            data_json = event.get("data_json")
            data = {}
            if data_json:
                with contextlib.suppress(Exception):
                    data = json_module.loads(data_json)

            events.append(
                {
                    "id": event["id"],
                    "game_date": event["game_date"],
                    "event_type": event["event_type"],
                    "summary": event["summary"],
                    "data": data,
                }
            )

        return {"events": events}

    @app.post("/api/end-session", dependencies=[Depends(verify_token)])
    async def end_session(request: Request) -> dict[str, Any]:
        """End the current active session.

        Returns the session ID, ended_at timestamp, and snapshot count.
        Returns 400 if no active session exists.
        """
        import time as time_module

        from backend.core.history import compute_save_id

        companion = getattr(request.app.state, "companion", None)
        ingestion = getattr(request.app.state, "ingestion", None)
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        save_path: Path | None = None
        campaign_id: str | None = None
        player_id: int | None = None
        empire_name: str | None = None

        if ingestion is not None:
            status = ingestion.get_status()
            if not status.get("t2_ready"):
                raise HTTPException(
                    status_code=400,
                    detail={"error": "No active session - briefing not ready yet"},
                )
            t2_meta = status.get("t2_meta") if isinstance(status.get("t2_meta"), dict) else {}
            campaign_id = t2_meta.get("campaign_id")
            player_id = t2_meta.get("player_id")
            empire_name = t2_meta.get("empire_name")
            sp = status.get("current_save_path")
            if isinstance(sp, str) and sp:
                save_path = Path(sp)
        elif companion is not None and companion.is_loaded:
            extractor = getattr(companion, "extractor", None)
            player_id = extractor.get_player_empire_id() if extractor else None
            empire_name = (companion.metadata or {}).get("name")
            save_path = getattr(companion, "save_path", None)

        save_id = compute_save_id(
            campaign_id=campaign_id,
            player_id=player_id,
            empire_name=empire_name,
            save_path=save_path,
        )

        # Check for active session
        active_session_id = db.get_active_session_id(save_id)
        if not active_session_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "No active session found for current save"},
            )

        # End the session
        db.end_active_sessions_for_save(save_id=save_id)

        # Get stats for the ended session
        stats = db.get_session_snapshot_stats(active_session_id)

        # Get ended_at timestamp (current time since we just ended it)
        ended_at = int(time_module.time())

        return {
            "session_id": active_session_id,
            "ended_at": ended_at,
            "snapshot_count": stats.get("snapshot_count", 0),
        }

    @app.post("/api/recap", dependencies=[Depends(verify_token)])
    def generate_recap(request: Request, body: RecapRequest) -> dict[str, Any]:
        """Generate a recap summary for a session.

        Returns a narrative recap of events and key changes during the session.
        Supports two styles:
        - "summary": Fast deterministic recap (default)
        - "dramatic": LLM-powered dramatic narrative

        Note: This is a sync endpoint because the LLM client is synchronous.
        FastAPI runs sync endpoints in a threadpool.
        """
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        # Check if session exists
        session = db.get_session_by_id(body.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "Session not found"},
            )

        # Get session stats for date range
        stats = db.get_session_snapshot_stats(body.session_id)
        first_date = stats.get("first_game_date")
        last_date = stats.get("last_game_date")

        # Build date range string
        if first_date and last_date:
            date_range = f"{first_date} - {last_date}"
        elif first_date:
            date_range = f"{first_date} - ongoing"
        elif last_date:
            date_range = f"unknown - {last_date}"
        else:
            date_range = "No snapshots"

        # Use ChronicleGenerator for both styles
        from backend.core.chronicle import ChronicleGenerator

        generator = ChronicleGenerator(db=db)

        try:
            result = generator.generate_recap(
                session_id=body.session_id,
                style=body.style,
            )
            result["date_range"] = date_range
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"error": f"Recap generation failed: {str(e)}"},
            )

    @app.post("/api/chronicle", dependencies=[Depends(verify_token)])
    def generate_chronicle(request: Request, body: ChronicleRequest) -> dict[str, Any]:
        """Generate a full LLM-powered chronicle for a session.

        Returns a dramatic, multi-chapter narrative of the empire's history.
        Chronicles are cached and regenerated when significant new events occur.

        Note: This is a sync endpoint (def, not async def) because the
        Gemini client is synchronous. FastAPI runs sync endpoints in a
        threadpool, avoiding event loop blocking.
        """
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        # Check if session exists
        session = db.get_session_by_id(body.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "Session not found"},
            )

        # Prevent request storms from spawning concurrent LLM calls.
        # Chronicle generation can be network-intensive; serialize per-save.
        save_id = (
            db.get_save_id_for_session(body.session_id) or session.get("save_id") or body.session_id
        )
        with _chronicle_in_flight_lock:
            if save_id in _chronicle_in_flight:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "Chronicle generation already in progress",
                        "code": "CHRONICLE_IN_PROGRESS",
                        "retry_after_ms": 2000,
                    },
                )
            _chronicle_in_flight.add(save_id)

        from backend.core.chronicle import ChronicleGenerator

        generator = ChronicleGenerator(db=db)

        try:
            result = generator.generate_chronicle(
                session_id=body.session_id,
                force_refresh=body.force_refresh,
                chapter_only=body.chapter_only,
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"error": f"Chronicle generation failed: {str(e)}"},
            )
        finally:
            with _chronicle_in_flight_lock:
                _chronicle_in_flight.discard(save_id)

    @app.post("/api/chronicle/regenerate-chapter", dependencies=[Depends(verify_token)])
    def regenerate_chapter(
        request: Request,
        body: RegenerateChapterRequest,
    ) -> dict[str, Any]:
        """Regenerate a specific finalized chapter.

        Requires confirm=true to proceed. Marks downstream chapters as context_stale.

        Returns:
            The regenerated chapter and list of stale chapter numbers.
        """
        db = getattr(request.app.state, "db", None)

        if db is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "Database not initialized"},
            )

        # Check if session exists
        session = db.get_session_by_id(body.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "Session not found"},
            )

        from backend.core.chronicle import ChronicleGenerator

        generator = ChronicleGenerator(db=db)

        try:
            result = generator.regenerate_chapter(
                session_id=body.session_id,
                chapter_number=body.chapter_number,
                confirm=body.confirm,
                regeneration_instructions=body.regeneration_instructions,
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"error": f"Chapter regeneration failed: {str(e)}"},
            )

    return app
