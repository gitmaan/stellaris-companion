"""Parse provider JSON consistently for generation and Chronicle validation."""

from pydantic import BaseModel


def repair_json_string(text: str) -> str:
    """Repair JSON with unescaped newlines in string values.

    Gemini sometimes returns JSON with literal newlines inside strings,
    which is invalid JSON. This function escapes them properly.
    """
    # Track quoted strings, respecting escaped quotes.
    result = []
    in_string = False
    escape_next = False
    i = 0

    while i < len(text):
        char = text[i]

        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue

        if char == "\\":
            result.append(char)
            escape_next = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = not in_string
            i += 1
            continue

        if in_string and char == "\n":
            # Escape the newline
            result.append("\\n")
            i += 1
            continue

        if in_string and char == "\r":
            # Skip carriage returns (will be part of \r\n -> \n)
            i += 1
            continue

        if in_string and char == "\t":
            # Escape tabs
            result.append("\\t")
            i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


def _extract_json_object(text: str) -> str:
    """Extract a JSON object from plain text or a fenced provider response."""
    candidate = str(text or "").strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Response did not contain a JSON object")
    return candidate[start : end + 1]


def validate_structured_response(
    text: str,
    response_schema: type[BaseModel],
) -> BaseModel:
    """Validate provider JSON, repairing literal control characters once."""
    candidate = _extract_json_object(text)
    try:
        return response_schema.model_validate_json(candidate)
    except Exception as initial_error:
        repaired = repair_json_string(candidate)
        if repaired == candidate:
            raise initial_error
        return response_schema.model_validate_json(repaired)
