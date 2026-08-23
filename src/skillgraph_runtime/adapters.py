"""Adapter boundaries that keep Runtime authority inside the Kernel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .domain import ValidatedExecutorProposal, deep_freeze
from .errors import RuntimeContractError


class ExecutorAdapter(Protocol):
    adapter_type: str

    def execute(self, request: ValidatedExecutorProposal) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ManualExecutionInstruction:
    attempt_id: str
    skill_ref: str
    input_artifact_refs: tuple[str, ...]
    permissions: Mapping[str, Any]
    budget: Mapping[str, Any]


class FixtureAdapter:
    """Returns only predeclared deterministic results for isolated tests."""

    adapter_type = "fixture"

    def __init__(self, catalog: Mapping[str, Mapping[str, Any]]) -> None:
        self.catalog = deep_freeze(catalog)

    def execute(self, request: ValidatedExecutorProposal) -> Mapping[str, Any]:
        payload = request.payload["executor_request"]
        key = f"{payload['skill_ref']}:{payload['attempt_id']}"
        result = self.catalog.get(key) or self.catalog.get(payload["skill_ref"])
        if not isinstance(result, Mapping):
            raise RuntimeContractError("Fixture Catalog has no deterministic result for the Attempt", rule="fixture_catalog")
        return result


class ManualAdapter:
    """Produces an instruction only; it never performs I/O or changes Runtime state."""

    adapter_type = "manual"

    def execute(self, request: ValidatedExecutorProposal) -> Mapping[str, Any]:
        payload = request.payload["executor_request"]
        return {
            "manual_instruction": ManualExecutionInstruction(
                attempt_id=payload["attempt_id"],
                skill_ref=payload["skill_ref"],
                input_artifact_refs=tuple(payload["input_artifact_refs"]),
                permissions=deep_freeze(payload["permissions"]),
                budget=deep_freeze(payload["budget"]),
            )
        }


class HostAgentAdapter:
    """Calls a supplied Host function; results remain untrusted proposals."""

    adapter_type = "host_agent"

    def __init__(self, callback: Callable[[ValidatedExecutorProposal], Mapping[str, Any]]) -> None:
        self.callback = callback

    def execute(self, request: ValidatedExecutorProposal) -> Mapping[str, Any]:
        result = self.callback(request)
        if not isinstance(result, Mapping):
            raise RuntimeContractError("Host Agent callback must return an Executor Result mapping", rule="host_agent_result")
        return result


class AdapterRegistry:
    """Explicit adapter lookup; no vendor, subprocess, or network fallback exists."""

    def __init__(self, adapters: tuple[ExecutorAdapter, ...] = ()) -> None:
        values = {adapter.adapter_type: adapter for adapter in adapters}
        if len(values) != len(adapters):
            raise RuntimeContractError("Adapter Registry contains duplicate adapter types", rule="adapter_registry")
        self._adapters = deep_freeze(values)

    def get(self, adapter_type: str) -> ExecutorAdapter:
        try:
            return self._adapters[adapter_type]
        except KeyError as exc:
            raise RuntimeContractError("Requested Executor Adapter is not configured", rule="adapter_unavailable") from exc
