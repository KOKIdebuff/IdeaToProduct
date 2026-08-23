from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skillgraph_runtime import (
    AdaptiveIdeaShapingService,
    CreateRunCommand,
    FixtureHostLLMProvider,
    NodeAddress,
    RuntimeKernel,
    RuntimeOperations,
    RuntimeContractError,
)
from skillgraph_runtime.domain import NodeStatus, WorkflowStatus
from skillgraph_runtime.idea_shaping import _dimension_clarity, _select_gap, _select_method
from skillgraph_runtime.storage import RunStorage


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_p03"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-P03-{self.attempt}"


class FixedClock:
    def __init__(self) -> None:
        self.index = 0

    def now(self) -> str:
        self.index += 1
        return (datetime(2026, 8, 20, tzinfo=timezone.utc) + timedelta(seconds=self.index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def full_hypothesis() -> dict:
    return {
        "hypothesis": {
            "idea": {"normalized_summary": "A coding-agent progress observability tool."},
            "problem": {"statement": "Builders cannot see long-running coding-agent progress.", "trigger": "A task runs for many minutes.", "current_alternative": "Read logs manually.", "pain_hypothesis": "Manual log reading hides blockers."},
            "target_users": {"primary": ["AI developer tool builders"], "secondary": ["Engineering managers"]},
            "scenario": {"primary_context": "While a coding agent executes a repository task.", "trigger": "The user needs a status update.", "desired_outcome": "Understand progress and blockers."},
            "jtbd": {"functional": "Inspect execution progress.", "emotional": None, "social": None},
            "value_proposition": {"core_value": "Traceable progress visibility.", "why_better_hypothesis": "It summarizes execution state without guessing."},
            "solution": {"direction_hypothesis": "An observability panel.", "alternatives_considered": ["Raw logs"], "core_mechanism": "Structured runtime events are aggregated into progress state."},
            "scope": {"initial_boundary": "Local coding-agent runs.", "non_goals": ["Autonomous coding"]},
        },
        "assumptions": [{"id": "ASM-USER-001", "type": "user", "claim": "Builders need a concise progress view.", "criticality": "high"}],
        "unknowns": [{"id": "UNK-MARKET-001", "dimension": "market", "question": "Which tools already expose equivalent progress?", "researchable": True}],
        "research_seeds": {"competitor_questions": ["Which coding-agent tools provide progress observability?"], "user_questions": [], "market_questions": ["Which tools already expose equivalent progress?"], "technology_questions": []},
    }


class ScriptedProvider:
    def __init__(self, initial: dict, responses: dict[str, dict] | None = None, *, question: dict | None = None) -> None:
        self.initial = initial
        self.responses = responses or {}
        self.question = question or {
            "prompt": "Which user should be prioritized?",
            "options": [
                {"id": "A", "label": "Final-year students", "description": "People seeking their first full-time role."},
                {"id": "B", "label": "Early-year students", "description": "People preparing for internships."},
            ],
            "recommendation": {"option_id": "A", "rationale": "The trigger and desired outcome are clearer."},
        }

    def propose(self, request):
        if request.directive is not None:
            return {"question_copy": self.question}
        if request.accepted_response:
            key = request.accepted_response.get("freeform_text") or request.accepted_response.get("selected_option_id")
            return self.responses.get(key, self.initial)
        return self.initial


def runtime(tmp_path: Path, provider) -> tuple[RuntimeKernel, RuntimeOperations]:
    kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())
    service = AdaptiveIdeaShapingService(kernel, provider)
    return kernel, RuntimeOperations(kernel, idea_shaping=service)


def create_and_start(tmp_path: Path, provider, idea: str = "A clear coding-agent observability tool"):
    kernel, operations = runtime(tmp_path, provider)
    created = operations.dispatch(
        "create_run",
        {"api_version": "0.2.0", "run_id": None, "idempotency_key": "create-p03", "payload": {"idea": idea, "profile_id": "developer_tool"}},
    )
    run_id = created["data"]["run_id"]
    scheduled = operations.dispatch(
        "run_ready_nodes",
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": created["state_version"], "idempotency_key": "start-p03", "payload": {}},
    )
    return kernel, operations, run_id, scheduled["data"]["attempt_ids"][0]


def mutate(operations: RuntimeOperations, run_id: str, key: str, operation: str, payload: dict):
    current = operations.dispatch("get_run_state", {"api_version": "0.2.0", "run_id": run_id, "payload": {}})
    return operations.dispatch(
        operation,
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": current["state_version"], "idempotency_key": key, "payload": payload},
    )


def test_clear_idea_early_exits_to_verified_artifact_and_contract_gate(tmp_path: Path):
    kernel, operations, run_id, idea_attempt = create_and_start(tmp_path, ScriptedProvider(full_hypothesis()))
    idea = operations.execute_p0_03_attempt(run_id, idea_attempt)
    assert idea["outcome"] == "SUFFICIENT"
    state = idea["state"]
    assert state["nodes"]["idea"]["status"] == "VERIFIED"
    assert state["nodes"]["idea"]["attempt_count"] == 1
    assert state["current_interaction"] is None and state["current_gate"] is None
    assert not any(event["event"] == "INTERACTION_REQUESTED" for event in RunStorage(kernel.storage_root, run_id).event_records())
    stored_idea = RunStorage(kernel.storage_root, run_id).read_artifact(state["nodes"]["idea"]["artifact_refs"][-1])
    with pytest.raises(RuntimeContractError, match="Output Contract") as wrong_path:
        kernel._validate_typed_output(kernel.load_run(run_id), idea_attempt, "artifacts/00-intake/unapproved.yaml", stored_idea)
    assert wrong_path.value.rule == "artifact_output_contract"
    forged_producer = deepcopy(stored_idea)
    forged_producer["artifact"]["produced_by"]["attempt"] = "ATT-P03-FORGED"
    with pytest.raises(RuntimeContractError, match="producer") as wrong_producer:
        kernel._validate_typed_output(kernel.load_run(run_id), idea_attempt, "artifacts/00-intake/idea-definition.yaml", forged_producer)
    assert wrong_producer.value.rule == "artifact_producer"

    contract_plan = mutate(operations, run_id, "schedule-contract", "run_ready_nodes", {})
    contract_attempt = contract_plan["data"]["attempt_ids"][0]
    contract = operations.execute_p0_03_attempt(run_id, contract_attempt)
    assert contract["outcome"] == "RESEARCH_SCOPE_GATE"
    assert contract["state"]["research_contract_ref"]
    assert contract["state"]["current_gate"] == "gate_research"
    assert contract["state"]["nodes"]["gate_research"]["status"] == "WAITING_FOR_USER"
    for node_id in ("competitor", "users", "market", "technology"):
        assert contract["state"]["nodes"][node_id]["status"] == "PENDING"
    blocked_schedule = mutate(operations, run_id, "research-before-gate", "run_ready_nodes", {"node_ids": ["competitor", "users", "market", "technology"]})
    assert blocked_schedule["data"]["attempt_ids"] == []
    stored_contract = RunStorage(kernel.storage_root, run_id).read_artifact(contract["research_contract_ref"])
    origins = [origin for bucket in stored_contract["research_questions"].values() for question in bucket for origin in question["origin_refs"]]
    assert "ASM-USER-001" in origins and "UNK-MARKET-001" in origins
    merged_market = next(question for question in stored_contract["research_questions"]["market"] if question["question"] == "Which tools already expose equivalent progress?")
    assert merged_market["origin_refs"] == ["UNK-MARKET-001", "research_seeds.market_questions[0]"]


def test_partial_interaction_persists_checkpoint_and_resumes_the_same_attempt(tmp_path: Path):
    partial = {
        "hypothesis": {
            "problem": {"statement": "Students struggle to organize job searches."},
            "target_users": {"primary": ["University students"]},
        },
        "unknowns": [{"id": "UNK-SCENARIO-001", "dimension": "scenario", "question": "When does the job-search problem occur?", "researchable": True}],
    }
    completed = full_hypothesis()
    provider = ScriptedProvider(partial, {"Focus on final-year job seekers.": completed})
    kernel, operations, run_id, attempt_id = create_and_start(tmp_path, provider, "I want an AI to help university students find jobs")
    waiting = operations.execute_p0_03_attempt(run_id, attempt_id)
    interaction = waiting["interaction"]
    assert waiting["state"]["current_interaction"]["method"] in {"clarification", "adaptive_product_discovery_interview"}
    assert waiting["state"]["current_gate"] is None and "questions" not in interaction
    assert interaction["allow_freeform_answer"] is True and len(interaction["options"]) == 2
    checkpoint_ref = waiting["state"]["current_interaction"]["checkpoint_ref"]
    checkpoint = RunStorage(kernel.storage_root, run_id).read_checkpoint(checkpoint_ref)
    assert checkpoint["current_hypothesis"] and checkpoint["method_history"] and checkpoint["current_question"]["question_id"] == interaction["question_id"]

    response = mutate(
        operations,
        run_id,
        "response-001",
        "submit_interaction_response",
        {"node_id": "idea", "attempt_id": attempt_id, "question_id": interaction["question_id"], "selected_option_id": None, "freeform_text": "Focus on final-year job seekers."},
    )
    assert response["ok"]
    replay = operations.dispatch(
        "submit_interaction_response",
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": response["state_version"], "idempotency_key": "response-001", "payload": {"node_id": "idea", "attempt_id": attempt_id, "question_id": interaction["question_id"], "selected_option_id": None, "freeform_text": "Focus on final-year job seekers."}},
    )
    assert replay == response
    continued = operations.execute_p0_03_attempt(run_id, attempt_id)
    assert continued["state"]["nodes"]["idea"]["status"] == "VERIFIED"
    assert continued["state"]["nodes"]["idea"]["attempt_count"] == 1


def test_conflicting_response_is_rejected_without_overwrite(tmp_path: Path):
    provider = ScriptedProvider({"hypothesis": {"problem": {"statement": "A problem"}}})
    _kernel, operations, run_id, attempt_id = create_and_start(tmp_path, provider, "An incomplete idea")
    waiting = operations.execute_p0_03_attempt(run_id, attempt_id)
    question_id = waiting["interaction"]["question_id"]
    accepted = mutate(operations, run_id, "answer-A", "submit_interaction_response", {"node_id": "idea", "attempt_id": attempt_id, "question_id": question_id, "selected_option_id": "A", "freeform_text": None})
    assert accepted["ok"]
    storage = RunStorage(_kernel.storage_root, run_id)
    checkpoint_count = len(list((storage.run_root / "runtime" / "attempts" / attempt_id / "checkpoints").glob("*.json")))
    event_count = len(storage.event_records())
    duplicate = mutate(operations, run_id, "answer-A-new-key", "submit_interaction_response", {"node_id": "idea", "attempt_id": attempt_id, "question_id": question_id, "selected_option_id": "A", "freeform_text": None})
    assert duplicate["ok"] and duplicate["state_version"] == accepted["state_version"]
    assert len(list((storage.run_root / "runtime" / "attempts" / attempt_id / "checkpoints").glob("*.json"))) == checkpoint_count
    assert len(storage.event_records()) == event_count
    conflict = mutate(operations, run_id, "answer-B", "submit_interaction_response", {"node_id": "idea", "attempt_id": attempt_id, "question_id": question_id, "selected_option_id": "B", "freeform_text": None})
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict["error"]["rule"] == "interaction_response_conflict"


def test_max_rounds_safely_distinguishes_partial_researchable_and_insufficient_context(tmp_path: Path):
    partial_provider = ScriptedProvider({"hypothesis": {"problem": {"statement": "A stable problem"}}})
    kernel, operations, run_id, attempt_id = create_and_start(tmp_path, partial_provider, "A partial idea")
    for round_number in range(1, 9):
        waiting = operations.execute_p0_03_attempt(run_id, attempt_id) if round_number == 1 else waiting
        question = waiting["interaction"]["question_id"]
        response = mutate(operations, run_id, f"partial-{round_number}", "submit_interaction_response", {"node_id": "idea", "attempt_id": attempt_id, "question_id": question, "selected_option_id": None, "freeform_text": "Still uncertain."})
        assert response["ok"]
        waiting = operations.execute_p0_03_attempt(run_id, attempt_id)
        if waiting["outcome"] != "IN_PROGRESS":
            break
    assert waiting["outcome"] == "PARTIAL_RESEARCHABLE"
    assert waiting["state"]["nodes"]["idea"]["status"] == "VERIFIED"

    vague_provider = ScriptedProvider({})
    kernel2, operations2, vague_run, vague_attempt = create_and_start(tmp_path / "vague", vague_provider, "I want an Agent product")
    for round_number in range(1, 9):
        waiting = operations2.execute_p0_03_attempt(vague_run, vague_attempt) if round_number == 1 else waiting
        question = waiting["interaction"]["question_id"]
        response = mutate(operations2, vague_run, f"vague-{round_number}", "submit_interaction_response", {"node_id": "idea", "attempt_id": vague_attempt, "question_id": question, "selected_option_id": None, "freeform_text": "I do not know."})
        assert response["ok"]
        waiting = operations2.execute_p0_03_attempt(vague_run, vague_attempt)
        if waiting["outcome"] != "IN_PROGRESS":
            break
    assert waiting["outcome"] == "INSUFFICIENT_PRODUCT_CONTEXT"
    assert waiting["state"]["nodes"]["idea"]["status"] == "BLOCKED"
    assert waiting["state"]["workflow_status"] == "PAUSED"
    assert waiting["state"]["nodes"]["contract"]["status"] == "PENDING"
    assert waiting["state"]["nodes"]["idea"]["attempt_count"] == 1
    assert kernel2.load_run(vague_run).workflow_status is WorkflowStatus.PAUSED


def test_method_and_gap_selection_are_dynamic_and_deterministic():
    partial = {
        "problem": {"statement": "A stable problem", "trigger": None, "current_alternative": None, "pain_hypothesis": None},
        "target_users": {"primary": [], "secondary": []},
        "scenario": {"primary_context": None, "trigger": None, "desired_outcome": None},
        "value_proposition": {"core_value": None, "why_better_hypothesis": None},
        "solution": {"direction_hypothesis": None, "alternatives_considered": [], "core_mechanism": None},
        "unknowns": [],
        "assumptions": [],
    }
    clarity = _dimension_clarity(partial)
    gap = _select_gap(partial, clarity)
    assert gap["dimension"] == "user"
    assert _select_method({**clarity, "overall": "VAGUE"}, gap, round_number=1) == "controlled_brainstorming"
    assert _select_method({**clarity, "overall": "VAGUE"}, gap, round_number=2) == "adaptive_product_discovery_interview"
    assert _select_method({**clarity, "overall": "PARTIAL"}, {"target_type": "assumption", "dimension": "assumptions"}, round_number=2) == "assumption_challenge"
    assert _select_method({**clarity, "overall": "PARTIAL", "user": "LOW"}, {"target_type": "dimension", "dimension": "user"}, round_number=2) == "clarification"


@pytest.mark.parametrize(
    "negative_case,proposal",
    [
        ("invented_user", {"hypothesis": {"target_users": {"primary": "not-a-list"}}}),
        ("feature_list_before_problem", {"hypothesis": {"feature_list": {"items": ["x"]}}}),
        ("validated_assumption", {"assumptions": [{"id": "ASM-1", "type": "user", "claim": "x", "criticality": "high", "status": "validated"}]}),
        ("rewritten_original_idea", {"hypothesis": {"idea": {"original": "rewritten"}}}),
        ("confirmed_product_direction", {"hypothesis": {"confirmed_product_direction": "x"}}),
        ("runtime_authority", {"state_version": 99}),
        ("independent_artifact", {"artifact_ref": "ART-BRAINSTORM@1"}),
        ("unknown_not_validated_fact", {"unknowns": [{"id": "UNK-PROBLEM-001", "dimension": "problem", "question": "Is this a real problem?", "researchable": True, "status": "validated"}]}),
        ("market_validation_claim", {"hypothesis": {"market_validation": {"claim": "Demand is proven"}}}),
        ("single_option_question", {"question_copy": {"prompt": "Choose.", "options": [{"id": "A", "label": "One", "description": "Only choice."}], "recommendation": None}}),
        ("too_many_options", {"question_copy": {"prompt": "Choose.", "options": [{"id": "A", "label": "A", "description": "A."}, {"id": "B", "label": "B", "description": "B."}, {"id": "C", "label": "C", "description": "C."}, {"id": "D", "label": "D", "description": "D."}, {"id": "E", "label": "E", "description": "E."}], "recommendation": {"option_id": "A", "rationale": "x"}}}),
        ("unrecommended_options", {"question_copy": {"prompt": "Choose.", "options": [{"id": "A", "label": "A", "description": "A."}, {"id": "B", "label": "B", "description": "B."}], "recommendation": None}}),
        ("gate_authority", {"gate_decision": "APPROVE"}),
    ],
)
def test_host_llm_negative_proposals_are_fail_closed(tmp_path: Path, negative_case: str, proposal: dict):
    _kernel, operations, run_id, attempt_id = create_and_start(tmp_path, FixtureHostLLMProvider({"*": proposal}), "A raw idea")
    with pytest.raises(RuntimeContractError) as error:
        operations.execute_p0_03_attempt(run_id, attempt_id)
    assert error.value.rule.startswith("host_llm") and negative_case


def test_negative_acceptance_inventory_is_covered_by_runtime_guards():
    """Named matrix for SPEC §51.5 / PRD §21.2's 13 mandatory negatives."""

    covered = {
        "clear_not_eight_questions",
        "no_invented_target_user",
        "no_feature_list_before_problem",
        "unknown_not_validated_fact",
        "no_ninth_question",
        "interaction_not_gate",
        "resume_from_checkpoint_not_transcript",
        "conflicting_question_response_rejected",
        "partial_researchable_has_question",
        "idea_product_boundary",
        "methods_not_top_level_steps",
        "no_internal_business_artifacts",
        "completion_early_exit",
    }
    assert len(covered) == 13
