"""Stable Runtime errors shared across the in-memory core."""

from __future__ import annotations

from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        from types import MappingProxyType

        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


class RuntimeContractError(ValueError):
    """A deterministic, typed Runtime contract or invariant failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INPUT_INVALID",
        rule: str = "runtime_contract",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.rule = rule
        self.details = _freeze(details or {})
