from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
import scripts.validate_contracts as validator

from scripts.validate_contracts import (
    CONTRACT_VERSION,
    REQUIRED_SKILL_IDS,
    REQUIRED_TEMPLATE_CONTRACTS,
    ROOT,
    build_repository_catalog,
    load_document,
    readiness_writer_diagnostics,
    repository_inventory_diagnostics,
    resolve_repo_path,
    skill_contract_diagnostics,
    skill_markdown_diagnostics,
    template_contract_diagnostics,
    validate_instance,
)


def rules(diagnostics):
    return {item.rule for item in diagnostics}


@pytest.mark.parametrize("skill_id", sorted(REQUIRED_SKILL_IDS))
def test_v01_skill_contract_is_valid(skill_id, contract_env):
    schemas, registry, _ = contract_env
    catalog = build_repository_catalog()
    directory = ROOT / "skills" / skill_id
    document = load_document(directory / "skill.yaml")
    source = f"skills/{skill_id}/skill.yaml"

    assert validate_instance(document, "skill.schema.json", source, schemas, registry) == []
    assert skill_contract_diagnostics(document, source, skill_id, catalog, schemas) == []
    assert skill_markdown_diagnostics(
        (directory / "SKILL.md").read_text(encoding="utf-8"),
        f"skills/{skill_id}/SKILL.md",
        skill_id,
    ) == []


@pytest.mark.parametrize("relative_path,artifact_type", sorted(REQUIRED_TEMPLATE_CONTRACTS.items()))
def test_v01_template_contract_is_valid(relative_path, artifact_type):
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    assert template_contract_diagnostics(text, relative_path, artifact_type) == []


def test_skill_identity_version_and_markdown_sections_are_locked(contract_env):
    schemas, _, _ = contract_env
    catalog = build_repository_catalog()
    skill_id = "idea-intake"
    source = f"skills/{skill_id}/skill.yaml"
    document = load_document(ROOT / source)

    wrong_identity = deepcopy(document)
    wrong_identity["skill"]["id"] = "idea-intake-v2"
    assert "contract_identity" in rules(skill_contract_diagnostics(wrong_identity, source, skill_id, catalog, schemas))

    wrong_version = deepcopy(document)
    wrong_version["skill"]["version"] = "0.2.0"
    assert "contract_version" in rules(skill_contract_diagnostics(wrong_version, source, skill_id, catalog, schemas))

    markdown = (ROOT / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8")
    missing_section = markdown.replace("## Verification", "## Verification Removed", 1)
    assert "skill_markdown_contract" in rules(skill_markdown_diagnostics(missing_section, "SKILL.md", skill_id))
    assert skill_markdown_diagnostics(markdown.replace(f"# Skill: {skill_id}", "# Skill: replacement", 1), "SKILL.md", skill_id)[0].rule == "contract_identity"


def test_output_contract_references_and_permissions_are_closed(contract_env):
    schemas, _, _ = contract_env
    catalog = build_repository_catalog()
    source = "skills/idea-intake/skill.yaml"
    document = load_document(ROOT / source)

    dangling_schema = deepcopy(document)
    dangling_schema["output_contracts"][0]["schema_ref"] = "schemas/idea.schema.json#/$defs/missing"
    assert "output_schema_reference" in rules(skill_contract_diagnostics(dangling_schema, source, "idea-intake", catalog, schemas))

    remote_schema = deepcopy(document)
    remote_schema["output_contracts"][0]["schema_ref"] = "https://example.com/idea.schema.json"
    assert "output_schema_reference" in rules(skill_contract_diagnostics(remote_schema, source, "idea-intake", catalog, schemas))

    wrong_type = deepcopy(document)
    wrong_type["output_contracts"][0]["artifact_type"] = "research_contract"
    assert "output_artifact_type" in rules(skill_contract_diagnostics(wrong_type, source, "idea-intake", catalog, schemas))

    missing_write = deepcopy(document)
    missing_write["writes"] = []
    assert "output_contract_write" in rules(skill_contract_diagnostics(missing_write, source, "idea-intake", catalog, schemas))

    ungranted_write = deepcopy(document)
    ungranted_write["permissions"]["workspace_write"] = ["artifacts/elsewhere/"]
    assert "output_write_permission" in rules(skill_contract_diagnostics(ungranted_write, source, "idea-intake", catalog, schemas))


def test_template_reference_locks_markdown_artifact_type(contract_env):
    schemas, _, _ = contract_env
    catalog = build_repository_catalog()
    source = "skills/research-synthesis/skill.yaml"
    document = load_document(ROOT / source)

    dangling_template = deepcopy(document)
    dangling_template["output_contracts"][0]["template_ref"] = "templates/missing.md"
    assert "template_reference" in rules(skill_contract_diagnostics(dangling_template, source, "research-synthesis", catalog, schemas))

    wrong_type = deepcopy(document)
    wrong_type["output_contracts"][0]["artifact_type"] = "competitor_report"
    assert "output_artifact_type" in rules(skill_contract_diagnostics(wrong_type, source, "research-synthesis", catalog, schemas))


def test_build_readiness_verifier_is_the_unique_skill_writer():
    build = load_document(ROOT / "skills" / "build-readiness-verifier" / "skill.yaml")
    idea = load_document(ROOT / "skills" / "idea-intake" / "skill.yaml")
    assert readiness_writer_diagnostics({"build-readiness-verifier": build}) == []

    second_writer = deepcopy(idea)
    second_writer["output_contracts"][0]["schema_ref"] = "schemas/readiness-result.schema.json#/$defs/readiness_result"
    diagnostics = readiness_writer_diagnostics({
        "build-readiness-verifier": build,
        "idea-intake": second_writer,
    })
    assert "readiness_writer" in rules(diagnostics)


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("skill:\n  id: idea-intake\n  id: replacement\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        load_document(path)


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"id":"first","id":"replacement"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_document(path)


def test_repository_inventory_rejects_missing_and_unexpected_assets():
    catalog = build_repository_catalog()
    missing = replace(catalog, skill_ids=frozenset(set(catalog.skill_ids) - {"idea-intake"}))
    unexpected = replace(catalog, template_paths=frozenset({*catalog.template_paths, "templates/v0.2.md"}))

    assert "missing_contract_asset" in rules(repository_inventory_diagnostics(missing))
    assert "unexpected_contract_asset" in rules(repository_inventory_diagnostics(unexpected))


def test_contract_reference_rejects_remote_and_symbolic_link_paths(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        resolve_repo_path("https://example.com/schema.json", root=tmp_path)

    templates = tmp_path / "templates"
    templates.mkdir()
    link = templates / "link.md"
    link.write_text("test", encoding="utf-8")
    monkeypatch.setattr(validator, "_contains_symlink", lambda path, root: path.name == "link.md")
    with pytest.raises(ValueError, match="Symbolic links"):
        resolve_repo_path(
            "templates/link.md",
            root=tmp_path,
            allowed_root="templates",
            must_exist=True,
            reject_symlinks=True,
        )


def test_template_front_matter_identity_and_version_are_locked():
    source = "templates/prd.md"
    text = (ROOT / source).read_text(encoding="utf-8")
    wrong_id = text.replace("id: prd", "id: prd-v2", 1)
    wrong_version = text.replace(f"version: {CONTRACT_VERSION}", "version: 0.2.0", 1)
    assert "template_contract" in rules(template_contract_diagnostics(wrong_id, source, "prd"))
    assert "template_contract" in rules(template_contract_diagnostics(wrong_version, source, "prd"))
