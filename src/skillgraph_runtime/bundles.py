"""Fail-closed Contract Bundle registry and resolution helpers.

This module is static infrastructure for repository validation.  It does not
create or resume Runtime runs, write artifacts, or migrate data between
contract versions.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry as SchemaRegistry, Resource


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "contracts" / "registry.yaml"
REGISTRY_SCHEMA_PATH = REPOSITORY_ROOT / "contracts" / "registry.schema.json"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
SUPPORTED_OPERATIONS = frozenset({"new_run", "resume", "audit"})
LEGACY_SCHEMA_BY_REF_TYPE = {
    "source": "source.schema.json",
    "evidence": "evidence.schema.json",
    "claim": "claim.schema.json",
}
SHA256_PATTERN = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
VERSIONED_REFERENCE_PATTERN = re.compile(r"^(?P<identity>[a-z][a-z0-9_-]*)@(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$")


class DuplicateKeyError(ValueError):
    """Raised when a Registry YAML or JSON document repeats a mapping key."""


class ContractResolutionError(ValueError):
    """A deterministic, typed version or path resolution failure."""

    def __init__(self, message: str, *, code: str = "SCHEMA_VERSION_UNSUPPORTED", rule: str = "bundle_resolution") -> None:
        super().__init__(message)
        self.code = code
        self.rule = rule


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise DuplicateKeyError(f"Unhashable YAML key at line {key_node.start_mark.line + 1}") from exc
        if duplicate:
            raise DuplicateKeyError(f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _construct_unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_document(path: Path) -> Any:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ContractResolutionError(
            f"Document exceeds {MAX_DOCUMENT_BYTES} byte limit: {path}",
            code="INPUT_INVALID",
            rule="document_size",
        )
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text, object_pairs_hook=_construct_unique_json_object)
    loader = _UniqueKeySafeLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _contains_symlink(path: Path, root: Path) -> bool:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError:
        return True
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _relative_repository_path(
    value: str,
    *,
    repository_root: Path,
    allow_repository_root: bool = False,
    must_exist: bool = True,
    expect_directory: bool | None = None,
) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractResolutionError("Repository-relative path must be a non-empty string", code="INPUT_INVALID", rule="unsafe_path")
    if value == ".":
        if not allow_repository_root:
            raise ContractResolutionError("Repository root is not allowed for this reference", code="INPUT_INVALID", rule="unsafe_path")
    else:
        parsed = urlparse(value)
        raw_parts = value.split("/")
        if (
            parsed.scheme
            or parsed.netloc
            or value.startswith(("/", "\\"))
            or "\\" in value
            or re.match(r"^[A-Za-z]:", value)
            or any(part in {"", ".", ".."} for part in raw_parts)
        ):
            raise ContractResolutionError(f"Unsafe repository-relative path: {value}", code="INPUT_INVALID", rule="unsafe_path")
        if PurePosixPath(value).is_absolute():
            raise ContractResolutionError(f"Absolute path is forbidden: {value}", code="INPUT_INVALID", rule="unsafe_path")

    candidate = repository_root if value == "." else repository_root.joinpath(*value.split("/"))
    resolved_root = repository_root.resolve()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ContractResolutionError(f"Path escapes repository root: {value}", code="INPUT_INVALID", rule="unsafe_path") from exc
    if _contains_symlink(candidate, repository_root):
        raise ContractResolutionError(f"Symbolic links are forbidden in Contract paths: {value}", code="INPUT_INVALID", rule="unsafe_path")
    if must_exist and not candidate.exists():
        raise ContractResolutionError(f"Contract path does not exist: {value}", code="INPUT_INVALID", rule="missing_contract_asset")
    if must_exist and expect_directory is True and not candidate.is_dir():
        raise ContractResolutionError(f"Expected Contract directory: {value}", code="INPUT_INVALID", rule="contract_path_type")
    if must_exist and expect_directory is False and not candidate.is_file():
        raise ContractResolutionError(f"Expected Contract file: {value}", code="INPUT_INVALID", rule="contract_path_type")
    return resolved


@dataclass(frozen=True)
class VersionEntry:
    contract_version: str
    status: str
    bundle_root_ref: str
    bundle_root: Path
    new_runs_allowed: bool
    resume_allowed: bool
    audit_allowed: bool


@dataclass(frozen=True)
class CompatibilityRule:
    id: str
    source_contract_version: str
    target_contract_version: str
    ref_type: str
    purpose: str
    access: str
    current_manifest_allowed: bool
    state_driving_allowed: bool
    required_revalidation: tuple[str, ...]


@dataclass(frozen=True)
class VersionRegistry:
    path: Path
    default_new_run_version: str
    versions: Mapping[str, VersionEntry]
    default_compatibility_policy: str
    compatibility_rules: tuple[CompatibilityRule, ...]
    baseline_manifest_ref: str
    frozen_documents_sha256: Mapping[str, str]


@dataclass(frozen=True)
class ContractBundle:
    contract_version: str
    root: Path
    status: str
    operation: str


@dataclass(frozen=True)
class BundleContext:
    bundle: ContractBundle
    workflow_path: Path
    schema_dir: Path
    profile_dir: Path
    skill_dir: Path
    subgraph_dir: Path
    template_dir: Path
    fixture_manifest_path: Path


@dataclass(frozen=True)
class LegacyReferenceDecision:
    accepted: bool
    reason: str
    rule_id: str | None = None
    source_path: Path | None = None
    required_revalidation: tuple[str, ...] = ()


def load_version_registry(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    registry_path: Path | None = None,
    require_bundles: bool = True,
) -> VersionRegistry:
    repository_root = repository_root.resolve()
    path = registry_path or repository_root / "contracts" / "registry.yaml"
    schema_path = repository_root / "contracts" / "registry.schema.json"
    try:
        document = _load_document(path)
        schema = _load_document(schema_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        if isinstance(exc, ContractResolutionError):
            raise
        raise ContractResolutionError(f"Registry load failed: {exc}", code="INPUT_INVALID", rule="registry_load") from exc
    if not isinstance(document, dict) or not isinstance(schema, dict):
        raise ContractResolutionError("Registry and Registry Schema must be objects", code="INPUT_INVALID", rule="registry_type")
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path))
    if errors:
        first = errors[0]
        location = "$" + "".join(f".{part}" if isinstance(part, str) else f"[{part}]" for part in first.absolute_path)
        raise ContractResolutionError(f"Registry Schema validation failed at {location}: {first.message}", code="INPUT_INVALID", rule=str(first.validator or "registry_schema"))

    payload = document["registry"]
    versions: dict[str, VersionEntry] = {}
    for contract_version, raw in payload["versions"].items():
        root = _relative_repository_path(
            raw["bundle_root"],
            repository_root=repository_root,
            allow_repository_root=contract_version == "0.1.0",
            must_exist=require_bundles,
            expect_directory=True if require_bundles else None,
        )
        versions[contract_version] = VersionEntry(
            contract_version=contract_version,
            status=raw["status"],
            bundle_root_ref=raw["bundle_root"],
            bundle_root=root,
            new_runs_allowed=raw["new_runs_allowed"],
            resume_allowed=raw["resume_allowed"],
            audit_allowed=raw["audit_allowed"],
        )

    default_version = payload["default_new_run_version"]
    if default_version not in versions or not versions[default_version].new_runs_allowed:
        raise ContractResolutionError("Default new-run version must exist and allow new runs", rule="registry_default")
    if [version for version, entry in versions.items() if entry.status == "current"] != [default_version]:
        raise ContractResolutionError("Registry must have exactly one current version equal to the default", rule="registry_current")
    if [version for version, entry in versions.items() if entry.new_runs_allowed] != [default_version]:
        raise ContractResolutionError("Only the default current version may allow new runs", rule="registry_new_run")

    rules = tuple(
        CompatibilityRule(
            id=raw["id"],
            source_contract_version=raw["source_contract_version"],
            target_contract_version=raw["target_contract_version"],
            ref_type=raw["ref_type"],
            purpose=raw["purpose"],
            access=raw["access"],
            current_manifest_allowed=raw["current_manifest_allowed"],
            state_driving_allowed=raw["state_driving_allowed"],
            required_revalidation=tuple(raw["required_revalidation"]),
        )
        for raw in payload["compatibility_matrix"]["rules"]
    )
    identities = [(rule.source_contract_version, rule.target_contract_version, rule.ref_type, rule.purpose) for rule in rules]
    if len(identities) != len(set(identities)) or len({rule.id for rule in rules}) != len(rules):
        raise ContractResolutionError("Compatibility rules must have unique IDs and match identities", code="INPUT_INVALID", rule="compatibility_rule_identity")

    integrity = payload["integrity"]
    return VersionRegistry(
        path=path.resolve(),
        default_new_run_version=default_version,
        versions=versions,
        default_compatibility_policy=payload["compatibility_matrix"]["default_policy"],
        compatibility_rules=rules,
        baseline_manifest_ref=integrity["baseline_manifest"],
        frozen_documents_sha256=dict(integrity["frozen_documents_sha256"]),
    )


def resolve_contract_bundle(
    contract_version: str | None = None,
    *,
    operation: str = "new_run",
    repository_root: Path = REPOSITORY_ROOT,
    registry: VersionRegistry | None = None,
) -> ContractBundle:
    if operation not in SUPPORTED_OPERATIONS:
        raise ContractResolutionError(f"Unsupported bundle operation: {operation}", code="INPUT_INVALID", rule="bundle_operation")
    registry = registry or load_version_registry(repository_root=repository_root)
    if contract_version is None:
        if operation != "new_run":
            raise ContractResolutionError(f"contract_version is required for {operation}", code="INPUT_INVALID", rule="contract_version_required")
        contract_version = registry.default_new_run_version
    entry = registry.versions.get(contract_version)
    if entry is None:
        raise ContractResolutionError(f"Contract version is not registered: {contract_version}")
    allowed = {
        "new_run": entry.new_runs_allowed,
        "resume": entry.resume_allowed,
        "audit": entry.audit_allowed,
    }[operation]
    if not allowed:
        raise ContractResolutionError(f"Contract version {contract_version} does not allow {operation}")
    return ContractBundle(contract_version=contract_version, root=entry.bundle_root, status=entry.status, operation=operation)


def load_bundle_context(bundle: ContractBundle) -> BundleContext:
    root = bundle.root
    fixture_manifest = root / ("fixtures/contracts/manifest.json" if bundle.contract_version == "0.1.0" else "fixtures/manifest.json")
    required = {
        "workflow": root / "workflow.yaml",
        "schemas": root / "schemas",
        "profiles": root / "profiles",
        "skills": root / "skills",
        "subgraphs": root / "subgraphs",
        "templates": root / "templates",
        "fixture_manifest": fixture_manifest,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise ContractResolutionError(
            f"Bundle {bundle.contract_version} is incomplete; missing: {', '.join(sorted(missing))}",
            code="INPUT_INVALID",
            rule="missing_contract_asset",
        )
    for name, path in required.items():
        if _contains_symlink(path, root):
            raise ContractResolutionError(f"Bundle asset uses a symbolic link: {name}", code="INPUT_INVALID", rule="unsafe_path")
    return BundleContext(
        bundle=bundle,
        workflow_path=required["workflow"],
        schema_dir=required["schemas"],
        profile_dir=required["profiles"],
        skill_dir=required["skills"],
        subgraph_dir=required["subgraphs"],
        template_dir=required["templates"],
        fixture_manifest_path=fixture_manifest,
    )


def resolve_bundle_reference(
    context: BundleContext,
    reference: str,
    *,
    allowed_prefixes: tuple[str, ...] = (),
    must_exist: bool = True,
    expect_directory: bool | None = False,
) -> Path:
    """Resolve one reference strictly within the selected Bundle root."""
    path = _relative_repository_path(
        reference,
        repository_root=context.bundle.root,
        must_exist=must_exist,
        expect_directory=expect_directory,
    )
    if allowed_prefixes and not any(
        reference == prefix.rstrip("/") or reference.startswith(prefix.rstrip("/") + "/")
        for prefix in allowed_prefixes
    ):
        raise ContractResolutionError(
            f"Bundle reference must stay within {allowed_prefixes}: {reference}",
            code="INPUT_INVALID",
            rule="bundle_reference_scope",
        )
    return path


def require_bundle_version(reference: str, contract_version: str) -> str:
    """Return the identity from an ``identity@version`` reference or fail closed."""
    match = VERSIONED_REFERENCE_PATTERN.fullmatch(reference) if isinstance(reference, str) else None
    if match is None:
        raise ContractResolutionError(
            f"Versioned Contract reference is malformed: {reference!r}",
            code="INPUT_INVALID",
            rule="versioned_reference",
        )
    actual_version = match.group("version")
    if actual_version != contract_version:
        raise ContractResolutionError(
            f"Mixed-version reference {reference}; selected Bundle is {contract_version}",
            code="SCHEMA_VERSION_UNSUPPORTED",
            rule="mixed_bundle_version",
        )
    return match.group("identity")


def _load_schema_registry(schema_dir: Path) -> tuple[dict[str, dict[str, Any]], SchemaRegistry]:
    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        schema = _load_document(path)
        if not isinstance(schema, dict):
            raise ContractResolutionError(f"Schema must be an object: {path}", code="INPUT_INVALID", rule="schema_type")
        schema = dict(schema)
        schema.setdefault("$id", path.resolve().as_uri())
        schemas[path.name] = schema
        resources.append((path.resolve().as_uri(), Resource.from_contents(schema)))
    return schemas, SchemaRegistry().with_resources(resources)


def load_bundle_schemas(context: BundleContext) -> tuple[dict[str, dict[str, Any]], SchemaRegistry]:
    """Load only the selected Bundle's local Draft 2020-12 Schema registry."""
    return _load_schema_registry(context.schema_dir)


