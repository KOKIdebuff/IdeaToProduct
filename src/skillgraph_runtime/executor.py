"""Executor Wire validation without Adapter execution or Runtime writes."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from .domain import AdapterType, AttemptRecord, AttemptStatus, NodeStatus, RunSnapshot, ValidatedExecutorProposal
from .errors import RuntimeContractError
from .graph import CompiledBundle


_FORBIDDEN_AUTHORITY_FIELDS = {
    "runtime_state",
    "workflow_state",
    "state_version",
    "manifest",
    "artifact_manifest",
    "event",
    "event_log",
    "decision",
    "decision_log",
}


def _reject_runtime_authority(value: Any, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_AUTHORITY_FIELDS:
                raise RuntimeContractError(
                    "Executor payload attempts to submit Runtime-owned authority",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="executor_authority",
                    details={"path": path + (str(key),)},
                )
            _reject_runtime_authority(item, path=path + (str(key),))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_runtime_authority(item, path=path + (str(index),))


def _validate_schema(payload: Mapping[str, Any], schema_name: str, bundle: CompiledBundle) -> None:
    schema = bundle.schemas[schema_name]
    errors = sorted(
        Draft202012Validator(
            schema,
            registry=bundle.schema_registry,
            format_checker=FormatChecker(),
        ).iter_errors(payload),
        key=lambda error: (tuple(str(item) for item in error.absolute_path), error.validator or ""),
    )
    if errors:
        first = errors[0]
        raise RuntimeContractError(
            f"Executor Wire payload is invalid: {first.message}",
            code="SCHEMA_INVALID",
            rule=f"{schema_name.removesuffix('.schema.json').replace('-', '_')}_schema",
            details={
                "path": tuple(first.absolute_path),
                "validator": first.validator,
                "errors": len(errors),
            },
        )


def _attempt(snapshot: RunSnapshot, attempt_id: str) -> AttemptRecord:
    matches = [attempt for attempt in snapshot.attempts if attempt.attempt_id == attempt_id]
    if len(matches) != 1:
        raise RuntimeContractError(
            "Executor attempt_id does not identify exactly one Runtime Attempt",
            rule="executor_attempt",
            details={"attempt_id": attempt_id, "matches": len(matches)},
        )
    attempt = matches[0]
    if attempt.run_id != snapshot.run_id:
        raise RuntimeContractError("Attempt belongs to a different Run", rule="executor_attempt_run")
    return attempt


def _identity_checks(payload: Mapping[str, Any], snapshot: RunSnapshot, attempt: AttemptRecord) -> None:
    expected = {
        "schema_version": snapshot.contract_version,
        "run_id": snapshot.run_id,
        "node_id": attempt.address.node_id,
        "attempt_id": attempt.attempt_id,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise RuntimeContractError(
                f"Executor {field} does not match the Runtime Attempt",
                rule=f"executor_{field}",
                details={"expected": value, "actual": payload.get(field)},
            )


def _safe_relative_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        raise RuntimeContractError("Workspace write path is invalid", code="SECURITY_POLICY_VIOLATION", rule="workspace_path")
    if "\\" in raw_path or ":" in raw_path or any(ord(character) < 32 for character in raw_path):
        raise RuntimeContractError(
            "Workspace write path contains an unsafe platform-specific component",
            code="SECURITY_POLICY_VIOLATION",
            rule="workspace_path",
            details={"path": raw_path},
        )
    normalized = raw_path
    raw_parts = normalized.rstrip("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
    if any(
        part in {"", ".", ".."}
        or part.endswith((".", " "))
        or part.split(".", 1)[0].upper() in reserved
        for part in raw_parts
    ):
        raise RuntimeContractError(
            "Workspace write path contains an unsafe component",
            code="SECURITY_POLICY_VIOLATION",
            rule="workspace_path",
            details={"path": raw_path},
        )
    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise RuntimeContractError(
            "Workspace write path must be a safe relative path",
            code="SECURITY_POLICY_VIOLATION",
            rule="workspace_path",
            details={"path": raw_path},
        )
    return path.as_posix() + ("/" if normalized.endswith("/") else "")


def _path_is_within(requested: str, allowed: str) -> bool:
    requested_normalized = _safe_relative_path(requested)
    allowed_normalized = _safe_relative_path(allowed)
    if requested_normalized == allowed_normalized:
        return True
    if allowed_normalized.endswith("/"):
        return requested_normalized.startswith(allowed_normalized)
    return False


def _validate_permissions(request: Mapping[str, Any], attempt: AttemptRecord) -> None:
    permissions = request["permissions"]
    external_rank = {"none": 0, "read_only": 1}
    if external_rank[permissions["external_access"]] > external_rank[attempt.permissions.external_access]:
        raise RuntimeContractError(
            "Executor Request escalates external access",
            code="SECURITY_POLICY_VIOLATION",
            rule="permission_external_access",
        )
    if permissions["secrets"] != attempt.permissions.secrets:
        raise RuntimeContractError(
            "Executor Request escalates secret access",
            code="SECURITY_POLICY_VIOLATION",
            rule="permission_secrets",
        )
    requested_paths = permissions["workspace_write_paths"]
    normalized = [_safe_relative_path(path) for path in requested_paths]
    if len(normalized) != len(set(normalized)):
        raise RuntimeContractError("Workspace paths are not unique after normalization", rule="workspace_path_duplicate")
    for requested in requested_paths:
        if not any(_path_is_within(requested, allowed) for allowed in attempt.permissions.workspace_write_paths):
            raise RuntimeContractError(
                "Executor Request exceeds the Skill workspace declaration",
                code="SECURITY_POLICY_VIOLATION",
                rule="permission_workspace_path",
                details={"path": requested},
            )


def _validate_budget(request: Mapping[str, Any], attempt: AttemptRecord) -> None:
    budget = request["budget"]
    planned = {
        "timeout_minutes": attempt.budget.timeout_minutes,
        "max_sources": attempt.budget.max_sources,
        "token_limit": attempt.budget.token_limit,
        "cost_limit": attempt.budget.cost_limit,
    }
    fields = tuple(field for field, value in planned.items() if budget[field] != value)
    if fields:
        exceeded = tuple(
            field
            for field in fields
            if planned[field] is not None and (budget[field] is None or budget[field] > planned[field])
        )
        raise RuntimeContractError(
            "Executor Request budget must match the effective Attempt plan",
            code="BUDGET_EXCEEDED" if exceeded else "INPUT_INVALID",
            rule="executor_request_budget",
            details={"fields": fields, "exceeded": exceeded},
        )


def validate_executor_request(
    snapshot: RunSnapshot,
    attempt_id: str,
    request: Mapping[str, Any],
    bundle: CompiledBundle,
) -> ValidatedExecutorProposal:
    if not isinstance(request, Mapping):
        raise RuntimeContractError("Executor Request must be a mapping", rule="executor_request_type")
    _reject_runtime_authority(request)
    _validate_schema(request, "executor-request.schema.json", bundle)
    attempt = _attempt(snapshot, attempt_id)
    payload = request["executor_request"]
    _identity_checks(payload, snapshot, attempt)
    exact = {
        "skill_ref": attempt.skill_ref,
        "profile_ref": attempt.profile_ref,
        "research_contract_ref": attempt.research_contract_ref,
    }
    for field, expected in exact.items():
        if payload[field] != expected:
            raise RuntimeContractError(
                f"Executor Request {field} does not match the Attempt plan",
                rule=f"executor_{field}",
                details={"expected": expected, "actual": payload[field]},
            )
    if tuple(sorted(payload["input_artifact_refs"])) != attempt.input_artifact_refs:
        raise RuntimeContractError(
            "Executor Request input_artifact_refs do not match the Attempt plan",
            rule="executor_input_artifact_refs",
            details={"expected": attempt.input_artifact_refs, "actual": tuple(payload["input_artifact_refs"])},
        )
    try:
        adapter = AdapterType(payload["adapter_type"])
    except ValueError as exc:
        raise RuntimeContractError("Executor adapter_type is unknown", rule="executor_adapter") from exc
    if adapter not in attempt.allowed_adapter_types:
        raise RuntimeContractError(
            "Executor adapter_type is not allowed by the Skill",
            code="SECURITY_POLICY_VIOLATION",
            rule="executor_adapter",
        )
    _validate_permissions(payload, attempt)
    _validate_budget(payload, attempt)

    resume = payload.get("interaction_resume")
    state = snapshot.node_states.get(attempt.address)
    definition = bundle.definition(attempt.address)
    if resume is not None:
        if (
            not definition.interactive
            or attempt.status is not AttemptStatus.WAITING_FOR_USER
            or state is None
            or state.status is not NodeStatus.WAITING_FOR_USER
            or state.active_attempt_id != attempt.attempt_id
            or state.interaction_checkpoint_ref != resume["checkpoint_ref"]
        ):
            raise RuntimeContractError(
                "Interaction Resume does not match the waiting node and Attempt checkpoint",
                rule="interaction_resume",
            )
    elif (
        attempt.status is not AttemptStatus.RUNNING
        or state is None
        or state.status is not NodeStatus.RUNNING
        or state.active_attempt_id != attempt.attempt_id
    ):
        raise RuntimeContractError("Executor Request does not match the active running Attempt", rule="executor_attempt_status")
    return ValidatedExecutorProposal("request", attempt_id, request)


def _validate_usage(result: Mapping[str, Any], attempt: AttemptRecord) -> None:
    usage = result["usage"]
    cumulative = attempt.usage.add(usage)
    violations: list[str] = []
    if cumulative.automated_duration_seconds > attempt.budget.timeout_minutes * 60:
        violations.append("automated_duration_seconds")
    if cumulative.source_count > attempt.budget.max_sources or len(result["source_upserts"]) > attempt.budget.max_sources:
        violations.append("source_count")
    if attempt.budget.token_limit is not None:
        input_tokens = cumulative.input_tokens
        output_tokens = cumulative.output_tokens
        if input_tokens is None or output_tokens is None or input_tokens + output_tokens > attempt.budget.token_limit:
            violations.append("token_limit")
    if attempt.budget.cost_limit is not None:
        cost = cumulative.estimated_cost
        if cost is None or cost > attempt.budget.cost_limit:
            violations.append("cost_limit")
    if violations:
        raise RuntimeContractError(
            "Executor Result usage exceeds the corresponding Attempt request",
            code="BUDGET_EXCEEDED",
            rule="executor_result_usage",
            details={"fields": tuple(dict.fromkeys(violations))},
        )


def _validate_interaction(result: Mapping[str, Any], attempt: AttemptRecord, bundle: CompiledBundle) -> None:
    if result["status"] != "WAITING_FOR_USER":
        return
    definition = bundle.definition(attempt.address)
    if not definition.interactive:
        raise RuntimeContractError("Only an interactive Skill may wait for the user", rule="interaction_skill")
    skill = bundle.skills[definition.implementation_ref or ""]
    interaction = skill["interaction"]
    request = result["interaction_request"]
    checkpoint = result["interaction_checkpoint"]
    if request["method"] != checkpoint["current_method"]:
        raise RuntimeContractError("Interaction method and checkpoint do not match", rule="interaction_method_mismatch")
    if request["round"] != checkpoint["round"]:
        raise RuntimeContractError("Interaction round and checkpoint do not match", rule="interaction_round_mismatch")
    if request["method"] not in interaction["supported_methods"] or request["round"] > interaction["max_rounds"]:
        raise RuntimeContractError("Interaction exceeds the Skill contract", rule="interaction_contract")
    recommendation = request["recommendation"]
    if recommendation is not None and recommendation["option_id"] not in {option["id"] for option in request["options"]}:
        raise RuntimeContractError("Interaction recommendation does not reference an option", rule="interaction_recommendation")


def validate_executor_result(
    snapshot: RunSnapshot,
    attempt_id: str,
    result: Mapping[str, Any],
    bundle: CompiledBundle,
) -> ValidatedExecutorProposal:
    if not isinstance(result, Mapping):
        raise RuntimeContractError("Executor Result must be a mapping", rule="executor_result_type")
    _reject_runtime_authority(result)
    _validate_schema(result, "executor-result.schema.json", bundle)
    attempt = _attempt(snapshot, attempt_id)
    payload = result["executor_result"]
    _identity_checks(payload, snapshot, attempt)
    state = snapshot.node_states.get(attempt.address)
    if (
        attempt.status is not AttemptStatus.RUNNING
        or state is None
        or state.status is not NodeStatus.RUNNING
        or state.active_attempt_id != attempt.attempt_id
    ):
        raise RuntimeContractError("Executor Result targets a non-active Attempt", rule="executor_attempt_status")
    _validate_usage(payload, attempt)
    _validate_interaction(payload, attempt, bundle)
    return ValidatedExecutorProposal("result", attempt_id, result)
