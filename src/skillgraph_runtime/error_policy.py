"""Frozen v0.2 Error Taxonomy mapped to deterministic local Runtime effects.

The mapping is intentionally declarative.  Effects such as a Research Gap,
Decision Log entry, idempotency ledger, or downstream invalidation are exposed
as deferred effects until their owning P0 tasks exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .errors import RuntimeContractError


class ErrorAction(Enum):
    BLOCK_NODE = "BLOCK_NODE"
    RETRY_NODE = "RETRY_NODE"
    OPEN_RESEARCH_GAP = "OPEN_RESEARCH_GAP"
    OFFER_EVIDENCE_WAIVER = "OFFER_EVIDENCE_WAIVER"
    WAIT_FOR_USER = "WAIT_FOR_USER"
    WAIT_FOR_EXTERNAL = "WAIT_FOR_EXTERNAL"
    PAUSE_AUTOMATION = "PAUSE_AUTOMATION"
    FAIL_WORKFLOW = "FAIL_WORKFLOW"
    REJECT_NO_MUTATION = "REJECT_NO_MUTATION"
    MARK_NOT_READY = "MARK_NOT_READY"
    REPAIR_INPUT = "REPAIR_INPUT"


@dataclass(frozen=True)
class ErrorPolicy:
    action: ErrorAction
    recoverable: bool
    consumes_node_attempt: bool = False
    consumes_global_research_cycle: bool = False
    deferred_effect: str | None = None


@dataclass(frozen=True)
class ErrorOutcome:
    code: str
    action: ErrorAction
    deferred_effect: str | None
    consumes_node_attempt: bool
    consumes_global_research_cycle: bool


_POLICIES: Mapping[str, ErrorPolicy] = {
    "INPUT_INVALID": ErrorPolicy(ErrorAction.BLOCK_NODE, False),
    "ARTIFACT_MISSING": ErrorPolicy(ErrorAction.BLOCK_NODE, True, deferred_effect="locate_or_invalidate_upstream"),
    "SCHEMA_INVALID": ErrorPolicy(ErrorAction.BLOCK_NODE, False),
    "SOURCE_UNAVAILABLE": ErrorPolicy(ErrorAction.RETRY_NODE, True, consumes_node_attempt=True),
    "INSUFFICIENT_EVIDENCE": ErrorPolicy(
        ErrorAction.OPEN_RESEARCH_GAP,
        True,
        consumes_node_attempt=True,
        consumes_global_research_cycle=True,
        deferred_effect="research_gap",
    ),
    "RESEARCH_LIMIT_REACHED": ErrorPolicy(
        ErrorAction.OFFER_EVIDENCE_WAIVER,
        False,
        deferred_effect="evidence_waiver_or_not_ready",
    ),
    "DEPENDENCY_NOT_READY": ErrorPolicy(ErrorAction.BLOCK_NODE, True, deferred_effect="locate_or_invalidate_upstream"),
    "GATE_NOT_APPROVED": ErrorPolicy(ErrorAction.WAIT_FOR_USER, True),
    "VISUALIZATION_DATA_INSUFFICIENT": ErrorPolicy(
        ErrorAction.OPEN_RESEARCH_GAP,
        True,
        consumes_node_attempt=True,
        consumes_global_research_cycle=True,
        deferred_effect="research_gap",
    ),
    "EXECUTOR_FAILED": ErrorPolicy(ErrorAction.RETRY_NODE, True, consumes_node_attempt=True),
    "PROOF_RESULT_INVALID": ErrorPolicy(ErrorAction.WAIT_FOR_EXTERNAL, True),
    "PROOF_REQUIRED_FAILED": ErrorPolicy(ErrorAction.MARK_NOT_READY, False),
    "BUDGET_EXCEEDED": ErrorPolicy(ErrorAction.PAUSE_AUTOMATION, False),
    "SECURITY_POLICY_VIOLATION": ErrorPolicy(ErrorAction.FAIL_WORKFLOW, False),
    "STATE_VERSION_CONFLICT": ErrorPolicy(ErrorAction.REJECT_NO_MUTATION, False, deferred_effect="state_version_retry"),
    "IDEMPOTENCY_CONFLICT": ErrorPolicy(ErrorAction.REJECT_NO_MUTATION, False, deferred_effect="new_idempotency_key"),
    "PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY": ErrorPolicy(ErrorAction.REPAIR_INPUT, False),
    "INSUFFICIENT_PRODUCT_CONTEXT": ErrorPolicy(ErrorAction.PAUSE_AUTOMATION, False),
    "SCHEMA_VERSION_UNSUPPORTED": ErrorPolicy(ErrorAction.REJECT_NO_MUTATION, False),
}


def error_policy(code: str) -> ErrorPolicy:
    try:
        return _POLICIES[code]
    except KeyError as exc:
        raise RuntimeContractError(
            "Error code is not part of the v0.2 Error Taxonomy",
            code="SCHEMA_INVALID",
            rule="error_taxonomy",
            details={"code": code},
        ) from exc


def validate_structured_error(error: Mapping[str, Any]) -> ErrorOutcome:
    """Reject Executor-selected policy metadata that contradicts the taxonomy."""

    if not isinstance(error, Mapping) or not isinstance(error.get("code"), str):
        raise RuntimeContractError("Executor Error must include a string code", rule="error_taxonomy")
    policy = error_policy(error["code"])
    expected = {
        "recoverable": policy.recoverable,
        "consumes_node_attempt": policy.consumes_node_attempt,
        "consumes_global_research_cycle": policy.consumes_global_research_cycle,
        "next_action": policy.action.value,
    }
    for field, value in expected.items():
        if field in error and error[field] is not None and error[field] != value:
            raise RuntimeContractError(
                "Executor Error metadata contradicts the Runtime Error Taxonomy",
                rule="error_taxonomy",
                details={"field": field, "expected": value, "actual": error[field], "code": error["code"]},
            )
    return ErrorOutcome(
        code=error["code"],
        action=policy.action,
        deferred_effect=policy.deferred_effect,
        consumes_node_attempt=policy.consumes_node_attempt,
        consumes_global_research_cycle=policy.consumes_global_research_cycle,
    )


def all_error_codes() -> frozenset[str]:
    return frozenset(_POLICIES)