def validate_bundle(
    bundle: ContractBundle | BundleContext,
    *,
    registry: VersionRegistry | None = None,
) -> tuple[list[Any], int]:
    """Validate one Bundle through the parameterized static validator.

    The validator implementation is packaged in a private Runtime namespace.
    A source-tree fallback is allowed only when it is co-located with this
    module, never from an arbitrary caller-supplied repository root.
    """
    context = bundle if isinstance(bundle, BundleContext) else load_bundle_context(bundle)
    if registry is None:
        repository_root = context.bundle.root if context.bundle.contract_version == "0.1.0" else context.bundle.root.parents[1]
        registry = load_version_registry(repository_root=repository_root)
    try:
        from skillgraph_runtime._validation import validate_contracts as validator_module
    except ModuleNotFoundError:
        source_repository_root = Path(__file__).resolve().parents[2]
        validator_path = source_repository_root / "scripts" / "validate_contracts.py"
        if not validator_path.is_file():
            raise ContractResolutionError(
                "Packaged Contract validator is unavailable",
                code="INPUT_INVALID",
                rule="missing_repository_validator",
            )
        module_key = hashlib.sha256(str(validator_path).encode("utf-8")).hexdigest()[:16]
        module_name = f"_skillgraph_runtime_validator_{module_key}"
        validator_module = sys.modules.get(module_name)
        if validator_module is None:
            spec = importlib.util.spec_from_file_location(module_name, validator_path)
            if spec is None or spec.loader is None:
                raise ContractResolutionError(
                    "Repository validator cannot be loaded",
                    code="INPUT_INVALID",
                    rule="repository_validator_load",
                )
            validator_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = validator_module
            try:
                spec.loader.exec_module(validator_module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise
    validate_selected_bundle = validator_module.validate_bundle
    return validate_selected_bundle(context, version_registry=registry)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def evaluate_legacy_input_ref(
    reference: Mapping[str, Any],
    target_version: str,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    registry: VersionRegistry | None = None,
) -> LegacyReferenceDecision:
    registry = registry or load_version_registry(repository_root=repository_root)
    required = {"source_contract_version", "ref_type", "ref", "content_hash", "purpose"}
    if not isinstance(reference, Mapping) or set(reference) != required:
        return LegacyReferenceDecision(False, "LEGACY_REF_SHAPE_INVALID")
    source_version = reference["source_contract_version"]
    source_entry = registry.versions.get(source_version)
    if source_entry is None or source_version == target_version:
        return LegacyReferenceDecision(False, "SOURCE_CONTRACT_VERSION_UNSUPPORTED")
    if target_version not in registry.versions:
        return LegacyReferenceDecision(False, "TARGET_CONTRACT_VERSION_UNSUPPORTED")
    ref_value = reference["ref"]
    try:
        source_path = _relative_repository_path(
            ref_value,
            repository_root=repository_root.resolve(),
            must_exist=True,
            expect_directory=False,
        )
    except ContractResolutionError:
        return LegacyReferenceDecision(False, "LEGACY_REF_PATH_INVALID")
    if not _path_is_within(source_path, source_entry.bundle_root):
        return LegacyReferenceDecision(False, "LEGACY_REF_OUTSIDE_SOURCE_BUNDLE")
    for version, entry in registry.versions.items():
        if version != source_version and entry.bundle_root != repository_root.resolve() and _path_is_within(source_path, entry.bundle_root):
            return LegacyReferenceDecision(False, "LEGACY_REF_MIXED_BUNDLE")

    match = SHA256_PATTERN.fullmatch(str(reference["content_hash"]))
    if match is None:
        return LegacyReferenceDecision(False, "CONTENT_HASH_INVALID")
    actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual_hash.lower() != match.group(1).lower():
        return LegacyReferenceDecision(False, "CONTENT_HASH_MISMATCH", source_path=source_path)

    schema_name = LEGACY_SCHEMA_BY_REF_TYPE.get(reference["ref_type"])
    if schema_name is None:
        return LegacyReferenceDecision(False, "WORKFLOW_DRIVING_ARTIFACT_BLOCKED", source_path=source_path)
    try:
        document = _load_document(source_path)
        schemas, schema_registry = _load_schema_registry(source_entry.bundle_root / "schemas")
        schema = schemas[schema_name]
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError):
        return LegacyReferenceDecision(False, "SOURCE_SCHEMA_VALIDATION_FAILED", source_path=source_path)
    validator = Draft202012Validator(schema, registry=schema_registry, format_checker=FormatChecker())
    if next(validator.iter_errors(document), None) is not None:
        return LegacyReferenceDecision(False, "SOURCE_SCHEMA_VALIDATION_FAILED", source_path=source_path)

    rule = next(
        (
            item
            for item in registry.compatibility_rules
            if item.source_contract_version == source_version
            and item.target_contract_version == target_version
            and item.ref_type == reference["ref_type"]
            and item.purpose == reference["purpose"]
        ),
        None,
    )
    if rule is None:
        return LegacyReferenceDecision(False, "LEGACY_REF_DEFAULT_DENY", source_path=source_path)
    if rule.access != "read_only" or rule.current_manifest_allowed or rule.state_driving_allowed:
        return LegacyReferenceDecision(False, "LEGACY_RULE_UNSAFE", rule_id=rule.id, source_path=source_path)
    return LegacyReferenceDecision(
        True,
        "LEGACY_REF_ACCEPTED_READ_ONLY",
        rule_id=rule.id,
        source_path=source_path,
        required_revalidation=rule.required_revalidation,
    )


