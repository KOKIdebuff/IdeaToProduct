"""Public Runtime Kernel orchestration boundary."""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from jsonschema import Draft202012Validator, FormatChecker

from .bundles import evaluate_legacy_input_ref
from .domain import (
    AttemptStatus,
    CreateRunCommand,
    ExecutionPlan,
    FanOutExpansion,
    GateDecision,
    LegacyInputRecord,
    NodeAddress,
    NodeKind,
    NodeStatus,
    NodeState,
    RunSnapshot,
    WorkflowStatus,
    TerminalEvent,
    ValidatedExecutorProposal,
    deep_freeze,
    deep_thaw,
)
from .errors import RuntimeContractError
from .graph import CompiledBundle, compile_bundle
from .executor import validate_executor_request as validate_request_proposal
from .executor import validate_executor_result as validate_result_proposal
from .scheduler import schedule_snapshot
from .runtime_state import (
    ExternalSubmission,
    ResultApplication,
    apply_executor_result as apply_executor_result_state,
    open_gate as open_gate_state,
    resume_interaction as resume_interaction_state,
    submit_external_proof as submit_external_proof_state,
    submit_gate_decision as submit_gate_decision_state,
)
from .storage import RecoveryReport, RunStorage, StoredArtifact, declared_workspace_path_matches
from .invalidation import InvalidationResult, invalidate_downstream, resume_invalidated
from .transitions import transition_node


