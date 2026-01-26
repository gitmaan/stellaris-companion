#!/usr/bin/env python3
"""
Test script for Stellaris Companion structured logging.

This script demonstrates the performance logging capabilities
by loading a save file and making a chat request.

Usage:
    python test_logging.py [save_path]

If no save_path is provided, uses a placeholder path.
"""

import logging
import sys
from pathlib import Path

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from core.companion import Companion


def setup_logging():
    """Configure logging to show structured output."""

    # Create a custom formatter that shows the extra fields
    class StructuredFormatter(logging.Formatter):
        def format(self, record):
            # Start with base message
            base = super().format(record)

            # Add extra fields if present
            extras = []
            for key, value in record.__dict__.items():
                if key not in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                    "message",
                    "asctime",
                    "taskName",
                }:
                    extras.append(f"  {key}={value}")

            if extras:
                return base + "\n" + "\n".join(extras)
            return base

    # Configure the stellaris.companion logger
    logger = logging.getLogger("stellaris.companion")
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

    return logger


def print_stats(stats: dict):
    """Pretty print the call statistics."""
    print("\n" + "=" * 50)
    print("CALL STATISTICS")
    print("=" * 50)
    print(f"  Total tool calls:  {stats['total_calls']}")
    print(f"  Tools used:        {', '.join(stats['tools_used']) or 'None'}")
    print(
        f"  Wall time:         {stats['wall_time_ms']:.1f} ms ({stats['wall_time_ms'] / 1000:.2f} s)"
    )
    print(f"  Response length:   {stats['response_length']} chars")

    if stats.get("payload_sizes"):
        print("  Payload sizes:")
        for tool, size in stats["payload_sizes"].items():
            print(f"    - {tool}: {size:,} bytes")
        print(f"  Total payload:     {sum(stats['payload_sizes'].values()):,} bytes")

    if stats.get("error"):
        print(f"  Error:             {stats['error']}")

    print("=" * 50)


def main():
    """Run the logging test."""
    # Setup logging
    setup_logging()

    # Get save path from args or use placeholder
    if len(sys.argv) > 1:
        save_path = sys.argv[1]
    else:
        # Default test path - update this to your actual save file location
        save_path = Path.home() / "Documents/Paradox Interactive/Stellaris/save games/test/test.sav"
        print(f"No save path provided. Using default: {save_path}")
        print("Usage: python test_logging.py <path_to_save_file>")
        print()

    # Check if save exists
    save_path = Path(save_path)
    if not save_path.exists():
        print(f"ERROR: Save file not found: {save_path}")
        print("Please provide a valid save file path.")
        return 1

    print(f"Loading save file: {save_path}")
    print()

    try:
        # Initialize companion
        companion = Companion(save_path=save_path)
        print(f"Loaded empire: {companion.metadata.get('name', 'Unknown')}")
        print(f"Game date: {companion.metadata.get('date', 'Unknown')}")
        print()

        # Test 1: Simple status question
        print("=" * 50)
        print("TEST 1: Simple question (target: 3-8s)")
        print("=" * 50)
        question = "What is my current military power?"
        print(f"Question: {question}")
        print()

        response, elapsed = companion.chat(question)
        stats = companion.get_call_stats()

        print(f"\nResponse ({len(response)} chars):")
        print("-" * 40)
        print(response[:500] + "..." if len(response) > 500 else response)

        print_stats(stats)

        # Evaluate against target
        if stats["wall_time_ms"] < 8000:
            print("PASS: Response time within target (< 8s)")
        else:
            print("WARNING: Response time exceeded target (> 8s)")

        # Test 2: Briefing (more complex)
        print("\n" + "=" * 50)
        print("TEST 2: Strategic briefing (target: 6-12s)")
        print("=" * 50)

        # Clear conversation for fresh test
        companion.clear_conversation()

        response, elapsed = companion.get_briefing()
        stats = companion.get_call_stats()

        print(f"\nResponse ({len(response)} chars):")
        print("-" * 40)
        print(response[:500] + "..." if len(response) > 500 else response)

        print_stats(stats)

        # Evaluate against target
        if stats["wall_time_ms"] < 12000:
            print("PASS: Briefing time within target (< 12s)")
        else:
            print("WARNING: Briefing time exceeded target (> 12s)")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
