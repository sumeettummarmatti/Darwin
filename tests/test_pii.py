"""The PII proxy: what reaches a model."""

import pytest

from core.pii import PointerOnlyViolation


def test_undeclared_and_prohibited_fields_are_stripped_and_identifiers_tokenised(kernel):
    source = {"subject.display_name": "Meera Iyer", "subject.grade": "L4", "subject.pan_token": "tok_x",
              "subject.date_of_birth": "1990-01-01", "subject.basic_monthly": 78000,
              "args.note": "Call Meera on 9000004821 or meera@example.net, PAN SYNPA4821K"}
    out = kernel.proxy.minimise(source, ["subject.display_name", "subject.grade", "subject.pan_token", "subject.date_of_birth", "args.note"])
    assert out.payload["subject.display_name"] == "«PERSON_1»"
    assert out.payload["subject.pan_token"].startswith("«VAULT")
    assert "subject.basic_monthly" not in out.payload                       # undeclared
    assert "subject.date_of_birth" not in out.payload                     # prohibited (age proxy): stripped outright
    note = out.payload["args.note"]
    assert "Meera" not in note and "9000004821" not in note and "example.net" not in note and "SYNPA4821K" not in note
    assert out.rehydrate(out.payload["subject.display_name"]) == "Meera Iyer"


def test_prohibited_criteria_are_stripped_even_if_declared(kernel):
    out = kernel.proxy.minimise({"args.college_tier": 1, "args.skills": ["go"]}, ["args.college_tier", "args.skills"])
    assert "args.college_tier" not in out.payload
    assert {"field": "args.college_tier", "reason": "prohibited criterion"} in out.stripped


def test_pointer_only_subject_never_reaches_a_model(kernel):
    with pytest.raises(PointerOnlyViolation):
        kernel.proxy.minimise({"subject.public_url": "https://x"}, ["subject.public_url"],
                              {"id": "SRC-1", "processing_mode": "pointer_only"})


def test_cross_purpose_read_is_refused(kernel):
    from core.pii import PurposeViolation
    assert kernel.vault.read("EMP-4821", "bank_account", "payroll").startswith("SYN-")
    with pytest.raises(PurposeViolation):
        kernel.vault.read("EMP-4821", "bank_account", "onboarding_logistics")
