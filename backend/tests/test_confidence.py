from app.services.confidence import needs_review, rule_based_confidence


def test_high_confidence_model_fields_do_not_need_review():
    confidence = {
        "disease_name": {"source": "model", "score": 0.95},
        "region": {"source": "model", "score": 0.8},
        "report_date": {"source": "rule_based", "score": None},
    }
    assert needs_review(confidence) is False


def test_low_confidence_model_field_needs_review():
    confidence = {
        "disease_name": {"source": "model", "score": 0.51},
        "region": {"source": "model", "score": 0.8},
    }
    assert needs_review(confidence) is True


def test_missing_model_field_needs_review():
    confidence = {
        "disease_name": {"source": "model", "score": None, "note": "not found in text"},
        "region": {"source": "model", "score": 0.8},
    }
    assert needs_review(confidence) is True


def test_rule_based_only_fields_never_trigger_review_on_their_own():
    confidence = {
        "report_date": {"source": "rule_based", "score": None},
        "patient_age": {"source": "rule_based", "score": None},
    }
    assert needs_review(confidence) is False


def test_custom_threshold_is_respected():
    confidence = {"disease_name": {"source": "model", "score": 0.65}}
    assert needs_review(confidence, threshold=0.6) is False
    assert needs_review(confidence, threshold=0.7) is True


# --- Regression coverage for the silent date.today() fallback bug -------
# (found real via blind testing 2026-08-17 — see decisions-log.md).
# A required date field (report_date/administration_date/result_date)
# that fell through to a fabricated date.today() used to be
# indistinguishable from a genuinely-parsed one: both got the exact same
# {"source": "rule_based", "score": None} entry, and needs_review()
# blanket-skipped every rule_based field. found=False closes that gap.

def test_rule_based_confidence_omits_found_key_by_default():
    """Fields with no fallback-fabrication risk stay exactly as before —
    no unexpected new key for every other rule-based field."""
    assert rule_based_confidence() == {"source": "rule_based", "score": None}


def test_rule_based_confidence_includes_found_when_specified():
    assert rule_based_confidence(found=True) == {"source": "rule_based", "score": None, "found": True}
    assert rule_based_confidence(found=False) == {"source": "rule_based", "score": None, "found": False}


def test_rule_based_field_with_found_false_needs_review():
    confidence = {"result_date": {"source": "rule_based", "score": None, "found": False}}
    assert needs_review(confidence) is True


def test_rule_based_field_with_found_true_does_not_need_review():
    confidence = {"result_date": {"source": "rule_based", "score": None, "found": True}}
    assert needs_review(confidence) is False
