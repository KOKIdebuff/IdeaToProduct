"""Deterministic, offline-only Report Bundle publication core.

Recovery provenance:
    product_discovery_skillgraph_runtime-0.2.0-py3-none-any.whl
    skillgraph_runtime/report_publisher.py

The recovered wheel depended on Report-specific methods that are not present
in the current ``RunStorage``.  This module therefore keeps its publication
transaction in a private isolated store.  It deliberately does not update the
Runtime Manifest, Event log, or Artifact repository; that integration belongs
to the later Runtime-writer task.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .domain import deep_thaw
from .errors import RuntimeContractError
from .fact_provenance import canonical_value_hash


_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]+$")
_DOM_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_SECTION_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
_ARTIFACT_REF = re.compile(r"^(ART-[A-Za-z0-9_-]+)@([1-9][0-9]*)$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_SVG_BYTES = 5 * 1024 * 1024
_DIRECTORY_COMMIT_ATTEMPTS = 5
_DIRECTORY_COMMIT_RETRY_SECONDS = 0.02


def _commit_staging_directory(staging_root: Path, final_root: Path) -> None:
    """Commit a complete bundle directory while tolerating transient file locks.

    Windows file scanners can briefly retain handles to files that were just
    flushed, causing an otherwise valid directory rename to fail with access
    denied. Retry only while the source still exists and the destination does
    not; every real conflict or persistent error remains fail-closed.
    """

    for attempt in range(_DIRECTORY_COMMIT_ATTEMPTS):
        try:
            os.replace(staging_root, final_root)
            return
        except PermissionError:
            staging_exists = staging_root.exists()
            final_exists = final_root.exists()
            if final_exists and not staging_exists:
                return
            if final_exists:
                raise RuntimeContractError(
                    "Report Bundle version already exists",
                    code="IDEMPOTENCY_CONFLICT",
                    rule="report_append_only",
                )
            if not staging_exists or attempt + 1 == _DIRECTORY_COMMIT_ATTEMPTS:
                raise
            time.sleep(_DIRECTORY_COMMIT_RETRY_SECONDS * (attempt + 1))
_MAX_REPORT_BYTES = 10 * 1024 * 1024
_MAX_TEMPLATE_BYTES = 1024 * 1024
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(deep_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _key_hash(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise RuntimeContractError(
            "idempotency_key must be a non-empty bounded string", rule="report_idempotency"
        )
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _publication_identity_payload(
    *,
    report_ref: str,
    base_report_ref: str | None,
    key_hash: str,
    request_hash: str,
    publication: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the non-circular identity bound into pointer and inventory."""

    return {
        "report_ref": report_ref,
        "base_report_ref": base_report_ref,
        "idempotency_key_hash": key_hash,
        "request_hash": request_hash,
        "publication": deep_thaw(publication),
    }


def _artifact_ref(document: Mapping[str, Any], *, expected_type: str, rule: str) -> str:
    header = document.get("artifact") if isinstance(document, Mapping) else None
    if not isinstance(header, Mapping) or header.get("type") != expected_type:
        raise RuntimeContractError(f"Artifact is not typed as {expected_type}", code="SCHEMA_INVALID", rule=rule)
    artifact_id = header.get("id")
    version = header.get("version")
    if (
        not isinstance(artifact_id, str)
        or isinstance(version, bool)
        or not isinstance(version, int)
        or _ARTIFACT_REF.fullmatch(f"{artifact_id}@{version}") is None
    ):
        raise RuntimeContractError("Artifact header is malformed", code="SCHEMA_INVALID", rule=rule)
    return f"{artifact_id}@{version}"


