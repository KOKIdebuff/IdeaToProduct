from __future__ import annotations

from scripts.validate_contracts import main, validate_repository


def test_repository_contracts_are_valid():
    diagnostics, checked = validate_repository()
    assert checked == 111
    assert diagnostics == []


def test_validator_exit_code_is_zero():
    assert main() == 0
