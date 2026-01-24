"""
Stellaris Companion Core
========================

Refactored companion class from v2_native_tools.py.
Provides a reusable interface for the Gemini-powered strategic advisor.
"""

import hashlib
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

from save_extractor import SaveExtractor
from personality import build_optimized_prompt, get_personality_summary
from backend.core.conversation import ConversationManager


# Configure dedicated logger for companion performance metrics
logger = logging.getLogger("stellaris.companion")


# Fallback system prompt (used if personality generation fails)
FALLBACK_SYSTEM_PROMPT = """You are a Stellaris strategic advisor. You have access to tools that can query the player's save file.

Your role:
- Answer questions about the game state using the tools provided
- Provide strategic analysis and advice
- Be conversational and helpful, like a trusted advisor
- Call tools to get the data you need before answering

IMPORTANT - Tool Selection Strategy (you have 4 tools):

1. get_snapshot() - ALWAYS call this FIRST
   Returns comprehensive empire data covering ~80% of questions in ONE call.
   Includes: military power, economy, resources, colonies, diplomacy, starbases, leaders.

2. get_details(categories, limit) - Call AFTER get_snapshot() if you need MORE detail
   Categories: "leaders", "planets", "starbases", "technology", "wars", "fleets", "resources", "diplomacy"
   Only use if get_snapshot() doesn't have enough information.

3. search_save_file(query) - Escape hatch for edge cases
   Search raw save data when other tools don't have what you need.

4. get_empire_details(empire_name) - Look up other empires by name
   Use when asked about a specific AI empire.

WORKFLOW:
1. Call get_snapshot() first
2. Answer from that data if possible
3. Only call get_details() or other tools if you need more specific information

FACTUAL ACCURACY CONTRACT:
- ALL numbers (military power, resources, populations, dates) MUST come from tool data or injected context
- If a specific value is not in the data, say "unknown" or "I don't have that information" - NEVER estimate or guess
- You may provide strategic advice and opinions, but clearly distinguish them from facts
- When quoting numbers, use the exact values from the data

Always use tools to get current data rather than guessing."""


