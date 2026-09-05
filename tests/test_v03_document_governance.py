from __future__ import annotations

import hashlib

from scripts.contract_bundles import load_version_registry, verify_integrity
from scripts.validate_contracts import ROOT


def test_v03_documents_are_frozen_and_inherit_v02_outside_the_amendment():
    registry = load_version_registry()
    assert verify_integrity(registry) == []

    prd = (ROOT / "PRD_v0.3.md").read_text(encoding="utf-8")
    spec = (ROOT / "SPEC_v0.3.md").read_text(encoding="utf-8")
    impact = (ROOT / "V0.3_CHANGE_IMPACT.md").read_text(encoding="utf-8")
    assert "not a rewrite of PRD v0.2" in prd
    normalized_spec = " ".join(spec.split())
    assert "All other v0.2 Product, Spec, Runtime, Workflow, Research, Evidence, Verification, and Human Gate semantics are inherited." in normalized_spec
    normalized_prd = " ".join(prd.split())
    assert "competitor-report.md" in normalized_prd
    assert "not a final report artifact" in normalized_prd
    assert "`bundle-self-contained`" in prd
    assert "`png_ref`" in prd
    assert "remains a valid attribute but is optional" in normalized_prd
    assert "0.3.0 + 0.2.0" in prd
    assert "single-file-self-contained" not in prd + spec
    assert "Renderer Implementation (deferred)" in prd
    assert "complete `0.2.0` Workflow, Schema, Skill, Subgraph, Template, Profile, and" in prd
    assert "Fixture Bundle" in prd
    assert "HTML Report Builder" in impact
    assert "remain unimplemented" in impact


def test_v03_current_indexes_and_registry_lifecycle_are_consistent():
    registry = load_version_registry()
    v02 = registry.versions["0.2.0"]
    v03 = registry.versions["0.3.0"]
    assert (v02.status, v02.new_runs_allowed, v02.resume_allowed, v02.audit_allowed) == (
        "frozen_previous",
        False,
        True,
        True,
    )
    assert (v03.status, v03.new_runs_allowed, v03.resume_allowed, v03.audit_allowed) == (
        "current",
        True,
        True,
        True,
    )
    assert registry.default_new_run_version == "0.3.0"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    backend = (ROOT / "BACKEND_STRUCTURE.md").read_text(encoding="utf-8")
    prd_changelog = (ROOT / "PRD_CHANGELOG.md").read_text(encoding="utf-8")
    spec_changelog = (ROOT / "SPEC_CHANGELOG.md").read_text(encoding="utf-8")
    implementation_plan = (ROOT / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    progress = (ROOT / "progress.md").read_text(encoding="utf-8")
    assert "PRD_v0.3.md" in readme and "SPEC_v0.3.md" in readme
    assert "`contracts/0.3.0/`：当前 Bundle" in backend
    assert "Amendment / Current Source of Truth: `PRD_v0.3.md`" in prd_changelog
    assert "Amendment and Current Source of Truth: `SPEC_v0.3.md` / Contract `0.3.0`" in spec_changelog
    assert implementation_plan.count("[new / completed]") >= 3
    assert "P0-04-T11" in implementation_plan and "Decision B" in implementation_plan
    assert "contract_amendment_completed" in progress
    assert "真实 Renderer、HTML Builder" in progress
    assert "Visualization / Verifier Workflow" in progress


def test_v02_historical_decision_records_remain_byte_for_byte_preserved():
    expected = {
        "V0.2_CHANGE_IMPACT.md": "30fac2f828a0e20cf5009af5d2841ebfc0c8c657b1bb25df44ae756171342847",
        "PRD_CONSOLIDATION_REPORT.md": "55427f476ab80b625002025e96dcd10b79ae5d542c3ff33bf1323a3f1d59b169",
    }
    for filename, expected_hash in expected.items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected_hash