def _canonical_source_url(value: Any) -> str | None:
    """Normalize a Source URL without fetching or otherwise resolving it."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeContractError("Source canonical_url must be a non-empty URI or null", code="SCHEMA_INVALID", rule="source_canonical_url")
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeContractError("Source canonical_url must be a credential-free HTTP(S) URL", code="INPUT_INVALID", rule="source_canonical_url")
    hostname = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as error:
        raise RuntimeContractError(
            "Source canonical_url has an invalid port",
            code="SCHEMA_INVALID",
            rule="source_canonical_url",
        ) from error
    if port is not None and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        hostname = f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), hostname, path, parsed.query, ""))


def _source_identity(source: Mapping[str, Any]) -> tuple[Any, ...]:
    canonical_url = source.get("canonical_url")
    if isinstance(canonical_url, str):
        return ("url", canonical_url)
    return ("fallback", source.get("publisher"), source.get("title"), source.get("published_at"), source.get("content_hash"))


def _source_stable_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    value = deep_thaw(source)
    for field in ("id", "accessed_at", "freshness_status"):
        value.pop(field, None)
    return value


class IdFactory(Protocol):
    def new_run_id(self) -> str: ...

    def new_attempt_id(self) -> str: ...


class Clock(Protocol):
    def now(self) -> str: ...


class UuidIdFactory:
    def new_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex}"

    def new_attempt_id(self) -> str:
        return f"ATT-{uuid.uuid4().hex.upper()}"


class SystemClock:
    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimeKernel:
    """Single in-memory Runtime facade for one repository Contract Registry."""

    def __init__(
        self,
        repository_root: Path,
        *,
        host_max_parallel: int | None = None,
        host_token_limit: int | None = None,
        host_cost_limit: float | None = None,
        id_factory: IdFactory | None = None,
        clock: Clock | None = None,
        storage_root: Path | None = None,
    ) -> None:
        root = Path(repository_root).resolve()
        if not (root / "contracts" / "registry.yaml").is_file():
            raise RuntimeContractError("repository_root has no Contract Registry", rule="repository_root")
        if host_max_parallel is not None and host_max_parallel < 1:
            raise RuntimeContractError("host_max_parallel must be positive", rule="host_max_parallel")
        if host_token_limit is not None and host_token_limit < 1:
            raise RuntimeContractError("host_token_limit must be positive", rule="host_token_limit")
        if host_cost_limit is not None and host_cost_limit < 0:
            raise RuntimeContractError("host_cost_limit cannot be negative", rule="host_cost_limit")
        self.repository_root = root
        self.host_max_parallel = host_max_parallel
        self.host_token_limit = host_token_limit
        self.host_cost_limit = host_cost_limit
        self.id_factory = id_factory or UuidIdFactory()
        self.clock = clock or SystemClock()
        self.storage_root = Path(storage_root).resolve() if storage_root is not None else None
        self._bundle_cache: dict[tuple[str, str], CompiledBundle] = {}

    def _storage_for(self, run_id: str) -> RunStorage:
        if self.storage_root is None:
            raise RuntimeContractError(
                "This RuntimeKernel has no storage_root; use the pure in-memory API or configure explicit storage",
                rule="storage_root_required",
            )
        return RunStorage(self.storage_root, run_id)

    @staticmethod
    def _validate_schema(document: Mapping[str, Any], schema_name: str, bundle: CompiledBundle, *, rule: str) -> None:
        schema = bundle.schemas[schema_name]
        errors = sorted(
            Draft202012Validator(schema, registry=bundle.schema_registry, format_checker=FormatChecker()).iter_errors(document),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.validator or ""),
        )
        if errors:
            first = errors[0]
            raise RuntimeContractError(
                f"Runtime document is invalid: {first.message}",
                code="SCHEMA_INVALID",
                rule=rule,
                details={"path": tuple(first.absolute_path), "validator": first.validator},
            )

    def _validate_wire_state(self, snapshot: RunSnapshot, bundle: CompiledBundle) -> None:
        self._validate_schema(snapshot.to_wire_state(), "workflow-state.schema.json", bundle, rule="runtime_state_schema")

    @staticmethod
    def _validate_schema_ref(document: Mapping[str, Any], schema_ref: str, bundle: CompiledBundle, *, rule: str) -> None:
        """Validate against the exact local schema target declared by a Skill."""

        if not isinstance(schema_ref, str) or not schema_ref.startswith("schemas/"):
            raise RuntimeContractError("Schema reference must target the selected local Bundle", rule="artifact_output_contract")
        schema_path, separator, fragment = schema_ref.partition("#")
        schema_name = schema_path.removeprefix("schemas/")
        try:
            root = bundle.schemas[schema_name]
        except KeyError as exc:
            raise RuntimeContractError("Skill Output Contract references an unavailable Schema", rule="artifact_output_contract") from exc
        schema: Mapping[str, Any] = root
        if separator:
            if not fragment.startswith("/") or not isinstance(root.get("$id"), str):
                raise RuntimeContractError("Skill Output Contract has an invalid Schema fragment", rule="artifact_output_contract")
            schema = {"$ref": f"{root['$id']}#{fragment}"}
        errors = sorted(
            Draft202012Validator(schema, registry=bundle.schema_registry, format_checker=FormatChecker()).iter_errors(document),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.validator or ""),
        )
        if errors:
            first = errors[0]
            raise RuntimeContractError(
                f"Runtime document is invalid: {first.message}",
                code="SCHEMA_INVALID",
                rule=rule,
                details={"path": tuple(first.absolute_path), "validator": first.validator},
            )

    def _source_index_update(
        self,
        snapshot: RunSnapshot,
        source_records: Sequence[Mapping[str, Any]],
    ) -> tuple[tuple[Mapping[str, Any], ...], Mapping[str, str]]:
        """Merge Source records deterministically and return provider-ID aliases.

        The Source Index is a private Runtime sidecar.  It deliberately accepts
        only schema-valid metadata, canonicalizes HTTP(S) identity locally, and
        never performs a request while deduplicating records.
        """

        storage = self._storage_for(snapshot.run_id)
        existing: list[dict[str, Any]] = []
        for current in storage.read_source_index(snapshot.state_version):
            document = {"source": current}
            self._validate_schema(document, "source.schema.json", self.compiled_bundle_for(snapshot), rule="source_index_read")
            normalized = deep_thaw(current)
            normalized["canonical_url"] = _canonical_source_url(normalized.get("canonical_url"))
            existing.append(normalized)

        supplied: list[dict[str, Any]] = []
        for raw in source_records:
            if not isinstance(raw, Mapping):
                raise RuntimeContractError("Provider Source records must be objects", code="SCHEMA_INVALID", rule="source_index_source")
            source = raw.get("source") if set(raw) == {"source"} else raw
            if not isinstance(source, Mapping):
                raise RuntimeContractError("Provider Source record is malformed", code="SCHEMA_INVALID", rule="source_index_source")
            normalized = deep_thaw(source)
            normalized["canonical_url"] = _canonical_source_url(normalized.get("canonical_url"))
            self._validate_schema({"source": normalized}, "source.schema.json", self.compiled_bundle_for(snapshot), rule="source_index_source")
            if not isinstance(normalized.get("id"), str):
                raise RuntimeContractError("Provider Source has no identity", code="SCHEMA_INVALID", rule="source_index_source")
            supplied.append(normalized)

        groups: dict[tuple[Any, ...], list[tuple[dict[str, Any], bool]]] = {}
        for item in existing:
            groups.setdefault(_source_identity(item), []).append((item, True))
        for item in supplied:
            groups.setdefault(_source_identity(item), []).append((item, False))

        merged: dict[str, dict[str, Any]] = {}
        aliases: dict[str, str] = {}
        for identity, records in groups.items():
            baseline = _source_stable_fields(records[0][0])
            if any(_source_stable_fields(item) != baseline for item, _persisted in records[1:]):
                raise RuntimeContractError(
                    "Sources with the same canonical identity have conflicting immutable metadata",
                    code="INPUT_INVALID",
                    rule="source_index_dedup_conflict",
                    details={"identity": identity},
                )
            persisted_ids = sorted(str(item["id"]) for item, persisted in records if persisted)
            canonical_id = persisted_ids[0] if persisted_ids else min(str(item["id"]) for item, _persisted in records)
            newest = max(records, key=lambda item: (str(item[0].get("accessed_at", "")), str(item[0]["id"])))[0]
            canonical = deep_thaw(newest)
            canonical["id"] = canonical_id
            if identity[0] == "url":
                canonical["canonical_url"] = identity[1]
            if canonical_id in merged and merged[canonical_id] != canonical:
                raise RuntimeContractError("Source Index canonical identity collides", code="INPUT_INVALID", rule="source_index_canonical_id")
            merged[canonical_id] = canonical
            for item, _persisted in records:
                aliases[str(item["id"])] = canonical_id

        return tuple(merged[key] for key in sorted(merged)), deep_freeze(aliases)

    def _merged_source_index(self, snapshot: RunSnapshot, source_records: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
        return self._source_index_update(snapshot, source_records)[0]

    def _source_aliases_for(self, run_id: str, source_records: Sequence[Mapping[str, Any]]) -> Mapping[str, str]:
        snapshot = self.load_run(run_id)
        return self._source_index_update(snapshot, source_records)[1]

    def source_index_for(self, run_id: str, source_records: Sequence[Mapping[str, Any]] = ()) -> Mapping[str, Mapping[str, Any]]:
        """Expose a read-only, validated Source Index to Kernel-owned services."""

        snapshot = self.load_run(run_id)
        return deep_freeze({item["id"]: item for item in self._merged_source_index(snapshot, source_records)})

    def _merged_research_provenance(
        self,
        snapshot: RunSnapshot,
        evidence_records: Sequence[Mapping[str, Any]],
        claim_records: Sequence[Mapping[str, Any]],
        *,
        source_index: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
        """Return the merged, validated private Evidence/Claim sidecar state."""

        storage = self._storage_for(snapshot.run_id)
        existing_evidence, existing_claims = storage.read_research_provenance(snapshot.state_version)
        evidence: dict[str, Mapping[str, Any]] = {}
        claims: dict[str, Mapping[str, Any]] = {}

        def merge(target: dict[str, Mapping[str, Any]], raw: Mapping[str, Any], *, wrapper: str, schema: str, rule: str) -> None:
            document = {wrapper: deep_thaw(raw)}
            self._validate_schema(document, schema, self.compiled_bundle_for(snapshot), rule=rule)
            identifier = document[wrapper].get("id")
            if not isinstance(identifier, str):  # Schema validation keeps this defensive guard explicit.
                raise RuntimeContractError("Research Provenance record has no identity", code="SCHEMA_INVALID", rule=rule)
            previous = target.get(identifier)
            if previous is not None and deep_thaw(previous) != document[wrapper]:
                raise RuntimeContractError("Research Provenance identity conflicts with existing content", code="STATE_VERSION_CONFLICT", rule="provenance_identity")
            target[identifier] = document[wrapper]

        for item in existing_evidence:
            merge(evidence, item, wrapper="evidence", schema="evidence.schema.json", rule="provenance_read")
        for item in evidence_records:
            merge(evidence, item, wrapper="evidence", schema="evidence.schema.json", rule="provenance_evidence")
        for item in existing_claims:
            merge(claims, item, wrapper="claim", schema="claim.schema.json", rule="provenance_read")
        for item in claim_records:
            merge(claims, item, wrapper="claim", schema="claim.schema.json", rule="provenance_claim")

        sources = {item.get("id") for item in (source_index if source_index is not None else self._merged_source_index(snapshot, ())) if isinstance(item, Mapping)}
        for item in evidence.values():
            if item.get("source_id") not in sources:
                raise RuntimeContractError("Evidence references a missing Source", code="SCHEMA_INVALID", rule="provenance_source_ref")
        for item in claims.values():
            references = tuple(item.get("evidence_ids", ())) + tuple(item.get("contradiction_ids", ()))
            if any(reference not in evidence for reference in references):
                raise RuntimeContractError("Claim references missing Evidence", code="SCHEMA_INVALID", rule="provenance_evidence_ref")

        return (
            tuple(evidence[key] for key in sorted(evidence)),
            tuple(claims[key] for key in sorted(claims)),
        )

    def _persist(
        self,
        snapshot: RunSnapshot,
        *,
        manifest_updates: Mapping[str, Mapping[str, str]] | None = None,
        manifest_remove_types: tuple[str, ...] = (),
        events: Sequence[Mapping[str, Any]] = (),
        decisions: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        """Commit a validated Snapshot and its immutable audit side records.

        The current Manifest remains the source of truth for effective state;
        audit records are appended first and become committed only once the
        Manifest advances its ``last_event_offset``.
        """

        bundle = self.compiled_bundle_for(snapshot)
        self._validate_wire_state(snapshot, bundle)
        storage = self._storage_for(snapshot.run_id)
        last_offset = 0
        for raw in events:
            event = dict(deep_thaw(raw))
            event.setdefault("ts", self.clock.now())
            event.setdefault("state_version", snapshot.state_version)
            last_offset = storage.append_event(event)
        if last_offset == 0:
            manifest = storage._manifest()  # private, same storage boundary
            last_offset = int(manifest.get("last_event_offset", 0) if manifest else 0)
        for decision in decisions:
            storage.append_decision(decision, event_offset=last_offset)
        storage.commit_snapshot(
            snapshot,
            updated_at=self.clock.now(),
            manifest_updates=manifest_updates,
            manifest_remove_types=manifest_remove_types,
            last_event_offset=last_offset,
        )

    def _compiled_bundle(self, profile_id: str, contract_version: str | None) -> CompiledBundle:
        requested = contract_version or "<default>"
        key = (requested, profile_id)
        if key not in self._bundle_cache:
            compiled = compile_bundle(self.repository_root, profile_id, contract_version)
            self._bundle_cache[key] = compiled
            self._bundle_cache[(compiled.context.bundle.contract_version, profile_id)] = compiled
        return self._bundle_cache[key]

    def create_run(self, command: CreateRunCommand, *, run_id: str | None = None) -> RunSnapshot:
        if not isinstance(command, CreateRunCommand):
            raise RuntimeContractError("create_run requires CreateRunCommand", rule="create_run_command")
        if not isinstance(command.idea, str) or not command.idea.strip():
            raise RuntimeContractError("idea must be a non-empty string", rule="idea")
        if not isinstance(command.profile_id, str) or re.fullmatch(r"^[a-z][a-z0-9_]*$", command.profile_id) is None:
            raise RuntimeContractError("profile_id is malformed", rule="profile_id")
        if command.contract_version is not None and not isinstance(command.contract_version, str):
            raise RuntimeContractError("contract_version must be a string when provided", rule="contract_version")

        compiled = self._compiled_bundle(command.profile_id, command.contract_version)
        version = compiled.context.bundle.contract_version
        legacy_records: list[LegacyInputRecord] = []
        for reference in command.legacy_input_refs:
            decision = evaluate_legacy_input_ref(
                reference,
                version,
                repository_root=self.repository_root,
                registry=compiled.registry,
            )
            if not decision.accepted:
                raise RuntimeContractError(
                    f"Legacy input reference rejected: {decision.reason}",
                    rule="legacy_input_ref",
                    details={"reason": decision.reason, "rule_id": decision.rule_id},
                )
            legacy_records.append(
                LegacyInputRecord(
                    accepted=True,
                    reason=decision.reason,
                    rule_id=decision.rule_id,
                    required_revalidation=decision.required_revalidation,
                )
            )

        states = {address: NodeState() for address in compiled.top_level.definitions}
        resolved_run_id = run_id if run_id is not None else self.id_factory.new_run_id()
        if re.fullmatch(r"^run_[A-Za-z0-9_-]+$", resolved_run_id) is None:
            raise RuntimeContractError("IdFactory returned an invalid run_id", rule="run_id")
        snapshot = RunSnapshot(
            run_id=resolved_run_id,
            contract_version=version,
            workflow_id=compiled.workflow_id,
            workflow_version=compiled.workflow_version,
            profile_ref=compiled.profile_ref,
            initial_idea=command.idea.strip(),
            state_version=0,
            workflow_status=WorkflowStatus.CREATED,
            run_policy=compiled.run_policy,
            node_states=states,
            legacy_inputs=tuple(legacy_records),
        )
        self._validate_wire_state(snapshot, compiled)
        return snapshot

    def compiled_bundle_for(self, snapshot: RunSnapshot) -> CompiledBundle:
        key = (snapshot.contract_version, snapshot.profile_ref.rsplit("@", 1)[0])
        if key not in self._bundle_cache:
            self._bundle_cache[key] = compile_bundle(self.repository_root, key[1], key[0])
        return self._bundle_cache[key]

    def schedule(
        self,
        snapshot: RunSnapshot,
        requested_nodes: Iterable[NodeAddress] | None = None,
        terminal_events: Iterable[TerminalEvent | str] = (),
        fanout_expansions: Sequence[FanOutExpansion] = (),
    ) -> ExecutionPlan:
        if not isinstance(snapshot, RunSnapshot):
            raise RuntimeContractError("schedule requires a RunSnapshot", rule="schedule_snapshot")
        bundle = self.compiled_bundle_for(snapshot)
        return schedule_snapshot(
            snapshot,
            bundle,
            id_factory=self.id_factory,
            now=self.clock.now,
            host_max_parallel=self.host_max_parallel,
            host_token_limit=self.host_token_limit,
            host_cost_limit=self.host_cost_limit,
            requested_nodes=requested_nodes,
            terminal_events=terminal_events,
            fanout_expansions=fanout_expansions,
        )

    def validate_executor_request(
        self,
        snapshot: RunSnapshot,
        attempt_id: str,
        request: Mapping[str, Any],
    ) -> ValidatedExecutorProposal:
        return validate_request_proposal(snapshot, attempt_id, request, self.compiled_bundle_for(snapshot))

    def validate_executor_result(
        self,
        snapshot: RunSnapshot,
        attempt_id: str,
        result: Mapping[str, Any],
    ) -> ValidatedExecutorProposal:
        return validate_result_proposal(snapshot, attempt_id, result, self.compiled_bundle_for(snapshot))

    # T7--T10 pure state advancement.  These methods deliberately keep the
    # existing proposal-validation API side-effect free.
    def apply_executor_result(
        self,
        snapshot: RunSnapshot,
        attempt_id: str,
        result: Mapping[str, Any],
    ) -> ResultApplication:
        proposal = self.validate_executor_result(snapshot, attempt_id, result)
        return apply_executor_result_state(
            snapshot,
            attempt_id,
            proposal.payload,
            self.compiled_bundle_for(snapshot),
            now=self.clock.now,
        )

    def resume_interaction(self, snapshot: RunSnapshot, address: NodeAddress) -> RunSnapshot:
        return resume_interaction_state(snapshot, address, self.compiled_bundle_for(snapshot))

    # Persistent entry points.  They all load the Manifest-selected Snapshot,
    # persist immutable Runtime records before the state/manifest commit, and
    # return only immutable Runtime values.
    def create_persisted_run(
        self,
        command: CreateRunCommand,
        *,
        run_id: str | None = None,
        creation_identity: Mapping[str, str] | None = None,
    ) -> RunSnapshot:
        snapshot = self.create_run(command, run_id=run_id)
        storage = self._storage_for(snapshot.run_id)
        if storage._manifest() is not None:
            raise RuntimeContractError("Create Run location already has committed state", code="IDEMPOTENCY_CONFLICT", rule="create_idempotency_identity")
        if creation_identity is not None:
            storage.write_creation_identity(
                key_hash=creation_identity["key_hash"],
                request_hash=creation_identity["request_hash"],
            )
        events: list[Mapping[str, Any]] = [{"event": "RUN_CREATED", "run_id": snapshot.run_id}]
        for reference, record in zip(command.legacy_input_refs, snapshot.legacy_inputs, strict=True):
            events.append(
                {
                    "event": "LEGACY_INPUT_ACCEPTED" if record.accepted else "LEGACY_INPUT_REJECTED",
                    "source_contract_version": reference.get("source_contract_version"),
                    "ref_type": reference.get("ref_type"),
                    "content_hash": reference.get("content_hash"),
                    "matrix_rule": record.rule_id,
                }
            )
        self._persist(snapshot, events=events)
        return snapshot

    def load_run(self, run_id: str) -> RunSnapshot:
        storage = self._storage_for(run_id)
        snapshot = storage.load_snapshot()
        self._validate_wire_state(snapshot, self.compiled_bundle_for(snapshot))
        return snapshot

    def recover_run(self, run_id: str) -> RecoveryReport:
        storage = self._storage_for(run_id)
        report = storage.recover()
        snapshot = storage.load_snapshot()
        self._validate_wire_state(snapshot, self.compiled_bundle_for(snapshot))
        return report

    def schedule_persisted(
        self,
        run_id: str,
        requested_nodes: Iterable[NodeAddress] | None = None,
        terminal_events: Iterable[TerminalEvent | str] = (),
        fanout_expansions: Sequence[FanOutExpansion] = (),
    ) -> ExecutionPlan:
        snapshot = self.load_run(run_id)
        plan = self.schedule(snapshot, requested_nodes, terminal_events, fanout_expansions)
        if plan.next_snapshot is not snapshot:
            events: list[Mapping[str, Any]] = [
                {
                    "event": f"NODE_{transition.to_status.value}",
                    "node": transition.address.node_id,
                    "reason": transition.reason,
                }
                for transition in plan.decision.transitions
            ]
            events.extend(
                {"event": "ATTEMPT_STARTED", "node": attempt.address.node_id, "attempt": attempt.attempt_id}
                for attempt in plan.attempts_to_start
            )
            self._persist(plan.next_snapshot, events=events)
        return plan

    def apply_persisted_executor_result(
        self,
        run_id: str,
        attempt_id: str,
        result: Mapping[str, Any],
        *,
        adapter_type: str | None = None,
    ) -> ResultApplication:
        snapshot = self.load_run(run_id)
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Executor Attempt is not part of the Run", rule="attempt_identity")
        if adapter_type is not None and adapter_type not in {item.value for item in attempt.allowed_adapter_types}:
            raise RuntimeContractError("Executor Adapter is not allowed for this Attempt", code="SECURITY_POLICY_VIOLATION", rule="adapter_type")
        application = self.apply_executor_result(snapshot, attempt_id, result)
        storage = self._storage_for(run_id)
        if application.checkpoint_ref is not None and application.checkpoint is not None:
            storage.write_checkpoint(application.checkpoint_ref, application.checkpoint)
        event = "INTERACTION_REQUESTED" if application.checkpoint_ref else "NODE_COMPLETED"
        events: list[Mapping[str, Any]] = []
        if adapter_type is not None:
            events.append({"event": "ADAPTER_EXECUTED", "node": attempt.address.node_id, "attempt": attempt_id, "adapter_type": adapter_type})
        events.append({"event": event, "node": attempt.address.node_id, "attempt": attempt_id})
        self._persist(
            application.next_snapshot,
            events=events,
        )
        return application

    def _validate_typed_output(
        self,
        snapshot: RunSnapshot,
        attempt_id: str,
        logical_path: str,
        document: Mapping[str, Any],
    ) -> tuple[str, str]:
        """Validate one Runtime-owned business Artifact against its Skill output.

        Executor proposals never receive this capability.  P0-03 calls it from
        the Kernel-owned business service immediately before the single writer
        persists an Artifact document.
        """

        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Business Artifact producer Attempt does not exist", rule="artifact_attempt")
        definition = self.compiled_bundle_for(snapshot).definition(attempt.address)
        if not definition.implementation_ref:
            raise RuntimeContractError("Business Artifact producer is not a Skill", rule="artifact_skill")
        artifact = document.get("artifact") if isinstance(document, Mapping) else None
        artifact_type = artifact.get("type") if isinstance(artifact, Mapping) else None
        if not isinstance(artifact_type, str):
            raise RuntimeContractError("Business Artifact type is missing", code="SCHEMA_INVALID", rule="artifact_type")
        produced_by = artifact.get("produced_by") if isinstance(artifact, Mapping) else None
        expected_skill = attempt.skill_ref.rsplit("@", 1)[0]
        if (
            not isinstance(produced_by, Mapping)
            or produced_by.get("skill") != expected_skill
            or produced_by.get("attempt") != attempt_id
        ):
            raise RuntimeContractError(
                "Business Artifact producer does not match the active Skill Attempt",
                code="SECURITY_POLICY_VIOLATION",
                rule="artifact_producer",
            )
        skill = self.compiled_bundle_for(snapshot).skills[definition.implementation_ref]
        matches = [
            output
            for output in skill.get("output_contracts", ())
            if output.get("artifact_type") == artifact_type
            and isinstance(output.get("write"), str)
            and declared_workspace_path_matches(logical_path, (output["write"],))
        ]
        if len(matches) != 1:
            raise RuntimeContractError(
                "Business Artifact does not match the producing Skill Output Contract",
                code="SECURITY_POLICY_VIOLATION",
                rule="artifact_output_contract",
            )
        schema_ref = matches[0].get("schema_ref")
        if not isinstance(schema_ref, str) or not schema_ref.startswith("schemas/"):
            raise RuntimeContractError("Skill Output Contract has no local schema reference", rule="artifact_output_contract")
        if definition.implementation_ref == "competitor-deep-dive":
            expected = f"artifacts/02-research/competitors/deep-dives/{attempt.address.instance_key}.yaml" if attempt.address.instance_key else None
            if logical_path != expected:
                raise RuntimeContractError("Deep Dive Artifact path must match its fan-out competitor ID", code="SECURITY_POLICY_VIOLATION", rule="deep_dive_artifact_path")
        self._validate_schema_ref(document, schema_ref, self.compiled_bundle_for(snapshot), rule="artifact_type_schema")
        schema_name = schema_ref.split("#", 1)[0].removeprefix("schemas/")
        return artifact_type, schema_name

    def write_typed_artifact(
        self,
        run_id: str,
        attempt_id: str,
        logical_path: str,
        document: Mapping[str, Any],
        *,
        source_records: Sequence[Mapping[str, Any]] = (),
    ) -> StoredArtifact:
        """Persist one schema-valid Skill Output Contract through the Kernel."""

        snapshot = self.load_run(run_id)
        source_index = self._merged_source_index(snapshot, source_records) if source_records else None
        self._validate_typed_output(snapshot, attempt_id, logical_path, document)
        storage = self._storage_for(run_id)
        stored = storage.write_artifact(snapshot, attempt_id, logical_path, document)
        attempt = next(item for item in snapshot.attempts if item.attempt_id == attempt_id)
        states = dict(snapshot.node_states)
        state = states[attempt.address]
        states[attempt.address] = replace(state, artifact_refs=tuple(dict.fromkeys((*state.artifact_refs, stored.artifact_ref))))
        updated = replace(snapshot, state_version=snapshot.state_version + 1, node_states=states)
        if source_index is not None:
            storage.write_source_index(state_version=updated.state_version, schema_version=updated.contract_version, sources=source_index)
        events: list[Mapping[str, Any]] = [{"event": "ARTIFACT_WRITTEN", "artifact": stored.artifact_ref, "attempt": attempt_id}]
        if source_index is not None:
            events.append({"event": "SOURCE_INDEX_UPDATED", "node": attempt.address.node_id, "attempt": attempt_id})
        self._persist(
            updated,
            manifest_updates={stored.artifact_type: {"artifact_ref": stored.artifact_ref, "content_hash": stored.content_hash}},
            events=tuple(events),
        )
        return stored

    def complete_persisted_business_attempt(
        self,
        run_id: str,
        attempt_id: str,
        artifacts: Sequence[tuple[str, Mapping[str, Any]]],
        *,
        events: Sequence[str] = (),
        source_records: Sequence[Mapping[str, Any]] = (),
        evidence_records: Sequence[Mapping[str, Any]] = (),
        claim_records: Sequence[Mapping[str, Any]] = (),
    ) -> RunSnapshot:
        """Atomically finish and verify a Kernel-owned business Skill Attempt.

        Artifact files are immutable append-only objects; the Snapshot and
        Current Manifest commit make their effective versions visible together
        with the completed/verified Node state.
        """

        snapshot = self.load_run(run_id)
        source_index = self._merged_source_index(snapshot, source_records) if source_records else None
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Business Attempt does not exist", rule="business_attempt")
        state = snapshot.node_states.get(attempt.address)
        if attempt.status is not AttemptStatus.RUNNING or state is None or state.status is not NodeStatus.RUNNING:
            raise RuntimeContractError("Business Artifact completion requires an active running Attempt", rule="business_attempt_state")
        if not artifacts:
            raise RuntimeContractError("Business Attempt requires at least one Artifact", rule="business_artifact")
        validated: list[tuple[str, Mapping[str, Any], str]] = []
        for logical_path, document in artifacts:
            artifact_type, _schema_name = self._validate_typed_output(snapshot, attempt_id, logical_path, document)
            validated.append((logical_path, document, artifact_type))
        if len({artifact_type for _, _, artifact_type in validated}) != len(validated):
            raise RuntimeContractError("Business Attempt cannot write duplicate Artifact types", rule="business_artifact")

        # Validate the complete Source -> Evidence -> Claim closure before any
        # immutable Artifact or sidecar file is written.  A rejected closure
        # must not leave an otherwise valid business Artifact looking like a
        # candidate for recovery; the Current Manifest remains the effective
        # commit point for a fully validated write.
        provenance = None
        if evidence_records or claim_records:
            provenance = self._merged_research_provenance(
                snapshot,
                evidence_records,
                claim_records,
                source_index=source_index,
            )

        storage = self._storage_for(run_id)
        stored = [storage.write_artifact(snapshot, attempt_id, logical_path, document) for logical_path, document, _ in validated]
        result = {
            "executor_result": {
                "schema_version": snapshot.contract_version,
                "run_id": run_id,
                "node_id": attempt.address.node_id,
                "attempt_id": attempt_id,
                "status": "COMPLETED",
                "output_artifact_refs": [item.artifact_ref for item in stored],
                "source_upserts": [],
                "usage": {
                    "automated_duration_seconds": 0,
                    "source_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost": 0,
                },
                "error": None,
            }
        }
        application = self.apply_executor_result(snapshot, attempt_id, result)
        bundle = self.compiled_bundle_for(snapshot)
        states = dict(application.next_snapshot.node_states)
        completed_state = states[attempt.address]
        verifying_state = transition_node(bundle.definition(attempt.address), completed_state, NodeStatus.VERIFYING)
        states[attempt.address] = transition_node(bundle.definition(attempt.address), verifying_state, NodeStatus.VERIFIED)
        attempts = list(application.next_snapshot.attempts)
        position = next(index for index, item in enumerate(attempts) if item.attempt_id == attempt_id)
        attempts[position] = replace(attempts[position], verified=True)
        research_contract_ref = application.next_snapshot.research_contract_ref
        for item in stored:
            if item.artifact_type == "research_contract":
                research_contract_ref = item.artifact_ref
        completed = replace(
            application.next_snapshot,
            node_states=states,
            attempts=tuple(attempts),
            research_contract_ref=research_contract_ref,
        )
        if source_index is not None:
            storage.write_source_index(state_version=completed.state_version, schema_version=completed.contract_version, sources=source_index)
        if provenance is not None:
            storage.write_research_provenance(
                state_version=completed.state_version,
                schema_version=completed.contract_version,
                evidence=provenance[0],
                claims=provenance[1],
            )
        manifest_updates = {
            item.artifact_type: {"artifact_ref": item.artifact_ref, "content_hash": item.content_hash}
            for item in stored
        }
        audit_events: list[Mapping[str, Any]] = [
            {"event": "ARTIFACT_WRITTEN", "artifact": item.artifact_ref, "attempt": attempt_id}
            for item in stored
        ]
        audit_events.extend({"event": event, "node": attempt.address.node_id, "attempt": attempt_id} for event in events)
        if source_index is not None:
            audit_events.append({"event": "SOURCE_INDEX_UPDATED", "node": attempt.address.node_id, "attempt": attempt_id})
        if provenance is not None:
            audit_events.append({"event": "RESEARCH_PROVENANCE_UPDATED", "node": attempt.address.node_id, "attempt": attempt_id})
        audit_events.extend(
            (
                {"event": "NODE_COMPLETED", "node": attempt.address.node_id, "attempt": attempt_id},
                {"event": "NODE_VERIFIED", "node": attempt.address.node_id, "attempt": attempt_id},
            )
        )
        self._persist(completed, manifest_updates=manifest_updates, events=tuple(audit_events))
        return completed

    def persist_idea_interaction(
        self,
        run_id: str,
        attempt_id: str,
        result: Mapping[str, Any],
        full_checkpoint: Mapping[str, Any],
    ) -> RunSnapshot:
        """Persist a validated Idea wait with the P0-03 full Checkpoint shape."""

        snapshot = self.load_run(run_id)
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None or attempt.address.node_id != "idea":
            raise RuntimeContractError("P0-03 Interaction must target the active idea Attempt", rule="idea_interaction_attempt")
        if full_checkpoint.get("attempt_id") != attempt_id:
            raise RuntimeContractError("Idea Checkpoint Attempt identity is invalid", rule="idea_checkpoint_attempt")
        application = self.apply_executor_result(snapshot, attempt_id, result)
        if application.checkpoint_ref is None:
            raise RuntimeContractError("Idea Interaction Result has no Checkpoint", rule="idea_checkpoint")
        if application.checkpoint_ref.rsplit("/", 1)[-1] != f"{full_checkpoint.get('checkpoint_id')}.json":
            raise RuntimeContractError("Idea Checkpoint identity does not match Executor Result", rule="idea_checkpoint")
        self._storage_for(run_id).write_checkpoint(application.checkpoint_ref, full_checkpoint)
        request = result["executor_result"]["interaction_request"]
        gap = full_checkpoint.get("target_unknown_id")
        events = [
            {
                "event": "INTERACTION_METHOD_SELECTED",
                "node": "idea",
                "attempt": attempt_id,
                "question_id": request["question_id"],
                "method": request["method"],
                "round": request["round"],
            },
            {
                "event": "INTERACTION_REQUESTED",
                "node": "idea",
                "attempt": attempt_id,
                "question_id": request["question_id"],
                "method": request["method"],
                "round": request["round"],
            },
        ]
        if isinstance(gap, str):
            events[0]["target_unknown_id"] = gap
        self._persist(application.next_snapshot, events=tuple(events))
        return application.next_snapshot

    def submit_interaction_response(
        self,
        run_id: str,
        address: NodeAddress,
        question_id: str,
        *,
        selected_option_id: str | None = None,
        freeform_text: str | None = None,
    ) -> RunSnapshot:
        if not selected_option_id and not (isinstance(freeform_text, str) and freeform_text.strip()):
            raise RuntimeContractError("Interaction response requires an option or freeform text", rule="interaction_response")
        snapshot = self.load_run(run_id)
        state = snapshot.node_states.get(address)
        current = snapshot.current_interaction
        storage = self._storage_for(run_id)
        normalized_response = {
            "selected_option_id": selected_option_id,
            "freeform_text": freeform_text.strip() if isinstance(freeform_text, str) else None,
        }
        if (
            state is None
            or state.status is not NodeStatus.WAITING_FOR_USER
            or current is None
            or current.get("node_id") != address.node_id
            or current.get("question_id") != question_id
            or state.interaction_checkpoint_ref is None
        ):
            # A newly supplied idempotency key may repeat an already accepted
            # Question after the Attempt has resumed or issued a later one.
            # The Checkpoint carries the complete structured history, so this
            # remains transcript-independent and cannot overwrite an answer.
            if state is not None and state.active_attempt_id and state.interaction_checkpoint_ref:
                checkpoint = storage.read_checkpoint(state.interaction_checkpoint_ref)
                answers = checkpoint.get("answers", ())
                matching = [item for item in answers if isinstance(item, Mapping) and item.get("question_id") == question_id]
                if matching:
                    accepted = matching[-1]
                    prior = {
                        "selected_option_id": accepted.get("selected_option_id"),
                        "freeform_text": accepted.get("freeform_text"),
                    }
                    if prior == normalized_response:
                        return snapshot
                    raise RuntimeContractError(
                        "Interaction Question already accepted a different response",
                        code="IDEMPOTENCY_CONFLICT",
                        rule="interaction_response_conflict",
                    )
            raise RuntimeContractError("Interaction response does not match the current Question", rule="interaction_response")
        checkpoint = dict(storage.read_checkpoint(state.interaction_checkpoint_ref))
        version = int(checkpoint.get("checkpoint_version", 0)) + 1
        base_id = checkpoint.get("checkpoint_id")
        if not isinstance(base_id, str) or not base_id.startswith("CP-"):
            raise RuntimeContractError("Stored Interaction Checkpoint identity is invalid", code="SCHEMA_INVALID", rule="checkpoint_read")
        checkpoint_id = f"{base_id}-R{version}"
        checkpoint["checkpoint_id"] = checkpoint_id
        checkpoint["checkpoint_version"] = version
        answers = list(checkpoint.get("answers", ()))
        answers.append(
            {
                "question_id": question_id,
                **normalized_response,
            }
        )
        checkpoint["answers"] = answers
        reference = f"runtime/attempts/{state.active_attempt_id}/checkpoints/{checkpoint_id}.json"
        storage.write_checkpoint(reference, checkpoint)
        states = dict(snapshot.node_states)
        states[address] = replace(state, interaction_checkpoint_ref=reference)
        interaction = dict(current)
        interaction["checkpoint_ref"] = reference
        prepared = replace(snapshot, node_states=states, current_interaction=interaction)
        resumed = self.resume_interaction(prepared, address)
        self._persist(
            resumed,
            events=(
                {"event": "INTERACTION_RESPONSE_RECORDED", "node": address.node_id, "question_id": question_id},
                {"event": "ATTEMPT_RESUMED", "node": address.node_id, "attempt": state.active_attempt_id},
            ),
        )
        return resumed

    def open_human_gate(self, run_id: str, address: NodeAddress, gate: Mapping[str, Any]) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        bundle = self.compiled_bundle_for(snapshot)
        self._validate_schema(gate, "gate.schema.json", bundle, rule="gate_schema")
        definition = bundle.definition(address)
        expected_type = (definition.implementation_ref or "").replace("-", "_")
        if definition.kind is not NodeKind.HUMAN_GATE or gate["gate"]["gate_type"] != expected_type:
            raise RuntimeContractError("Gate Contract does not match the Workflow Gate node", rule="gate_identity")
        storage = self._storage_for(run_id)
        reference = storage.write_gate_request(address.node_id, snapshot.state_version + 1, gate)
        opened = open_gate_state(snapshot, address, reference, bundle)
        self._persist(opened, events=({"event": "GATE_OPENED", "node": address.node_id},))
        return opened

    def submit_persisted_gate_decision(
        self,
        run_id: str,
        address: NodeAddress,
        decision: GateDecision | str,
        *,
        modification: Mapping[str, Any] | None = None,
        decision_document: Mapping[str, Any] | None = None,
    ) -> ExternalSubmission:
        snapshot = self.load_run(run_id)
        try:
            parsed = decision if isinstance(decision, GateDecision) else GateDecision(decision)
        except ValueError as exc:
            raise RuntimeContractError("Gate Decision is unknown", rule="gate_decision") from exc
        if snapshot.current_gate_request_ref is None:
            raise RuntimeContractError("Waiting Gate has no saved Gate Contract", rule="gate_request")
        request = self._storage_for(run_id).read_gate_request(snapshot.current_gate_request_ref)
        if parsed.value not in request.get("allowed_actions", ()):
            raise RuntimeContractError("Gate Decision is not allowed by the saved Gate Contract", rule="gate_action")
        outcome = submit_gate_decision_state(snapshot, address, parsed, self.compiled_bundle_for(snapshot))
        if parsed is GateDecision.MODIFY:
            if not isinstance(modification, Mapping) or not modification:
                raise RuntimeContractError("Gate MODIFY requires a non-empty pending modification", rule="gate_modification")
            reference = self._storage_for(run_id).write_gate_modification(address.node_id, snapshot.state_version + 1, modification)
            pending = replace(snapshot, state_version=snapshot.state_version + 1, current_gate_modification_ref=reference)
            self._persist(pending, events=({"event": "GATE_MODIFICATION_PENDING", "node": address.node_id},))
            return ExternalSubmission(pending, outcome.deferred_effects)
        document = decision_document or {
            "decision": {
                "id": f"DEC-{address.node_id}-{snapshot.state_version + 1}",
                "date": self.clock.now(),
                "gate_id": address.node_id,
                "question": request.get("question", f"Decision for {address.node_id}"),
                "decision": parsed.value,
                "rationale": ["Recorded through the Runtime Gate boundary."],
                "evidence_ids": [],
                "artifact_refs": list(request.get("input_artifact_refs", ())),
                "alternatives": [],
                "accepted_risks": [],
                "structured_diff_ref": None,
                "reversible": parsed is not GateDecision.CANCEL,
                "approved_by": {"type": "user", "id": None},
            }
        }
        self._validate_schema(document, "decision.schema.json", self.compiled_bundle_for(snapshot), rule="decision_schema")
        if document["decision"]["gate_id"] != address.node_id or document["decision"]["decision"] != parsed.value:
            raise RuntimeContractError("Decision Contract does not match the submitted Gate action", rule="decision_gate_identity")
        self._persist(
            outcome.next_snapshot,
            events=({"event": "GATE_DECISION_RECORDED", "node": address.node_id, "decision_id": document["decision"]["id"]},),
            decisions=(document,),
        )
        return outcome

    def submit_external_proof(self, run_id: str, address: NodeAddress, payload: Mapping[str, Any]) -> ExternalSubmission:
        snapshot = self.load_run(run_id)
        bundle = self.compiled_bundle_for(snapshot)
        self._validate_schema(payload, "proof-result.schema.json", bundle, rule="proof_result_schema")
        outcome = submit_external_proof_state(snapshot, address, payload, bundle)
        self._persist(outcome.next_snapshot, events=({"event": "EXTERNAL_PROOF_SUBMITTED", "node": address.node_id},))
        return outcome

    def write_artifact(
        self,
        run_id: str,
        attempt_id: str,
        logical_path: str,
        document: Mapping[str, Any],
    ) -> StoredArtifact:
        snapshot = self.load_run(run_id)
        storage = self._storage_for(run_id)
        document_to_store = dict(document)
        if any(
            record.get("attempt") == attempt_id and record.get("adapter_type") == "fixture"
            for record in storage.event_records()
        ):
            # The frozen base Artifact Contract permits extensions at the
            # document top level; keep the producer identity untouched while
            # making deterministic Fixture provenance impossible to mistake
            # for a live Research result.
            document_to_store["execution"] = {"adapter_type": "fixture", "fixture": True}
        self._validate_schema(document_to_store, "artifact.schema.json", self.compiled_bundle_for(snapshot), rule="artifact_schema")
        stored = storage.write_artifact(snapshot, attempt_id, logical_path, document_to_store)
        attempt = next(item for item in snapshot.attempts if item.attempt_id == attempt_id)
        states = dict(snapshot.node_states)
        state = states[attempt.address]
        states[attempt.address] = replace(state, artifact_refs=tuple(dict.fromkeys((*state.artifact_refs, stored.artifact_ref))))
        updated = replace(snapshot, state_version=snapshot.state_version + 1, node_states=states)
        self._persist(
            updated,
            manifest_updates={stored.artifact_type: {"artifact_ref": stored.artifact_ref, "content_hash": stored.content_hash}},
            events=({"event": "ARTIFACT_WRITTEN", "artifact": stored.artifact_ref, "attempt": attempt_id},),
        )
        return stored

    def pause_persisted_run(self, run_id: str) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        if snapshot.workflow_status in {WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}:
            raise RuntimeContractError("A terminal Workflow cannot be paused", rule="workflow_terminal")
        paused = replace(snapshot, state_version=snapshot.state_version + 1, workflow_status=WorkflowStatus.PAUSED)
        self._persist(paused, events=({"event": "RUN_PAUSED", "run_id": run_id},))
        return paused

    def resume_persisted_run(self, run_id: str) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        if snapshot.workflow_status is not WorkflowStatus.PAUSED:
            raise RuntimeContractError("Only a paused Workflow can be resumed", rule="workflow_resume")
        resumed = replace(snapshot, state_version=snapshot.state_version + 1, workflow_status=WorkflowStatus.RUNNING)
        self._persist(resumed, events=({"event": "RUN_RESUMED", "run_id": run_id},))
        return resumed

    def cancel_persisted_run(self, run_id: str) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        if snapshot.workflow_status in {WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}:
            raise RuntimeContractError("A terminal Workflow cannot be cancelled", rule="workflow_terminal")
        cancelled = replace(snapshot, state_version=snapshot.state_version + 1, workflow_status=WorkflowStatus.CANCELLED)
        self._persist(cancelled, events=({"event": "RUN_CANCELLED", "run_id": run_id},))
        return cancelled

    def record_persisted_operation_result(self, run_id: str, operation: str) -> RunSnapshot:
        """Commit a compact success audit event without re-running the mutation.

        The effective Snapshot is unchanged; advancing only the Manifest's
        Event prefix is intentional and keeps operation outcomes auditable
        without duplicating domain transitions on idempotent replay.
        """

        if not isinstance(operation, str) or not operation:
            raise RuntimeContractError("Operation audit event requires a name", rule="operation_name")
        snapshot = self.load_run(run_id)
        self._persist(snapshot, events=({"event": "OPERATION_COMPLETED", "run_id": run_id, "operation": operation},))
        return snapshot

    def retry_persisted_node(self, run_id: str, address: NodeAddress) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        state = snapshot.node_states.get(address)
        if state is None or state.status not in {NodeStatus.BLOCKED, NodeStatus.FAILED, NodeStatus.RETRY_READY}:
            raise RuntimeContractError("Only a blocked or failed node can be retried", rule="retry_node_state")
        states = dict(snapshot.node_states)
        states[address] = replace(state, status=NodeStatus.PENDING, active_attempt_id=None, interaction_checkpoint_ref=None, error=None)
        retried = replace(snapshot, state_version=snapshot.state_version + 1, node_states=states, workflow_status=WorkflowStatus.RUNNING)
        self._persist(retried, events=({"event": "NODE_RETRY_REQUESTED", "node": address.node_id},))
        return retried

    def open_manual_wait(self, run_id: str, attempt_id: str) -> RunSnapshot:
        """Place one running skill Attempt in an external manual-work wait."""

        snapshot = self.load_run(run_id)
        position = next((index for index, item in enumerate(snapshot.attempts) if item.attempt_id == attempt_id), None)
        if position is None:
            raise RuntimeContractError("Manual Adapter Attempt does not exist", rule="manual_attempt")
        attempt = snapshot.attempts[position]
        state = snapshot.node_states.get(attempt.address)
        if attempt.status.value != "RUNNING" or state is None or state.status is not NodeStatus.RUNNING:
            raise RuntimeContractError("Manual Adapter requires an active running Attempt", rule="manual_attempt_state")
        definition = self.compiled_bundle_for(snapshot).definition(attempt.address)
        attempts = list(snapshot.attempts)
        attempts[position] = replace(attempt, status=type(attempt.status).WAITING_FOR_EXTERNAL)
        states = dict(snapshot.node_states)
        states[attempt.address] = replace(
            state,
            status=NodeStatus.WAITING_FOR_EXTERNAL,
            active_attempt_id=attempt_id,
        )
        waiting = replace(
            snapshot,
            state_version=snapshot.state_version + 1,
            workflow_status=WorkflowStatus.WAITING_FOR_EXTERNAL,
            node_states=states,
            attempts=tuple(attempts),
        )
        self._persist(
            waiting,
            events=({"event": "MANUAL_EXECUTION_REQUESTED", "node": definition.address.node_id, "attempt": attempt_id, "adapter_type": "manual"},),
        )
        return waiting

    def resume_manual_attempt(self, run_id: str, attempt_id: str) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        position = next((index for index, item in enumerate(snapshot.attempts) if item.attempt_id == attempt_id), None)
        if position is None:
            raise RuntimeContractError("Manual Adapter Attempt does not exist", rule="manual_attempt")
        attempt = snapshot.attempts[position]
        state = snapshot.node_states.get(attempt.address)
        if attempt.status.value != "WAITING_FOR_EXTERNAL" or state is None or state.status is not NodeStatus.WAITING_FOR_EXTERNAL:
            raise RuntimeContractError("Manual Adapter Attempt is not waiting", rule="manual_attempt_state")
        attempts = list(snapshot.attempts)
        attempts[position] = replace(attempt, status=type(attempt.status).RUNNING)
        states = dict(snapshot.node_states)
        states[attempt.address] = replace(state, status=NodeStatus.RUNNING, active_attempt_id=attempt_id)
        resumed = replace(snapshot, state_version=snapshot.state_version + 1, workflow_status=WorkflowStatus.RUNNING, node_states=states, attempts=tuple(attempts))
        self._persist(resumed, events=({"event": "MANUAL_EXECUTION_RESUMED", "node": attempt.address.node_id, "attempt": attempt_id},))
        return resumed

    def invalidate_persisted_downstream(self, run_id: str, changed_address: NodeAddress) -> InvalidationResult:
        snapshot = self.load_run(run_id)
        result = invalidate_downstream(snapshot, self.compiled_bundle_for(snapshot), changed_address)
        if result.next_snapshot is not snapshot:
            self._persist(
                result.next_snapshot,
                manifest_remove_types=result.removed_artifact_types,
                events=tuple({"event": "NODE_INVALIDATED", "node": address.node_id} for address in result.invalidated),
            )
        return result

    def resume_invalidated_persisted(self, run_id: str) -> RunSnapshot:
        snapshot = self.load_run(run_id)
        resumed = resume_invalidated(snapshot)
        if resumed is not snapshot:
            self._persist(resumed, events=({"event": "INVALIDATED_NODES_RESUMED", "run_id": run_id},))
        return resumed