def _safe_relative(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw or ":" in raw:
        raise RuntimeContractError(
            "Report path must be a safe POSIX relative path",
            code="SECURITY_POLICY_VIOLATION",
            rule="report_asset_path",
        )
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeContractError(
            "Report path escapes its version directory",
            code="SECURITY_POLICY_VIOLATION",
            rule="report_asset_path",
        )
    for part in path.parts:
        if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in _RESERVED:
            raise RuntimeContractError(
                "Report path has a reserved platform component",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_asset_path",
            )
    return path


def _safe_http_url(value: Any) -> str:
    if not isinstance(value, str) or not value or any(ord(character) < 33 for character in value):
        raise RuntimeContractError(
            "Citation Source has no canonical URL", code="SCHEMA_INVALID", rule="report_citation"
        )
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeContractError(
            "Citation Source URL has an invalid port",
            code="SECURITY_POLICY_VIOLATION",
            rule="report_citation",
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port is not None and not 1 <= port <= 65535
    ):
        raise RuntimeContractError(
            "Citation Source URL is not a safe HTTP(S) URL",
            code="SECURITY_POLICY_VIOLATION",
            rule="report_citation",
        )
    return value


def _source_metadata(source_id: str, record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    if record.get("id") != source_id:
        raise RuntimeContractError(
            "Citation Source identity does not match its index key", code="SCHEMA_INVALID", rule="report_citation"
        )
    url = _safe_http_url(record.get("canonical_url"))
    metadata = record.get("citation_metadata")
    if not isinstance(metadata, Mapping):
        raise RuntimeContractError(
            "Citation Source has no verified metadata", code="SCHEMA_INVALID", rule="report_citation"
        )
    values = {
        "publisher_short_name": metadata.get("publisher_short_name"),
        "title": record.get("title"),
        "excerpt": metadata.get("excerpt"),
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise RuntimeContractError(
            f"Citation Source {source_id} has incomplete metadata", code="SCHEMA_INVALID", rule="report_citation"
        )
    return str(values["publisher_short_name"]), str(values["title"]), str(values["excerpt"]), url


class _TemplatePolicyParser(HTMLParser):
    """Small static-shell validator; it never rewrites or executes HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_open = 0
        self.main_close = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "main":
            self.main_open += 1
        if lowered in {"script", "iframe", "object", "embed", "link", "base", "form"}:
            raise RuntimeContractError(
                "Report template contains an active or external-resource element",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_template",
            )
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if name.startswith("on"):
                raise RuntimeContractError(
                    "Report template contains an event handler",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_template",
                )
            if name in {"src", "srcset"} and value:
                raise RuntimeContractError(
                    "Report template contains an undeclared asset",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_template",
                )
            if name == "href" and value and not value.startswith("#"):
                raise RuntimeContractError(
                    "Report template contains an external link",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_template",
                )
            if name == "style" and ("url(" in value.lower() or "@import" in value.lower()):
                raise RuntimeContractError(
                    "Report template contains an external CSS reference",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_template",
                )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "main":
            self.main_close += 1

    def handle_entityref(self, name: str) -> None:
        return


def _validate_template(template: str) -> None:
    lowered = template.lower()
    if (
        not template.startswith("<!doctype html>")
        or len(template.encode()) > _MAX_TEMPLATE_BYTES
        or "@import" in lowered
        or re.search(r"url\s*\(", lowered)
        or "<?xml-stylesheet" in lowered
    ):
        raise RuntimeContractError(
            "Report template is not a safe static HTML shell", code="SCHEMA_INVALID", rule="report_template"
        )
    parser = _TemplatePolicyParser()
    try:
        parser.feed(template)
        parser.close()
    except RuntimeContractError:
        raise
    except Exception as exc:
        raise RuntimeContractError(
            "Report template is malformed", code="SCHEMA_INVALID", rule="report_template"
        ) from exc
    if parser.main_open != 1 or parser.main_close != 1 or template.count("<main>") != 1 or template.count("</main>") != 1:
        raise RuntimeContractError(
            "Report template must contain one literal main shell", code="SCHEMA_INVALID", rule="report_template"
        )


def _validate_canonical_svg(svg: str) -> None:
    if not isinstance(svg, str) or not svg or len(svg.encode()) > _MAX_SVG_BYTES:
        raise RuntimeContractError(
            "Chart Bundle SVG is malformed or too large", code="SCHEMA_INVALID", rule="report_svg"
        )
    lowered = svg.lower()
    if "<!doctype" in lowered or "<!entity" in lowered or "<?xml-stylesheet" in lowered or "@import" in lowered:
        raise RuntimeContractError(
            "Chart Bundle SVG contains an external or active declaration",
            code="SECURITY_POLICY_VIOLATION",
            rule="report_svg",
        )
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise RuntimeContractError(
            "Chart Bundle SVG is malformed", code="SCHEMA_INVALID", rule="report_svg"
        ) from exc
    local_name = lambda value: value.rsplit("}", 1)[-1]
    if local_name(root.tag) != "svg" or root.get("viewBox") is None or root.get("role") != "img":
        raise RuntimeContractError(
            "Chart Bundle SVG is not canonical and accessible", code="SCHEMA_INVALID", rule="report_svg"
        )
    direct_children = {local_name(child.tag) for child in root}
    if not {"title", "desc"} <= direct_children:
        raise RuntimeContractError(
            "Chart Bundle SVG is not canonical and accessible", code="SCHEMA_INVALID", rule="report_svg"
        )
    for element in root.iter():
        if local_name(element.tag) in {"script", "foreignObject", "image"}:
            raise RuntimeContractError(
                "Chart Bundle SVG contains a forbidden element",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_svg",
            )
        if local_name(element.tag) == "style" and ("url(" in (element.text or "").lower() or "@import" in (element.text or "").lower()):
            raise RuntimeContractError(
                "Chart Bundle SVG contains an external CSS reference",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_svg",
            )
        for attribute, raw_value in element.attrib.items():
            name = local_name(attribute).lower()
            value = str(raw_value)
            if name.startswith("on"):
                raise RuntimeContractError(
                    "Chart Bundle SVG contains an event handler",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_svg",
                )
            if name in {"href", "src"} and value:
                raise RuntimeContractError(
                    "Chart Bundle SVG contains an external reference",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_svg",
                )
            if "url(" in value.lower():
                raise RuntimeContractError(
                    "Chart Bundle SVG contains a referenced resource",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_svg",
                )


@dataclass(frozen=True)
class ReportPublicationRequest:
    """All validated in-memory inputs required to publish one Report version."""

    run_id: str
    attempt_id: str
    report_ref: str
    expected_base_report_ref: str | None
    idempotency_key: str
    publication_projection: Mapping[str, Any]
    chart_bundle_collection: Mapping[str, Any]
    profile: Mapping[str, Any]
    source_records: Mapping[str, Mapping[str, Any]]
    fact_values: Mapping[str, Any]
    template_path: Path
    fixture_svg_assets: Mapping[str, str] | None = None


def build_competitor_report_document(
    *,
    artifact: Mapping[str, Any],
    publication_pointer: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the typed Artifact proposal owned by the future Runtime writer.

    This helper does not persist the proposal.  Keeping Artifact Header commit
    outside the isolated Publisher preserves the Runtime single-writer
    boundary while still allowing the core result to be validated against the
    staged ``competitor_report`` Contract.
    """

    report_ref = _artifact_ref(
        {"artifact": artifact}, expected_type="competitor_report", rule="report_artifact"
    )
    if publication_pointer.get("report_ref") != report_ref:
        raise RuntimeContractError(
            "Report Artifact identity does not match the published Bundle",
            code="SCHEMA_INVALID",
            rule="report_artifact",
        )
    required = (
        "report_publication_projection_ref",
        "chart_bundle_collection_ref",
        "root_ref",
        "inventory_ref",
        "base_report_ref",
    )
    if any(field not in publication_pointer for field in required):
        raise RuntimeContractError(
            "Report publication pointer is incomplete", code="SCHEMA_INVALID", rule="report_artifact"
        )
    for field in ("root_ref", "inventory_ref"):
        value = publication_pointer[field]
        if not isinstance(value, str):
            raise RuntimeContractError(
                "Report publication path is malformed", code="SCHEMA_INVALID", rule="report_artifact"
            )
        _safe_relative(value)
    if publication_pointer["base_report_ref"] is not None:
        raise RuntimeContractError(
            "Initial Report builder cannot publish a successor",
            code="STATE_VERSION_CONFLICT",
            rule="report_cas",
        )
    return {
        "artifact": dict(artifact),
        "publication_kind": "INITIAL",
        "report_publication_projection_ref": publication_pointer["report_publication_projection_ref"],
        "chart_bundle_collection_ref": publication_pointer["chart_bundle_collection_ref"],
        "report_root_ref": publication_pointer["root_ref"],
        "inventory_ref": publication_pointer["inventory_ref"],
        "base_report_ref": publication_pointer["base_report_ref"],
        "verification": {"status": "PENDING", "verification_ref": None},
        "scoring": {"status": "NOT_PERFORMED", "score_collection_ref": None},
    }


class _IsolatedReportStore:
    """Report-only append store; deliberately separate from Runtime state."""

    def __init__(self, storage_root: Path, run_id: str) -> None:
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise RuntimeContractError("run_id is malformed for Report storage", rule="report_run_id")
        self.run_root = Path(storage_root).resolve() / "runs" / run_id

    def _path(self, relative: str) -> Path:
        safe = _safe_relative(relative)
        self.run_root.mkdir(parents=True, exist_ok=True)
        if self.run_root.is_symlink():
            raise RuntimeContractError(
                "Report Run root cannot be a symbolic link",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_asset_path",
            )
        root = self.run_root.resolve()
        candidate = self.run_root.joinpath(*safe.parts)
        parent = candidate.parent
        while parent != root and parent != parent.parent:
            if parent.exists() and parent.is_symlink():
                raise RuntimeContractError(
                    "Report path crosses a symbolic link",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_asset_path",
                )
            parent = parent.parent
        try:
            candidate.parent.resolve().relative_to(root)
        except ValueError as exc:
            raise RuntimeContractError(
                "Report path escapes the Run root",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_asset_path",
            ) from exc
        return candidate

    def _read_json(self, relative: str) -> Any:
        path = self._path(relative)
        if path.is_symlink():
            raise RuntimeContractError(
                "Report metadata path is a symbolic link",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_pointer",
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeContractError(
                "Report metadata is unreadable", code="SCHEMA_INVALID", rule="report_pointer"
            ) from exc

    def _atomic_json(self, relative: str, value: Any) -> None:
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _write_immutable_json(self, relative: str, value: Any) -> None:
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise RuntimeContractError(
                "Append-only Report record already exists", rule="report_append_only", details={"path": relative}
            )
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def current_report(self) -> Mapping[str, Any] | None:
        path = self._path("runtime/current-report.json")
        if not path.is_file():
            return None
        pointer = self._read_json("runtime/current-report.json")
        required = {
            "report_ref",
            "root_ref",
            "inventory_ref",
            "inventory_hash",
            "base_report_ref",
            "idempotency_key_hash",
            "request_hash",
            "result_identity",
            "attempt_id",
            "report_publication_projection_ref",
            "chart_bundle_collection_ref",
        }
        if not isinstance(pointer, Mapping) or not required <= set(pointer):
            raise RuntimeContractError(
                "Current Report pointer is invalid", code="SCHEMA_INVALID", rule="report_pointer"
            )
        if not isinstance(pointer.get("report_ref"), str) or _ARTIFACT_REF.fullmatch(pointer["report_ref"]) is None:
            raise RuntimeContractError(
                "Current Report reference is invalid", code="SCHEMA_INVALID", rule="report_pointer"
            )
        base_report_ref = pointer.get("base_report_ref")
        if base_report_ref is not None and (
            not isinstance(base_report_ref, str) or _ARTIFACT_REF.fullmatch(base_report_ref) is None
        ):
            raise RuntimeContractError(
                "Current Report base reference is invalid", code="SCHEMA_INVALID", rule="report_pointer"
            )
        for field in ("idempotency_key_hash", "request_hash", "result_identity", "inventory_hash"):
            if not isinstance(pointer.get(field), str) or _SHA256.fullmatch(pointer[field]) is None:
                raise RuntimeContractError(
                    "Current Report identity hash is invalid", code="SCHEMA_INVALID", rule="report_pointer"
                )
        if (
            not isinstance(pointer.get("attempt_id"), str)
            or not pointer["attempt_id"]
            or not isinstance(pointer.get("report_publication_projection_ref"), str)
            or _ARTIFACT_REF.fullmatch(pointer["report_publication_projection_ref"]) is None
            or not isinstance(pointer.get("chart_bundle_collection_ref"), str)
            or _ARTIFACT_REF.fullmatch(pointer["chart_bundle_collection_ref"]) is None
        ):
            raise RuntimeContractError(
                "Current Report publication metadata is invalid", code="SCHEMA_INVALID", rule="report_pointer"
            )
        inventory_ref = pointer.get("inventory_ref")
        root_ref = pointer.get("root_ref")
        if not isinstance(inventory_ref, str) or not isinstance(root_ref, str):
            raise RuntimeContractError(
                "Current Report path is invalid", code="SCHEMA_INVALID", rule="report_pointer"
            )
        inventory_path = self._path(inventory_ref)
        root_path = self._path(root_ref)
        version_root = f"artifacts/02-research/competitors/report-bundles/{pointer['report_ref']}"
        if root_ref != f"{version_root}/competitor-report.html" or inventory_ref != f"{version_root}/inventory.json":
            raise RuntimeContractError(
                "Current Report paths do not match its immutable version",
                code="SCHEMA_INVALID",
                rule="report_pointer",
            )
        if inventory_path.is_symlink() or root_path.is_symlink() or not inventory_path.is_file() or not root_path.is_file():
            raise RuntimeContractError(
                "Current Report points to an unsafe or missing file", code="SCHEMA_INVALID", rule="report_pointer"
            )
        inventory = self._read_json(inventory_ref)
        files = inventory.get("files") if isinstance(inventory, Mapping) else None
        if not isinstance(files, list) or not files or inventory.get("report_ref") != pointer["report_ref"]:
            raise RuntimeContractError(
                "Current Report inventory is malformed", code="SCHEMA_INVALID", rule="report_pointer"
            )
        publication = {
            "attempt_id": pointer["attempt_id"],
            "report_publication_projection_ref": pointer["report_publication_projection_ref"],
            "chart_bundle_collection_ref": pointer["chart_bundle_collection_ref"],
        }
        identity_payload = _publication_identity_payload(
            report_ref=pointer["report_ref"],
            base_report_ref=base_report_ref,
            key_hash=pointer["idempotency_key_hash"],
            request_hash=pointer["request_hash"],
            publication=publication,
        )
        expected_result_identity = _canonical_hash(identity_payload)
        expected_inventory_identity = {**identity_payload, "result_identity": expected_result_identity}
        if (
            pointer["result_identity"] != expected_result_identity
            or inventory.get("publication_identity") != expected_inventory_identity
        ):
            raise RuntimeContractError(
                "Current Report publication identity does not match its immutable inventory",
                code="SCHEMA_INVALID",
                rule="report_pointer",
            )
        inventory_root = inventory_path.parent.resolve()
        seen: set[str] = set()
        for item in files:
            if not isinstance(item, Mapping) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                raise RuntimeContractError(
                    "Current Report inventory entry is malformed", code="SCHEMA_INVALID", rule="report_pointer"
                )
            relative = _safe_relative(item["path"])
            if relative.as_posix() in seen:
                raise RuntimeContractError(
                    "Current Report inventory has duplicate paths", code="SCHEMA_INVALID", rule="report_pointer"
                )
            seen.add(relative.as_posix())
            target = inventory_root.joinpath(*relative.parts)
            try:
                target.parent.resolve().relative_to(inventory_root)
            except ValueError as exc:
                raise RuntimeContractError(
                    "Current Report inventory path escapes its version directory",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_pointer",
                ) from exc
            if target.is_symlink() or not target.is_file():
                raise RuntimeContractError(
                    "Current Report inventory points to an unsafe or missing file",
                    code="SCHEMA_INVALID",
                    rule="report_pointer",
                )
            actual_hash = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_hash != item["sha256"]:
                raise RuntimeContractError(
                    "Current Report inventory file hash does not match",
                    code="SCHEMA_INVALID",
                    rule="report_pointer",
                )
        if "competitor-report.html" not in seen or any(
            path != "competitor-report.html"
            and (not path.startswith("visualizations/") or not path.endswith("/chart.svg"))
            for path in seen
        ):
            raise RuntimeContractError(
                "Current Report inventory contains an undeclared file",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_pointer",
            )
        actual_inventory_hash = _canonical_hash(inventory)
        if actual_inventory_hash != pointer.get("inventory_hash"):
            raise RuntimeContractError(
                "Current Report inventory hash does not match", code="SCHEMA_INVALID", rule="report_pointer"
            )
        return pointer

    def publication_record(self, key_hash: str) -> Mapping[str, Any] | None:
        if not isinstance(key_hash, str) or _SHA256.fullmatch(key_hash) is None:
            raise RuntimeContractError("Report idempotency key hash is malformed", rule="report_idempotency")
        path = self._path(f"runtime/report-publications/{key_hash.removeprefix('sha256:')}.json")
        return None if not path.is_file() else self._read_json(path.relative_to(self.run_root).as_posix())

    def _publication_record_value(self, pointer: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "idempotency_key_hash": pointer["idempotency_key_hash"],
            "request_hash": pointer["request_hash"],
            "result_identity": pointer["result_identity"],
            "pointer": deep_thaw(pointer),
        }

    def recover_publication_record(
        self,
        *,
        key_hash: str,
        request_hash: str,
        current: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        """Rebuild a missing index only from a fully committed current result."""

        committed = self.current_report() if current is None else current
        if committed is None or committed.get("idempotency_key_hash") != key_hash:
            return None
        if committed.get("request_hash") != request_hash:
            raise RuntimeContractError(
                "Report idempotency key was reused with a different request",
                code="IDEMPOTENCY_CONFLICT",
                rule="report_idempotency",
            )
        self._write_immutable_json(
            f"runtime/report-publications/{key_hash.removeprefix('sha256:')}.json",
            self._publication_record_value(committed),
        )
        return committed

    def publish(
        self,
        *,
        report_ref: str,
        expected_base_report_ref: str | None,
        key_hash: str,
        request_hash: str,
        root_html: str,
        assets: Mapping[str, str],
        publication: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        match = _ARTIFACT_REF.fullmatch(report_ref)
        if match is None:
            raise RuntimeContractError("Report reference is malformed", code="SCHEMA_INVALID", rule="report_ref")
        if expected_base_report_ref is not None:
            base_match = _ARTIFACT_REF.fullmatch(expected_base_report_ref)
            if base_match is None:
                raise RuntimeContractError(
                    "Expected base Report reference is malformed", code="SCHEMA_INVALID", rule="report_cas"
                )
            if match.group(1) != base_match.group(1) or int(match.group(2)) != int(base_match.group(2)) + 1:
                raise RuntimeContractError(
                    "Report successor must increment the same Artifact identity",
                    code="STATE_VERSION_CONFLICT",
                    rule="report_cas",
                )
        if not root_html.startswith("<!doctype html>") or len(root_html.encode()) > _MAX_REPORT_BYTES:
            raise RuntimeContractError("Report root is malformed or too large", code="SCHEMA_INVALID", rule="report_html")
        existing = self.publication_record(key_hash)
        if existing is not None:
            if existing.get("idempotency_key_hash") != key_hash or existing.get("request_hash") != request_hash:
                raise RuntimeContractError(
                    "Report idempotency key was reused with a different request",
                    code="IDEMPOTENCY_CONFLICT",
                    rule="report_idempotency",
                )
            pointer = existing.get("pointer")
            if not isinstance(pointer, Mapping):
                raise RuntimeContractError(
                    "Report idempotency record is malformed", code="SCHEMA_INVALID", rule="report_idempotency"
                )
            current = self.current_report()
            if (
                current is None
                or deep_thaw(current) != deep_thaw(pointer)
                or existing.get("result_identity") != current.get("result_identity")
            ):
                raise RuntimeContractError(
                    "Report idempotency record does not identify the committed current result",
                    code="STATE_VERSION_CONFLICT",
                    rule="report_cas",
                )
            return pointer

        current = self.current_report()
        recovered = self.recover_publication_record(
            key_hash=key_hash,
            request_hash=request_hash,
            current=current,
        )
        if recovered is not None:
            return recovered
        current_ref = None if current is None else current["report_ref"]
        if current_ref != expected_base_report_ref:
            raise RuntimeContractError(
                "Report publication base version is stale",
                code="STATE_VERSION_CONFLICT",
                rule="report_cas",
                details={"expected_base_report_ref": expected_base_report_ref, "current_report_ref": current_ref},
            )

        normalized_assets: dict[str, str] = {}
        for raw_path, value in assets.items():
            path = _safe_relative(raw_path).as_posix()
            if not path.startswith("visualizations/") or not path.endswith("/chart.svg"):
                raise RuntimeContractError(
                    "Report assets must be contained canonical SVG files",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="report_asset_path",
                )
            if path in normalized_assets or not isinstance(value, str) or not value:
                raise RuntimeContractError(
                    "Report asset is malformed or duplicated", code="SCHEMA_INVALID", rule="report_asset"
                )
            normalized_assets[path] = value

        version_root = f"artifacts/02-research/competitors/report-bundles/{report_ref}"
        root_ref = f"{version_root}/competitor-report.html"
        inventory_ref = f"{version_root}/inventory.json"
        final_root = self._path(version_root)
        if final_root.exists():
            raise RuntimeContractError(
                "Report Bundle version already exists", code="IDEMPOTENCY_CONFLICT", rule="report_append_only"
            )
        staging_root = self._path(
            f"artifacts/02-research/competitors/report-bundles/.staging/{report_ref}-{uuid.uuid4().hex}"
        )
        staging_root.mkdir(parents=True, exist_ok=False)

        def write_text(relative: str, value: str) -> None:
            target = staging_root.joinpath(*_safe_relative(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())

        write_text("competitor-report.html", root_html)
        for path, value in sorted(normalized_assets.items()):
            write_text(path, value)
        publication_metadata = deep_thaw(publication)
        identity_payload = _publication_identity_payload(
            report_ref=report_ref,
            base_report_ref=expected_base_report_ref,
            key_hash=key_hash,
            request_hash=request_hash,
            publication=publication_metadata,
        )
        result_identity = _canonical_hash(identity_payload)
        inventory = {
            "report_ref": report_ref,
            "publication_identity": {**identity_payload, "result_identity": result_identity},
            "files": [
                {
                    "path": "competitor-report.html",
                    "sha256": "sha256:" + hashlib.sha256(root_html.encode()).hexdigest(),
                },
                *[
                    {"path": path, "sha256": "sha256:" + hashlib.sha256(value.encode()).hexdigest()}
                    for path, value in sorted(normalized_assets.items())
                ],
            ],
        }
        write_text(
            "inventory.json",
            json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        )
        final_root.parent.mkdir(parents=True, exist_ok=True)
        _commit_staging_directory(staging_root, final_root)
        pointer = {
            **publication_metadata,
            "report_ref": report_ref,
            "base_report_ref": expected_base_report_ref,
            "idempotency_key_hash": key_hash,
            "request_hash": request_hash,
            "result_identity": result_identity,
            "root_ref": root_ref,
            "inventory_ref": inventory_ref,
            "inventory_hash": _canonical_hash(inventory),
        }
        self._atomic_json("runtime/current-report.json", pointer)
        self._write_immutable_json(
            f"runtime/report-publications/{key_hash.removeprefix('sha256:')}.json",
            self._publication_record_value(pointer),
        )
        return pointer


class ImmutableReportBundlePublisher:
    """Build and publish one strictly local, append-only HTML Report Bundle."""

    def __init__(self, storage_root: Path, *, fixture_assets_allowed: bool = False) -> None:
        self.storage_root = Path(storage_root)
        self.fixture_assets_allowed = fixture_assets_allowed

    @staticmethod
    def _template(path: Path) -> str:
        template_path = Path(path)
        if template_path.is_symlink():
            raise RuntimeContractError(
                "Report template cannot be a symbolic link",
                code="SECURITY_POLICY_VIOLATION",
                rule="report_template",
            )
        try:
            template = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeContractError(
                "Report template is unavailable", code="SOURCE_UNAVAILABLE", rule="report_template"
            ) from exc
        _validate_template(template)
        return template

    @staticmethod
    def _request_hash(request: ReportPublicationRequest, template: str, svg_assets: Mapping[str, str] | None = None) -> tuple[str, str]:
        if svg_assets is None:
            svg_assets = request.fixture_svg_assets or {}
        key_hash = _key_hash(request.idempotency_key)
        request_hash = _canonical_hash(
            {
                "run_id": request.run_id,
                "attempt_id": request.attempt_id,
                "report_ref": request.report_ref,
                "expected_base_report_ref": request.expected_base_report_ref,
                "publication_projection": request.publication_projection,
                "chart_bundle_collection": request.chart_bundle_collection,
                "profile": request.profile,
                "source_records": request.source_records,
                "fact_values": request.fact_values,
                "svg_assets": svg_assets,
                "template_hash": "sha256:" + hashlib.sha256(template.encode()).hexdigest(),
            }
        )
        return key_hash, request_hash

    @staticmethod
    def _required_chart_types(profile: Mapping[str, Any], *, observed_types: set[str]) -> set[str]:
        visualizations = profile.get("competitor_visualizations")
        if not isinstance(visualizations, Mapping):
            raise RuntimeContractError(
                "Product Profile has no visualization contract", code="SCHEMA_INVALID", rule="report_chart_coverage"
            )
        required = visualizations.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(value, str) or _SECTION_ID.fullmatch(value) is None for value in required
        ):
            raise RuntimeContractError(
                "Product Profile has malformed required visualizations",
                code="SCHEMA_INVALID",
                rule="report_chart_coverage",
            )
        selected = set(required)
        choice = visualizations.get("choose_one")
        if choice is not None:
            if not isinstance(choice, Mapping):
                raise RuntimeContractError(
                    "Product Profile has a malformed visualization choice",
                    code="SCHEMA_INVALID",
                    rule="report_chart_coverage",
                )
            options = choice.get("options")
            if (
                not isinstance(options, list)
                or any(not isinstance(value, str) or _SECTION_ID.fullmatch(value) is None for value in options)
                or choice.get("selected_by") != "research_contract"
            ):
                raise RuntimeContractError(
                    "Product Profile has a malformed visualization choice",
                    code="SCHEMA_INVALID",
                    rule="report_chart_coverage",
                )
            realized = set(options) & observed_types
            if len(realized) != 1:
                raise RuntimeContractError(
                    "Profile visualization choice is unresolved",
                    code="DEPENDENCY_NOT_READY",
                    rule="report_chart_coverage",
                )
            selected.update(realized)
        if not selected:
            raise RuntimeContractError(
                "Product Profile requires no visualizations", code="SCHEMA_INVALID", rule="report_chart_coverage"
            )
        return selected

    def _chart_assets(self, request: ReportPublicationRequest, svg_assets: Mapping[str, str]) -> tuple[dict[str, str], str]:
        collection = request.chart_bundle_collection
        bundles = collection.get("bundles") if isinstance(collection, Mapping) else None
        if not isinstance(bundles, list) or not bundles:
            raise RuntimeContractError(
                "Chart Bundle collection is missing", code="DEPENDENCY_NOT_READY", rule="report_chart_coverage"
            )
        observed: dict[str, Mapping[str, Any]] = {}
        for bundle in bundles:
            if not isinstance(bundle, Mapping):
                raise RuntimeContractError(
                    "Chart Bundle collection contains a malformed entry",
                    code="SCHEMA_INVALID",
                    rule="report_chart_coverage",
                )
            _artifact_ref(bundle, expected_type="chart_bundle", rule="report_chart_coverage")
            chart = bundle.get("chart")
            chart_type = chart.get("type") if isinstance(chart, Mapping) else None
            if not isinstance(chart_type, str) or _SECTION_ID.fullmatch(chart_type) is None:
                raise RuntimeContractError(
                    "Chart Bundle has no safe chart type", code="SCHEMA_INVALID", rule="report_chart_coverage"
                )
            if chart_type in observed:
                raise RuntimeContractError(
                    "Chart Bundle collection has duplicate chart types",
                    code="SCHEMA_INVALID",
                    rule="report_chart_coverage",
                )
            claim_refs = bundle.get("claim_refs")
            evidence_ids = bundle.get("evidence_ids")
            if (
                not isinstance(claim_refs, list)
                or not claim_refs
                or len(claim_refs) != len(set(claim_refs))
                or not isinstance(evidence_ids, list)
                or not evidence_ids
                or len(evidence_ids) != len(set(evidence_ids))
            ):
                raise RuntimeContractError(
                    "Chart Bundle lacks explicit Claim/Evidence provenance",
                    code="SCHEMA_INVALID",
                    rule="report_chart_provenance",
                )
            observed[chart_type] = bundle
        required_types = self._required_chart_types(request.profile, observed_types=set(observed))
        missing = sorted(required_types - set(observed))
        if missing:
            raise RuntimeContractError(
                "Profile-required canonical SVG chart is missing",
                code="DEPENDENCY_NOT_READY",
                rule="report_chart_coverage",
                details={"missing_chart_types": tuple(missing)},
            )

        referenced_svg_refs = {str(observed[chart_type].get("svg_ref")) for chart_type in required_types}
        if set(svg_assets) != referenced_svg_refs:
            raise RuntimeContractError(
                "Fixture SVG assets must exactly match required Chart references",
                code="SCHEMA_INVALID",
                rule="report_asset_fixture",
            )

        assets: dict[str, str] = {}
        figures: list[str] = []
        for chart_type in sorted(required_types):
            bundle = observed[chart_type]
            svg_ref = bundle.get("svg_ref")
            if not isinstance(svg_ref, str):
                raise RuntimeContractError(
                    "Chart Bundle canonical SVG is unavailable", code="DEPENDENCY_NOT_READY", rule="report_svg"
                )
            _safe_relative(svg_ref)
            svg = svg_assets.get(svg_ref)
            if not isinstance(svg, str):
                raise RuntimeContractError(
                    "Chart Bundle canonical SVG is unavailable", code="DEPENDENCY_NOT_READY", rule="report_svg"
                )
            _validate_canonical_svg(svg)
            target = f"visualizations/{chart_type}/chart.svg"
            assets[target] = svg
            chart = bundle["chart"]
            title = chart.get("id", chart_type)
            figures.append(
                f'<figure data-chart-type="{html.escape(chart_type, quote=True)}">'
                f'<figcaption>{html.escape(str(title))}</figcaption>'
                f'<img src="{html.escape(target, quote=True)}" alt="{html.escape(chart_type)}"></figure>'
            )
        return assets, "".join(figures)

    @staticmethod
    def _closure_from_groups(groups: list[Mapping[str, Any]]) -> dict[str, list[str]]:
        closure: dict[str, set[str]] = {"claim_ids": set(), "evidence_ids": set(), "source_ids": set()}
        for group in groups:
            facts = group.get("facts") if isinstance(group, Mapping) else None
            if not isinstance(facts, list) or not facts:
                raise RuntimeContractError(
                    "Publication Projection Fact Group is malformed", code="SCHEMA_INVALID", rule="report_projection"
                )
            for fact in facts:
                if not isinstance(fact, Mapping):
                    raise RuntimeContractError(
                        "Publication Projection Fact is malformed", code="SCHEMA_INVALID", rule="report_projection"
                    )
                for target, field in (
                    ("claim_ids", "claim_refs"),
                    ("evidence_ids", "evidence_refs"),
                    ("source_ids", "source_refs"),
                ):
                    refs = fact.get(field)
                    if not isinstance(refs, list) or not refs or any(not isinstance(value, str) for value in refs):
                        raise RuntimeContractError(
                            "Publication Projection Fact provenance is malformed",
                            code="SCHEMA_INVALID",
                            rule="report_projection",
                        )
                    closure[target].update(refs)
        return {field: sorted(values) for field, values in closure.items()}

    def _report_content(self, request: ReportPublicationRequest, figures: str) -> str:
        projection = request.publication_projection
        groups = projection.get("fact_groups") if isinstance(projection, Mapping) else None
        declared_closure = projection.get("citation_closure") if isinstance(projection, Mapping) else None
        if not isinstance(groups, list) or not groups or not isinstance(declared_closure, Mapping):
            raise RuntimeContractError(
                "Publication Projection is incomplete", code="SCHEMA_INVALID", rule="report_projection"
            )
        actual_closure = self._closure_from_groups(groups)
        if any(declared_closure.get(field) != actual_closure[field] for field in actual_closure):
            raise RuntimeContractError(
                "Publication Projection Citation Closure is not minimal",
                code="SCHEMA_INVALID",
                rule="report_citation",
            )

        sections: list[str] = []
        rendered_sources: set[str] = set()
        seen_group_ids: set[str] = set()
        seen_dom_scopes: set[str] = set()
        seen_fact_ids: set[str] = set()
        for group in sorted(groups, key=lambda item: str(item.get("id", "")) if isinstance(item, Mapping) else ""):
            if not isinstance(group, Mapping):
                raise RuntimeContractError(
                    "Publication Projection Fact Group is malformed", code="SCHEMA_INVALID", rule="report_projection"
                )
            group_id = group.get("id")
            section_id = group.get("section_id")
            dom_scope_id = group.get("dom_scope_id")
            facts = group.get("facts")
            source_ids = group.get("citation_source_ids")
            if not isinstance(group_id, str) or group_id in seen_group_ids:
                raise RuntimeContractError(
                    "Publication Projection Fact Group identity is duplicated",
                    code="SCHEMA_INVALID",
                    rule="report_projection",
                )
            if (
                not isinstance(section_id, str)
                or _SECTION_ID.fullmatch(section_id) is None
                or not isinstance(dom_scope_id, str)
                or _DOM_ID.fullmatch(dom_scope_id) is None
                or dom_scope_id in seen_dom_scopes
            ):
                raise RuntimeContractError(
                    "Publication Projection DOM scope is invalid or duplicated",
                    code="SCHEMA_INVALID",
                    rule="report_projection",
                )
            seen_group_ids.add(group_id)
            seen_dom_scopes.add(dom_scope_id)
            if (
                not isinstance(facts, list)
                or not facts
                or not isinstance(source_ids, list)
                or not source_ids
                or any(not isinstance(source_id, str) for source_id in source_ids)
                or len(source_ids) != len(set(source_ids))
            ):
                raise RuntimeContractError(
                    "Publication Projection Fact Group lacks facts or citations",
                    code="SCHEMA_INVALID",
                    rule="report_projection",
                )
            fact_sources = {
                source_id
                for fact in facts
                if isinstance(fact, Mapping)
                for source_id in fact.get("source_refs", ())
                if isinstance(source_id, str)
            }
            if set(source_ids) != fact_sources:
                raise RuntimeContractError(
                    "Fact Group Citation Sources do not match its Fact Bindings",
                    code="SCHEMA_INVALID",
                    rule="report_citation",
                )
            badges: list[str] = []
            for source_id in sorted(source_ids):
                record = request.source_records.get(source_id)
                if not isinstance(record, Mapping):
                    raise RuntimeContractError(
                        "Publication Projection Source is unavailable",
                        code="SCHEMA_INVALID",
                        rule="report_citation",
                    )
                short_name, title, excerpt, url = _source_metadata(source_id, record)
                rendered_sources.add(source_id)
                preview_id = f"source-preview-{dom_scope_id}-{source_id.lower()}"
                badges.append(
                    '<span class="citation-group">'
                    f'<a class="citation-badge" href="{html.escape(url, quote=True)}" aria-describedby="{html.escape(preview_id, quote=True)}">{html.escape(short_name)}</a>'
                    f'<span class="source-preview" id="{html.escape(preview_id, quote=True)}" role="note">'
                    f'<strong>{html.escape(short_name)}</strong> '
                    f'<span>{html.escape(title)}</span> '
                    f'<span>{html.escape(excerpt)}</span> '
                    f'<span>{html.escape(url)}</span>'
                    "</span></span>"
                )
            facts_html: list[str] = []
            for fact in facts:
                if not isinstance(fact, Mapping):
                    raise RuntimeContractError(
                        "Publication Projection Fact is malformed", code="SCHEMA_INVALID", rule="report_projection"
                    )
                fact_id = fact.get("fact_id")
                if not isinstance(fact_id, str) or fact_id in seen_fact_ids or fact_id not in request.fact_values:
                    raise RuntimeContractError(
                        "Rendered Fact identity or value is unavailable",
                        code="DEPENDENCY_NOT_READY",
                        rule="report_fact_value",
                    )
                seen_fact_ids.add(fact_id)
                value = request.fact_values[fact_id]
                if canonical_value_hash(value) != fact.get("content_hash"):
                    raise RuntimeContractError(
                        "Rendered Fact value differs from its binding",
                        code="SCHEMA_INVALID",
                        rule="report_fact_value",
                    )
                text = value if isinstance(value, str) else json.dumps(
                    value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                facts_html.append(
                    f'<li data-fact-id="{html.escape(fact_id, quote=True)}">{html.escape(text)}</li>'
                )
            sections.append(
                f'<section id="{html.escape(dom_scope_id, quote=True)}" data-section-id="{html.escape(section_id, quote=True)}">'
                f'<h2>{html.escape(section_id.replace("-", " ").replace("_", " ").title())}</h2>'
                f'<ul>{"".join(facts_html)}</ul>{"".join(badges)}</section>'
            )
        if rendered_sources != set(actual_closure["source_ids"]):
            raise RuntimeContractError(
                "Publication Projection has an unrendered or extra Citation Source",
                code="SCHEMA_INVALID",
                rule="report_citation",
            )
        if set(request.source_records) != rendered_sources:
            raise RuntimeContractError(
                "Source input contains records outside the minimum Citation Closure",
                code="SCHEMA_INVALID",
                rule="report_citation",
            )
        if set(request.fact_values) != seen_fact_ids:
            raise RuntimeContractError(
                "Fact input contains values outside the Publication Projection",
                code="SCHEMA_INVALID",
                rule="report_fact_value",
            )
        sections.append(f'<section id="svg-visualizations"><h2>SVG Visualizations</h2>{figures}</section>')
        sections.append(
            '<section id="scoring-methodology"><h2>Scoring Methodology</h2>'
            '<p data-scoring-status="NOT_PERFORMED">Transparent scoring has not produced a valid Score Artifact for this Run.</p></section>'
        )
        sections.append(
            '<section id="verification-summary"><h2>Verification Summary</h2>'
            '<p data-verification-status="PENDING">Verification has not completed.</p></section>'
        )
        return "".join(sections)

    def _validate_inputs(self, request: ReportPublicationRequest) -> tuple[str, str]:
        if not isinstance(request.attempt_id, str) or not request.attempt_id:
            raise RuntimeContractError("Report attempt identity is malformed", rule="report_attempt")
        if _ARTIFACT_REF.fullmatch(request.report_ref) is None:
            raise RuntimeContractError("Report Artifact reference is malformed", code="SCHEMA_INVALID", rule="report_ref")
        projection_ref = _artifact_ref(
            request.publication_projection,
            expected_type="report_publication_projection",
            rule="report_projection",
        )
        collection_ref = _artifact_ref(
            request.chart_bundle_collection,
            expected_type="chart_bundle_collection",
            rule="report_chart_coverage",
        )
        if request.publication_projection.get("chart_bundle_collection_ref") != collection_ref:
            raise RuntimeContractError(
                "Publication Projection does not reference the supplied Chart Bundle Collection",
                code="SCHEMA_INVALID",
                rule="report_chart_coverage",
            )
        if request.publication_projection.get("verification_status") != "PENDING":
            raise RuntimeContractError(
                "Initial Report verification status must be PENDING", code="SCHEMA_INVALID", rule="report_projection"
            )
        if request.publication_projection.get("scoring_status") != "NOT_PERFORMED":
            raise RuntimeContractError(
                "Initial Report scoring status must be NOT_PERFORMED",
                code="SCHEMA_INVALID",
                rule="report_projection",
            )
        return projection_ref, collection_ref

    def replay(self, request: ReportPublicationRequest) -> Mapping[str, Any] | None:
        """Return the current result of a prior byte-equivalent publication."""

        if not self.fixture_assets_allowed or request.fixture_svg_assets is None:
            raise RuntimeContractError("Fixture replay requires an explicit fixture Publisher", code="SECURITY_POLICY_VIOLATION", rule="report_asset_fixture")
        self._validate_inputs(request)
        template = self._template(request.template_path)
        key_hash, request_hash = self._request_hash(request, template, request.fixture_svg_assets)
        store = _IsolatedReportStore(self.storage_root, request.run_id)
        existing = store.publication_record(key_hash)
        if existing is None:
            return store.recover_publication_record(key_hash=key_hash, request_hash=request_hash)
        if existing.get("idempotency_key_hash") != key_hash or existing.get("request_hash") != request_hash:
            raise RuntimeContractError(
                "Report idempotency key was reused with a different request",
                code="IDEMPOTENCY_CONFLICT",
                rule="report_idempotency",
            )
        pointer = existing.get("pointer")
        current = store.current_report()
        if (
            not isinstance(pointer, Mapping)
            or current is None
            or deep_thaw(current) != deep_thaw(pointer)
            or existing.get("result_identity") != current.get("result_identity")
        ):
            raise RuntimeContractError(
                "Report idempotency record does not identify the committed current result",
                code="STATE_VERSION_CONFLICT",
                rule="report_cas",
            )
        return pointer

    def publish(self, request: ReportPublicationRequest) -> Mapping[str, Any]:
        if request.fixture_svg_assets is None:
            raise RuntimeContractError("Runtime Chart asset resolution is not integrated", code="DEPENDENCY_NOT_READY", rule="report_asset_integration")
        if not self.fixture_assets_allowed:
            raise RuntimeContractError("Fixture assets require an explicit fixture Publisher", code="SECURITY_POLICY_VIOLATION", rule="report_asset_fixture")
        return self._publish(request, request.fixture_svg_assets)

    def _publish_from_inventory(self, request: ReportPublicationRequest, chart_storage: Any, collection_entry: Mapping[str, Any]) -> Mapping[str, Any]:
        """Resolve Runtime SVGs from a hash-checked current Chart inventory."""

        if request.fixture_svg_assets is not None or self.fixture_assets_allowed:
            raise RuntimeContractError("Runtime publishing cannot use fixture assets", code="SECURITY_POLICY_VIOLATION", rule="report_asset_fixture")
        collection_ref = _artifact_ref(request.chart_bundle_collection, expected_type="chart_bundle_collection", rule="report_chart_coverage")
        if collection_entry.get("artifact_ref") != collection_ref:
            raise RuntimeContractError("Runtime Chart inventory is stale", code="STATE_VERSION_CONFLICT", rule="report_asset_integration")
        inventory = chart_storage.read_asset_inventory(
            artifact_ref=collection_ref,
            inventory_ref=str(collection_entry.get("asset_inventory_ref", "")),
            inventory_hash=str(collection_entry.get("asset_inventory_hash", "")),
        )
        svg_refs = {bundle["svg_ref"] for bundle in request.chart_bundle_collection.get("bundles", ()) if isinstance(bundle, Mapping)}
        try:
            svg_assets = {reference: inventory[reference].decode("utf-8") for reference in svg_refs}
        except (KeyError, UnicodeDecodeError) as exc:
            raise RuntimeContractError("Runtime Chart SVG assets are unavailable", code="ARTIFACT_MISSING", rule="report_asset_integration") from exc
        return self._publish(request, svg_assets)

    def _publish(self, request: ReportPublicationRequest, svg_assets: Mapping[str, str]) -> Mapping[str, Any]:
        projection_ref, collection_ref = self._validate_inputs(request)
        template = self._template(request.template_path)
        key_hash, request_hash = self._request_hash(request, template, svg_assets)
        assets, figures = self._chart_assets(request, svg_assets)
        content = self._report_content(request, figures)
        before, after = template.split("<main>", 1)
        _discarded, closing = after.split("</main>", 1)
        root_html = f"{before}<main><h1>Competitor Research Report</h1>{content}</main>{closing}"
        return _IsolatedReportStore(self.storage_root, request.run_id).publish(
            report_ref=request.report_ref,
            expected_base_report_ref=request.expected_base_report_ref,
            key_hash=key_hash,
            request_hash=request_hash,
            root_html=root_html,
            assets=assets,
            publication={
                "attempt_id": request.attempt_id,
                "report_publication_projection_ref": projection_ref,
                "chart_bundle_collection_ref": collection_ref,
            },
        )
