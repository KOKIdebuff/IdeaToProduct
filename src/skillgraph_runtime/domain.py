"""Immutable domain types for the deterministic Runtime Core."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, TypeVar

from .errors import RuntimeContractError


MACHINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
COMPETITOR_ID_PATTERN = re.compile(r"^cmp_[a-z0-9][a-z0-9_-]*$")


class NodeKind(Enum):
    SKILL = "skill"
    SUBGRAPH = "subgraph"
    HUMAN_GATE = "human_gate"
    VERIFIER = "verifier"
    ROUTER = "router"
    EXTERNAL_INPUT = "external_input"


class NodeStatus(Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_EXTERNAL = "WAITING_FOR_EXTERNAL"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    RETRY_READY = "RETRY_READY"
    SKIPPED = "SKIPPED"
    INVALIDATED = "INVALIDATED"


class VerificationResult(Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class GateDecision(Enum):
    APPROVE = "APPROVE"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    SELECT_OTHER = "SELECT_OTHER"
    REQUEST_MORE_RESEARCH = "REQUEST_MORE_RESEARCH"
    PARTIAL_ACCEPTED = "PARTIAL_ACCEPTED"


class FeasibilityResult(Enum):
    FEASIBLE = "FEASIBLE"
    CONDITIONALLY_FEASIBLE = "CONDITIONALLY_FEASIBLE"
    BLOCKED = "BLOCKED"
    NOT_FEASIBLE = "NOT_FEASIBLE"


class WorkflowStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_EXTERNAL = "WAITING_FOR_EXTERNAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ReadinessStatus(Enum):
    READY_FOR_BUILD = "READY_FOR_BUILD"
    READY_WITH_ACCEPTED_RISKS = "READY_WITH_ACCEPTED_RISKS"
    NOT_READY = "NOT_READY"


class ProofOutcome(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class AttemptStatus(Enum):
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_EXTERNAL = "WAITING_FOR_EXTERNAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


class AttemptMode(Enum):
    INITIAL = "initial"
    RETRY = "retry"
    REFRESH = "refresh"
    INTERACTION_RESUME = "interaction_resume"


class AdapterType(Enum):
    FIXTURE = "fixture"
    MANUAL = "manual"
    HOST_AGENT = "host_agent"


class SkipReason(Enum):
    PROFILE_DISABLED = "PROFILE_DISABLED"
    CONDITION_NOT_MATCHED = "CONDITION_NOT_MATCHED"
    APPROVED_OPTIONAL_SKIP = "APPROVED_OPTIONAL_SKIP"
    TERMINAL_BRANCH_NOT_SELECTED = "TERMINAL_BRANCH_NOT_SELECTED"


class TerminalEvent(Enum):
    CRITICAL_RESEARCH_BLOCKER = "CRITICAL_RESEARCH_BLOCKER"
    FEASIBILITY_NOT_FEASIBLE = "FEASIBILITY_NOT_FEASIBLE"
    REQUIRED_PROOF_FAILED = "REQUIRED_PROOF_FAILED"
    PRD_CONSISTENCY_FAILED = "PRD_CONSISTENCY_FAILED"


class Priority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}[self]


_T = TypeVar("_T")


def immutable_mapping(value: Mapping[_T, Any] | None = None) -> Mapping[_T, Any]:
    return MappingProxyType(dict(value or {}))


def deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value


def deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: deep_thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [deep_thaw(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(deep_thaw(item) for item in value)
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True, order=True)
class NodeAddress:
    graph_path: tuple[str, ...]
    node_id: str
    instance_key: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.graph_path, str) or not isinstance(self.graph_path, (tuple, list)):
            raise RuntimeContractError("NodeAddress graph_path must be a sequence of identifiers", rule="node_address_graph")
        object.__setattr__(self, "graph_path", tuple(self.graph_path))
        values = (*self.graph_path, self.node_id)
        if any(not isinstance(value, str) or MACHINE_ID_PATTERN.fullmatch(value) is None for value in values):
            raise RuntimeContractError(
                "NodeAddress contains an invalid machine identifier",
                rule="node_address",
                details={"graph_path": self.graph_path, "node_id": self.node_id},
            )
        if self.instance_key is not None and (
            not isinstance(self.instance_key, str) or MACHINE_ID_PATTERN.fullmatch(self.instance_key) is None
        ):
            raise RuntimeContractError(
                "NodeAddress instance_key is invalid",
                rule="node_address_instance",
                details={"instance_key": self.instance_key},
            )

    @property
    def is_top_level(self) -> bool:
        return not self.graph_path and self.instance_key is None


@dataclass(frozen=True)
class ConditionPredicate:
    node_id: str
    result_field: str
    expected_values: tuple[str, ...]


@dataclass(frozen=True)
class ConditionExpression:
    predicates: tuple[ConditionPredicate, ...]
    any_of: bool = False


@dataclass(frozen=True)
class NodeDefinition:
    address: NodeAddress
    kind: NodeKind
    implementation_ref: str | None
    depends_on: tuple[str, ...] = ()
    required: bool = False
    configurable_by_profile: bool = False
    enabled: bool = True
    interactive: bool = False
    condition: ConditionExpression | None = None
    trigger_on_terminal_events: tuple[TerminalEvent, ...] = ()
    priority: Priority = Priority.HIGH
    declaration_order: int = 0
    relevant_config: Mapping[str, Any] = field(default_factory=immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        object.__setattr__(self, "trigger_on_terminal_events", tuple(self.trigger_on_terminal_events))
        object.__setattr__(self, "relevant_config", deep_freeze(self.relevant_config))


@dataclass(frozen=True)
class NodeState:
    status: NodeStatus = NodeStatus.PENDING
    attempt_count: int = 0
    active_attempt_id: str | None = None
    interaction_checkpoint_ref: str | None = None
    artifact_refs: tuple[str, ...] = ()
    verification_result: VerificationResult | None = None
    gate_decision: GateDecision | None = None
    feasibility_result: FeasibilityResult | None = None
    proof_outcome: ProofOutcome | None = None
    skip_reason: SkipReason | None = None
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.attempt_count < 0:
            raise RuntimeContractError("attempt_count cannot be negative", rule="attempt_count")
        if len(self.artifact_refs) != len(set(self.artifact_refs)):
            raise RuntimeContractError("artifact_refs must be unique", rule="artifact_refs")
        if self.error is not None:
            object.__setattr__(self, "error", deep_freeze(self.error))


@dataclass(frozen=True)
class RunPolicy:
    max_parallel: int
    automated_attempt_timeout_minutes: int
    max_sources_per_research_node: int
    max_retries_per_node: int
    max_global_research_cycles: int
    automated_run_timeout_minutes: int
    host_token_limit: int | None
    host_cost_limit: float | None


@dataclass(frozen=True)
class PermissionSet:
    external_access: str
    workspace_write_paths: tuple[str, ...]
    secrets: str = "forbidden"

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_write_paths", tuple(self.workspace_write_paths))


@dataclass(frozen=True)
class BudgetLimits:
    timeout_minutes: int
    max_sources: int
    token_limit: int | None
    cost_limit: float | None


@dataclass(frozen=True)
class UsageRecord:
    """Cumulative automated resource usage for one Attempt.

    Wall-clock time is deliberately absent: user, Gate, and external waits are
    not automated execution and must never consume the Runtime budget.
    """

    automated_duration_seconds: float = 0.0
    source_count: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    estimated_cost: float | None = 0.0

    def __post_init__(self) -> None:
        values = {
            "automated_duration_seconds": self.automated_duration_seconds,
            "source_count": self.source_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": self.estimated_cost,
        }
        if any(value is not None and value < 0 for value in values.values()):
            raise RuntimeContractError("Usage values cannot be negative", rule="usage")

    def add(self, value: Mapping[str, Any]) -> "UsageRecord":
        """Add one Executor-reported automated segment deterministically."""

        def optional_total(current: int | float | None, incoming: int | float | None) -> int | float | None:
            return None if current is None or incoming is None else current + incoming

        return UsageRecord(
            automated_duration_seconds=self.automated_duration_seconds + value["automated_duration_seconds"],
            source_count=self.source_count + value["source_count"],
            input_tokens=optional_total(self.input_tokens, value["input_tokens"]),
            output_tokens=optional_total(self.output_tokens, value["output_tokens"]),
            estimated_cost=optional_total(self.estimated_cost, value["estimated_cost"]),
        )


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    run_id: str
    address: NodeAddress
    skill_ref: str
    status: AttemptStatus
    mode: AttemptMode
    input_fingerprint: str
    input_artifact_refs: tuple[str, ...]
    profile_ref: str
    research_contract_ref: str | None
    permissions: PermissionSet
    budget: BudgetLimits
    allowed_adapter_types: tuple[AdapterType, ...]
    started_at: str
    finished_at: str | None = None
    verified: bool = False
    interaction_checkpoint_ref: str | None = None
    usage: UsageRecord = field(default_factory=UsageRecord)
    relevant_config: Mapping[str, Any] = field(default_factory=immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "relevant_config", deep_freeze(self.relevant_config))


@dataclass(frozen=True)
class LegacyInputRecord:
    accepted: bool
    reason: str
    rule_id: str | None
    required_revalidation: tuple[str, ...]


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    contract_version: str
    workflow_id: str
    workflow_version: str
    profile_ref: str
    initial_idea: str
    state_version: int
    workflow_status: WorkflowStatus
    run_policy: RunPolicy
    node_states: Mapping[NodeAddress, NodeState]
    attempts: tuple[AttemptRecord, ...] = ()
    fanout_instances: Mapping[NodeAddress, tuple[str, ...]] = field(default_factory=immutable_mapping)
    legacy_inputs: tuple[LegacyInputRecord, ...] = ()
    readiness_status: ReadinessStatus | None = None
    current_gate: str | None = None
    current_interaction: Mapping[str, Any] | None = None
    current_gate_request_ref: str | None = None
    current_gate_modification_ref: str | None = None
    global_research_cycle: int = 0
    research_contract_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_states", immutable_mapping(self.node_states))
        object.__setattr__(
            self,
            "fanout_instances",
            immutable_mapping({address: tuple(keys) for address, keys in self.fanout_instances.items()}),
        )
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "legacy_inputs", tuple(self.legacy_inputs))
        if self.current_interaction is not None:
            object.__setattr__(self, "current_interaction", deep_freeze(self.current_interaction))

    def to_wire_state(self) -> dict[str, Any]:
        nodes: dict[str, Any] = {}
        for address, state in self.node_states.items():
            if not address.is_top_level:
                continue
            item: dict[str, Any] = {
                "status": state.status.value,
                "attempt_count": state.attempt_count,
                "artifact_refs": list(state.artifact_refs),
            }
            optional = {
                "active_attempt_id": state.active_attempt_id,
                "interaction_checkpoint_ref": state.interaction_checkpoint_ref,
                "verification_result": state.verification_result,
                "gate_decision": state.gate_decision,
                "feasibility_result": state.feasibility_result,
                "proof_outcome": state.proof_outcome,
                "skip_reason": state.skip_reason,
                "error": state.error,
            }
            for key, value in optional.items():
                if value is not None:
                    item[key] = deep_thaw(value)
            nodes[address.node_id] = item
        return {
            "schema_version": self.contract_version,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "run_id": self.run_id,
            "state_version": self.state_version,
            "workflow_status": self.workflow_status.value,
            "readiness_status": self.readiness_status.value if self.readiness_status else None,
            "current_gate": self.current_gate,
            "current_interaction": deep_thaw(self.current_interaction),
            "global_research_cycle": self.global_research_cycle,
            "profile_ref": self.profile_ref,
            "research_contract_ref": self.research_contract_ref,
            "nodes": nodes,
        }


@dataclass(frozen=True)
class CreateRunCommand:
    idea: str
    profile_id: str
    contract_version: str | None = None
    legacy_input_refs: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "legacy_input_refs", tuple(deep_freeze(item) for item in self.legacy_input_refs))


@dataclass(frozen=True)
class FanOutExpansion:
    template: NodeAddress
    source_artifact_ref: str
    item_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_keys", tuple(self.item_keys))
        if self.template.instance_key is not None:
            raise RuntimeContractError("Fan-out template cannot have an instance key", rule="fanout_template")
        if not self.item_keys or len(self.item_keys) != len(set(self.item_keys)):
            raise RuntimeContractError("Fan-out item keys must be non-empty and unique", rule="fanout_items")
        if any(not isinstance(item, str) or COMPETITOR_ID_PATTERN.fullmatch(item) is None for item in self.item_keys):
            raise RuntimeContractError("Fan-out item key must be a competitor ID", rule="fanout_item_id")
        if not isinstance(self.source_artifact_ref, str) or not self.source_artifact_ref or any(
            character.isspace() for character in self.source_artifact_ref
        ):
            raise RuntimeContractError("Fan-out source Artifact reference is invalid", rule="fanout_source_artifact")


@dataclass(frozen=True)
class StateTransition:
    address: NodeAddress
    from_status: NodeStatus
    to_status: NodeStatus
    reason: str


@dataclass(frozen=True)
class DeferredNode:
    address: NodeAddress
    reason: str


@dataclass(frozen=True)
class SchedulingDecision:
    transitions: tuple[StateTransition, ...]
    ready_nodes: tuple[NodeAddress, ...]
    selected_nodes: tuple[NodeAddress, ...]
    deferred: tuple[DeferredNode, ...]
    effective_max_parallel: int
    available_slots: int


@dataclass(frozen=True)
class InvocationRequirements:
    attempt_id: str
    address: NodeAddress
    skill_ref: str
    input_artifact_refs: tuple[str, ...]
    profile_ref: str
    research_contract_ref: str | None
    permissions: PermissionSet
    budget: BudgetLimits
    allowed_adapter_types: tuple[AdapterType, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    decision: SchedulingDecision
    attempts_to_start: tuple[AttemptRecord, ...]
    invocations: tuple[InvocationRequirements, ...]
    reuse_candidates: tuple[str, ...]
    next_snapshot: RunSnapshot


@dataclass(frozen=True)
class ValidatedExecutorProposal:
    proposal_type: str
    attempt_id: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", deep_freeze(self.payload))
