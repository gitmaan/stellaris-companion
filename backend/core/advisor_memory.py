"""Helpers for keeping persisted Advisor memory limited to player intent."""

from __future__ import annotations


def sanitize_advisor_memory(summary: str | None) -> str:
    """Strip legacy persisted Advisor answers while retaining player requests.

    Older versions stored ``User asked: ... | Advisor suggested: ...``. The
    suggestion often contained time-sensitive campaign claims, so replaying it
    after a new save was ingested could contradict the current briefing.
    """
    lines: list[str] = []
    for raw_line in str(summary or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if " | Advisor suggested:" in line:
            line = line.split(" | Advisor suggested:", 1)[0].rstrip()
        lines.append(line)
    return "\n".join(lines)
