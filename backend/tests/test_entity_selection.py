"""
Tests for negation-aware entity selection.

Negation is the highest-stakes piece of the extraction: picking a disease
the report explicitly RULED OUT as the patient's diagnosis is a clinical
error, not a display glitch. These tests cover both phrasings — the cue
before the entity and the cue after it — because a real 500-report run
showed the second one was silently unhandled.
"""

from app.services.entity_selection import (
    first_non_negated_entity,
    is_negated,
)
from app.services.ner_client import ExtractedEntity


def entity_in(text, word, label="disease", score=0.9):
    """Build an entity with real character offsets into `text`."""
    start = text.find(word)
    assert start != -1, f"{word!r} not found in test text"
    return ExtractedEntity(label=label, text=word, score=score,
                           start=start, end=start + len(word))


# --- Cue BEFORE the entity (the original case) -----------------------------

def test_cue_before_entity_negates_it():
    text = "Ruled out dengue based on negative rapid test. Suspected typhoid fever."
    assert is_negated(text, entity_in(text, "dengue")) is True


def test_entity_after_a_negated_one_is_not_itself_negated():
    text = "Ruled out dengue based on negative rapid test. Suspected typhoid fever."
    assert is_negated(text, entity_in(text, "typhoid")) is False


# --- Cue AFTER the entity (found by the 500-report accuracy run) -----------

def test_trailing_ruled_out_negates_the_preceding_entity():
    """'Hepatitis A was ruled out' — cue follows the disease, not precedes it."""
    text = "Hepatitis A was ruled out on negative testing. Working diagnosis Mumps."
    assert is_negated(text, entity_in(text, "Hepatitis A")) is True


def test_actual_diagnosis_after_a_trailing_negation_survives():
    text = "Hepatitis A was ruled out on negative testing. Working diagnosis Mumps."
    assert is_negated(text, entity_in(text, "Mumps")) is False


def test_trailing_negative_result_negates_within_same_clause():
    text = "Dengue serology negative; Chikungunya confirmed."
    assert is_negated(text, entity_in(text, "Dengue")) is True


# --- The bound that makes trailing cues safe -------------------------------

def test_negation_does_not_leak_across_a_sentence_boundary():
    """
    Without a sentence bound, 'Rubella negative' in the next sentence would
    negate 'Measles' in this one — turning a confirmed diagnosis into a
    ruled-out one. This is the failure mode that makes naive trailing-cue
    matching worse than no trailing check at all.
    """
    text = "Measles confirmed by PCR. Rubella negative."
    assert is_negated(text, entity_in(text, "Measles")) is False
    assert is_negated(text, entity_in(text, "Rubella")) is True


def test_plain_confirmed_statement_is_never_negated():
    text = "Typhoid fever confirmed by blood culture."
    assert is_negated(text, entity_in(text, "Typhoid fever")) is False


# --- Selection behaviour ---------------------------------------------------

def test_selection_skips_negated_and_reports_how_many():
    text = "Hepatitis A was ruled out on negative testing. Working diagnosis Mumps."
    entities = [entity_in(text, "Hepatitis A"), entity_in(text, "Mumps")]
    selected, skipped = first_non_negated_entity(entities, "disease", text)
    assert selected.text == "Mumps"
    assert skipped == 1


def test_selection_returns_none_when_every_mention_is_negated():
    text = "Dengue was ruled out. Measles excluded."
    entities = [entity_in(text, "Dengue"), entity_in(text, "Measles")]
    selected, skipped = first_non_negated_entity(entities, "disease", text)
    assert selected is None
    assert skipped == 2


def test_entity_without_offsets_is_never_assumed_negated():
    """No position information means we cannot claim negation — stay conservative."""
    text = "Ruled out dengue. Suspected typhoid."
    no_offsets = ExtractedEntity(label="disease", text="dengue", score=0.9)
    assert is_negated(text, no_offsets) is False
