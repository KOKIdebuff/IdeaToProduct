from __future__ import annotations

import pytest

from scripts.validate_contracts import ROOT, load_document, load_schemas


@pytest.fixture(scope="session")
def contract_env():
    schemas, registry = load_schemas()
    workflow = load_document(ROOT / "workflow.yaml")
    return schemas, registry, workflow
