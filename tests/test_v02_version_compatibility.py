from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from scripts.contract_bundles import (
    ContractResolutionError,
    evaluate_legacy_input_ref,
    load_bundle_context,
    load_version_registry,
    resolve_bundle_reference,
    resolve_contract_bundle,
    verify_integrity,
)
from scripts.validate_contracts import ROOT, load_document


def _stable(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_legacy_fixture_matrix_is_explicit_default_deny_and_non_mutating():
    registry = load_version_registry()
    current = resolve_contract_bundle(registry=registry)
    context = load_bundle_context(current)
    manifest = load_document(context.fixture_manifest_path)

    cases = manifest["legacy_cases"]
    assert len(cases) == 7
    assert sum(case["expected_accepted"] for case in cases) == 1
    assert verify_integrity(registry) == []

    for case in cases:
        fixture_path = context.bundle.root / case["path"]
        reference = load_document(fixture_path)
        original_reference = deepcopy(reference)
        baseline_hash = hashlib.sha256((ROOT / "contracts" / "0.1.0-baseline.sha256.json").read_bytes()).hexdigest()

        decision = evaluate_legacy_input_ref(
            reference,
            case["target_contract_version"],
            registry=registry,
        )

        assert decision.accepted is case["expected_accepted"], case["path"]
        assert decision.reason == case["expected_reason"], case["path"]
        assert decision.rule_id == case.get("expected_rule"), case["path"]
        assert _stable(reference) == _stable(original_reference), case["path"]
        assert hashlib.sha256((ROOT / "contracts" / "0.1.0-baseline.sha256.json").read_bytes()).hexdigest() == baseline_hash
        assert verify_integrity(registry) == []

    accepted = evaluate_legacy_input_ref(
        load_document(context.bundle.root / "fixtures/legacy/accepted-evidence.yaml"),
        "0.2.0",
        registry=registry,
    )
    assert accepted.required_revalidation == (
        "source_schema",
        "content_hash",
        "freshness",
        "provenance",
        "security",
        "verification",
    )


def test_v01_resume_rejection_does_not_modify_legacy_state_bytes():
    registry = load_version_registry()
    state_path = ROOT / "fixtures" / "contracts" / "valid" / "workflow-state.yaml"
    before = hashlib.sha256(state_path.read_bytes()).hexdigest()

    with pytest.raises(ContractResolutionError) as captured:
        resolve_contract_bundle("0.1.0", operation="resume", registry=registry)

    assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert hashlib.sha256(state_path.read_bytes()).hexdigest() == before
    assert verify_integrity(registry) == []


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        "../schemas/common.schema.json",
        "schemas\\common.schema.json",
        "https://example.com/common.schema.json",
        "file:///schemas/common.schema.json",
        "C:/schemas/common.schema.json",
    ],
)
def test_v02_bundle_reference_resolution_fails_closed(unsafe_ref: str):
    context = load_bundle_context(resolve_contract_bundle())

    with pytest.raises(ContractResolutionError):
        resolve_bundle_reference(context, unsafe_ref, allowed_prefixes=("schemas",))


def test_v02_bundle_reference_never_falls_back_to_v01_root(tmp_path):
    context = load_bundle_context(resolve_contract_bundle())
    isolated_bundle = replace(
        context,
        bundle=replace(context.bundle, root=tmp_path.resolve()),
    )
    root_only_name = "schemas/common.schema.json"

    assert (ROOT / root_only_name).is_file()
    assert not (tmp_path / root_only_name).exists()
    with pytest.raises(ContractResolutionError) as captured:
        resolve_bundle_reference(isolated_bundle, root_only_name, allowed_prefixes=("schemas",))
    assert captured.value.rule == "missing_contract_asset"
