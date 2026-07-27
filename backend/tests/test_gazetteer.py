"""
Tests for closed-vocabulary matching.

The vocabulary in these tests is arbitrary — the point is that the module
itself carries no deployment-specific knowledge, so the tests deliberately
use a mix of realistic and invented terms rather than one country's list.
"""

from app.services.gazetteer import Gazetteer


VOCAB = ["Al Asimah", "Hawalli", "Farwaniya", "Ahmadi", "Jahra", "Mubarak Al-Kabeer"]


def test_finds_a_term_appearing_after_a_facility_name():
    """
    The exact case the model kept failing: region trails the facility, and
    the whole phrase reads like one place name.
    """
    g = Gazetteer(VOCAB)
    assert g.find("Seen 9/3/25 at Ardiya Clinic, Farwaniya. ?Chickenpox.") == "Farwaniya"


def test_finds_a_multiword_term():
    g = Gazetteer(VOCAB)
    assert g.find("Reporting facility: Adan District Hospital, Mubarak Al-Kabeer") \
        == "Mubarak Al-Kabeer"


def test_returns_none_when_no_term_is_present():
    """No guessing — an absent region must stay absent for a human to fill in."""
    g = Gazetteer(VOCAB)
    assert g.find("34yo M, fever x3d, seen at a clinic. ?Measles.") is None


def test_match_is_case_insensitive():
    g = Gazetteer(VOCAB)
    assert g.find("seen at clinic in HAWALLI today") == "Hawalli"


def test_canonical_spelling_is_returned_not_the_matched_text():
    """Storage should be consistent even when the report isn't."""
    g = Gazetteer(VOCAB)
    assert g.find("...in hawalli.") == "Hawalli"


def test_aliases_map_to_the_canonical_term():
    g = Gazetteer(VOCAB, aliases={"Capital Governorate": "Al Asimah", "Kuwait City": "Al Asimah"})
    assert g.find("Reported from Capital Governorate") == "Al Asimah"
    assert g.find("seen in Kuwait City") == "Al Asimah"


def test_partial_words_do_not_match():
    """'Jahra' must not match inside a longer unrelated word."""
    g = Gazetteer(VOCAB)
    assert g.find("Patient attended Jahraville Medical Centre") is None


def test_longer_term_wins_over_a_shorter_substring():
    g = Gazetteer(["Ahmadi", "Ahmadi North"])
    assert g.find("Reported from Ahmadi North district") == "Ahmadi North"


def test_find_all_returns_every_distinct_term_in_order():
    g = Gazetteer(VOCAB)
    found = g.find_all("Transferred from Jahra to Hawalli, then to Ahmadi.")
    assert found == ["Jahra", "Hawalli", "Ahmadi"]


def test_empty_vocabulary_is_falsy_and_matches_nothing():
    """A deployment with no reference data configured must degrade cleanly."""
    g = Gazetteer([])
    assert not g
    assert g.find("anything at all in Hawalli") is None
