"""JSON-only command line equivalent for the v0.2 Runtime operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .kernel import RuntimeKernel
from .operations import RuntimeOperations


class _JsonArgumentParser(argparse.ArgumentParser):
    """Turn parse failures into the same JSON-only CLI response boundary."""

    def error(self, message: str) -> None:
        raise ValueError(message)


def _json_file(path: str) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError("JSON input must be an object")
    return value


def _text(value: str) -> str:
    explicit = Path(value[1:]) if value.startswith("@") else Path(value)
    return explicit.read_text(encoding="utf-8") if explicit.is_file() else value


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="skillgraph-runtime", add_help=False)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--storage-root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--idea", required=True)
    init.add_argument("--profile", required=True)
    init.add_argument("--contract-version", default="0.2.0")
    init.add_argument("--legacy-input-refs")
    init.add_argument("--idempotency-key", required=True)
    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)
    for name in ("run", "pause", "resume", "retry", "cancel"):
        item = sub.add_parser(name)
        item.add_argument("--run-id", required=True)
        item.add_argument("--idempotency-key", required=True)
        if name == "retry":
            item.add_argument("--node-id", required=True)
    interaction = sub.add_parser("interaction")
    interaction_sub = interaction.add_subparsers(dest="interaction_command", required=True)
    submit = interaction_sub.add_parser("submit")
    submit.add_argument("--run-id", required=True)
    submit.add_argument("--node-id", required=True)
    submit.add_argument("--attempt-id", required=True)
    submit.add_argument("--question-id", required=True)
    submit.add_argument("--option")
    submit.add_argument("--text")
    submit.add_argument("--idempotency-key", required=True)
    gate = sub.add_parser("gate")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_submit = gate_sub.add_parser("submit")
    gate_submit.add_argument("--run-id", required=True)
    gate_submit.add_argument("--gate-id", required=True)
    gate_submit.add_argument("--decision", required=True)
    gate_submit.add_argument("--input", required=True)
    gate_submit.add_argument("--idempotency-key", required=True)
    proof = sub.add_parser("proof")
    proof_sub = proof.add_subparsers(dest="proof_command", required=True)
    proof_submit = proof_sub.add_parser("submit")
    proof_submit.add_argument("--run-id", required=True)
    proof_submit.add_argument("--input", required=True)
    proof_submit.add_argument("--idempotency-key", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--artifact-id", required=True)
    inspect.add_argument("--version", type=int)
    export = sub.add_parser("export")
    export.add_argument("--run-id", required=True)
    export.add_argument("--artifact", required=True)
    return parser


def _current_version(service: RuntimeOperations, run_id: str) -> int:
    response = service.dispatch("get_run_state", {"api_version": "0.2.0", "run_id": run_id, "payload": {}})
    if not response["ok"]:
        raise ValueError("Run cannot be loaded for mutation")
    return int(response["state_version"])


def _mutation(service: RuntimeOperations, operation: str, run_id: str, key: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.dispatch(
        operation,
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": _current_version(service, run_id), "idempotency_key": key, "payload": payload},
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        service = RuntimeOperations(RuntimeKernel(Path(args.repository_root), storage_root=Path(args.storage_root)))
        if args.command == "init":
            payload: dict[str, Any] = {"idea": _text(args.idea), "profile_id": args.profile, "contract_version": args.contract_version}
            if args.legacy_input_refs:
                payload["legacy_input_refs"] = _json_file(args.legacy_input_refs).get("legacy_input_refs", [])
            response = service.dispatch("create_run", {"api_version": "0.2.0", "run_id": None, "idempotency_key": args.idempotency_key, "payload": payload})
        elif args.command == "status":
            response = service.dispatch("get_run_state", {"api_version": "0.2.0", "run_id": args.run_id, "payload": {}})
        elif args.command in {"run", "pause", "resume", "retry", "cancel"}:
            operation = {"run": "run_ready_nodes", "pause": "pause_run", "resume": "resume_run", "retry": "retry_node", "cancel": "cancel_run"}[args.command]
            payload = {"node_id": args.node_id} if args.command == "retry" else {}
            response = _mutation(service, operation, args.run_id, args.idempotency_key, payload)
        elif args.command == "interaction":
            payload = {"node_id": args.node_id, "attempt_id": args.attempt_id, "question_id": args.question_id, "selected_option_id": args.option, "freeform_text": _text(args.text) if args.text else None}
            response = _mutation(service, "submit_interaction_response", args.run_id, args.idempotency_key, payload)
        elif args.command == "gate":
            document = _json_file(args.input)
            payload = {"gate_id": args.gate_id, "decision": args.decision, "decision_document": document}
            response = _mutation(service, "submit_gate_decision", args.run_id, args.idempotency_key, payload)
        elif args.command == "proof":
            response = _mutation(service, "submit_external_proof_result", args.run_id, args.idempotency_key, {"proof_result": _json_file(args.input)})
        elif args.command == "inspect":
            response = service.dispatch("get_artifact", {"api_version": "0.2.0", "run_id": args.run_id, "payload": {"artifact_id": args.artifact_id, "version": args.version}})
        else:
            response = service.dispatch("export_prd", {"api_version": "0.2.0", "run_id": args.run_id, "payload": {"artifact": args.artifact}})
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        response = {"api_version": "0.2.0", "request_id": None, "ok": False, "state_version": None, "data": {}, "error": {"code": "INPUT_INVALID", "rule": "cli_input", "details": {}}}
    except Exception:
        response = {"api_version": "0.2.0", "request_id": None, "ok": False, "state_version": None, "data": {}, "error": {"code": "INPUT_INVALID", "rule": "cli_internal", "details": {}}}
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if not response["ok"]:
        print(response["error"]["rule"], file=sys.stderr)
    return RuntimeOperations.exit_code(response)


if __name__ == "__main__":
    raise SystemExit(main())
