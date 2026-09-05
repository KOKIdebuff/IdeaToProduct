"""Deterministic primitives for state-version Fact Provenance.

These helpers are deliberately local-only: they operate on already persisted
Artifact documents and never resolve URLs, paths, or external resources.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .domain import deep_thaw
from .errors import RuntimeContractError


def canonical_value_hash(value: Any) -> str:
    """Return the stable SHA-256 identity of one JSON-compatible fact value."""

    payload = json.dumps(deep_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_pointer_value(document: Mapping[str, Any], pointer: str, *, rule: str) -> Any:
    """Resolve a strict RFC 6901 JSON Pointer without coercion or fallback."""

    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise RuntimeContractError("Fact Binding JSON Pointer is invalid", code="SCHEMA_INVALID", rule=rule)
    current: Any = document
    for raw_token in pointer[1:].split("/"):
        token = _unescape_pointer_token(raw_token, rule=rule)
        if isinstance(current, Mapping):
            if token not in current:
                raise RuntimeContractError("Fact Binding JSON Pointer does not resolve", code="SCHEMA_INVALID", rule=rule)
            current = current[token]
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if not token or token == "-" or (len(token) > 1 and token.startswith("0")) or not token.isdigit():
                raise RuntimeContractError("Fact Binding JSON Pointer array index is invalid", code="SCHEMA_INVALID", rule=rule)
            index = int(token)
            if index >= len(current):
                raise RuntimeContractError("Fact Binding JSON Pointer does not resolve", code="SCHEMA_INVALID", rule=rule)
            current = current[index]
            continue
        raise RuntimeContractError("Fact Binding JSON Pointer crosses a scalar", code="SCHEMA_INVALID", rule=rule)
    return current


def _unescape_pointer_token(raw: str, *, rule: str) -> str:
    value: list[str] = []
    index = 0
    while index < len(raw):
        character = raw[index]
        if character != "~":
            value.append(character)
            index += 1
            continue
        if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
            raise RuntimeContractError("Fact Binding JSON Pointer escape is invalid", code="SCHEMA_INVALID", rule=rule)
        value.append("~" if raw[index + 1] == "0" else "/")
        index += 2
    return "".join(value)
