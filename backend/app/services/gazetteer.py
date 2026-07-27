"""
Closed-vocabulary matching for fields where the set of valid answers is
known in advance.

Why this exists: zero-shot NER is the right tool for OPEN vocabularies —
disease names, facility names, anything where new values appear all the
time. It is the wrong tool for CLOSED ones. A deployment has a fixed list
of administrative regions; asking a model to guess a region out of free
text, when the list of six valid answers is already known, throws away
information and gets it wrong roughly 15% of the time (measured over 500
generated reports, where "Ardiya Clinic, Farwaniya" often yielded no region
at all because the model couldn't separate facility from region).

Why it doesn't break the system-agnostic ground rule: this module contains
NO country, ministry, or deployment-specific values. The vocabulary is
passed in as data. The same code serves Kuwait governorates, Egyptian
governorates, or English NHS regions — only the supplied list changes.
Callers get the list from the database or configuration; extraction logic
never hardcodes it.

Matching is deliberately conservative: exact whole-token matches only, plus
optional per-deployment aliases. It never guesses at a partial or fuzzy
match, because silently assigning a case to the wrong region is worse than
leaving it unknown for a human to fill in.
"""

import re
from typing import Dict, Iterable, List, Optional, Tuple


def _normalize(value: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation used as separators."""
    value = value.lower().strip()
    value = re.sub(r"[.,;:()\[\]]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class Gazetteer:
    """
    Matches text against a known list of terms.

    `terms` is the canonical vocabulary — what should be stored when a match
    is found. `aliases` maps alternative spellings to a canonical term, for
    the very common case where reports abbreviate or transliterate
    differently than the official list does.
    """

    def __init__(self, terms: Iterable[str], aliases: Optional[Dict[str, str]] = None):
        self.terms: List[str] = [t for t in terms if t and t.strip()]
        self._lookup: Dict[str, str] = {}

        for term in self.terms:
            self._lookup[_normalize(term)] = term

        for alias, canonical in (aliases or {}).items():
            if canonical in self.terms:
                self._lookup[_normalize(alias)] = canonical

        # Longest first, so "Mubarak Al-Kabeer" is matched before a shorter
        # term that happens to be a substring of it.
        self._sorted_keys = sorted(self._lookup, key=len, reverse=True)

    def find(self, text: str) -> Optional[str]:
        """
        Return the canonical term for the first vocabulary entry appearing in
        `text`, or None. Matches on whole-word boundaries only, so "Jahra"
        does not match inside "Jahraville" and a facility called "Hawalli
        Clinic" doesn't silently become the region by accident — the caller
        decides precedence, see find_with_position.
        """
        match = self.find_with_position(text)
        return match[0] if match else None

    def find_with_position(self, text: str) -> Optional[Tuple[str, int]]:
        """
        Same as find, but also returns the character offset of the match, so
        callers can prefer a later mention over an earlier one when the
        document format puts the value in a predictable place.
        """
        normalized = _normalize(text)
        best: Optional[Tuple[str, int]] = None

        for key in self._sorted_keys:
            for m in re.finditer(rf"(?<!\w){re.escape(key)}(?!\w)", normalized):
                position = m.start()
                if best is None or position < best[1]:
                    best = (self._lookup[key], position)
                break  # first occurrence of this key is enough

        return best

    def find_all(self, text: str) -> List[str]:
        """Every distinct vocabulary term appearing in `text`, in order."""
        normalized = _normalize(text)
        found: List[Tuple[str, int]] = []
        for key in self._sorted_keys:
            m = re.search(rf"(?<!\w){re.escape(key)}(?!\w)", normalized)
            if m:
                found.append((self._lookup[key], m.start()))
        found.sort(key=lambda pair: pair[1])

        seen = set()
        ordered = []
        for term, _pos in found:
            if term not in seen:
                seen.add(term)
                ordered.append(term)
        return ordered

    def __len__(self) -> int:
        return len(self.terms)

    def __bool__(self) -> bool:
        return bool(self.terms)
