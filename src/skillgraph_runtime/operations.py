"""Language-neutral, in-process Runtime API operations and envelopes."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapters import AdapterRegistry, ManualAdapter
from .domain import CreateRunCommand, GateDecision, NodeAddress, deep_thaw
from .errors import RuntimeContractError
from .kernel import RuntimeKernel
from .storage import RunStorage
from .idea_shaping import AdaptiveIdeaShapingService
from .competitor_research import CompetitorResearchService
from .research_gap import ResearchGapPlanner


_MUTATING = frozenset(
    {
        "create_run",
        "run_ready_nodes",
        "pause_run",
        "resume_run",
        "submit_interaction_response",
        "submit_gate_decision",
        "submit_external_proof_result",
        "retry_node",
        "cancel_run",
    }
)
_UNIMPLEMENTED = frozenset({"submit_artifact_patch", "get_source", "export_prd"})


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(deep_thaw(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _key_hash(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise RuntimeContractError("idempotency_key must be a non-empty bounded string", rule="idempotency_key")
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class RuntimeOperations:
    """The stable operation boundary shared by the CLI and embedders."""

    def __init__(
        self,
        kernel: RuntimeKernel,
        *,
        adapters: AdapterRegistry | None = None,
        idea_shaping: AdaptiveIdeaShapingService | None = None,
        competitor_research: CompetitorResearchService | None = None,
        research_gap_planner: ResearchGapPlanner | None = None,
    ) -> None:
        if kernel.storage_root is None:
            raise RuntimeContractError("RuntimeOperations requires an explicit storage_root", rule="storage_root_required")
        self.kernel = kernel
        self.storage_root = kernel.storage_root
        self.adapters = adapters or AdapterRegistry()
        if idea_shaping is not None and idea_shaping.kernel is not kernel:
            raise RuntimeContractError("P0-03 service must use the same RuntimeKernel", rule="idea_shaping_kernel")
        if competitor_research is not None and competitor_research.kernel is not kernel:
            raise RuntimeContractError("P0-04 service must use the same RuntimeKernel", rule="competitor_research_kernel")
        if research_gap_planner is not None and research_gap_planner.kernel is not kernel:
            raise RuntimeContractError("P0-05 service must use the same RuntimeKernel", rule="research_gap_kernel")
        self.idea_shaping = idea_shaping
        self.competitor_research = competitor_research
        self.research_gap_planner = research_gap_planner

    def execute_p0_03_attempt(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        """Advance an active `idea` or `contract` Attempt through P0-03.

        This is an embedding-only capability.  It is intentionally not a new
        normative CLI/API operation: the stable operation surface continues to
        schedule Attempts and submit user responses, while callers explicitly
        invoke a configured Host LLM-backed business service.
        """

        if self.idea_shaping is None:
            raise RuntimeContractError("P0-03 Idea Shaping service is not configured", rule="idea_shaping_unavailable")
        return self.idea_shaping.advance(run_id, attempt_id)

    def execute_p0_04_attempt(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        """Advance an active internal Competitor Research Attempt.

        As with P0-03, this is an embedding-only service hook rather than a
        new normative operation or CLI command.  Providers remain constrained
        by the Kernel-owned Artifact and state boundaries.
        """

        if self.competitor_research is None:
            raise RuntimeContractError("P0-04 Competitor Research service is not configured", rule="competitor_research_unavailable")
        return self.competitor_research.advance(run_id, attempt_id)

    def execute_p0_05_attempt(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        """Advance the configured bounded Research Gap Planner.

        This is an embedding-only hook, matching P0-03/P0-04.  It does not
        widen the stable operation/CLI surface or grant Provider storage
        authority.
        """

        if self.research_gap_planner is None:
            raise RuntimeContractError("P0-05 Research Gap Planner is not configured", rule="research_gap_unavailable")
        return self.research_gap_planner.advance(run_id, attempt_id)

    def execute_adapter_attempt(self, run_id: str, attempt_id: str, adapter_type: str) -> Mapping[str, Any]:
        """Run a configured adapter through the existing validation boundary.

        This is an embedding hook, deliberately separate from the normative
        user-facing operations.  It never grants adapters storage authority.
        """

        snapshot = self.kernel.load_run(run_id)
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Adapter Attempt is not part of the Run", rule="adapter_attempt")
        request = {
            "executor_request": {
                "schema_version": snapshot.contract_version,
                "run_id": run_id,
                "node_id": attempt.address.node_id,
                "attempt_id": attempt_id,
                "adapter_type": adapter_type,
                "skill_ref": attempt.skill_ref,
                "input_artifact_refs": list(attempt.input_artifact_refs),
                "profile_ref": attempt.profile_ref,
                "research_contract_ref": attempt.research_contract_ref,
                "permissions": {
                    "external_access": attempt.permissions.external_access,
                    "workspace_write_paths": list(attempt.permissions.workspace_write_paths),
                    "secrets": attempt.permissions.secrets,
                },
                "budget": {
                    "timeout_minutes": attempt.budget.timeout_minutes,
                    "max_sources": attempt.budget.max_sources,
                    "token_limit": attempt.budget.token_limit,
                    "cost_limit": attempt.budget.cost_limit,
                },
            }
        }
        validated = self.kernel.validate_executor_request(snapshot, attempt_id, request)
        adapter = self.adapters.get(adapter_type)
        # Adapters receive immutable requests and may return immutable Catalog
        # values.  Convert the untrusted proposal back to plain JSON data so
        # the existing Draft 2020-12 validator sees a standard object.
        result = deep_thaw(adapter.execute(validated))
        if isinstance(adapter, ManualAdapter):
            waiting = self.kernel.open_manual_wait(run_id, attempt_id)
            return {**result, "state": waiting.to_wire_state()}
        if not isinstance(result, Mapping) or "executor_result" not in result:
            raise RuntimeContractError("Executor Adapter must return an Executor Result proposal", rule="adapter_result")
        application = self.kernel.apply_persisted_executor_result(run_id, attempt_id, result, adapter_type=adapter_type)
        return {"state": application.next_snapshot.to_wire_state()}

    def submit_manual_result(self, run_id: str, attempt_id: str, result: Mapping[str, Any]) -> Mapping[str, Any]:
        """Controlled embedding hook for a Manual Adapter completion proposal."""

        self.kernel.resume_manual_attempt(run_id, attempt_id)
        application = self.kernel.apply_persisted_executor_result(run_id, attempt_id, result)
        return {"state": application.next_snapshot.to_wire_state()}

    def _response(
        self,
        *,
        ok: bool,
        state_version: int | None,
        data: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "api_version": "0.2.0",
            "request_id": request_id or f"REQ-{uuid.uuid4().hex.upper()}",
            "ok": ok,
            "state_version": state_version,
            "data": dict(data or {}),
            "error": None if error is None else dict(error),
        }

    def _error(self, error: RuntimeContractError, *, state_version: int | None = None) -> dict[str, Any]:
        return self._response(
            ok=False,
            state_version=state_version,
            error={"code": error.code, "rule": error.rule, "details": deep_thaw(error.details)},
        )

    @staticmethod
    def exit_code(response: Mapping[str, Any]) -> int:
        if response.get("ok"):
            data = response.get("data", {})
            state = data.get("state", {}) if isinstance(data, Mapping) else {}
            return 6 if isinstance(state, Mapping) and state.get("readiness_status") == "NOT_READY" else 0
        error = response.get("error") or {}
        if error.get("rule") in {"operation_internal", "cli_internal"}:
            return 10
        code = error.get("code")
        return {
            "INPUT_INVALID": 2,
            "SCHEMA_INVALID": 2,
            "SCHEMA_VERSION_UNSUPPORTED": 2,
            "STATE_VERSION_CONFLICT": 3,
            "IDEMPOTENCY_CONFLICT": 3,
            "GATE_NOT_APPROVED": 3,
            "SECURITY_POLICY_VIOLATION": 4,
            "EXECUTOR_FAILED": 5,
            "SOURCE_UNAVAILABLE": 5,
        }.get(code, 10)

    def _creation_records(self) -> tuple[Mapping[str, Any], ...]:
        path = self.storage_root / "runtime" / "create-idempotency-log.jsonl"
        if not path.is_file():
            return ()
        records: list[Mapping[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, Mapping):
                            raise ValueError("record is not an object")
                        records.append(value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeContractError("Create idempotency log is unreadable", code="SCHEMA_INVALID", rule="create_idempotency_log") from exc
        return tuple(records)

    def _append_creation_record(self, record: Mapping[str, Any]) -> None:
        path = self.storage_root / "runtime" / "create-idempotency-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            json.dump(deep_thaw(record), stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _create(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping) or envelope.get("run_id") not in {None, ""} or "expected_state_version" in envelope:
            raise RuntimeContractError("create_run has an invalid mutation envelope", rule="operation_envelope")
        key_hash = _key_hash(envelope.get("idempotency_key"))
        request_hash = _canonical_hash({"operation": "create_run", "payload": payload})
        deterministic_run_id = "run_" + key_hash.removeprefix("sha256:")
        deterministic_request_id = "REQ-" + key_hash.removeprefix("sha256:").upper()
        matches = [item for item in self._creation_records() if item.get("key_hash") == key_hash]
        if matches:
            record = matches[-1]
            if record.get("request_hash") != request_hash:
                raise RuntimeContractError("Idempotency key was reused with a different create payload", code="IDEMPOTENCY_CONFLICT", rule="idempotency_payload")
            return deep_thaw(record["response"])
        command = CreateRunCommand(
            str(payload.get("idea", "")),
            str(payload.get("profile_id", "")),
            payload.get("contract_version"),
            tuple(payload.get("legacy_input_refs", ())),
        )
        storage = RunStorage(self.storage_root, deterministic_run_id)
        identity = storage.creation_identity()
        expected_identity = {"key_hash": key_hash, "request_hash": request_hash}
        if identity is not None and identity != expected_identity:
            raise RuntimeContractError("Idempotency key is bound to a different create request", code="IDEMPOTENCY_CONFLICT", rule="create_idempotency_identity")
        if identity is not None and storage._manifest() is not None:
            snapshot = self.kernel.load_run(deterministic_run_id)
        else:
            snapshot = self.kernel.create_persisted_run(
                command,
                run_id=deterministic_run_id,
                creation_identity=expected_identity,
            )
        response = self._response(
            ok=True,
            state_version=snapshot.state_version,
            data={"run_id": snapshot.run_id, "contract_version": snapshot.contract_version, "state": snapshot.to_wire_state()},
            request_id=deterministic_request_id,
        )
        self._append_creation_record({"key_hash": key_hash, "request_hash": request_hash, "response": response})
        return response

    def _mutate(
        self,
        operation: str,
        envelope: Mapping[str, Any],
        action: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    ) -> dict[str, Any]:
        run_id = envelope.get("run_id")
        payload = envelope.get("payload")
        if not isinstance(run_id, str) or not isinstance(payload, Mapping) or not isinstance(envelope.get("expected_state_version"), int):
            raise RuntimeContractError("Mutating operation has an invalid envelope", rule="operation_envelope")
        key_hash = _key_hash(envelope.get("idempotency_key"))
        request_hash = _canonical_hash({"operation": operation, "run_id": run_id, "payload": payload})
        storage = RunStorage(self.storage_root, run_id)
        existing = storage.idempotency_record(key_hash)
        if existing is not None:
            if existing.get("request_hash") != request_hash or existing.get("operation") != operation:
                raise RuntimeContractError("Idempotency key was reused with a different payload", code="IDEMPOTENCY_CONFLICT", rule="idempotency_payload")
            return deep_thaw(existing["response"])
        snapshot = self.kernel.load_run(run_id)
        if envelope["expected_state_version"] != snapshot.state_version:
            raise RuntimeContractError(
                "Mutation expected_state_version does not match the current Run",
                code="STATE_VERSION_CONFLICT",
                rule="expected_state_version",
                details={"expected_state_version": envelope["expected_state_version"], "actual_state_version": snapshot.state_version},
            )
        data = action(run_id, payload)
        state_version = data.get("state", {}).get("state_version") if isinstance(data.get("state"), Mapping) else None
        # A P0-03 same-question/same-response replay with a fresh idempotency
        # key returns the existing Snapshot.  It must not manufacture an
        # operation Event when no Runtime state, Checkpoint, or Round changed.
        if state_version != snapshot.state_version:
            self.kernel.record_persisted_operation_result(run_id, operation)
        response = self._response(ok=True, state_version=state_version, data=data)
        storage.append_idempotency_record(key_hash=key_hash, request_hash=request_hash, operation=operation, response=response)
        return response

    def dispatch(self, operation: str, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """Dispatch one v0.2 operation without exposing Python exceptions."""

        try:
            if not isinstance(operation, str) or not isinstance(envelope, Mapping):
                raise RuntimeContractError("Operation and envelope must be objects", rule="operation_shape")
            if envelope.get("api_version") != "0.2.0":
                raise RuntimeContractError("Unsupported API version", code="SCHEMA_VERSION_UNSUPPORTED", rule="api_version")
            if operation == "create_run":
                return self._create(envelope)
            if operation in _UNIMPLEMENTED:
                raise RuntimeContractError("Operation belongs to a later product stage", rule="operation_not_implemented")
            if operation == "get_run_state":
                run_id = envelope.get("run_id")
                if not isinstance(run_id, str):
                    raise RuntimeContractError("get_run_state requires run_id", rule="operation_envelope")
                snapshot = self.kernel.load_run(run_id)
                return self._response(ok=True, state_version=snapshot.state_version, data={"state": snapshot.to_wire_state()})
            if operation == "get_artifact":
                run_id, payload = envelope.get("run_id"), envelope.get("payload", {})
                if not isinstance(run_id, str) or not isinstance(payload, Mapping) or not isinstance(payload.get("artifact_id"), str):
                    raise RuntimeContractError("get_artifact requires run_id and artifact_id", rule="operation_envelope")
                version = payload.get("version")
                storage = RunStorage(self.storage_root, run_id)
                if version is None:
                    manifest = storage._manifest() or {}
                    matches = [
                        item.get("artifact_ref")
                        for item in manifest.get("current_artifacts", {}).values()
                        if isinstance(item, Mapping) and isinstance(item.get("artifact_ref"), str) and item["artifact_ref"].startswith(payload["artifact_id"] + "@")
                    ]
                    if len(matches) != 1:
                        raise RuntimeContractError("Artifact has no unique current version", rule="artifact_current")
                    reference = matches[0]
                else:
                    reference = f"{payload['artifact_id']}@{version}"
                artifact = storage.read_artifact(reference)
                snapshot = self.kernel.load_run(run_id)
                return self._response(ok=True, state_version=snapshot.state_version, data={"artifact": artifact})
            handlers: dict[str, Callable[[str, Mapping[str, Any]], Mapping[str, Any]]] = {
                "run_ready_nodes": lambda run_id, payload: self._schedule(run_id, payload),
                "pause_run": lambda run_id, payload: {"state": self.kernel.pause_persisted_run(run_id).to_wire_state()},
                "resume_run": lambda run_id, payload: {"state": self.kernel.resume_persisted_run(run_id).to_wire_state()},
                "cancel_run": lambda run_id, payload: {"state": self.kernel.cancel_persisted_run(run_id).to_wire_state()},
                "retry_node": lambda run_id, payload: self._retry(run_id, payload),
                "submit_interaction_response": lambda run_id, payload: self._interaction(run_id, payload),
                "submit_gate_decision": lambda run_id, payload: self._gate(run_id, payload),
                "submit_external_proof_result": lambda run_id, payload: self._proof(run_id, payload),
            }
            if operation not in handlers:
                raise RuntimeContractError("Operation is unknown", rule="operation_name")
            return self._mutate(operation, envelope, handlers[operation])
        except RuntimeContractError as exc:
            state_version = exc.details.get("actual_state_version") if isinstance(exc.details, Mapping) else None
            return self._error(exc, state_version=state_version if isinstance(state_version, int) else None)
        except Exception:
            return self._response(
                ok=False,
                state_version=None,
                error={"code": "INPUT_INVALID", "rule": "operation_internal", "details": {}},
            )

    def _schedule(self, run_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        requested = payload.get("node_ids")
        nodes = None if requested is None else tuple(NodeAddress((), value) for value in requested)
        plan = self.kernel.schedule_persisted(run_id, requested_nodes=nodes)
        return {"attempt_ids": [attempt.attempt_id for attempt in plan.attempts_to_start], "state": plan.next_snapshot.to_wire_state()}

    def _retry(self, run_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            raise RuntimeContractError("retry_node requires node_id", rule="operation_payload")
        snapshot = self.kernel.retry_persisted_node(run_id, NodeAddress((), node_id))
        return {"state": snapshot.to_wire_state()}

    def _interaction(self, run_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        node_id, question_id = payload.get("node_id"), payload.get("question_id")
        if not isinstance(node_id, str) or not isinstance(question_id, str):
            raise RuntimeContractError("Interaction Response requires node_id and question_id", rule="operation_payload")
        snapshot = self.kernel.load_run(run_id)
        state = snapshot.node_states.get(NodeAddress((), node_id))
        if payload.get("attempt_id") != (state.active_attempt_id if state else None):
            raise RuntimeContractError("Interaction Response attempt_id is stale", code="STATE_VERSION_CONFLICT", rule="interaction_attempt")
        resumed = self.kernel.submit_interaction_response(
            run_id,
            NodeAddress((), node_id),
            question_id,
            selected_option_id=payload.get("selected_option_id"),
            freeform_text=payload.get("freeform_text"),
        )
        return {"state": resumed.to_wire_state()}

    def _gate(self, run_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        node_id, raw = payload.get("gate_id"), payload.get("decision")
        if not isinstance(node_id, str) or not isinstance(raw, str) or not isinstance(payload.get("decision_document"), Mapping):
            raise RuntimeContractError("Gate submission requires gate_id, decision, and decision_document", rule="operation_payload")
        outcome = self.kernel.submit_persisted_gate_decision(
            run_id,
            NodeAddress((), node_id),
            GateDecision(raw),
            modification=payload.get("modification"),
            decision_document=payload["decision_document"],
        )
        return {"state": outcome.next_snapshot.to_wire_state(), "deferred_effects": list(outcome.deferred_effects)}

    def _proof(self, run_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        proof = payload.get("proof_result")
        if not isinstance(proof, Mapping):
            raise RuntimeContractError("External Proof submission requires proof_result", rule="operation_payload")
        outcome = self.kernel.submit_external_proof(run_id, NodeAddress((), payload.get("node_id", "proof_result")), proof)
        return {"state": outcome.next_snapshot.to_wire_state(), "deferred_effects": list(outcome.deferred_effects)}
