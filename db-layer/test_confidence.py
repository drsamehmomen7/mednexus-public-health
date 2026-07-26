from app.services.confidence import needs_review


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
