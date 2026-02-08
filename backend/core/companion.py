"""
Stellaris Companion Core
========================

Provides the Companion class — the Gemini-powered strategic advisor
used by the Electron app via the backend API.
"""

import json
import logging
import os
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("google-genai package not installed. Run: pip install google-genai")

from backend.core.conversation import ConversationManager
from backend.core.json_utils import json_dumps
from backend.core.utils import compute_save_hash_from_briefing
from stellaris_companion.personality import build_optimized_prompt
from stellaris_save_extractor import SaveExtractor

# Configure dedicated logger for companion performance metrics
logger = logging.getLogger("stellaris.companion")


# Fallback system prompt (used if personality generation fails)
FALLBACK_SYSTEM_PROMPT = """You are a Stellaris strategic advisor.

Your role:
- Answer questions about the game state using the data provided
- Provide strategic analysis and advice
- Be conversational and helpful, like a trusted advisor
- Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest solutions

FACTUAL ACCURACY CONTRACT:
- ALL numbers (military power, resources, populations, dates) MUST come from the provided game state
- If a specific value is not in the data, say "unknown" or "I don't have that information" - NEVER estimate or guess
- You may provide strategic advice and opinions, but clearly distinguish them from facts
- When quoting numbers, use the exact values from the data"""


class Companion:
    """Stellaris companion powered by Gemini with precomputed briefings.

    Used by the Electron app via the backend API (server.py).
    """

    def __init__(
        self,
        save_path: str | Path | None = None,
        api_key: str | None = None,
        *,
        auto_precompute: bool = True,
    ):
        """Initialize the companion.

        Args:
            save_path: Path to the Stellaris .sav file. If None, will try to find most recent.
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var.
        """
        # Get API key
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        self.client = genai.Client(api_key=self.api_key)
        self._thinking_level = "dynamic"
        self._auto_precompute = bool(auto_precompute)

        # Initialize save-related attributes
        self.save_path: Path | None = None
        self.last_modified: float | None = None
        self.extractor: SaveExtractor | None = None
        self.metadata: dict = {}
        self.identity: dict = {}
        self.situation: dict = {}
        self.system_prompt: str = FALLBACK_SYSTEM_PROMPT
        self.custom_instructions: str | None = None

        # Performance tracking for last request
        self._last_call_stats: dict[str, Any] = {
            "total_calls": 0,
            "tools_used": [],
            "wall_time_ms": 0.0,
            "response_length": 0,
            "payload_sizes": {},
        }

        # Save state tracking
        self._last_known_date: str | None = None  # For context update messages

        # Phase 4: full precompute cache (Option B /ask)
        self._briefing_lock = threading.RLock()
        self._briefing_ready = threading.Event()
        self._complete_briefing_json: str | None = None
        self._briefing_game_date: str | None = None
        self._briefing_updated_at: float | None = None
        self._briefing_last_error: str | None = None
        self._precompute_generation = 0

        # Phase 4: sliding-window conversation memory (per session key)
        self._conversations = ConversationManager(
            max_turns=6,
            timeout_minutes=24 * 60,
            max_game_months=12,
            max_answer_chars=500,
            max_question_chars=320,
            max_recent_conversation_chars=5000,
            max_summary_chars=1800,
            max_history_context_chars=3500,
        )
        self._max_prompt_question_chars = 4000
        self._max_save_memory_chars = 2200
        self._max_save_memory_entries = 8

        # Load save if provided
        if save_path:
            self.load_save(save_path)

    def _build_minimal_situation(self) -> dict:
        """Build a low-cost situation stub for initial personality.

        Full situation is computed during background precompute.
        """
        date_str = (self.metadata or {}).get("date") or "2200.01.01"
        try:
            year = int(str(date_str).split(".")[0])
        except Exception:
            year = 2200

        if year < 2230:
            phase = "early"
        elif year < 2300:
            phase = "mid_early"
        elif year < 2350:
            phase = "mid_late"
        elif year < 2400:
            phase = "late"
        else:
            phase = "endgame"

        return {
            "game_phase": phase,
            "year": year,
            "at_war": False,
            "war_count": 0,
            "contacts_made": False,
            "contact_count": 0,
            "rivals": [],
            "allies": [],
            "crisis_active": False,
            "economy": {"resources_in_deficit": 0},
            "_note": "Minimal stub; full situation computed asynchronously.",
        }

    def load_save(self, save_path: str | Path) -> None:
        """Load a save file and initialize the companion.

        Args:
            save_path: Path to the Stellaris .sav file
        """
        self.save_path = Path(save_path)
        if not self.save_path.exists():
            raise FileNotFoundError(f"Save file not found: {save_path}")

        self.last_modified = self.save_path.stat().st_mtime
        self.extractor = SaveExtractor(str(self.save_path))

        # Get basic metadata for context
        self.metadata = self.extractor.get_metadata()

        # Extract identity cheaply; full situation is computed during precompute.
        self.identity = self.extractor.get_empire_identity()
        self.situation = self._build_minimal_situation()

        # Reset per-playthrough custom instructions on new load (UI will refetch from DB).
        self.custom_instructions = None

        # Build dynamic personality prompt
        self._build_personality()

        self._last_known_date = self.metadata.get("date")

        # Kick off Phase 4 background precompute immediately (unless disabled for Electron ingestion manager).
        if self._auto_precompute:
            self.start_background_precompute(self.save_path)

    def _build_personality(self) -> None:
        """Build the dynamic personality prompt from empire data.

        Uses optimized prompt (625 chars) that trusts Gemini's Stellaris knowledge.
        Only hardcodes address style (model can't infer). Handles all empire types.
        Includes version/DLC awareness to avoid recommending unavailable content.
        """
        if not self.identity or not self.situation:
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            return

        try:
            # Build game context for version/DLC awareness
            game_context = self._build_game_context()

            self.system_prompt = build_optimized_prompt(
                self.identity,
                self.situation,
                game_context,
                custom_instructions=self.custom_instructions,
            )
        except Exception as e:
            logger.warning("Failed to build personality (%s), using fallback", e)
            self.system_prompt = FALLBACK_SYSTEM_PROMPT

    def set_custom_instructions(self, text: str | None) -> None:
        """Set per-playthrough advisor customization (memory only; persistence handled elsewhere)."""
        cleaned = (text or "").strip()
        self.custom_instructions = cleaned or None
        self._build_personality()

    def _build_game_context(self) -> dict | None:
        """Build game context dict for version/DLC awareness.

        Returns:
            Dict with version, required_dlcs, and missing_dlcs, or None if unavailable
        """
        if not self.metadata:
            return None

        version = self.metadata.get("version")
        required_dlcs = self.metadata.get("required_dlcs", [])

        # Compute missing DLCs if extractor is available
        missing_dlcs = []
        if self.extractor and hasattr(self.extractor, "get_missing_dlcs"):
            try:
                missing_dlcs = self.extractor.get_missing_dlcs()
            except Exception:
                pass  # Fall back to empty list

        return {
            "version": version,
            "required_dlcs": required_dlcs,
            "missing_dlcs": missing_dlcs,
        }

    @property
    def is_loaded(self) -> bool:
        """Check if a save file is loaded."""
        return self.extractor is not None

    def check_save_changed(self) -> bool:
        """Check if the save file has been modified.

        Returns:
            True if save file changed, False otherwise
        """
        if not self.save_path:
            return False
        current_mtime = self.save_path.stat().st_mtime
        return current_mtime != self.last_modified

    def reload_save(self, new_path: Path | None = None) -> bool:
        """Reload the save file and rebuild personality.

        Args:
            new_path: Optional new path to switch to. If None, reloads from current path.
                      Use this when the save watcher detects a new file (e.g., new autosave).

        Returns:
            True if identity changed, False otherwise
        """
        if new_path is not None:
            if not new_path.exists():
                logger.warning(f"New save path does not exist: {new_path}")
                return False
            self.save_path = new_path

        if not self.save_path:
            return False

        old_identity = self.identity.copy() if self.identity else {}
        old_date = self._last_known_date

        # Reload extractor
        self.extractor = SaveExtractor(str(self.save_path))
        self.last_modified = self.save_path.stat().st_mtime
        self.metadata = self.extractor.get_metadata()

        # Re-extract identity and situation
        self.identity = self.extractor.get_empire_identity()
        self.situation = self._build_minimal_situation()

        # Check if identity changed
        identity_changed = (
            old_identity.get("ethics") != self.identity.get("ethics")
            or old_identity.get("authority") != self.identity.get("authority")
            or old_identity.get("civics") != self.identity.get("civics")
        )

        # Rebuild personality
        self._build_personality()

        self._last_known_date = self.metadata.get("date")

        logger.info(
            "save_update_detected",
            extra={
                "old_date": old_date,
                "new_date": self._last_known_date,
                "identity_changed": identity_changed,
            },
        )

        # Kick off Phase 4 background precompute for the new save (unless disabled for Electron ingestion manager).
        if self._auto_precompute:
            self.start_background_precompute(self.save_path)

        return identity_changed

    def get_call_stats(self) -> dict[str, Any]:
        """Get performance statistics from the last request.

        Returns:
            Dictionary with:
                - total_calls: number of tool calls made
                - tools_used: list of tool names called
                - wall_time_ms: total time in milliseconds
                - response_length: length of final response text
                - payload_sizes: dict mapping tool names to response sizes in bytes
        """
        return self._last_call_stats.copy()

    def get_precompute_status(self) -> dict[str, Any]:
        """Get current Phase 4 precompute cache status (safe for UI display)."""
        with self._briefing_lock:
            return {
                "ready": bool(self._briefing_ready.is_set()),
                "game_date": self._briefing_game_date,
                "updated_at": self._briefing_updated_at,
                "has_cache": self._complete_briefing_json is not None,
                "last_error": self._briefing_last_error,
            }

    def mark_precompute_stale(self) -> None:
        """Mark precompute as stale (keeps cached JSON but clears ready flag)."""
        with self._briefing_lock:
            self._briefing_ready.clear()
            self._briefing_last_error = None

    def apply_precomputed_briefing(
        self,
        *,
        save_path: Path | None,
        briefing_json: str,
        game_date: str | None,
        identity: dict[str, Any] | None,
        situation: dict[str, Any] | None,
        save_hash: str | None = None,
    ) -> None:
        """Activate a precomputed briefing produced externally (e.g., worker process)."""
        with self._briefing_lock:
            if save_path is not None:
                self.save_path = Path(save_path)
            self._complete_briefing_json = briefing_json
            self._briefing_game_date = game_date
            self._briefing_updated_at = time.time()
            self._briefing_last_error = None
            self._briefing_ready.set()

        # Update identity/situation/personality out of lock (prompt building can do I/O/logging).
        if isinstance(identity, dict):
            self.identity = identity
        if isinstance(situation, dict):
            self.situation = situation
        self._last_known_date = game_date
        self._build_personality()

    def start_background_precompute(self, save_path: Path | None = None) -> None:
        """Start background extraction of the complete briefing for /ask."""
        if save_path is not None:
            self.save_path = Path(save_path)

        if not self.save_path:
            return

        with self._briefing_lock:
            self._precompute_generation += 1
            generation = self._precompute_generation
            self._briefing_last_error = None
            # Mark as "not ready" while extraction runs; /ask can still use last cache.
            self._briefing_ready.clear()

        thread = threading.Thread(
            target=self._precompute_worker,
            args=(Path(self.save_path), generation),
            daemon=True,
            name=f"precompute-{generation}",
        )
        thread.start()

    def _precompute_worker(self, save_path: Path, generation: int) -> None:
        started = time.time()
        extractor: SaveExtractor | None = None
        briefing: dict[str, Any] | None = None

        for attempt in range(1, 4):
            try:
                extractor = SaveExtractor(str(save_path))
                briefing = extractor.get_complete_briefing()
                break
            except (zipfile.BadZipFile, KeyError) as e:
                # Save may still be writing; retry a couple times.
                logger.warning(f"precompute_retry attempt={attempt} error={e}")
                time.sleep(0.75)
            except Exception:
                break

        if not isinstance(briefing, dict):
            err = "Failed to compute complete briefing"
            with self._briefing_lock:
                if generation == self._precompute_generation:
                    self._briefing_last_error = err
            logger.error("precompute_failed")
            return

        briefing_json = json_dumps(briefing, default=str)
        meta = briefing.get("meta", {}) if isinstance(briefing.get("meta", {}), dict) else {}
        game_date = meta.get("date")
        save_hash = compute_save_hash_from_briefing(briefing)

        # Persist snapshot to SQLite (Phase 4)
        try:
            from backend.core.database import get_default_db
            from backend.core.history import record_snapshot_from_companion

            db = get_default_db()
            record_snapshot_from_companion(
                db=db,
                save_path=save_path,
                save_hash=save_hash,
                gamestate=getattr(extractor, "gamestate", None) if extractor else None,
                player_id=extractor.get_player_empire_id() if extractor else None,
                briefing=briefing,
            )
        except Exception as e:
            logger.warning(f"precompute_snapshot_persist_failed error={e}")

        # Atomic swap into in-memory cache
        with self._briefing_lock:
            if generation != self._precompute_generation:
                return

            self._complete_briefing_json = briefing_json
            self._briefing_game_date = str(game_date) if game_date is not None else None
            self._briefing_updated_at = time.time()
            self._briefing_last_error = None

            identity = briefing.get("identity")
            situation = briefing.get("situation")
            if isinstance(identity, dict):
                self.identity = identity
            if isinstance(situation, dict):
                self.situation = situation
            self._last_known_date = self._briefing_game_date

            # Update personality from full situation/identity.
            self._build_personality()

            self._briefing_ready.set()

        elapsed_ms = (time.time() - started) * 1000
        logger.info(
            "precompute_complete",
            extra={
                "generation": generation,
                "wall_time_ms": elapsed_ms,
                "briefing_bytes": len(briefing_json),
                "game_date": self._briefing_game_date,
            },
        )

    def _load_latest_briefing_json_from_db(self) -> tuple[str | None, str | None]:
        """Attempt to load the latest full briefing JSON from SQLite."""
        try:
            from backend.core.database import get_default_db
            from backend.core.history import compute_save_id

            db = get_default_db()

            # Best-effort: target the current save/campaign if possible.
            if self.save_path:
                # Avoid loading the full gamestate just to compute campaign_id; use save_path lookup.
                session_id = db.get_active_or_latest_session_id_for_save_path(
                    save_path=str(self.save_path)
                )
                if not session_id and self.extractor:
                    # Fallback: derive save_id without campaign_id (empire+root), which is cheap and stable.
                    save_id = compute_save_id(
                        campaign_id=None,
                        player_id=self.extractor.get_player_empire_id(),
                        empire_name=(self.metadata or {}).get("name"),
                        save_path=self.save_path,
                    )
                    session_id = db.get_active_or_latest_session_id(save_id=save_id)

                if session_id:
                    json_text = db.get_latest_session_briefing_json(
                        session_id=session_id
                    ) or db.get_latest_snapshot_full_briefing_json(session_id=session_id)
                    if json_text:
                        try:
                            parsed = json.loads(json_text)
                            gd = None
                            if isinstance(parsed, dict):
                                meta = (
                                    parsed.get("meta", {})
                                    if isinstance(parsed.get("meta", {}), dict)
                                    else {}
                                )
                                gd = meta.get("date")
                            return json_text, (str(gd) if gd is not None else None)
                        except Exception:
                            return json_text, None

            json_text = db.get_latest_session_briefing_json_any()
            if not json_text:
                json_text = db.get_latest_snapshot_full_briefing_json_any()
            if not json_text:
                return None, None
            try:
                parsed = json.loads(json_text)
                gd = None
                if isinstance(parsed, dict):
                    meta = (
                        parsed.get("meta", {}) if isinstance(parsed.get("meta", {}), dict) else {}
                    )
                    gd = meta.get("date")
                return json_text, (str(gd) if gd is not None else None)
            except Exception:
                return json_text, None

        except Exception:
            return None, None

    def _get_best_briefing_json(self) -> tuple[str | None, str | None, str | None]:
        """Return (briefing_json, game_date, data_note)."""
        # Prefer in-memory cache.
        with self._briefing_lock:
            cached_json = self._complete_briefing_json
            cached_date = self._briefing_game_date
            ready = self._briefing_ready.is_set()

        if cached_json:
            if ready:
                return cached_json, cached_date, None
            if cached_date:
                return (
                    cached_json,
                    cached_date,
                    f"Using cached data from {cached_date}; new save processing…",
                )
            return cached_json, cached_date, "Using cached data; new save processing…"

        # If we have a precompute running, wait briefly for it to finish (cold start).
        if not ready:
            self._briefing_ready.wait(timeout=20)
            with self._briefing_lock:
                if self._complete_briefing_json:
                    return self._complete_briefing_json, self._briefing_game_date, None

        # Try SQLite fallback (persistence across restarts).
        db_json, db_date = self._load_latest_briefing_json_from_db()
        if db_json:
            return (
                db_json,
                db_date,
                "Loaded from history cache; live save processing may still be running…",
            )

        return None, None, None

    def _normalize_text_line(self, text: str | None, *, limit: int) -> str:
        """Normalize user/model text for compact save-memory entries."""
        cleaned = " ".join(str(text or "").split())
        if len(cleaned) > limit:
            cleaned = cleaned[:limit].rstrip() + "..."
        return cleaned

    def _load_save_memory_summary(self, *, save_id: str | None) -> str | None:
        """Load persisted save-scoped memory summary (best effort)."""
        if not save_id:
            return None
        try:
            from backend.core.database import get_default_db

            db = get_default_db()
            summary = db.get_advisor_memory_summary(save_id)
            if not summary:
                return None
            return summary[: self._max_save_memory_chars]
        except Exception:
            return None

    def _update_save_memory_summary(
        self,
        *,
        save_id: str | None,
        question: str,
        answer: str,
        game_date: str | None,
    ) -> None:
        """Append a compact memory entry and persist per-save summary."""
        if not save_id:
            return

        q = self._normalize_text_line(question, limit=180)
        a = self._normalize_text_line(answer, limit=280)
        stamp = str(game_date or "date-unknown")
        entry = f"- [{stamp}] User asked: {q} | Advisor suggested: {a}"

        try:
            from backend.core.database import get_default_db

            db = get_default_db()
            existing = db.get_advisor_memory_summary(save_id) or ""
            lines = [ln.strip() for ln in existing.splitlines() if ln.strip()]

            # Keep recent continuity, then append current turn.
            if len(lines) >= self._max_save_memory_entries:
                lines = lines[-(self._max_save_memory_entries - 1) :]
            lines.append(entry)

            # Enforce character budget by trimming oldest lines first.
            while len("\n".join(lines)) > self._max_save_memory_chars and len(lines) > 1:
                lines.pop(0)

            db.upsert_advisor_memory_summary(
                save_id=save_id,
                summary_text="\n".join(lines),
                last_game_date=game_date,
            )
        except Exception as e:
            logger.debug("advisor_memory_update_failed error=%s", e)

    def ask_precomputed(
        self,
        question: str,
        session_key: str,
        save_id: str | None = None,
        history_context: str | None = None,
    ) -> tuple[str, float]:
        """Ask a question using the fully precomputed briefing (no tools)."""
        start_time = time.time()

        cleaned_question = (question or "").strip()
        if len(cleaned_question) > self._max_prompt_question_chars:
            cleaned_question = cleaned_question[: self._max_prompt_question_chars].rstrip() + "..."

        briefing_json, game_date, data_note = self._get_best_briefing_json()
        if not briefing_json:
            return (
                "No precomputed game state is available yet. Please wait for a save to be processed.",
                0.0,
            )

        save_memory_summary = self._load_save_memory_summary(save_id=save_id)

        # Build prompt with sliding-window history (Phase 4)
        user_prompt = self._conversations.build_prompt(
            session_key=session_key,
            briefing_json=briefing_json,
            game_date=game_date,
            question=cleaned_question,
            data_note=data_note,
            history_context=history_context,
            long_term_summary=save_memory_summary,
        )

        ask_system_prompt = (
            f"{self.system_prompt}\n\n"
            "ASK MODE (NO TOOLS):\n"
            "- You are given the complete current game state as JSON in the user message.\n"
            "- Do NOT call tools or ask to call tools.\n"
            "- ALL numbers and factual claims must come from the JSON.\n"
            "- If a value is missing, say 'unknown' and suggest what to check in-game.\n"
            "- Be a strategic ADVISOR: interpret, prioritize, and recommend next actions.\n"
        )

        try:
            cfg = types.GenerateContentConfig(
                system_instruction=ask_system_prompt,
                temperature=1.0,
                max_output_tokens=4096,
            )
            if self._thinking_level != "dynamic":
                cfg.thinking_config = types.ThinkingConfig(thinking_level=self._thinking_level)

            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=user_prompt,
                config=cfg,
            )
            response_text_raw = response.text or "Could not generate a response."
            response_text = response_text_raw

            # Deterministic disclaimer on stale/cache fallback.
            if data_note:
                response_text = f"*{data_note}*\n\n{response_text}"

            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            self._last_call_stats = {
                "total_calls": 1,
                "tools_used": ["ask_precomputed_no_tools"],
                "wall_time_ms": wall_time_ms,
                "response_length": len(response_text),
                "payload_sizes": {
                    "briefing_json": len(briefing_json),
                    "prompt_total": len(user_prompt),
                    "save_memory_summary": len(save_memory_summary or ""),
                },
            }

            self._conversations.record_turn(
                session_key=session_key,
                question=cleaned_question,
                answer=response_text,
                game_date=game_date,
            )
            self._update_save_memory_summary(
                save_id=save_id,
                question=cleaned_question,
                answer=response_text_raw,
                game_date=game_date,
            )

            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000
            self._last_call_stats = {
                "total_calls": 0,
                "tools_used": [],
                "wall_time_ms": wall_time_ms,
                "response_length": 0,
                "payload_sizes": {"briefing_json": len(briefing_json)},
                "error": str(e),
            }
            return f"Error: {str(e)}", elapsed

    def get_status_data(self) -> dict:
        """Get raw status data for embedding without LLM processing.

        Returns:
            Dictionary with all status data for the /status command
        """
        if not self.is_loaded:
            return {"error": "No save file loaded"}

        player = self.extractor.get_player_status()
        resources = self.extractor.get_resources()
        diplomacy = self.extractor.get_diplomacy()

        return {
            "empire_name": self.metadata.get("name", "Unknown"),
            "date": self.metadata.get("date", "Unknown"),
            "military_power": player.get("military_power", 0),
            "fleet_count": player.get("fleet_count", 0),
            "fleet_size": player.get("fleet_size", 0),
            "tech_power": player.get("tech_power", 0),
            "economy_power": player.get("economy_power", 0),
            "colonies": player.get("colonies", {}),
            "net_resources": resources.get("net_monthly", {}),
            "research_summary": resources.get("summary", {}).get("research_total", 0),
            "diplomacy_summary": diplomacy.get("summary", {}),
            "allies": diplomacy.get("allies", []),
            "federation": diplomacy.get("federation"),
        }
