"""Single-writer filesystem storage for P0-02-T11/T12.

The repository is deliberately local and append-only.  It has no inter-process
lock: callers must keep one Orchestrator writer per Run as required by the
contract.  Recovery never deletes a non-current version or a crash leftover.
Its diagnostics are only a Current Manifest view, never proof that a version is
eligible for retention or garbage collection.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .domain import (
    AdapterType,
    AttemptMode,
    AttemptRecord,
    AttemptStatus,
    BudgetLimits,
    GateDecision,
    LegacyInputRecord,
    NodeAddress,
    NodeState,
    NodeStatus,
    PermissionSet,
    ProofOutcome,
    ReadinessStatus,
    RunPolicy,
    RunSnapshot,
    SkipReason,
    UsageRecord,
    VerificationResult,
    WorkflowStatus,
    deep_thaw,
)
from .errors import RuntimeContractError


_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]+$")
_ARTIFACT_ID = re.compile(r"^ART-[A-Za-z0-9_-]+$")
_ARTIFACT_REF = re.compile(r"^ART-[A-Za-z0-9_-]+@[1-9][0-9]*$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{item}" for item in range(1, 10)), *(f"LPT{item}" for item in range(1, 10))}
_EVENT_FIELDS = frozenset(
    {
        "event",
        "ts",
        "state_version",
        "run_id",
        "node",
        "attempt",
        "question_id",
        "method",
        "round",
        "target_unknown_id",
        "reason",
        "source_contract_version",
        "ref_type",
        "content_hash",
        "matrix_rule",
        "artifact",
        "decision_id",
        "adapter_type",
        "operation",
    }
)


@dataclass(frozen=True)
class StoredArtifact:
    artifact_ref: str
    artifact_type: str
    content_hash: str
    logical_path: str


@dataclass(frozen=True)
class RecoveryReport:
    run_id: str
    recovered_state_version: int
    repaired_state_file: bool
    non_current_snapshot_files: tuple[str, ...]
    artifact_versions_not_in_current_manifest: tuple[str, ...]
    temporary_files: tuple[str, ...]
    event_log_last_offset: int = 0
    uncommitted_event_offsets: tuple[int, ...] = ()


def _safe_relative(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw or ":" in raw:
        raise RuntimeContractError("Storage path must be a safe POSIX relative path", code="SECURITY_POLICY_VIOLATION", rule="storage_path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeContractError("Storage path escapes the Run root", code="SECURITY_POLICY_VIOLATION", rule="storage_path")
    for part in path.parts:
        if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in _RESERVED:
            raise RuntimeContractError("Storage path has a reserved platform component", code="SECURITY_POLICY_VIOLATION", rule="storage_path")
    return path


def declared_workspace_path_matches(logical_path: str, declarations: tuple[str, ...]) -> bool:
    """Return whether a logical Artifact path matches a declared write path.

    Frozen Skill Contracts may declare either one exact file or a directory
    ending in ``/``.  Directory declarations are intentionally one-way: they
    authorize contained descendants only, never the directory itself or a
    sibling with a shared textual prefix.
    """

    logical = _safe_relative(logical_path).as_posix()
    for raw in declarations:
        if not isinstance(raw, str) or not raw:
            continue
        is_directory = raw.endswith("/")
        declared = _safe_relative(raw[:-1] if is_directory else raw).as_posix()
        if (is_directory and logical.startswith(declared + "/")) or (not is_directory and logical == declared):
            return True
    return False


def _enum(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _address(value: NodeAddress) -> dict[str, Any]:
    return {"graph_path": list(value.graph_path), "node_id": value.node_id, "instance_key": value.instance_key}


def _decode_address(value: Mapping[str, Any]) -> NodeAddress:
    return NodeAddress(tuple(value["graph_path"]), value["node_id"], value.get("instance_key"))


def _node_state(value: NodeState) -> dict[str, Any]:
    return {
        "status": value.status.value,
        "attempt_count": value.attempt_count,
        "active_attempt_id": value.active_attempt_id,
        "interaction_checkpoint_ref": value.interaction_checkpoint_ref,
        "artifact_refs": list(value.artifact_refs),
        "verification_result": _enum(value.verification_result),
        "gate_decision": _enum(value.gate_decision),
        "feasibility_result": _enum(value.feasibility_result),
        "proof_outcome": _enum(value.proof_outcome),
        "skip_reason": _enum(value.skip_reason),
        "error": deep_thaw(value.error),
    }


def _decode_node_state(value: Mapping[str, Any]) -> NodeState:
    from .domain import FeasibilityResult

    return NodeState(
        status=NodeStatus(value["status"]),
        attempt_count=value["attempt_count"],
        active_attempt_id=value.get("active_attempt_id"),
        interaction_checkpoint_ref=value.get("interaction_checkpoint_ref"),
        artifact_refs=tuple(value.get("artifact_refs", ())),
        verification_result=VerificationResult(value["verification_result"]) if value.get("verification_result") else None,
        gate_decision=GateDecision(value["gate_decision"]) if value.get("gate_decision") else None,
        feasibility_result=FeasibilityResult(value["feasibility_result"]) if value.get("feasibility_result") else None,
        proof_outcome=ProofOutcome(value["proof_outcome"]) if value.get("proof_outcome") else None,
        skip_reason=SkipReason(value["skip_reason"]) if value.get("skip_reason") else None,
        error=value.get("error"),
    )


def _attempt(value: AttemptRecord) -> dict[str, Any]:
    return {
        "attempt_id": value.attempt_id,
        "run_id": value.run_id,
        "address": _address(value.address),
        "skill_ref": value.skill_ref,
        "status": value.status.value,
        "mode": value.mode.value,
        "input_fingerprint": value.input_fingerprint,
        "input_artifact_refs": list(value.input_artifact_refs),
        "profile_ref": value.profile_ref,
        "research_contract_ref": value.research_contract_ref,
        "permissions": {
            "external_access": value.permissions.external_access,
            "workspace_write_paths": list(value.permissions.workspace_write_paths),
            "secrets": value.permissions.secrets,
        },
        "budget": {
            "timeout_minutes": value.budget.timeout_minutes,
            "max_sources": value.budget.max_sources,
            "token_limit": value.budget.token_limit,
            "cost_limit": value.budget.cost_limit,
        },
        "allowed_adapter_types": [item.value for item in value.allowed_adapter_types],
        "started_at": value.started_at,
        "finished_at": value.finished_at,
        "verified": value.verified,
        "interaction_checkpoint_ref": value.interaction_checkpoint_ref,
        "usage": {
            "automated_duration_seconds": value.usage.automated_duration_seconds,
            "source_count": value.usage.source_count,
            "input_tokens": value.usage.input_tokens,
            "output_tokens": value.usage.output_tokens,
            "estimated_cost": value.usage.estimated_cost,
        },
        "relevant_config": deep_thaw(value.relevant_config),
    }


def _decode_attempt(value: Mapping[str, Any]) -> AttemptRecord:
    permissions = value["permissions"]
    budget = value["budget"]
    usage = value.get("usage", {})
    return AttemptRecord(
        attempt_id=value["attempt_id"],
        run_id=value["run_id"],
        address=_decode_address(value["address"]),
        skill_ref=value["skill_ref"],
        status=AttemptStatus(value["status"]),
        mode=AttemptMode(value["mode"]),
        input_fingerprint=value["input_fingerprint"],
        input_artifact_refs=tuple(value["input_artifact_refs"]),
        profile_ref=value["profile_ref"],
        research_contract_ref=value.get("research_contract_ref"),
        permissions=PermissionSet(permissions["external_access"], tuple(permissions["workspace_write_paths"]), permissions.get("secrets", "forbidden")),
        budget=BudgetLimits(budget["timeout_minutes"], budget["max_sources"], budget.get("token_limit"), budget.get("cost_limit")),
        allowed_adapter_types=tuple(AdapterType(item) for item in value["allowed_adapter_types"]),
        started_at=value["started_at"],
        finished_at=value.get("finished_at"),
        verified=bool(value.get("verified", False)),
        interaction_checkpoint_ref=value.get("interaction_checkpoint_ref"),
        usage=UsageRecord(
            usage.get("automated_duration_seconds", 0.0),
            usage.get("source_count", 0),
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("estimated_cost", 0.0),
        ),
        relevant_config=value.get("relevant_config", {}),
    )


def serialize_snapshot(snapshot: RunSnapshot) -> dict[str, Any]:
    """Return the private, versioned recovery representation for a Snapshot."""

    return {
        "format": "skillgraph_runtime_snapshot",
        "format_version": 1,
        "snapshot": {
            "run_id": snapshot.run_id,
            "contract_version": snapshot.contract_version,
            "workflow_id": snapshot.workflow_id,
            "workflow_version": snapshot.workflow_version,
            "profile_ref": snapshot.profile_ref,
            "initial_idea": snapshot.initial_idea,
            "state_version": snapshot.state_version,
            "workflow_status": snapshot.workflow_status.value,
            "run_policy": {
                "max_parallel": snapshot.run_policy.max_parallel,
                "automated_attempt_timeout_minutes": snapshot.run_policy.automated_attempt_timeout_minutes,
                "max_sources_per_research_node": snapshot.run_policy.max_sources_per_research_node,
                "max_retries_per_node": snapshot.run_policy.max_retries_per_node,
                "max_global_research_cycles": snapshot.run_policy.max_global_research_cycles,
                "automated_run_timeout_minutes": snapshot.run_policy.automated_run_timeout_minutes,
                "host_token_limit": snapshot.run_policy.host_token_limit,
                "host_cost_limit": snapshot.run_policy.host_cost_limit,
            },
            "node_states": [{"address": _address(key), "state": _node_state(value)} for key, value in snapshot.node_states.items()],
            "attempts": [_attempt(value) for value in snapshot.attempts],
            "fanout_instances": [
                {"address": _address(key), "item_keys": list(value)} for key, value in snapshot.fanout_instances.items()
            ],
            "legacy_inputs": [
                {
                    "accepted": value.accepted,
                    "reason": value.reason,
                    "rule_id": value.rule_id,
                    "required_revalidation": list(value.required_revalidation),
                }
                for value in snapshot.legacy_inputs
            ],
            "readiness_status": _enum(snapshot.readiness_status),
            "current_gate": snapshot.current_gate,
            "current_interaction": deep_thaw(snapshot.current_interaction),
            "current_gate_request_ref": snapshot.current_gate_request_ref,
            "current_gate_modification_ref": snapshot.current_gate_modification_ref,
            "global_research_cycle": snapshot.global_research_cycle,
            "research_contract_ref": snapshot.research_contract_ref,
        },
    }


def deserialize_snapshot(value: Mapping[str, Any]) -> RunSnapshot:
    try:
        if value.get("format") != "skillgraph_runtime_snapshot" or value.get("format_version") != 1:
            raise ValueError("unsupported private snapshot format")
        raw = value["snapshot"]
        policy = raw["run_policy"]
        return RunSnapshot(
            run_id=raw["run_id"],
            contract_version=raw["contract_version"],
            workflow_id=raw["workflow_id"],
            workflow_version=raw["workflow_version"],
            profile_ref=raw["profile_ref"],
            initial_idea=raw["initial_idea"],
            state_version=raw["state_version"],
            workflow_status=WorkflowStatus(raw["workflow_status"]),
            run_policy=RunPolicy(
                policy["max_parallel"],
                policy["automated_attempt_timeout_minutes"],
                policy["max_sources_per_research_node"],
                policy["max_retries_per_node"],
                policy["max_global_research_cycles"],
                policy["automated_run_timeout_minutes"],
                policy.get("host_token_limit"),
                policy.get("host_cost_limit"),
            ),
            node_states={_decode_address(item["address"]): _decode_node_state(item["state"]) for item in raw["node_states"]},
            attempts=tuple(_decode_attempt(item) for item in raw.get("attempts", ())),
            fanout_instances={_decode_address(item["address"]): tuple(item["item_keys"]) for item in raw.get("fanout_instances", ())},
            legacy_inputs=tuple(
                LegacyInputRecord(item["accepted"], item["reason"], item.get("rule_id"), tuple(item.get("required_revalidation", ())))
                for item in raw.get("legacy_inputs", ())
            ),
            readiness_status=ReadinessStatus(raw["readiness_status"]) if raw.get("readiness_status") else None,
            current_gate=raw.get("current_gate"),
            current_interaction=raw.get("current_interaction"),
            current_gate_request_ref=raw.get("current_gate_request_ref"),
            current_gate_modification_ref=raw.get("current_gate_modification_ref"),
            global_research_cycle=raw.get("global_research_cycle", 0),
            research_contract_ref=raw.get("research_contract_ref"),
        )
    except (KeyError, TypeError, ValueError, RuntimeContractError) as exc:
        raise RuntimeContractError("Persisted Runtime Snapshot is invalid", code="SCHEMA_INVALID", rule="snapshot_decode") from exc


class RunStorage:
    """Filesystem layout and atomic writes for exactly one Run."""

    def __init__(self, storage_root: Path, run_id: str) -> None:
        if _RUN_ID.fullmatch(run_id) is None:
            raise RuntimeContractError("run_id is malformed for storage", rule="storage_run_id")
        self.storage_root = Path(storage_root).resolve()
        self.run_id = run_id
        self.run_root = self.storage_root / "runs" / run_id

    def _path(self, relative: str) -> Path:
        safe = _safe_relative(relative)
        candidate = self.run_root.joinpath(*safe.parts)
        self.run_root.mkdir(parents=True, exist_ok=True)
        root = self.run_root.resolve()
        parent = candidate.parent
        while parent != root and parent != parent.parent:
            if parent.exists() and parent.is_symlink():
                raise RuntimeContractError("Storage path crosses a symbolic link", code="SECURITY_POLICY_VIOLATION", rule="storage_symlink")
            parent = parent.parent
        resolved_parent = candidate.parent.resolve()
        try:
            resolved_parent.relative_to(root)
        except ValueError as exc:
            raise RuntimeContractError("Storage path escapes the Run root", code="SECURITY_POLICY_VIOLATION", rule="storage_path") from exc
        return candidate

    def _read_json(self, relative: str) -> Any:
        path = self._path(relative)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeContractError("Persisted Runtime document is unreadable", code="SCHEMA_INVALID", rule="storage_read", details={"path": relative}) from exc

    def _atomic_json(self, relative: str, value: Any, *, fault: str | None = None) -> None:
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if fault == "before_replace":
                raise RuntimeError("injected crash before atomic replacement")
            os.replace(temporary, path)
        except Exception:
            # The incomplete file is intentionally retained for RecoveryReport.
            raise

    def _write_immutable_json(self, relative: str, value: Any) -> None:
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise RuntimeContractError("Append-only Runtime record already exists", rule="storage_append_only", details={"path": relative})
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _append_jsonl(self, relative: str, value: Mapping[str, Any]) -> None:
        """Append one durable JSON object to a Runtime-owned audit ledger."""

        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _read_jsonl(self, relative: str) -> tuple[Mapping[str, Any], ...]:
        path = self._path(relative)
        if not path.is_file():
            return ()
        values: list[Mapping[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, Mapping):
                        raise ValueError("entry is not an object")
                    values.append(value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeContractError(
                "Runtime audit ledger is unreadable",
                code="SCHEMA_INVALID",
                rule="audit_log_read",
                details={"path": relative},
            ) from exc
        return tuple(values)

    def event_records(self) -> tuple[Mapping[str, Any], ...]:
        records = self._read_jsonl("runtime/event-log.jsonl")
        for expected, item in enumerate(records, start=1):
            if item.get("offset") != expected or not isinstance(item.get("event"), str):
                raise RuntimeContractError(
                    "Event Log offsets must be contiguous and deterministic",
                    code="SCHEMA_INVALID",
                    rule="event_log_order",
                    details={"expected_offset": expected},
                )
        return records

    def _event_prefix_records(self) -> tuple[tuple[Mapping[str, Any], ...], bool]:
        """Read the complete Event prefix without repairing an incomplete tail.

        A crash may leave a final partial JSON line after a durable committed
        prefix.  Recovery may use that prefix, but normal mutations keep using
        :meth:`event_records` and therefore remain fail-closed until an
        operator investigates the preserved tail.
        """

        path = self._path("runtime/event-log.jsonl")
        if not path.is_file():
            return (), False
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        nonempty = [index for index, line in enumerate(raw_lines) if line.strip()]
        records: list[Mapping[str, Any]] = []
        for index in nonempty:
            try:
                value = json.loads(raw_lines[index])
            except json.JSONDecodeError as exc:
                if index != nonempty[-1]:
                    raise RuntimeContractError(
                        "Runtime Event Log has a malformed non-tail entry",
                        code="SCHEMA_INVALID",
                        rule="event_log_order",
                    ) from exc
                return tuple(records), True
            if not isinstance(value, Mapping):
                raise RuntimeContractError("Runtime Event Log entry is not an object", code="SCHEMA_INVALID", rule="event_log_order")
            expected = len(records) + 1
            if value.get("offset") != expected or not isinstance(value.get("event"), str):
                raise RuntimeContractError(
                    "Event Log offsets must be contiguous and deterministic",
                    code="SCHEMA_INVALID",
                    rule="event_log_order",
                    details={"expected_offset": expected},
                )
            records.append(value)
        return tuple(records), False

    def append_event(self, event: Mapping[str, Any]) -> int:
        """Append a whitelisted Runtime event and return its monotonic offset."""

        if not isinstance(event, Mapping) or not isinstance(event.get("event"), str) or not event["event"]:
            raise RuntimeContractError("Runtime Event requires a non-empty event name", rule="event_shape")
        if not isinstance(event.get("ts"), str) or not event["ts"]:
            raise RuntimeContractError("Runtime Event requires a timestamp", rule="event_shape")
        if set(event) - _EVENT_FIELDS:
            raise RuntimeContractError("Runtime Event includes a non-whitelisted field", code="SECURITY_POLICY_VIOLATION", rule="event_field")
        for field, value in event.items():
            if not isinstance(value, (str, int, bool)) and value is not None:
                raise RuntimeContractError("Runtime Event values must be scalar audit metadata", code="SECURITY_POLICY_VIOLATION", rule="event_field")
            if isinstance(value, str) and len(value) > 256:
                raise RuntimeContractError("Runtime Event value is too large for audit metadata", code="SECURITY_POLICY_VIOLATION", rule="event_field")
        offset = len(self.event_records()) + 1
        record = {"offset": offset, **deep_thaw(event)}
        self._append_jsonl("runtime/event-log.jsonl", record)
        return offset

    def decision_records(self) -> tuple[Mapping[str, Any], ...]:
        return self._read_jsonl("runtime/decision-log.jsonl")

    def append_decision(self, decision: Mapping[str, Any], *, event_offset: int) -> None:
        if not isinstance(decision, Mapping) or not isinstance(decision.get("decision"), Mapping):
            raise RuntimeContractError("Decision Log entry must contain a Decision Contract", rule="decision_shape")
        if not isinstance(event_offset, int) or event_offset < 1:
            raise RuntimeContractError("Decision Log entry must reference an Event offset", rule="decision_event_offset")
        if event_offset > len(self.event_records()):
            raise RuntimeContractError("Decision Log references an Event that is not durable", rule="decision_event_offset")
        self._append_jsonl("runtime/decision-log.jsonl", {"event_offset": event_offset, "decision": deep_thaw(decision["decision"])})

    def idempotency_record(self, key_hash: str) -> Mapping[str, Any] | None:
        if not isinstance(key_hash, str) or not key_hash.startswith("sha256:"):
            raise RuntimeContractError("Idempotency key hash is malformed", rule="idempotency_key")
        matches = [item for item in self._read_jsonl("runtime/idempotency-log.jsonl") if item.get("key_hash") == key_hash]
        if len(matches) > 1:
            raise RuntimeContractError("Idempotency key has multiple Runtime records", code="SCHEMA_INVALID", rule="idempotency_record")
        return matches[0] if matches else None

    def append_idempotency_record(
        self,
        *,
        key_hash: str,
        request_hash: str,
        operation: str,
        response: Mapping[str, Any],
    ) -> None:
        if self.idempotency_record(key_hash) is not None:
            raise RuntimeContractError("Idempotency key was already recorded", code="IDEMPOTENCY_CONFLICT", rule="idempotency_record")
        self._append_jsonl(
            "runtime/idempotency-log.jsonl",
            {
                "key_hash": key_hash,
                "request_hash": request_hash,
                "operation": operation,
                "response": deep_thaw(response),
            },
        )

    def read_artifact(self, artifact_ref: str) -> Mapping[str, Any]:
        if _ARTIFACT_REF.fullmatch(artifact_ref) is None:
            raise RuntimeContractError("Artifact reference is malformed", rule="artifact_ref")
        value = self._read_json(f"artifacts/by-ref/{artifact_ref}.json")
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Stored Artifact is not an object", code="SCHEMA_INVALID", rule="artifact_read")
        return value

    def read_source_index(self, state_version: int) -> tuple[Mapping[str, Any], ...]:
        """Load the newest committed-or-earlier private Source Index snapshot.

        Source Index snapshots are Runtime sidecar records rather than business
        Artifacts because the frozen Bundle has no Source Index output contract.
        A future-version snapshot left by an interrupted commit is ignored by
        callers reading an older Current Manifest.
        """

        if not isinstance(state_version, int) or state_version < 0:
            raise RuntimeContractError("Source Index state version is invalid", rule="source_index_state_version")
        directory = self._path("runtime/source-index")
        candidates: list[int] = []
        if directory.is_dir():
            for path in directory.glob("*.json"):
                try:
                    version = int(path.stem)
                except ValueError:
                    continue
                if 0 <= version <= state_version:
                    candidates.append(version)
        if not candidates:
            return ()
        document = self._read_json(f"runtime/source-index/{max(candidates)}.json")
        if not isinstance(document, Mapping) or not isinstance(document.get("sources"), list):
            raise RuntimeContractError("Persisted Source Index is invalid", code="SCHEMA_INVALID", rule="source_index_read")
        sources = document["sources"]
        if any(not isinstance(item, Mapping) for item in sources):
            raise RuntimeContractError("Persisted Source Index contains an invalid Source", code="SCHEMA_INVALID", rule="source_index_read")
        return tuple(sources)

    def write_source_index(
        self,
        *,
        state_version: int,
        schema_version: str,
        sources: tuple[Mapping[str, Any], ...],
    ) -> None:
        """Write one immutable Source Index snapshot for a pending state commit."""

        if not isinstance(state_version, int) or state_version < 1:
            raise RuntimeContractError("Source Index state version is invalid", rule="source_index_state_version")
        if not isinstance(schema_version, str) or not schema_version:
            raise RuntimeContractError("Source Index schema version is invalid", rule="source_index_schema_version")
        ordered = tuple(sorted((deep_thaw(item) for item in sources), key=lambda item: str(item.get("id", ""))))
        document = {"schema_version": schema_version, "state_version": state_version, "sources": list(ordered)}
        reference = f"runtime/source-index/{state_version}.json"
        path = self._path(reference)
        if path.exists():
            existing = self._read_json(reference)
            if existing != document:
                raise RuntimeContractError("Source Index snapshot conflicts with an existing state version", code="STATE_VERSION_CONFLICT", rule="source_index_conflict")
            return
        self._write_immutable_json(reference, document)

    def read_research_provenance(self, state_version: int) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
        """Load the newest committed-or-earlier private Evidence/Claim snapshot.

        Provenance is intentionally a Runtime sidecar while the frozen Bundle
        has no producer-owned Evidence/Claim repository contract.  As with the
        Source Index, a later file created before a failed manifest commit is
        invisible to an older effective Run state.
        """

        if not isinstance(state_version, int) or state_version < 0:
            raise RuntimeContractError("Research Provenance state version is invalid", rule="provenance_state_version")
        directory = self._path("runtime/research-provenance")
        candidates: list[int] = []
        if directory.is_dir():
            for path in directory.glob("*.json"):
                try:
                    version = int(path.stem)
                except ValueError:
                    continue
                if 0 <= version <= state_version:
                    candidates.append(version)
        if not candidates:
            return (), ()
        document = self._read_json(f"runtime/research-provenance/{max(candidates)}.json")
        if not isinstance(document, Mapping) or not isinstance(document.get("evidence"), list) or not isinstance(document.get("claims"), list):
            raise RuntimeContractError("Persisted Research Provenance is invalid", code="SCHEMA_INVALID", rule="provenance_read")
        evidence, claims = document["evidence"], document["claims"]
        if any(not isinstance(item, Mapping) for item in evidence) or any(not isinstance(item, Mapping) for item in claims):
            raise RuntimeContractError("Persisted Research Provenance contains an invalid record", code="SCHEMA_INVALID", rule="provenance_read")
        return tuple(evidence), tuple(claims)

    def write_research_provenance(
        self,
        *,
        state_version: int,
        schema_version: str,
        evidence: tuple[Mapping[str, Any], ...],
        claims: tuple[Mapping[str, Any], ...],
    ) -> None:
        """Write one immutable Evidence/Claim snapshot for a pending commit."""

        if not isinstance(state_version, int) or state_version < 1:
            raise RuntimeContractError("Research Provenance state version is invalid", rule="provenance_state_version")
        if not isinstance(schema_version, str) or not schema_version:
            raise RuntimeContractError("Research Provenance schema version is invalid", rule="provenance_schema_version")
        ordered_evidence = tuple(sorted((deep_thaw(item) for item in evidence), key=lambda item: str(item.get("id", ""))))
        ordered_claims = tuple(sorted((deep_thaw(item) for item in claims), key=lambda item: str(item.get("id", ""))))
        document = {
            "schema_version": schema_version,
            "state_version": state_version,
            "evidence": list(ordered_evidence),
            "claims": list(ordered_claims),
        }
        reference = f"runtime/research-provenance/{state_version}.json"
        path = self._path(reference)
        if path.exists():
            existing = self._read_json(reference)
            if existing != document:
                raise RuntimeContractError("Research Provenance snapshot conflicts with an existing state version", code="STATE_VERSION_CONFLICT", rule="provenance_conflict")
            return
        self._write_immutable_json(reference, document)

    def write_checkpoint(self, reference: str, checkpoint: Mapping[str, Any]) -> None:
        if not reference.startswith("runtime/attempts/") or "/checkpoints/" not in reference:
            raise RuntimeContractError("Interaction Checkpoint reference is outside the Runtime checkpoint tree", rule="checkpoint_ref")
        self._write_immutable_json(reference, deep_thaw(checkpoint))

    def read_checkpoint(self, reference: str) -> Mapping[str, Any]:
        value = self._read_json(reference)
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Interaction Checkpoint must be a mapping", code="SCHEMA_INVALID", rule="checkpoint_read")
        return value

    def write_gate_request(self, node_id: str, state_version: int, gate: Mapping[str, Any]) -> str:
        reference = f"runtime/gates/{node_id}/requests/{state_version}.json"
        self._write_immutable_json(reference, deep_thaw(gate))
        return reference

    def read_gate_request(self, reference: str) -> Mapping[str, Any]:
        value = self._read_json(reference)
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Gate Request must be a mapping", code="SCHEMA_INVALID", rule="gate_read")
        return value

    def write_gate_modification(self, node_id: str, state_version: int, modification: Mapping[str, Any]) -> str:
        reference = f"runtime/gates/{node_id}/modifications/{state_version}.json"
        self._write_immutable_json(reference, deep_thaw(modification))
        return reference

    def _manifest(self) -> Mapping[str, Any] | None:
        path = self._path("runtime/current-manifest.json")
        return None if not path.is_file() else self._read_json("runtime/current-manifest.json")

    def creation_identity(self) -> Mapping[str, Any] | None:
        path = self._path("runtime/creation-identity.json")
        return None if not path.is_file() else self._read_json("runtime/creation-identity.json")

    def write_creation_identity(self, *, key_hash: str, request_hash: str) -> None:
        if not key_hash.startswith("sha256:") or not request_hash.startswith("sha256:"):
            raise RuntimeContractError("Creation identity hashes are malformed", rule="create_idempotency_log")
        existing = self.creation_identity()
        expected = {"key_hash": key_hash, "request_hash": request_hash}
        if existing is not None:
            if existing != expected:
                raise RuntimeContractError("Run location is already bound to a different create request", code="IDEMPOTENCY_CONFLICT", rule="create_idempotency_identity")
            return
        self._write_immutable_json("runtime/creation-identity.json", expected)

    def commit_snapshot(
        self,
        snapshot: RunSnapshot,
        *,
        updated_at: str,
        manifest_updates: Mapping[str, Mapping[str, str]] | None = None,
        manifest_remove_types: tuple[str, ...] = (),
        last_event_offset: int | None = None,
        fault: str | None = None,
    ) -> None:
        if snapshot.run_id != self.run_id:
            raise RuntimeContractError("Snapshot Run does not match storage Run", rule="storage_run_identity")
        snapshot_ref = f"runtime/snapshots/{snapshot.state_version}.json"
        path = self._path(snapshot_ref)
        if not path.exists():
            self._write_immutable_json(snapshot_ref, serialize_snapshot(snapshot))
        current = self._manifest()
        artifacts = dict(current.get("current_artifacts", {}) if current else {})
        for artifact_type in manifest_remove_types:
            artifacts.pop(artifact_type, None)
        for artifact_type, entry in (manifest_updates or {}).items():
            if artifact_type in {"interaction_checkpoint", "legacy_input_ref"}:
                raise RuntimeContractError("Runtime-only values cannot enter Current Manifest", rule="manifest_runtime_value")
            artifacts[artifact_type] = dict(entry)
        manifest = {
            "schema_version": snapshot.contract_version,
            "run_id": snapshot.run_id,
            "state_version": snapshot.state_version,
            "updated_at": updated_at,
            "last_event_offset": last_event_offset if last_event_offset is not None else int(current.get("last_event_offset", 0) if current else 0),
            "current_artifacts": artifacts,
        }
        self._atomic_json(
            "runtime/state.json",
            snapshot.to_wire_state(),
            fault="before_replace" if fault == "state_before_replace" else None,
        )
        self._atomic_json(
            "runtime/current-manifest.json",
            manifest,
            fault="before_replace" if fault == "manifest_before_replace" else None,
        )

    def load_snapshot(self) -> RunSnapshot:
        manifest = self._manifest()
        if not isinstance(manifest, Mapping) or manifest.get("run_id") != self.run_id or not isinstance(manifest.get("state_version"), int):
            raise RuntimeContractError("Current Manifest is missing or invalid", code="SCHEMA_INVALID", rule="manifest_read")
        snapshot = deserialize_snapshot(self._read_json(f"runtime/snapshots/{manifest['state_version']}.json"))
        if snapshot.run_id != self.run_id or snapshot.state_version != manifest["state_version"]:
            raise RuntimeContractError("Current Manifest does not point to a matching Snapshot", code="SCHEMA_INVALID", rule="manifest_snapshot")
        return snapshot

    def recover(self) -> RecoveryReport:
        snapshot = self.load_snapshot()
        repaired = False
        state_path = self._path("runtime/state.json")
        try:
            actual = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None
        except (OSError, json.JSONDecodeError):
            actual = None
        if actual != snapshot.to_wire_state():
            self._atomic_json("runtime/state.json", snapshot.to_wire_state())
            repaired = True
        snapshots = self._path("runtime/snapshots")
        non_current_snapshot_files = tuple(
            sorted(path.name for path in snapshots.glob("*.json") if path.stem != str(snapshot.state_version))
        )
        manifest = self._manifest() or {}
        current_refs = {
            entry.get("artifact_ref")
            for entry in manifest.get("current_artifacts", {}).values()
            if isinstance(entry, Mapping)
        }
        artifact_dir = self._path("artifacts/by-ref")
        artifact_versions_not_in_current_manifest = tuple(
            sorted(path.stem for path in artifact_dir.glob("*.json") if path.stem not in current_refs)
        )
        temporary_files = tuple(sorted(path.relative_to(self.run_root).as_posix() for path in self.run_root.rglob("*.tmp")))
        records, _has_incomplete_tail = self._event_prefix_records()
        last_event_offset = int(manifest.get("last_event_offset", 0))
        if last_event_offset < 0 or last_event_offset > len(records):
            raise RuntimeContractError("Current Manifest references an invalid Event offset", code="SCHEMA_INVALID", rule="manifest_event_offset")
        return RecoveryReport(
            self.run_id,
            snapshot.state_version,
            repaired,
            non_current_snapshot_files,
            artifact_versions_not_in_current_manifest,
            temporary_files,
            last_event_offset,
            tuple(int(item["offset"]) for item in records[last_event_offset:]),
        )

    def write_artifact(
        self,
        snapshot: RunSnapshot,
        attempt_id: str,
        logical_path: str,
        document: Mapping[str, Any],
    ) -> StoredArtifact:
        if not isinstance(document, Mapping) or not isinstance(document.get("artifact"), Mapping):
            raise RuntimeContractError("Artifact Repository requires an Artifact Metadata Header", code="SCHEMA_INVALID", rule="artifact_header")
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Artifact producer Attempt does not exist", rule="artifact_attempt")
        logical = _safe_relative(logical_path).as_posix()
        if not declared_workspace_path_matches(logical, attempt.permissions.workspace_write_paths):
            raise RuntimeContractError("Artifact logical path exceeds the producer Skill declaration", code="SECURITY_POLICY_VIOLATION", rule="artifact_path")
        if attempt.skill_ref.rsplit("@", 1)[0] == "competitor-deep-dive":
            instance_key = attempt.address.instance_key
            expected = f"artifacts/02-research/competitors/deep-dives/{instance_key}.yaml" if instance_key else None
            if logical != expected:
                raise RuntimeContractError("Deep Dive Artifact path must match its fan-out competitor ID", code="SECURITY_POLICY_VIOLATION", rule="deep_dive_artifact_path")
        header = document["artifact"]
        artifact_id = header.get("id")
        version = header.get("version")
        if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None or not isinstance(version, int) or version < 1:
            raise RuntimeContractError("Artifact identity is invalid", code="SCHEMA_INVALID", rule="artifact_identity")
        artifact_ref = f"{artifact_id}@{version}"
        produced_by = header.get("produced_by", {})
        if produced_by.get("attempt") != attempt_id or produced_by.get("skill") != attempt.skill_ref.rsplit("@", 1)[0]:
            raise RuntimeContractError("Artifact producer does not match the Runtime Attempt", rule="artifact_producer")
        if header.get("schema_version") != snapshot.contract_version:
            raise RuntimeContractError("Artifact Contract Version does not match the Run", rule="artifact_version")
        canonical = deep_thaw(document)
        hash_payload = json.loads(json.dumps(canonical, ensure_ascii=False))
        hash_payload["artifact"].pop("content_hash", None)
        digest = "sha256:" + hashlib.sha256(
            json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if header.get("content_hash") != digest:
            raise RuntimeContractError("Artifact content_hash does not match canonical Artifact content", code="SCHEMA_INVALID", rule="artifact_hash")
        self._write_immutable_json(f"artifacts/by-ref/{artifact_ref}.json", canonical)
        return StoredArtifact(artifact_ref, header.get("type", ""), digest, logical)
