"""Deterministic P0-03 Adaptive Idea Shaping business service.

The optional Host LLM is deliberately limited to language understanding and
copy generation.  All workflow state, method selection, checkpoint versions,
artifact writes, and gate transitions remain Runtime-owned.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, TYPE_CHECKING

from .domain import AttemptStatus, NodeAddress, NodeStatus, deep_thaw
from .errors import RuntimeContractError

if TYPE_CHECKING:  # pragma: no cover - imported only for static type checking
    from .kernel import RuntimeKernel


_DIMENSIONS = ("problem", "user", "scenario", "value", "mechanism")
_METHODS = (
    "adaptive_product_discovery_interview",
    "assumption_challenge",
    "clarification",
    "controlled_brainstorming",
)
_SEED_KEYS = (
    "competitor_questions",
    "user_questions",
    "market_questions",
    "technology_questions",
)
_HYPOTHESIS_KEYS = (
    "idea",
    "problem",
    "target_users",
    "scenario",
    "jtbd",
    "value_proposition",
    "solution",
    "scope",
)
_PROPOSAL_KEYS = frozenset({"hypothesis", "assumptions", "unknowns", "research_seeds", "question_copy"})


class HostLLMProvider(Protocol):
    """Injectable language-only provider used by the P0-03 service.

    ``host_agent`` remains the frozen wire identifier for compatibility, but
    this protocol intentionally describes the component's actual role: a Host
    LLM that proposes language data only.  It receives no storage, Kernel, or
    runtime-authority object.
    """

    def propose(self, request: "IdeaSemanticRequest") -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class IdeaSemanticRequest:
    raw_idea: str
    profile_ref: str
    checkpoint: Mapping[str, Any] | None
    accepted_response: Mapping[str, Any] | None
    directive: Mapping[str, Any] | None


class CallbackHostLLMProvider:
    """Small embedding adapter for a host-supplied LLM callback."""

    def __init__(self, callback: Callable[[IdeaSemanticRequest], Mapping[str, Any]]) -> None:
        self._callback = callback

    def propose(self, request: IdeaSemanticRequest) -> Mapping[str, Any]:
        result = self._callback(request)
        if not isinstance(result, Mapping):
            raise RuntimeContractError("Host LLM Provider must return an object proposal", rule="host_llm_proposal")
        return result


class FixtureHostLLMProvider:
    """Deterministic language proposal catalog for P0-03 tests and fixtures."""

    def __init__(self, catalog: Mapping[str, Mapping[str, Any]]) -> None:
        self._catalog = {str(key): deep_thaw(value) for key, value in catalog.items()}

    def propose(self, request: IdeaSemanticRequest) -> Mapping[str, Any]:
        response = request.accepted_response or {}
        response_key = response.get("freeform_text") or response.get("selected_option_id")
        key = str(response_key) if response_key else request.raw_idea
        result = self._catalog.get(key, self._catalog.get("*", {}))
        if not isinstance(result, Mapping):
            raise RuntimeContractError("Fixture Host LLM proposal is invalid", rule="fixture_host_llm")
        return deep_thaw(result)


class ConservativeHostLLMProvider:
    """A no-inference fallback that preserves unknowns rather than inventing facts."""

    def propose(self, request: IdeaSemanticRequest) -> Mapping[str, Any]:
        del request
        return {}


def _empty_hypothesis(raw_idea: str) -> dict[str, Any]:
    return {
        "idea": {"original": raw_idea, "normalized_summary": raw_idea},
        "problem": {"statement": None, "trigger": None, "current_alternative": None, "pain_hypothesis": None},
        "target_users": {"primary": [], "secondary": []},
        "scenario": {"primary_context": None, "trigger": None, "desired_outcome": None},
        "jtbd": {"functional": None, "emotional": None, "social": None},
        "value_proposition": {"core_value": None, "why_better_hypothesis": None},
        "solution": {"direction_hypothesis": None, "alternatives_considered": [], "core_mechanism": None},
        "scope": {"initial_boundary": None, "non_goals": []},
        "assumptions": [],
        "unknowns": [],
        "research_seeds": {key: [] for key in _SEED_KEYS},
    }


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(deep_thaw(value), ensure_ascii=False))


def _required_mapping(value: Any, *, rule: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Host LLM proposal must contain objects at this path", rule=rule)
    return value


def _text_or_none(value: Any, *, rule: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeContractError("Host LLM text values must be non-empty strings or null", rule=rule)
    return value.strip()


def _text_list(value: Any, *, rule: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RuntimeContractError("Host LLM list values must contain non-empty strings", rule=rule)
    return list(dict.fromkeys(item.strip() for item in value))


def _merge_hypothesis(base: Mapping[str, Any], proposal: Mapping[str, Any], *, raw_idea: str) -> dict[str, Any]:
    merged = _copy_mapping(base)
    unexpected = set(proposal) - _PROPOSAL_KEYS
    if unexpected:
        raise RuntimeContractError(
            "Host LLM proposal contains a Runtime-owned or unsupported field",
            code="SECURITY_POLICY_VIOLATION",
            rule="host_llm_authority",
            details={"fields": tuple(sorted(unexpected))},
        )
    patch = proposal.get("hypothesis", {})
    if patch is not None:
        patch = _required_mapping(patch, rule="host_llm_hypothesis")
        unexpected_hypothesis = set(patch) - set(_HYPOTHESIS_KEYS)
        if unexpected_hypothesis:
            raise RuntimeContractError(
                "Host LLM hypothesis contains an unsupported field",
                code="SECURITY_POLICY_VIOLATION",
                rule="host_llm_authority",
                details={"fields": tuple(sorted(unexpected_hypothesis))},
            )
        for key, value in patch.items():
            if key in {"target_users", "research_seeds", "assumptions", "unknowns"}:
                continue
            if not isinstance(value, Mapping):
                raise RuntimeContractError("Host LLM hypothesis sections must be objects", rule="host_llm_hypothesis")
            if key not in merged:
                raise RuntimeContractError("Host LLM hypothesis section is invalid", rule="host_llm_hypothesis")
            for field, field_value in value.items():
                if field not in merged[key]:
                    raise RuntimeContractError("Host LLM hypothesis field is invalid", rule="host_llm_hypothesis")
                if key == "idea" and field == "original" and field_value != raw_idea:
                    raise RuntimeContractError(
                        "Host LLM cannot rewrite the original user Idea",
                        code="SECURITY_POLICY_VIOLATION",
                        rule="host_llm_original_idea",
                    )
                if isinstance(merged[key][field], list):
                    merged[key][field] = _text_list(field_value, rule="host_llm_hypothesis")
                else:
                    merged[key][field] = _text_or_none(field_value, rule="host_llm_hypothesis")

    users = patch.get("target_users") if isinstance(patch, Mapping) else None
    if users is not None:
        users = _required_mapping(users, rule="host_llm_hypothesis")
        if set(users) - {"primary", "secondary"}:
            raise RuntimeContractError("Host LLM target user field is invalid", rule="host_llm_hypothesis")
        for key in ("primary", "secondary"):
            if key in users:
                merged["target_users"][key] = _text_list(users[key], rule="host_llm_hypothesis")

    if not merged["idea"]["original"]:
        merged["idea"]["original"] = raw_idea
    if not merged["idea"]["normalized_summary"]:
        merged["idea"]["normalized_summary"] = raw_idea

    if "assumptions" in proposal:
        merged["assumptions"] = _normalize_assumptions(proposal["assumptions"])
    if "unknowns" in proposal:
        merged["unknowns"] = _normalize_unknowns(proposal["unknowns"])
    if "research_seeds" in proposal:
        seeds = _required_mapping(proposal["research_seeds"], rule="host_llm_research_seeds")
        if set(seeds) - set(_SEED_KEYS):
            raise RuntimeContractError("Host LLM research seed category is invalid", rule="host_llm_research_seeds")
        for key, values in seeds.items():
            merged["research_seeds"][key] = _text_list(values, rule="host_llm_research_seeds")
    return merged


def _normalize_assumptions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise RuntimeContractError("Host LLM assumptions must be a list", rule="host_llm_assumptions")
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        item = _required_mapping(raw, rule="host_llm_assumptions")
        if set(item) - {"id", "type", "claim", "criticality"}:
            raise RuntimeContractError("Host LLM assumption contains an unsupported field", rule="host_llm_assumptions")
        assumption_type = item.get("type", "problem")
        criticality = item.get("criticality", "medium")
        if assumption_type not in {"user", "problem", "behavior", "solution", "market", "technical"}:
            raise RuntimeContractError("Host LLM assumption type is invalid", rule="host_llm_assumptions")
        if criticality not in {"high", "medium", "low"}:
            raise RuntimeContractError("Host LLM assumption criticality is invalid", rule="host_llm_assumptions")
        identifier = item.get("id", f"ASM-{index:03d}")
        claim = _text_or_none(item.get("claim"), rule="host_llm_assumptions")
        if not isinstance(identifier, str) or not identifier.startswith("ASM-") or claim is None:
            raise RuntimeContractError("Host LLM assumption identity is invalid", rule="host_llm_assumptions")
        results.append({"id": identifier, "type": assumption_type, "claim": claim, "status": "unvalidated", "criticality": criticality})
    if len({item["id"] for item in results}) != len(results):
        raise RuntimeContractError("Host LLM assumptions must have unique IDs", rule="host_llm_assumptions")
    return results


def _normalize_unknowns(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise RuntimeContractError("Host LLM unknowns must be a list", rule="host_llm_unknowns")
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        item = _required_mapping(raw, rule="host_llm_unknowns")
        if set(item) - {"id", "dimension", "question", "researchable"}:
            raise RuntimeContractError("Host LLM unknown contains an unsupported field", rule="host_llm_unknowns")
        dimension = item.get("dimension")
        identifier = item.get("id", f"UNK-{str(dimension or 'UNKNOWN').upper()}-{index:03d}")
        question = _text_or_none(item.get("question"), rule="host_llm_unknowns")
        researchable = item.get("researchable", True)
        if dimension not in {"problem", "user", "scenario", "value", "mechanism", "market", "technical"}:
            raise RuntimeContractError("Host LLM unknown dimension is invalid", rule="host_llm_unknowns")
        if not isinstance(identifier, str) or not identifier.startswith("UNK-") or question is None or not isinstance(researchable, bool):
            raise RuntimeContractError("Host LLM unknown identity is invalid", rule="host_llm_unknowns")
        results.append({"id": identifier, "dimension": dimension, "question": question, "researchable": researchable})
    if len({item["id"] for item in results}) != len(results):
        raise RuntimeContractError("Host LLM unknowns must have unique IDs", rule="host_llm_unknowns")
    return results


def _dimension_clarity(hypothesis: Mapping[str, Any]) -> dict[str, str]:
    problem = hypothesis["problem"]
    scenario = hypothesis["scenario"]
    value = hypothesis["value_proposition"]
    solution = hypothesis["solution"]
    users = hypothesis["target_users"]
    values = {
        "problem": "HIGH" if problem["statement"] else ("LOW" if problem["pain_hypothesis"] or problem["trigger"] else "UNKNOWN"),
        "user": "HIGH" if users["primary"] else "UNKNOWN",
        "scenario": "HIGH" if scenario["primary_context"] else ("LOW" if scenario["trigger"] or scenario["desired_outcome"] else "UNKNOWN"),
        "value": "HIGH" if value["core_value"] else ("LOW" if value["why_better_hypothesis"] else "UNKNOWN"),
        "mechanism": "HIGH" if solution["core_mechanism"] else ("LOW" if solution["direction_hypothesis"] else "UNKNOWN"),
    }
    stable_anchors = sum(item == "HIGH" for item in values.values())
    values["overall"] = "CLEAR" if stable_anchors == len(_DIMENSIONS) else ("PARTIAL" if stable_anchors or any(item == "LOW" for item in values.values()) else "VAGUE")
    return values


def _has_unknown(hypothesis: Mapping[str, Any], dimension: str) -> bool:
    return any(item["dimension"] == dimension for item in hypothesis["unknowns"])


def _ensure_research_seed(hypothesis: dict[str, Any]) -> None:
    has_origins = any(item["criticality"] == "high" for item in hypothesis["assumptions"]) or any(
        item["researchable"] for item in hypothesis["unknowns"]
    ) or any(hypothesis["research_seeds"][key] for key in _SEED_KEYS)
    anchors = hypothesis["problem"]["statement"] or hypothesis["target_users"]["primary"] or hypothesis["scenario"]["primary_context"]
    if not has_origins and anchors:
        hypothesis["research_seeds"]["user_questions"].append("What evidence confirms the described problem and target user need?")


def _research_derivable(hypothesis: Mapping[str, Any]) -> bool:
    return any(item["criticality"] == "high" for item in hypothesis["assumptions"]) or any(
        item["researchable"] for item in hypothesis["unknowns"]
    ) or any(hypothesis["research_seeds"][key] for key in _SEED_KEYS)


def _completion(hypothesis: Mapping[str, Any], clarity: Mapping[str, str], *, round_number: int) -> str:
    has_minimum = (
        bool(hypothesis["problem"]["statement"] or _has_unknown(hypothesis, "problem"))
        and bool(hypothesis["target_users"]["primary"] or _has_unknown(hypothesis, "user"))
        and bool(hypothesis["scenario"]["primary_context"] or _has_unknown(hypothesis, "scenario"))
        and bool(hypothesis["value_proposition"]["core_value"])
        and bool(hypothesis["solution"]["core_mechanism"] or hypothesis["solution"]["direction_hypothesis"])
        and _research_derivable(hypothesis)
    )
    if has_minimum:
        return "SUFFICIENT"
    if round_number >= 8:
        return "PARTIAL_RESEARCHABLE" if _research_derivable(hypothesis) else "INSUFFICIENT_PRODUCT_CONTEXT"
    del clarity
    return "IN_PROGRESS"


def _select_gap(hypothesis: Mapping[str, Any], clarity: Mapping[str, str]) -> dict[str, Any]:
    critical = [item for item in hypothesis["assumptions"] if item["criticality"] == "high"]
    if critical:
        first = sorted(critical, key=lambda item: item["id"])[0]
        return {"dimension": "assumptions", "target_unknown_id": None, "target_type": "assumption", "rationale": f"Critical assumption {first['id']} requires challenge."}
    levels = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    candidates = []
    for order, dimension in enumerate(_DIMENSIONS):
        if clarity[dimension] == "HIGH":
            continue
        unknown = next((item for item in hypothesis["unknowns"] if item["dimension"] == dimension), None)
        candidates.append((order, levels[clarity[dimension]], dimension, unknown))
    if not candidates:
        return {"dimension": "assumptions", "target_unknown_id": None, "target_type": "assumption", "rationale": "No incomplete core dimension remains; review assumptions."}
    _, _, dimension, unknown = sorted(candidates, key=lambda item: (item[0], item[1], item[2]))[0]
    return {
        "dimension": dimension,
        "target_unknown_id": unknown["id"] if unknown else None,
        "target_type": "unknown" if unknown else "dimension",
        "rationale": f"{dimension} is the highest-value unresolved dependency for research-question derivation.",
    }


def _select_method(clarity: Mapping[str, str], gap: Mapping[str, Any], *, round_number: int) -> str:
    if gap["target_type"] == "assumption":
        return "assumption_challenge"
    if clarity["overall"] == "VAGUE" and round_number == 1:
        return "controlled_brainstorming"
    if clarity["overall"] == "VAGUE":
        return "adaptive_product_discovery_interview"
    if gap["target_type"] == "dimension" and clarity[gap["dimension"]] == "LOW":
        return "clarification"
    return "adaptive_product_discovery_interview"


def _fallback_question(gap: Mapping[str, Any], method: str) -> dict[str, Any]:
    dimension = gap["dimension"]
    prompt = {
        "problem": "What specific problem should this idea solve first?",
        "user": "Which primary user should be prioritized?",
        "scenario": "In which concrete situation does the user face this problem?",
        "value": "What outcome would make this meaningfully better for the user?",
        "mechanism": "What product mechanism is currently hypothesized to create that value?",
        "assumptions": "Which critical assumption should be challenged before research begins?",
    }[dimension]
    return {"prompt": prompt, "options": [], "recommendation": None, "method": method}


def _question_copy(value: Any, fallback: Mapping[str, Any]) -> dict[str, Any]:
    if value is None:
        return dict(fallback)
    item = _required_mapping(value, rule="host_llm_question")
    if set(item) - {"prompt", "options", "recommendation"}:
        raise RuntimeContractError("Host LLM question copy contains an unsupported field", rule="host_llm_question")
    prompt = _text_or_none(item.get("prompt", fallback["prompt"]), rule="host_llm_question")
    options = item.get("options", fallback["options"])
    if not isinstance(options, (list, tuple)) or len(options) == 1 or len(options) > 4:
        raise RuntimeContractError("Host LLM question options must contain zero or two to four values", rule="host_llm_question")
    normalized_options: list[dict[str, str]] = []
    for option in options:
        raw = _required_mapping(option, rule="host_llm_question")
        if set(raw) != {"id", "label", "description"}:
            raise RuntimeContractError("Host LLM question option shape is invalid", rule="host_llm_question")
        if not all(isinstance(raw[name], str) and raw[name].strip() for name in raw):
            raise RuntimeContractError("Host LLM question option values are invalid", rule="host_llm_question")
        normalized_options.append({name: raw[name].strip() for name in ("id", "label", "description")})
    if len({option["id"] for option in normalized_options}) != len(normalized_options):
        raise RuntimeContractError("Host LLM question options must have unique IDs", rule="host_llm_question")
    recommendation = item.get("recommendation", fallback["recommendation"])
    if normalized_options:
        if not isinstance(recommendation, Mapping) or set(recommendation) != {"option_id", "rationale"}:
            raise RuntimeContractError("Host LLM choices require a recommendation", rule="host_llm_question")
        if recommendation["option_id"] not in {option["id"] for option in normalized_options} or not isinstance(recommendation["rationale"], str) or not recommendation["rationale"].strip():
            raise RuntimeContractError("Host LLM recommendation is invalid", rule="host_llm_question")
        recommendation = {"option_id": recommendation["option_id"], "rationale": recommendation["rationale"].strip()}
    elif recommendation is not None:
        raise RuntimeContractError("Host LLM cannot recommend an absent option", rule="host_llm_question")
    return {"prompt": prompt, "options": normalized_options, "recommendation": recommendation}


def _canonical_hash(document: Mapping[str, Any]) -> str:
    payload = _copy_mapping(document)
    payload["artifact"].pop("content_hash", None)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _artifact_version(kernel: "RuntimeKernel", run_id: str, artifact_type: str) -> int:
    manifest = kernel._storage_for(run_id)._manifest() or {}
    entry = manifest.get("current_artifacts", {}).get(artifact_type, {})
    reference = entry.get("artifact_ref") if isinstance(entry, Mapping) else None
    if not isinstance(reference, str) or "@" not in reference:
        return 1
    return int(reference.rsplit("@", 1)[1]) + 1


def _artifact_header(kernel: "RuntimeKernel", snapshot, attempt, artifact_type: str, prefix: str) -> dict[str, Any]:
    version = _artifact_version(kernel, snapshot.run_id, artifact_type)
    artifact_id = f"{prefix}-{snapshot.run_id.removeprefix('run_')}"
    previous = None if version == 1 else f"{artifact_id}@{version - 1}"
    return {
        "id": artifact_id,
        "type": artifact_type,
        "schema_version": snapshot.contract_version,
        "version": version,
        "produced_by": {"skill": attempt.skill_ref.rsplit("@", 1)[0], "attempt": attempt.attempt_id},
        "created_at": kernel.clock.now(),
        "supersedes": previous,
        "status": "active",
        "content_hash": "",
    }


def _idea_document(kernel: "RuntimeKernel", snapshot, attempt, hypothesis: Mapping[str, Any], clarity: Mapping[str, str], outcome: str, rounds_used: int) -> dict[str, Any]:
    document = _copy_mapping(hypothesis)
    document["artifact"] = _artifact_header(kernel, snapshot, attempt, "idea_definition", "ART-IDEA")
    document["clarity"] = dict(clarity)
    document["confidence"] = {
        "overall": "medium" if clarity["overall"] == "CLEAR" else ("low" if clarity["overall"] == "PARTIAL" else "insufficient"),
        "basis": "Qualitative understanding of user-provided input only; no external validation was performed.",
    }
    document["shaping"] = {"mode": clarity["overall"], "rounds_used": rounds_used, "completion_outcome": outcome}
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _question_bucket_from_assumption(item: Mapping[str, Any]) -> str:
    return {"market": "market", "technical": "technology", "solution": "competitors"}.get(item["type"], "users")


def _question_bucket_from_unknown(item: Mapping[str, Any]) -> str:
    return {"market": "market", "technical": "technology"}.get(item["dimension"], "users")


def _research_contract_document(kernel: "RuntimeKernel", snapshot, attempt, idea: Mapping[str, Any]) -> dict[str, Any]:
    bundle = kernel.compiled_bundle_for(snapshot)
    questions: dict[str, list[dict[str, Any]]] = {"competitors": [], "users": [], "market": [], "technology": []}
    counters = {"competitors": 0, "users": 0, "market": 0, "technology": 0}
    codes = {"competitors": "COMP", "users": "USER", "market": "MARKET", "technology": "TECH"}

    def add(bucket: str, question: str, origin: str) -> None:
        for existing in questions[bucket]:
            if existing["question"] == question:
                existing["origin_refs"].append(origin)
                existing["origin_refs"] = list(dict.fromkeys(existing["origin_refs"]))
                return
        counters[bucket] += 1
        questions[bucket].append({"id": f"RQ-{codes[bucket]}-{counters[bucket]:02d}", "question": question, "origin_refs": [origin]})

    for assumption in idea["assumptions"]:
        if assumption["criticality"] == "high":
            add(_question_bucket_from_assumption(assumption), f"What evidence can test this assumption: {assumption['claim']}?", assumption["id"])
    origin_exceptions = []
    for unknown in idea["unknowns"]:
        if unknown["researchable"]:
            add(_question_bucket_from_unknown(unknown), unknown["question"], unknown["id"])
        else:
            origin_exceptions.append({"origin_ref": unknown["id"], "not_researchable_reason": "The Idea Definition marks this unknown as not researchable."})
    seed_buckets = {
        "competitor_questions": "competitors",
        "user_questions": "users",
        "market_questions": "market",
        "technology_questions": "technology",
    }
    for seed_key, bucket in seed_buckets.items():
        origin_key = seed_key.removesuffix("_questions")
        for index, question in enumerate(idea["research_seeds"][seed_key]):
            add(bucket, question, f"research_seeds.{origin_key}_questions[{index}]")
    if not any(questions.values()):
        raise RuntimeContractError("Idea Definition has no derivable Research Question", rule="research_question_origin")

    definitions = bundle.top_level.definitions
    effective_research = {
        node: definitions[NodeAddress((), node)].relevant_config.get("research_mode", "required")
        for node in ("competitor", "users", "market", "technology")
    }
    defaults = definitions[NodeAddress((), "competitor")].relevant_config["research_defaults"]
    visualizations = list(definitions[NodeAddress((), "competitor")].relevant_config["competitor_visualizations"].get("required", ()))
    choose_one = definitions[NodeAddress((), "competitor")].relevant_config["competitor_visualizations"].get("choose_one")
    if isinstance(choose_one, Mapping):
        options = choose_one.get("options", ())
        if options:
            visualizations.append(options[0])
    document = {
        "artifact": _artifact_header(kernel, snapshot, attempt, "research_contract", "ART-CONTRACT"),
        "profile_ref": snapshot.profile_ref,
        "effective_research": effective_research,
        "research_questions": questions,
        "origin_exceptions": origin_exceptions,
        "required_evidence": {
            "competitor_count": defaults["competitor_count"],
            "primary_sources": defaults["primary_sources"],
            "user_evidence_items": defaults["user_evidence_items"],
            "oss_projects": defaults["technology_items"],
        },
        "required_source_types": ["primary_source"],
        "required_visualizations": visualizations,
        "profile_adjustments": [],
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
        "stop_conditions": {"max_research_loops": snapshot.run_policy.max_global_research_cycles},
    }
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


class AdaptiveIdeaShapingService:
    """Kernel-owned P0-03 execution for the ``idea`` and ``contract`` nodes."""

    def __init__(self, kernel: "RuntimeKernel", provider: HostLLMProvider | None = None) -> None:
        self.kernel = kernel
        self.provider = provider or ConservativeHostLLMProvider()

    def advance(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None or attempt.status is not AttemptStatus.RUNNING:
            raise RuntimeContractError("P0-03 service requires an active running Attempt", rule="idea_shaping_attempt")
        if attempt.address.node_id == "idea":
            return self._advance_idea(snapshot, attempt)
        if attempt.address.node_id == "contract":
            return self._advance_contract(snapshot, attempt)
        raise RuntimeContractError("P0-03 service only handles the idea and contract nodes", rule="idea_shaping_node")

    def _advance_idea(self, snapshot, attempt) -> Mapping[str, Any]:
        storage = self.kernel._storage_for(snapshot.run_id)
        checkpoint = storage.read_checkpoint(attempt.interaction_checkpoint_ref) if attempt.interaction_checkpoint_ref else None
        if checkpoint is not None and checkpoint.get("attempt_id") not in {None, attempt.attempt_id}:
            raise RuntimeContractError("Idea Checkpoint belongs to a different Attempt", code="SCHEMA_INVALID", rule="idea_checkpoint_attempt")
        base = checkpoint.get("current_hypothesis") if isinstance(checkpoint, Mapping) else None
        hypothesis = _copy_mapping(base) if isinstance(base, Mapping) else _empty_hypothesis(snapshot.initial_idea)
        answers = checkpoint.get("answers", ()) if isinstance(checkpoint, Mapping) else ()
        accepted_response = answers[-1] if isinstance(answers, (list, tuple)) and answers else None
        initial = self.provider.propose(
            IdeaSemanticRequest(snapshot.initial_idea, snapshot.profile_ref, checkpoint, accepted_response, None)
        )
        hypothesis = _merge_hypothesis(hypothesis, initial, raw_idea=snapshot.initial_idea)
        _ensure_research_seed(hypothesis)
        clarity = _dimension_clarity(hypothesis)
        round_number = int(checkpoint.get("round", 0)) if isinstance(checkpoint, Mapping) else 0
        outcome = _completion(hypothesis, clarity, round_number=round_number)
        if outcome in {"SUFFICIENT", "PARTIAL_RESEARCHABLE"}:
            document = _idea_document(self.kernel, snapshot, attempt, hypothesis, clarity, outcome, round_number)
            completed = self.kernel.complete_persisted_business_attempt(
                snapshot.run_id,
                attempt.attempt_id,
                (("artifacts/00-intake/idea-definition.yaml", document),),
                events=(("IDEA_SHAPING_EARLY_EXIT" if outcome == "SUFFICIENT" else "IDEA_SHAPING_MAX_ROUNDS_REACHED"),),
            )
            return {"state": completed.to_wire_state(), "outcome": outcome, "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1]}
        if outcome == "INSUFFICIENT_PRODUCT_CONTEXT":
            document = _idea_document(self.kernel, snapshot, attempt, hypothesis, clarity, outcome, round_number)
            self.kernel.write_typed_artifact(snapshot.run_id, attempt.attempt_id, "artifacts/00-intake/idea-definition.yaml", document)
            failed = self.kernel.apply_persisted_executor_result(
                snapshot.run_id,
                attempt.attempt_id,
                {
                    "executor_result": {
                        "schema_version": snapshot.contract_version,
                        "run_id": snapshot.run_id,
                        "node_id": "idea",
                        "attempt_id": attempt.attempt_id,
                        "status": "FAILED",
                        "output_artifact_refs": [],
                        "source_upserts": [],
                        "usage": {"automated_duration_seconds": 0, "source_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0},
                        "error": {"code": "INSUFFICIENT_PRODUCT_CONTEXT", "recoverable": False, "details": {}},
                    }
                },
            )
            return {"state": failed.next_snapshot.to_wire_state(), "outcome": outcome}

        gap = _select_gap(hypothesis, clarity)
        next_round = round_number + 1
        method = _select_method(clarity, gap, round_number=next_round)
        directive = {"target_dimension": gap["dimension"], "target_unknown_id": gap["target_unknown_id"], "method": method, "round": next_round}
        phrased = self.provider.propose(IdeaSemanticRequest(snapshot.initial_idea, snapshot.profile_ref, checkpoint, accepted_response, directive))
        hypothesis = _merge_hypothesis(hypothesis, phrased, raw_idea=snapshot.initial_idea)
        _ensure_research_seed(hypothesis)
        question_copy = _question_copy(phrased.get("question_copy") if isinstance(phrased, Mapping) else None, _fallback_question(gap, method))
        question_id = f"IQ-{attempt.attempt_id.removeprefix('ATT-')}-R{next_round}"
        request = {
            "method": method,
            "question_id": question_id,
            "round": next_round,
            "dimension": gap["dimension"] if gap["dimension"] in _DIMENSIONS else "mechanism",
            "prompt": question_copy["prompt"],
            "options": question_copy["options"],
            "recommendation": question_copy["recommendation"],
            "allow_freeform_answer": True,
        }
        version = int(checkpoint.get("checkpoint_version", 0)) + 1 if isinstance(checkpoint, Mapping) else 1
        history = list(checkpoint.get("method_history", ())) if isinstance(checkpoint, Mapping) else []
        history.append({"round": next_round, "method": method, "target_unknown_id": gap["target_unknown_id"]})
        full_checkpoint = {
            "schema_version": snapshot.contract_version,
            "checkpoint_id": f"CP-{attempt.attempt_id.removeprefix('ATT-')}-V{version}",
            "attempt_id": attempt.attempt_id,
            "checkpoint_version": version,
            "round": next_round,
            "unresolved_dimensions": [dimension for dimension in _DIMENSIONS if clarity[dimension] != "HIGH"],
            "current_method": method,
            "target_unknown_id": gap["target_unknown_id"],
            "target_dimension": gap["dimension"] if gap["dimension"] in _DIMENSIONS else "mechanism",
            "selection_rationale": gap["rationale"],
            "method_history": history,
            "current_question": request,
            "answers": list(checkpoint.get("answers", ())) if isinstance(checkpoint, Mapping) else [],
            "current_hypothesis": hypothesis,
            "clarity": clarity,
            "completion_status": "IN_PROGRESS",
        }
        minimal_checkpoint = {
            key: full_checkpoint[key]
            for key in ("checkpoint_id", "checkpoint_version", "round", "current_method", "target_unknown_id", "target_dimension", "selection_rationale", "completion_status")
        }
        result = {
            "executor_result": {
                "schema_version": snapshot.contract_version,
                "run_id": snapshot.run_id,
                "node_id": "idea",
                "attempt_id": attempt.attempt_id,
                "status": "WAITING_FOR_USER",
                "output_artifact_refs": [],
                "source_upserts": [],
                "interaction_request": request,
                "interaction_checkpoint": minimal_checkpoint,
                "usage": {"automated_duration_seconds": 0, "source_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0},
                "error": None,
            }
        }
        waiting = self.kernel.persist_idea_interaction(snapshot.run_id, attempt.attempt_id, result, full_checkpoint)
        return {"state": waiting.to_wire_state(), "outcome": "IN_PROGRESS", "interaction": request}

    def _advance_contract(self, snapshot, attempt) -> Mapping[str, Any]:
        idea_state = snapshot.node_states.get(NodeAddress((), "idea"))
        if idea_state is None or idea_state.status is not NodeStatus.VERIFIED or not idea_state.artifact_refs:
            raise RuntimeContractError("Research Contract requires a verified Idea Definition", rule="research_contract_input")
        idea = self.kernel._storage_for(snapshot.run_id).read_artifact(idea_state.artifact_refs[-1])
        document = _research_contract_document(self.kernel, snapshot, attempt, idea)
        completed = self.kernel.complete_persisted_business_attempt(
            snapshot.run_id,
            attempt.attempt_id,
            (("artifacts/01-contract/research-contract.yaml", document),),
        )
        scheduled = self.kernel.schedule_persisted(snapshot.run_id).next_snapshot
        contract_ref = completed.node_states[attempt.address].artifact_refs[-1]
        gate = {
            "gate": {"id": "gate_research", "status": "WAITING_FOR_USER", "gate_type": "research_scope"},
            "question": "Approve the proposed research scope before any research is scheduled?",
            "options": [
                {"id": "approve", "label": "Approve", "description": "Proceed with the proposed research scope."},
                {"id": "modify", "label": "Modify", "description": "Keep research blocked while a structured change is prepared."},
                {"id": "cancel", "label": "Cancel", "description": "Stop this product-discovery run."},
            ],
            "recommendation": {"option": "approve"},
            "input_artifact_refs": [contract_ref],
            "risks": ["The Contract contains hypotheses and research questions, not externally verified findings."],
            "proposed_structured_diff_ref": None,
            "allowed_actions": ["APPROVE", "MODIFY", "CANCEL"],
        }
        opened = self.kernel.open_human_gate(snapshot.run_id, NodeAddress((), "gate_research"), gate)
        return {"state": opened.to_wire_state(), "outcome": "RESEARCH_SCOPE_GATE", "research_contract_ref": contract_ref, "scheduled_state_version": scheduled.state_version}
