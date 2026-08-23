"""Pure Attempt planning and deterministic input fingerprinting."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import Any, Callable, Iterable, Mapping, Protocol

from .domain import (
    AdapterType,
    AttemptMode,
    AttemptRecord,
    AttemptStatus,
    BudgetLimits,
    InvocationRequirements,
    NodeAddress,
    NodeDefinition,
    NodeState,
    NodeStatus,
    PermissionSet,
    RunSnapshot,
    deep_thaw,
)
from .errors import RuntimeContractError
from .graph import CompiledBundle
from .transitions import transition_attempt, transition_node


class AttemptIdFactory(Protocol):
    def new_attempt_id(self) -> str: ...


def _minimum_optional(*values: int | float | None) -> int | float | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def invocation_policy(
    bundle: CompiledBundle,
    definition: NodeDefinition,
    snapshot: RunSnapshot,
    *,
    host_token_limit: int | None = None,
    host_cost_limit: float | None = None,
) -> tuple[PermissionSet, BudgetLimits, tuple[AdapterType, ...]]:
    """Return the effective least-privilege permissions, budgets and adapter set."""

    if definition.implementation_ref is None or definition.implementation_ref not in bundle.skills:
        raise RuntimeContractError(
            "Executable node has no selected Skill contract",
            rule="attempt_skill",
            details={"node_id": definition.address.node_id},
        )
    skill = bundle.skills[definition.implementation_ref]
    raw_permissions = skill["permissions"]
    permissions = PermissionSet(
        external_access=raw_permissions["external_access"],
        workspace_write_paths=tuple(raw_permissions.get("workspace_write", ())),
        secrets=raw_permissions.get("secrets", "forbidden"),
    )
    raw_budget = skill["budget"]
    budget = BudgetLimits(
        timeout_minutes=min(raw_budget["timeout_minutes"], snapshot.run_policy.automated_attempt_timeout_minutes),
        max_sources=min(raw_budget["max_sources"], snapshot.run_policy.max_sources_per_research_node),
        token_limit=_minimum_optional(snapshot.run_policy.host_token_limit, host_token_limit),
        cost_limit=_minimum_optional(snapshot.run_policy.host_cost_limit, host_cost_limit),
    )
    adapters = tuple(AdapterType(value) for value in skill["executor"]["allowed_adapter_types"])
    return permissions, budget, adapters


def input_fingerprint(
    *,
    skill_ref: str,
    input_artifact_refs: Iterable[str],
    profile_ref: str,
    research_contract_ref: str | None,
    relevant_config: Mapping[str, Any],
    permissions: PermissionSet,
    budget: BudgetLimits,
) -> str:
    """Hash the canonical, execution-relevant input envelope.

    Artifact references and workspace paths have set semantics and are sorted.
    Lists nested in business configuration retain their declared order.
    """

    payload = {
        "budget": {
            "cost_limit": budget.cost_limit,
            "max_sources": budget.max_sources,
            "timeout_minutes": budget.timeout_minutes,
            "token_limit": budget.token_limit,
        },
        "input_artifact_refs": sorted(set(input_artifact_refs)),
        "permissions": {
            "external_access": permissions.external_access,
            "secrets": permissions.secrets,
            "workspace_write_paths": sorted(set(permissions.workspace_write_paths)),
        },
        "profile_ref": profile_ref,
        "relevant_config": deep_thaw(relevant_config),
        "research_contract_ref": research_contract_ref,
        "skill_ref": skill_ref,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def plan_attempt(
    snapshot: RunSnapshot,
    definition: NodeDefinition,
    bundle: CompiledBundle,
    *,
    input_artifact_refs: Iterable[str],
    id_factory: AttemptIdFactory,
    now: Callable[[], str],
    mode: AttemptMode = AttemptMode.INITIAL,
    host_token_limit: int | None = None,
    host_cost_limit: float | None = None,
) -> tuple[AttemptRecord | None, InvocationRequirements | None, str | None]:
    permissions, budget, adapters = invocation_policy(
        bundle,
        definition,
        snapshot,
        host_token_limit=host_token_limit,
        host_cost_limit=host_cost_limit,
    )
    refs = tuple(sorted(set(input_artifact_refs)))
    skill_ref = f"{definition.implementation_ref}@{snapshot.contract_version}"
    address_config = dict(definition.relevant_config)
    address_config["node_address"] = {
        "graph_path": list(definition.address.graph_path),
        "node_id": definition.address.node_id,
        "instance_key": definition.address.instance_key,
    }
    fingerprint = input_fingerprint(
        skill_ref=skill_ref,
        input_artifact_refs=refs,
        profile_ref=snapshot.profile_ref,
        research_contract_ref=snapshot.research_contract_ref,
        relevant_config=address_config,
        permissions=permissions,
        budget=budget,
    )
    if mode is not AttemptMode.REFRESH:
        reusable = next(
            (
                attempt
                for attempt in reversed(snapshot.attempts)
                if attempt.input_fingerprint == fingerprint
                and attempt.status is AttemptStatus.COMPLETED
                and attempt.verified
            ),
            None,
        )
        if reusable is not None:
            return None, None, reusable.attempt_id

    attempt_id = id_factory.new_attempt_id()
    if re.fullmatch(r"^ATT-[A-Za-z0-9_-]+$", attempt_id) is None:
        raise RuntimeContractError("IdFactory returned an invalid attempt_id", rule="attempt_id")
    if any(existing.attempt_id == attempt_id for existing in snapshot.attempts):
        raise RuntimeContractError(
            "IdFactory returned an existing attempt_id",
            rule="attempt_id_duplicate",
            details={"attempt_id": attempt_id},
        )
    attempt = AttemptRecord(
        attempt_id=attempt_id,
        run_id=snapshot.run_id,
        address=definition.address,
        skill_ref=skill_ref,
        status=AttemptStatus.RUNNING,
        mode=mode,
        input_fingerprint=fingerprint,
        input_artifact_refs=refs,
        profile_ref=snapshot.profile_ref,
        research_contract_ref=snapshot.research_contract_ref,
        permissions=permissions,
        budget=budget,
        allowed_adapter_types=adapters,
        started_at=now(),
        relevant_config=address_config,
    )
    invocation = InvocationRequirements(
        attempt_id=attempt_id,
        address=definition.address,
        skill_ref=skill_ref,
        input_artifact_refs=refs,
        profile_ref=snapshot.profile_ref,
        research_contract_ref=snapshot.research_contract_ref,
        permissions=permissions,
        budget=budget,
        allowed_adapter_types=adapters,
    )
    return attempt, invocation, None


def resume_interactive_attempt(
    snapshot: RunSnapshot,
    address: NodeAddress,
    bundle: CompiledBundle,
) -> RunSnapshot:
    """Resume the same waiting Attempt identity; never append a new Attempt."""

    try:
        state = snapshot.node_states[address]
    except KeyError as exc:
        raise RuntimeContractError("Unknown interaction node", rule="interaction_resume_node") from exc
    definition = bundle.definition(address)
    if not definition.interactive or state.status is not NodeStatus.WAITING_FOR_USER or not state.active_attempt_id:
        raise RuntimeContractError("Node has no resumable interaction", rule="interaction_resume_state")
    index = next(
        (position for position, attempt in enumerate(snapshot.attempts) if attempt.attempt_id == state.active_attempt_id),
        None,
    )
    if index is None:
        raise RuntimeContractError("Active interaction Attempt is missing", rule="interaction_resume_attempt")
    attempt = snapshot.attempts[index]
    if attempt.address != address or attempt.status is not AttemptStatus.WAITING_FOR_USER:
        raise RuntimeContractError("Interaction Attempt identity does not match node state", rule="interaction_resume_attempt")
    attempts = list(snapshot.attempts)
    # A response creates an append-only successor checkpoint before this
    # transition.  Keep the active Attempt aligned with the NodeState so an
    # embedded business service resumes from the accepted response instead of
    # the earlier waiting checkpoint.
    attempts[index] = replace(
        transition_attempt(attempt, AttemptStatus.RUNNING),
        interaction_checkpoint_ref=state.interaction_checkpoint_ref,
    )
    states = dict(snapshot.node_states)
    states[address] = transition_node(definition, state, NodeStatus.RUNNING)
    return replace(snapshot, state_version=snapshot.state_version + 1, node_states=states, attempts=tuple(attempts))