def verify_integrity(registry: VersionRegistry, *, repository_root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return deterministic integrity failures without modifying protected data."""
    failures: list[str] = []
    try:
        manifest_path = _relative_repository_path(
            registry.baseline_manifest_ref,
            repository_root=repository_root.resolve(),
            must_exist=True,
            expect_directory=False,
        )
        manifest = _load_document(manifest_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"baseline manifest: {exc}"]
    if (
        not isinstance(manifest, dict)
        or manifest.get("contract_version") != "0.1.0"
        or not isinstance(manifest.get("protected_roots"), list)
        or not isinstance(manifest.get("files"), dict)
    ):
        return ["baseline manifest has an invalid shape"]
    actual_files: set[str] = set()
    for root_ref in manifest["protected_roots"]:
        if root_ref == "workflow.yaml":
            if (repository_root / root_ref).is_file():
                actual_files.add(root_ref)
            continue
        root_path = repository_root / root_ref
        if root_path.is_dir():
            actual_files.update(
                path.relative_to(repository_root).as_posix()
                for path in root_path.rglob("*")
                if path.is_file()
            )
    expected_files = set(manifest["files"])
    missing_files = sorted(expected_files - actual_files)
    unexpected_files = sorted(actual_files - expected_files)
    if missing_files:
        failures.append("baseline inventory missing: " + ", ".join(missing_files))
    if unexpected_files:
        failures.append("baseline inventory unexpected: " + ", ".join(unexpected_files))
    for relative_path, expected_hash in sorted(manifest["files"].items()):
        try:
            path = _relative_repository_path(
                relative_path,
                repository_root=repository_root.resolve(),
                must_exist=True,
                expect_directory=False,
            )
        except ContractResolutionError as exc:
            failures.append(f"{relative_path}: {exc}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            failures.append(f"{relative_path}: expected {expected_hash}, got {actual_hash}")
    for filename, expected_hash in sorted(registry.frozen_documents_sha256.items()):
        path = repository_root / filename
        if not path.is_file():
            failures.append(f"{filename}: frozen document missing")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            failures.append(f"{filename}: expected {expected_hash}, got {actual_hash}")
    return failures