class Companion:
    """Stellaris companion using native Gemini SDK with automatic tool execution.

    This is a reusable class that can be used by the CLI, Discord bot, or other interfaces.
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
        self._chat_session = None
        self._thinking_level = 'dynamic'
        self._auto_precompute = bool(auto_precompute)

        # Initialize save-related attributes
        self.save_path: Path | None = None
        self.last_modified: float | None = None
        self.extractor: SaveExtractor | None = None
        self.metadata: dict = {}
        self.identity: dict = {}
        self.situation: dict = {}
        self.system_prompt: str = FALLBACK_SYSTEM_PROMPT
        self.personality_summary: str = "No save loaded"

        # Performance tracking for last request
        self._last_call_stats: dict[str, Any] = {
            "total_calls": 0,
            "tools_used": [],
            "wall_time_ms": 0.0,
            "response_length": 0,
            "payload_sizes": {},
        }

        # Save state tracking for staleness detection
        self._save_hash: str | None = None  # Hash of current save state
        self._last_known_date: str | None = None  # For context update messages

        # Snapshot tracking for diff mode (foundation for future use)
        self._previous_snapshot: dict | None = None
        self._current_snapshot: dict | None = None

        # Phase 4: full precompute cache (Option B /ask)
        self._briefing_lock = threading.RLock()
        self._briefing_ready = threading.Event()
        self._complete_briefing_json: str | None = None
        self._briefing_game_date: str | None = None
        self._briefing_updated_at: float | None = None
        self._briefing_last_error: str | None = None
        self._precompute_generation = 0

        # Phase 4: sliding-window conversation memory (per session key)
        self._conversations = ConversationManager(max_turns=5, timeout_minutes=15, max_answer_chars=500)

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

        # Build dynamic personality prompt
        self._build_personality()

        # Initialize save state tracking (finalized after precompute)
        self._save_hash = None
        self._last_known_date = self.metadata.get("date")

        # Initialize snapshot tracking (set on precompute completion)
        self._previous_snapshot = None
        self._current_snapshot = None

        # Reset chat session for new save
        self._chat_session = None

        # Kick off Phase 4 background precompute immediately (unless disabled for Electron ingestion manager).
        if self._auto_precompute:
            self.start_background_precompute(self.save_path)

    def _build_personality(self) -> None:
        """Build the dynamic personality prompt from empire data.

        Uses optimized prompt (625 chars) that trusts Gemini's Stellaris knowledge.
        Only hardcodes address style (model can't infer). Handles all empire types.
        """
        if not self.identity or not self.situation:
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            self.personality_summary = "Fallback: Generic advisor"
            return

        try:
            self.system_prompt = build_optimized_prompt(self.identity, self.situation)
            self.personality_summary = get_personality_summary(self.identity, self.situation)
        except Exception as e:
            print(f"Warning: Failed to build personality ({e}), using fallback")
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            self.personality_summary = "Fallback: Generic advisor"

    def _compute_save_hash(self) -> str:
        """Compute a hash of the current save state for staleness detection.

        Returns:
            8-character hash string, or empty string if no save loaded.
        """
        if not self.is_loaded:
            return ""
        # Hash key fields: date, military_power, empire_name
        player = self.extractor.get_player_status()
        key_data = f"{self.metadata.get('date')}|{player.get('military_power')}|{self.metadata.get('name')}"
        return hashlib.md5(key_data.encode()).hexdigest()[:8]

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
            old_identity.get('ethics') != self.identity.get('ethics') or
            old_identity.get('authority') != self.identity.get('authority') or
            old_identity.get('civics') != self.identity.get('civics')
        )

        # Rebuild personality
        self._build_personality()

        # Keep previous snapshot for diffing until a fresh precompute swaps in.
        self._previous_snapshot = self._current_snapshot
        self._last_known_date = self.metadata.get("date")

        # Reset tool-mode chat session on reload.
        self._chat_session = None
        logger.info(
            "save_update_detected",
            extra={
                "old_date": old_date,
                "new_date": self._last_known_date,
                "identity_changed": identity_changed,
            }
        )

        # Kick off Phase 4 background precompute for the new save (unless disabled for Electron ingestion manager).
        if self._auto_precompute:
            self.start_background_precompute(self.save_path)

        return identity_changed

    def get_changes_summary(self) -> str | None:
        """Get a summary of what changed since the last save.

        Compares key metrics between the previous and current snapshots
        to provide a human-readable summary of changes.

        Returns:
            Human-readable summary of changes, or None if no previous snapshot.
        """
        if self._previous_snapshot is None or self._current_snapshot is None:
            return None

        changes = []
        prev = self._previous_snapshot
        curr = self._current_snapshot

        # Compare military power
        prev_mil = prev.get('military', {}).get('power', 0)
        curr_mil = curr.get('military', {}).get('power', 0)
        if prev_mil != curr_mil and prev_mil > 0:
            pct = ((curr_mil - prev_mil) / prev_mil) * 100
            sign = '+' if pct > 0 else ''
            changes.append(f"Military power: {prev_mil:,} -> {curr_mil:,} ({sign}{pct:.0f}%)")

        # Compare fleet count
        prev_fleets = prev.get('military', {}).get('fleet_count', 0)
        curr_fleets = curr.get('military', {}).get('fleet_count', 0)
        if prev_fleets != curr_fleets:
            diff = curr_fleets - prev_fleets
            sign = '+' if diff > 0 else ''
            changes.append(f"Fleets: {prev_fleets} -> {curr_fleets} ({sign}{diff})")

        # Compare tech power
        prev_tech = prev.get('economy', {}).get('tech_power', 0)
        curr_tech = curr.get('economy', {}).get('tech_power', 0)
        if prev_tech != curr_tech and prev_tech > 0:
            pct = ((curr_tech - prev_tech) / prev_tech) * 100
            sign = '+' if pct > 0 else ''
            changes.append(f"Tech power: {prev_tech:,} -> {curr_tech:,} ({sign}{pct:.0f}%)")

        # Compare population
        prev_pop = prev.get('territory', {}).get('total_population', 0)
        curr_pop = curr.get('territory', {}).get('total_population', 0)
        if prev_pop != curr_pop:
            diff = curr_pop - prev_pop
            sign = '+' if diff > 0 else ''
            changes.append(f"Population: {prev_pop} -> {curr_pop} ({sign}{diff})")

        # Compare colony count
        prev_colonies = prev.get('territory', {}).get('colony_count', 0)
        curr_colonies = curr.get('territory', {}).get('colony_count', 0)
        if prev_colonies != curr_colonies:
            diff = curr_colonies - prev_colonies
            sign = '+' if diff > 0 else ''
            changes.append(f"Colonies: {prev_colonies} -> {curr_colonies} ({sign}{diff})")

        # Check for new wars (compare war counts or detect new entries)
        prev_wars = prev.get('military', {}).get('active_wars', [])
        curr_wars = curr.get('military', {}).get('active_wars', [])
        prev_war_names = {w.get('name', '') for w in prev_wars} if isinstance(prev_wars, list) else set()
        curr_war_names = {w.get('name', '') for w in curr_wars} if isinstance(curr_wars, list) else set()
        new_wars = curr_war_names - prev_war_names
        for war_name in new_wars:
            if war_name:
                changes.append(f"New war detected: {war_name}")

        # Compare key resources (net monthly)
        for resource in ['energy', 'minerals', 'alloys', 'food']:
            prev_net = prev.get('economy', {}).get('net_monthly', {}).get(resource, 0)
            curr_net = curr.get('economy', {}).get('net_monthly', {}).get(resource, 0)
            if prev_net != curr_net:
                diff = curr_net - prev_net
                sign = '+' if diff > 0 else ''
                changes.append(f"{resource.capitalize()} income: {prev_net:+.0f} -> {curr_net:+.0f} ({sign}{diff:.0f})")

        if not changes:
            return "No significant changes detected."

        return "\n".join(changes)

    def notify_save_update(self) -> tuple[bool, str]:
        """Check if save changed and return notification info.

        This method is designed for the Discord bot to poll for save changes
        and notify the user when the game state has been updated.

        Returns:
            Tuple of (changed: bool, message: str)
            - changed: True if save file has been modified
            - message: Human-readable message about the change
        """
        if not self.save_path:
            return False, "No save file loaded."

        if not self.check_save_changed():
            return False, "No changes detected."

        # Save changed, reload and get summary
        old_date = self._last_known_date
        self.reload_save()
        new_date = self._last_known_date

        # Build notification message
        message_parts = [f"Save updated: {old_date} -> {new_date}"]

        changes = self.get_changes_summary()
        if changes and changes != "No significant changes detected.":
            message_parts.append(changes)

        return True, "\n".join(message_parts)

    # === Tool Functions ===
    # These are passed directly to the SDK which auto-generates schemas from docstrings

    def get_player_status(self) -> dict:
        """Get the player's current empire status including military power, economy, tech, planets, and fleet count.

        Returns:
            Dictionary with player empire metrics
        """
        return self.extractor.get_player_status()

    def get_empire_details(self, empire_name: str) -> dict:
        """Get detailed information about a specific empire by name.

        Args:
            empire_name: The name of the empire to look up (e.g., "Prikkiki-Ti", "Fallen Empire")

        Returns:
            Dictionary with empire details including military power and relations
        """
        return self.extractor.get_empire(empire_name)

    def get_active_wars(self) -> dict:
        """Get information about all active wars in the galaxy.

        Returns:
            Dictionary with war names and details
        """
        return self.extractor.get_wars()

    def get_fleet_info(self) -> dict:
        """Get information about the player's fleets.

        Returns:
            Dictionary with fleet names and count
        """
        return self.extractor.get_fleets()

    def search_save_file(self, query: str) -> dict:
        """Search the full save file for specific text. Use this to find detailed information not available through other tools.

        Args:
            query: Text to search for in the save file

        Returns:
            Dictionary with search results and surrounding context
        """
        return self.extractor.search(query, max_results=3, context_chars=1500)

    def get_leaders(self) -> dict:
        """Get information about all the player's leaders including scientists, admirals, generals, governors, and envoys.

        Returns:
            Dictionary with leader names, classes, levels, ages, and traits
        """
        return self.extractor.get_leaders()

    def get_technology(self) -> dict:
        """Get the player's technology research status including completed technologies and current research projects.

        Returns:
            Dictionary with completed techs, current research in physics/society/engineering, and tech counts
        """
        return self.extractor.get_technology()

    def get_resources(self) -> dict:
        """Get the player's economy snapshot including resource income, expenses, and net monthly production.

        Returns:
            Dictionary with monthly income/expenses for energy, minerals, alloys, food, consumer goods, research, and strategic resources
        """
        return self.extractor.get_resources()

    def get_diplomacy(self) -> dict:
        """Get the player's diplomatic relations with other empires including opinion scores, treaties, and alliances.

        Returns:
            Dictionary with relations list, allies, federation membership, and opinion summaries
        """
        return self.extractor.get_diplomacy()

    def get_planets(self) -> dict:
        """Get information about the player's colonized planets including names, types, population, and stability.

        Returns:
            Dictionary with planet details, total population, and counts by planet type
        """
        return self.extractor.get_planets()

    def get_starbases(self) -> dict:
        """Get information about the player's starbases including levels, modules, and buildings.

        Returns:
            Dictionary with starbase details, counts by level, and module/building lists
        """
        return self.extractor.get_starbases()

    def get_snapshot(self) -> dict:
        """Get comprehensive empire snapshot - CALL THIS FIRST for any question.

        This is your PRIMARY data source. It returns all major empire data in ONE call
        and answers ~80% of questions directly without needing other tools.

        Returns data on:
        - Military: power, fleet count, fleet size
        - Economy: power, tech power, net monthly resources (energy, minerals, alloys, etc.)
        - Territory: colonies (count, population, breakdown by type), planets by type
        - Diplomacy: contact count, allies, rivals, federation membership
        - Defense: starbase count and levels
        - Leadership: leader count and breakdown by class

        ALWAYS call this first. Only use get_details() if you need MORE information
        on a specific category than what's provided here.

        Returns:
            Dictionary with military status, economy, diplomacy, territory, defense, and leadership
        """
        return self.extractor.get_full_briefing()

    def get_details(self, categories: list[str], limit: int = 10) -> dict:
        """Get detailed information for one or more categories - use AFTER get_snapshot().

        This is a drill-down tool for when get_snapshot() doesn't have enough detail.
        Only call this if you need MORE information than what get_snapshot() provides.

        Args:
            categories: List of categories to return. Valid items:
                - "leaders" - Full leader list with traits, levels, ages
                - "planets" - Full planet list with stability, amenities, size
                - "starbases" - Full starbase list with modules and buildings
                - "technology" - Completed techs and current research
                - "wars" - Active war details
                - "fleets" - Fleet names and details
                - "resources" - Full income/expense breakdown
                - "diplomacy" - Full relations list with opinion scores
            limit: Max items to return (default 10, max 50)

        Returns:
            Dictionary with per-category details (batched)
        """
        return self.extractor.get_details(categories, limit)

    def get_full_briefing(self) -> dict:
        """DEPRECATED: Use get_snapshot() instead. Kept for backwards compatibility."""
        return self.extractor.get_full_briefing()

    def _get_tools_list(self, mode: str = "full") -> list:
        """Get list of tool functions for the SDK.

        Args:
            mode: Tool availability mode:
                - "none": No tools (for /briefing where data is pre-injected)
                - "minimal": [get_snapshot, search_save_file] (for simple /ask)
                - "full": [get_snapshot, get_details, search_save_file, get_empire_details]
                         (for complex /ask requiring drill-down)

        Returns:
            List of tool functions based on mode
        """
        if mode == "none":
            return []

        elif mode == "minimal":
            # Snapshot + escape hatch only - for simple questions
            return [
                self.get_snapshot,
                self.search_save_file,
            ]

        elif mode == "full":
            # Full consolidated toolset - 4 tools instead of 12
            return [
                self.get_snapshot,      # Primary data source (80% of questions)
                self.get_details,       # Drill-down by category
                self.search_save_file,  # Escape hatch for edge cases
                self.get_empire_details,  # Look up other empires by name
            ]

        else:
            # Default to full if invalid mode
            return self._get_tools_list("full")

    def set_thinking_level(self, level: str) -> None:
        """Set the thinking level for the model.

        Args:
            level: One of 'dynamic', 'minimal', 'low', 'medium', 'high'
        """
        valid_levels = ['dynamic', 'minimal', 'low', 'medium', 'high']
        if level not in valid_levels:
            raise ValueError(f"Invalid thinking level. Must be one of: {valid_levels}")
        self._thinking_level = level
        self._chat_session = None

    async def chat_async(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response asynchronously.

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        # For now, just wrap the sync version
        # In future, could use async SDK if available
        return self.chat(user_message)

    def _extract_afc_stats(self, history_before: int = 0) -> tuple[
        int, dict[str, int], dict[str, int], set[str], list[list[str]]
    ]:
        """Extract per-request automatic function calling statistics.

        Args:
            history_before: Length of chat history before the request started.
                Only history entries added after this index are analyzed.

        Returns:
            Tuple of:
                - total_function_calls
                - function_call_counts: tool_name -> count
                - payload_sizes: tool_name -> response payload bytes (approx)
                - get_details_categories_seen: union of category strings requested
                - get_details_batches: list of category lists requested per get_details call
        """
        total_calls = 0
        call_counts: dict[str, int] = {}
        payload_sizes: dict[str, int] = {}
        details_categories_seen: set[str] = set()
        details_batches: list[list[str]] = []

        if self._chat_session is None:
            return total_calls, call_counts, payload_sizes, details_categories_seen, details_batches

        try:
            history = self._chat_session.get_history()
        except Exception as e:
            logger.debug(f"Could not read chat history for AFC stats: {e}")
            return total_calls, call_counts, payload_sizes, details_categories_seen, details_batches

        new_entries = history[history_before:] if isinstance(history, list) else []

        for content in new_entries:
            parts = getattr(content, "parts", None)
            if not parts:
                continue
            for part in parts:
                if hasattr(part, "function_call") and part.function_call:
                    func_name = getattr(part.function_call, "name", "unknown_tool")
                    total_calls += 1
                    call_counts[func_name] = call_counts.get(func_name, 0) + 1

                    if func_name == "get_details":
                        args = getattr(part.function_call, "args", None) or {}
                        cats = args.get("categories")
                        if isinstance(cats, list):
                            batch: list[str] = []
                            for c in cats:
                                if isinstance(c, str):
                                    details_categories_seen.add(c)
                                    batch.append(c)
                            if batch:
                                details_batches.append(batch)

                if hasattr(part, "function_response") and part.function_response:
                    func_name = getattr(part.function_response, "name", "unknown_tool")
                    response_data = getattr(part.function_response, "response", None)
                    try:
                        payload_str = json.dumps(response_data, default=str)
                        payload_sizes[func_name] = len(payload_str)
                    except (TypeError, ValueError):
                        payload_sizes[func_name] = 0

        return total_calls, call_counts, payload_sizes, details_categories_seen, details_batches

    def _response_has_pending_function_call(self, response: Any) -> bool:
        """Return True if the response contains a function_call part."""
        try:
            if not getattr(response, "candidates", None):
                return False
            candidate = response.candidates[0]
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None)
            if not parts:
                return False
            for part in parts:
                if hasattr(part, "function_call") and part.function_call:
                    return True
            return False
        except Exception:
            return False

    def _extract_new_tool_payloads(self, history_before: int) -> dict[str, Any]:
        """Extract tool payloads from chat history entries added since history_before."""
        if self._chat_session is None:
            return {}
        try:
            history = self._chat_session.get_history()
        except Exception:
            return {}

        new_entries = history[history_before:] if isinstance(history, list) else []
        tool_payloads: dict[str, Any] = {}

        for content in new_entries:
            parts = getattr(content, "parts", None)
            if not parts:
                continue
            for part in parts:
                if hasattr(part, "function_response") and part.function_response:
                    name = getattr(part.function_response, "name", "unknown_tool")
                    payload = getattr(part.function_response, "response", None)
                    tool_payloads[name] = payload

        return tool_payloads

    def chat(self, user_message: str, tool_mode: str = "full") -> tuple[str, float]:
        """Send a message and get a response using automatic function calling.

        The SDK handles the tool execution loop automatically for gemini-3-flash-preview.

        Args:
            user_message: The user's question or message
            tool_mode: Tool availability mode ("none", "minimal", "full")
                - "none": No tools (data pre-injected)
                - "minimal": get_snapshot + search_save_file only
                - "full": All 4 consolidated tools (default)

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        if not self.is_loaded:
            return "No save file loaded. Please load a save file first.", 0.0

        start_time = time.time()
        truncated_question = user_message[:100] + "..." if len(user_message) > 100 else user_message

        # Log request start
        logger.info(
            "chat_request_start",
            extra={
                "timestamp": time.time(),
                "mode": "afc",
                "question_preview": truncated_question,
                "question_length": len(user_message),
            }
        )

        try:
            # Check for stale context before sending message
            # Compute current hash to see if save changed since last interaction
            context_update_note = ""
            if self._chat_session is not None:
                current_hash = self._compute_save_hash()
                if current_hash != self._save_hash:
                    # Save state changed - prepend context update note
                    old_date = self._last_known_date
                    new_date = self.metadata.get('date')
                    context_update_note = (
                        f"[SAVE UPDATE: The game state has changed since our last conversation. "
                        f"Previous: {old_date}, Current: {new_date}]\n\n"
                    )
                    # Update tracking state
                    self._save_hash = current_hash
                    self._last_known_date = new_date
                    logger.info(
                        "stale_context_detected",
                        extra={
                            "old_date": old_date,
                            "new_date": new_date,
                        }
                    )

            # Create chat session once (just for history management)
            if self._chat_session is None:
                self._chat_session = self.client.chats.create(
                    model="gemini-3-flash-preview",
                )

            # Prepare message with optional context update note
            message_to_send = context_update_note + user_message if context_update_note else user_message

            # Build per-message config with tools (cookbook pattern)
            tools = self._get_tools_list(tool_mode)
            message_config = {
                'system_instruction': self.system_prompt,
                'tools': tools if tools else None,  # None if empty list (no tools mode)
                'temperature': 1.0,  # Gemini 3 recommended default
                'max_output_tokens': 4096,
            }

            # Only add AFC config if we have tools
            if tools:
                message_config['automatic_function_calling'] = types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=8,
                )

            # Add thinking config if not dynamic
            if self._thinking_level != 'dynamic':
                message_config['thinking_config'] = types.ThinkingConfig(
                    thinking_level=self._thinking_level
                )

            # Capture history length before sending (for AFC stats extraction)
            try:
                history_before = len(self._chat_session.get_history())
            except Exception:
                history_before = 0

            # Send message with config - SDK handles automatic function calling
            response = self._chat_session.send_message(
                message_to_send,
                config=message_config,
            )

            # Extract AFC statistics from history entries added by this request
            total_calls, call_counts, payload_sizes, _, _ = self._extract_afc_stats(history_before)
            tools_used = list(call_counts.keys())

            # Extract text from response
            if response.text:
                response_text = response.text
            else:
                # Check if we hit AFC limit with pending function calls
                has_pending_calls = False
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            has_pending_calls = True
                            break

                if has_pending_calls:
                    response_text = (
                        "I gathered a lot of data but ran out of processing steps. "
                        "Try asking a more specific question, or use /status for a quick overview."
                    )
                else:
                    response_text = "I processed your request but couldn't generate a text response."

            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            # Update call stats
            self._last_call_stats = {
                "total_calls": total_calls,
                "tools_used": tools_used,
                "wall_time_ms": wall_time_ms,
                "response_length": len(response_text),
                "payload_sizes": payload_sizes,
            }

            # Log response completion
            logger.info(
                "chat_request_complete",
                extra={
                    "mode": "afc",
                    "wall_time_ms": wall_time_ms,
                    "total_tool_calls": total_calls,
                    "tools_used": tools_used,
                    "response_length": len(response_text),
                    "payload_sizes": payload_sizes,
                    "total_payload_bytes": sum(payload_sizes.values()),
                }
            )

            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            # Reset stats on error
            self._last_call_stats = {
                "total_calls": 0,
                "tools_used": [],
                "wall_time_ms": wall_time_ms,
                "response_length": 0,
                "payload_sizes": {},
                "error": str(e),
            }

            # Log error
            logger.error(
                "chat_request_error",
                extra={
                    "mode": "afc",
                    "wall_time_ms": wall_time_ms,
                    "error": str(e),
                }
            )

            return f"Error: {str(e)}", elapsed

    def get_call_stats(self) -> dict[str, Any]:
        """Get performance statistics from the last chat() call.

        Returns:
            Dictionary with:
                - total_calls: number of tool calls made
                - tools_used: list of tool names called
                - wall_time_ms: total time in milliseconds
                - response_length: length of final response text
                - payload_sizes: dict mapping tool names to response sizes in bytes
        """
        return self._last_call_stats.copy()

    def clear_conversation(self) -> None:
        """Clear the conversation history by resetting the chat session."""
        self._chat_session = None
        # Also clear precomputed /ask conversation windows.
        self._conversations = ConversationManager(max_turns=5, timeout_minutes=15, max_answer_chars=500)

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
            self._save_hash = save_hash
            self._briefing_ready.set()

        # Update identity/situation/personality out of lock (prompt building can do I/O/logging).
        if isinstance(identity, dict):
            self.identity = identity
        if isinstance(situation, dict):
            self.situation = situation
        self._last_known_date = game_date
        self._build_personality()
        self._chat_session = None

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

    def _compute_save_hash_from_briefing(self, briefing: dict[str, Any]) -> str | None:
        """Compute a stable-ish hash for deduping snapshots."""
        if not isinstance(briefing, dict):
            return None
        meta = briefing.get("meta", {}) if isinstance(briefing.get("meta", {}), dict) else {}
        military = briefing.get("military", {}) if isinstance(briefing.get("military", {}), dict) else {}
        date = meta.get("date")
        empire_name = meta.get("empire_name") or meta.get("name")
        mil = military.get("military_power")
        if date is None and empire_name is None and mil is None:
            return None
        key_data = f"{date}|{mil}|{empire_name}"
        return hashlib.md5(key_data.encode("utf-8", errors="replace")).hexdigest()[:8]

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

        briefing_json = json.dumps(briefing, ensure_ascii=False, separators=(",", ":"), default=str)
        meta = briefing.get("meta", {}) if isinstance(briefing.get("meta", {}), dict) else {}
        game_date = meta.get("date")
        save_hash = self._compute_save_hash_from_briefing(briefing)

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
            self._save_hash = save_hash

            # Keep dict form for internal consumers (/history, etc.)
            self._previous_snapshot = self._current_snapshot
            self._current_snapshot = briefing

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
                session_id = db.get_active_or_latest_session_id_for_save_path(save_path=str(self.save_path))
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
                    json_text = db.get_latest_session_briefing_json(session_id=session_id) or db.get_latest_snapshot_full_briefing_json(session_id=session_id)
                    if json_text:
                        try:
                            parsed = json.loads(json_text)
                            gd = None
                            if isinstance(parsed, dict):
                                meta = parsed.get("meta", {}) if isinstance(parsed.get("meta", {}), dict) else {}
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
                    meta = parsed.get("meta", {}) if isinstance(parsed.get("meta", {}), dict) else {}
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
                return cached_json, cached_date, f"Using cached data from {cached_date}; new save processing…"
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
            return db_json, db_date, "Loaded from history cache; live save processing may still be running…"

        return None, None, None

    def ask_precomputed(
        self,
        question: str,
        session_key: str,
        history_context: str | None = None,
    ) -> tuple[str, float]:
        """Ask a question using the fully precomputed briefing (no tools)."""
        start_time = time.time()

        briefing_json, game_date, data_note = self._get_best_briefing_json()
        if not briefing_json:
            return "No precomputed game state is available yet. Please wait for a save to be processed.", 0.0

        # Build prompt with sliding-window history (Phase 4)
        user_prompt = self._conversations.build_prompt(
            session_key=session_key,
            briefing_json=briefing_json,
            game_date=game_date,
            question=question,
            data_note=data_note,
            history_context=history_context,
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
            response_text = response.text or "Could not generate a response."

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
                "payload_sizes": {"briefing_json": len(briefing_json)},
            }

            self._conversations.record_turn(
                session_key=session_key,
                question=question,
                answer=response_text,
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

    def briefing_direct(self) -> tuple[str, float]:
        """Get a strategic briefing with a single model call (no AFC).

        This pre-computes the state snapshot and sends it directly to the model,
        avoiding the multi-round-trip AFC loop.

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        if not self.is_loaded:
            return "No save file loaded. Please load a save file first.", 0.0

        start_time = time.time()

        # Log request start
        logger.info(
            "briefing_direct_start",
            extra={
                "timestamp": time.time(),
                "mode": "direct",
            }
        )

        try:
            # Get all briefing data in one local call
            briefing_data = self.extractor.get_full_briefing()
            briefing_json = json.dumps(briefing_data, indent=2, default=str)
            briefing_size = len(briefing_json)

            # Create a single prompt with all data pre-injected
            user_prompt = f"""Here is the current state of my empire:

```json
{briefing_json}
```

Based on this data, give me a strategic briefing. Cover:
1. Military strength and any immediate threats
2. Economic health and resource bottlenecks
3. Diplomatic situation and key relationships
4. Top 2-3 priorities I should focus on

Format your response as:

**FACTS** (from the data):
[Key metrics and numbers from the empire data]

**ANALYSIS** (your strategic assessment):
[Your interpretation and advice based on the facts]

Be concise but insightful."""

            # Build config for single direct call - no tools, no AFC
            message_config = types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=1.0,  # Gemini 3 recommended default
                max_output_tokens=4096,
            )

            # Add thinking config if not dynamic
            if self._thinking_level != 'dynamic':
                message_config.thinking_config = types.ThinkingConfig(
                    thinking_level=self._thinking_level
                )

            # Make ONE model call with no tools
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=user_prompt,
                config=message_config,
            )

            # Extract text from response
            response_text = response.text if response.text else "Could not generate briefing."

            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            # Update call stats for direct mode
            self._last_call_stats = {
                "total_calls": 1,  # Single direct call
                "tools_used": ["briefing_direct"],
                "wall_time_ms": wall_time_ms,
                "response_length": len(response_text),
                "payload_sizes": {"briefing_data": briefing_size},
            }

            # Log response completion
            logger.info(
                "briefing_direct_complete",
                extra={
                    "mode": "direct",
                    "wall_time_ms": wall_time_ms,
                    "briefing_data_size": briefing_size,
                    "response_length": len(response_text),
                }
            )

            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            # Reset stats on error
            self._last_call_stats = {
                "total_calls": 0,
                "tools_used": [],
                "wall_time_ms": wall_time_ms,
                "response_length": 0,
                "payload_sizes": {},
                "error": str(e),
            }

            # Log error
            logger.error(
                "briefing_direct_error",
                extra={
                    "mode": "direct",
                    "wall_time_ms": wall_time_ms,
                    "error": str(e),
                }
            )

            return f"Error: {str(e)}", elapsed

    def ask_simple(self, question: str, history_context: str | None = None) -> tuple[str, float]:
        """Ask a question using the 4 consolidated tools.

        Uses get_snapshot(), get_details(), search_save_file(), and get_empire_details().
        The system prompt instructs the model to call get_snapshot() first, which
        should provide enough data for most questions in a single call.

        Args:
            question: User's question
            history_context: Optional compact history context for trend/delta questions.

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        if not self.is_loaded:
            return "No save file loaded. Please load a save file first.", 0.0

        start_time = time.time()
        truncated_question = question[:100] + "..." if len(question) > 100 else question

        # Log request start
        logger.info(
            "ask_simple_start",
            extra={
                "timestamp": time.time(),
                "mode": "afc",
                "question_preview": truncated_question,
                "question_length": len(question),
            }
        )

        try:
            # Create chat session if needed
            if self._chat_session is None:
                self._chat_session = self.client.chats.create(
                    model="gemini-3-flash-preview",
                )

            # Use slim snapshot (summaries only, no truncated lists) to prevent hallucination.
            # Model must call get_details() for specific leader/planet/diplomacy info.
            snapshot_data = self.extractor.get_slim_briefing()
            snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
            snapshot_size = len(snapshot_json)

            user_prompt = (
                "GAME STATE SUMMARY (counts and headlines only):\n"
                "```json\n"
                f"{snapshot_json}\n"
                "```\n\n"
            )

            if history_context:
                # Keep small and deterministic: recent derived events + a few timeline points.
                user_prompt += (
                    "HISTORY CONTEXT (only use if the question asks about changes over time):\n"
                    f"{history_context[:3500]}\n\n"
                )

            user_prompt += (
                "USER_QUESTION:\n"
                f"{question}\n\n"
                "RULES:\n"
                "- The snapshot above contains SUMMARIES only (counts, totals, capital, ruler).\n"
                "- For specific leaders, planets, starbases, or diplomacy details: call get_details().\n"
                "- Example: get_details(['leaders']) for admiral traits, get_details(['planets']) for buildings.\n"
                "- Do NOT guess or make up details not in the snapshot - use tools instead.\n"
            )

            # Expose only drill-down tools for /ask; snapshot is injected above.
            tools = [
                self.get_details,
                self.search_save_file,
                self.get_empire_details,
            ]

            # Capture history length so we can extract tool payloads added by this request
            try:
                history_before = len(self._chat_session.get_history())
            except Exception:
                history_before = 0

            # Build config with consolidated tools
            ask_system_prompt = (
                f"{self.system_prompt}\n\n"
                "ASK MODE:\n"
                "- A game state SUMMARY is in the user message (counts, totals, headlines).\n"
                "- For SPECIFIC details (leader traits, planet buildings, diplomacy), USE get_details().\n"
                "- Batch categories when possible: get_details(['leaders', 'planets']).\n"
                "- Do NOT make up details - if it's not in the summary, call tools.\n"
                "- Maintain your full personality and colorful language - be an advisor, not a data dump!\n"
            )
            message_config = {
                'system_instruction': ask_system_prompt,
                'tools': tools,
                'temperature': 1.0,  # Gemini 3 recommended default
                'max_output_tokens': 4096,
                # Allow a couple drill-down calls without reintroducing long AFC chains.
                'automatic_function_calling': types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=6,
                ),
            }

            # Add thinking config if not dynamic
            if self._thinking_level != 'dynamic':
                message_config['thinking_config'] = types.ThinkingConfig(
                    thinking_level=self._thinking_level
                )

            # Send message
            response = self._chat_session.send_message(
                user_prompt,
                config=message_config,
            )

            # Extract per-request AFC statistics
            total_calls, call_counts, payload_sizes, details_categories_seen, details_batches = self._extract_afc_stats(history_before)
            tools_used = list(call_counts.keys())

            # If the model hit the AFC cap and left a pending function_call, do a final
            # tools-disabled call using whatever tool outputs we already gathered.
            has_pending_calls = self._response_has_pending_function_call(response)

            if has_pending_calls:
                logger.info(
                    "ask_simple_finalize_start cap=6 tool_calls=%s details=%s",
                    call_counts,
                    sorted(details_categories_seen),
                )
                tool_payloads = self._extract_new_tool_payloads(history_before)
                tool_payload_json = json.dumps(tool_payloads, separators=(",", ":"), default=str)
                # Keep the finalization prompt bounded
                if len(tool_payload_json) > 12000:
                    tool_payload_json = tool_payload_json[:12000] + "...TRUNCATED"

                finalize_prompt = (
                    "You previously attempted to answer but ran out of tool steps.\n"
                    "Answer now using ONLY the data below. Do NOT call tools.\n\n"
                    "SNAPSHOT_JSON:\n"
                    "```json\n"
                    f"{snapshot_json}\n"
                    "```\n\n"
                    "TOOL_OUTPUTS_JSON (may be partial):\n"
                    "```json\n"
                    f"{tool_payload_json}\n"
                    "```\n\n"
                    "QUESTION:\n"
                    f"{question}\n\n"
                    "RULES:\n"
                    "- All numbers must come from the JSON provided. If missing, say 'unknown'.\n"
                    "- If the question can't be fully answered from the data, ask one clarifying question.\n"
                )

                direct_config = types.GenerateContentConfig(
                    system_instruction=ask_system_prompt,
                    temperature=1.0,
                    max_output_tokens=4096,
                )
                if self._thinking_level != 'dynamic':
                    direct_config.thinking_config = types.ThinkingConfig(
                        thinking_level=self._thinking_level
                    )

                direct_response = self.client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=finalize_prompt,
                    config=direct_config,
                )

                # Log finish reason for debugging truncation issues
                finish_reason = None
                if direct_response.candidates:
                    finish_reason = getattr(direct_response.candidates[0], 'finish_reason', None)
                    if finish_reason and str(finish_reason) != "STOP":
                        logger.warning(
                            "ask_simple_finalize_finish_reason=%s (may indicate truncation)",
                            finish_reason,
                        )

                response_text = direct_response.text or (
                    "I gathered data but couldn't produce a final answer. "
                    "Try asking a more specific question."
                )

                # Warn if response seems truncated (ends mid-sentence)
                if response_text and len(response_text) > 50:
                    last_char = response_text.rstrip()[-1] if response_text.rstrip() else ''
                    if last_char not in '.!?")\']':
                        logger.warning(
                            "ask_simple_possible_truncation finish_reason=%s last_char='%s' response_len=%d",
                            finish_reason,
                            last_char,
                            len(response_text),
                        )

                # Update stats to reflect the extra direct call
                total_calls = max(total_calls, 0)
                tools_used = list(dict.fromkeys(tools_used + ["finalize_no_tools"]))
                payload_sizes = dict(payload_sizes)
                payload_sizes["snapshot_json"] = snapshot_size
                payload_sizes["finalize_tool_outputs"] = len(tool_payload_json)

            else:
                # Log finish reason for non-finalized responses too
                finish_reason = None
                if response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', None)
                    if finish_reason and str(finish_reason) != "STOP":
                        logger.warning(
                            "ask_simple_afc_finish_reason=%s (may indicate truncation)",
                            finish_reason,
                        )

                response_text = response.text or "Could not generate response."

                # Warn if response seems truncated
                if response_text and len(response_text) > 50:
                    last_char = response_text.rstrip()[-1] if response_text.rstrip() else ''
                    if last_char not in '.!?")\']':
                        logger.warning(
                            "ask_simple_possible_truncation finish_reason=%s last_char='%s' response_len=%d",
                            finish_reason,
                            last_char,
                            len(response_text),
                        )

            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000
            total_payload_kb = sum(payload_sizes.values()) // 1024

            details_batches_compact = []
            for batch in details_batches[:3]:
                # Keep ordering stable but compact in logs
                compact = "+".join(batch[:6])
                if len(batch) > 6:
                    compact += "+..."
                details_batches_compact.append(compact)
            if len(details_batches) > 3:
                details_batches_compact.append("...")  # Truncated

            # Update call stats
            self._last_call_stats = {
                "total_calls": total_calls,
                "tools_used": tools_used,
                "wall_time_ms": wall_time_ms,
                "response_length": len(response_text),
                "payload_sizes": {
                    **payload_sizes,
                    "snapshot_json": snapshot_size,
                },
            }

            # Log response completion (keep it concise for copy/paste)
            logger.info(
                "ask_simple_complete wall_ms=%.0f tool_calls=%s details=%s batches=%s payload_kb=%d finalized=%s response_chars=%d",
                wall_time_ms,
                call_counts,
                sorted(details_categories_seen),
                details_batches_compact,
                total_payload_kb,
                bool(has_pending_calls),
                len(response_text),
            )

            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            wall_time_ms = elapsed * 1000

            # Reset stats on error
            self._last_call_stats = {
                "total_calls": 0,
                "tools_used": [],
                "wall_time_ms": wall_time_ms,
                "response_length": 0,
                "payload_sizes": {},
                "error": str(e),
            }

            # Log error
            logger.error(
                "ask_simple_error",
                extra={
                    "mode": "afc",
                    "wall_time_ms": wall_time_ms,
                    "error": str(e),
                }
            )

            return f"Error: {str(e)}", elapsed

    def get_briefing(self) -> tuple[str, float]:
        """Get a strategic briefing from the advisor.

        Uses the fast single-call direct path instead of AFC.

        Returns:
            Tuple of (briefing_text, elapsed_time_seconds)
        """
        return self.briefing_direct()
