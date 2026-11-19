"""Compare what a company wrote about a topic in two consecutive annual reports.

Much of an annual report is repeated from the year before. What carries information is the
difference: a passage that is new, one that was dropped, and one that was reworded, above
all when it now states an amount where it did not before.

The thresholds have only been checked against one pair of reports, RWE 2024 and 2025.
There, paragraphs that were clearly the same one rewritten with new figures scored between
0.40 and 0.47, and no dropped paragraph without a counterpart scored above 0.37.

Wording cannot match a paragraph that was written anew. Pairs for those come from
``pairing``, where a model reads the passages that are left over.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from document_impact_analyzer.pairing import Pair
from document_impact_analyzer.passages import Passage, normalize

_TOKEN = re.compile(r"\w+(?:[.,]\d+)*")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
_AMOUNT = re.compile(
    r"[$€£]\s?\d|\d[\d.,]*\s?(?:%|percent\b|million\b|billion\b|bn\b|USD\b|EUR\b|GBP\b)",
    re.IGNORECASE,
)


class Status(str, Enum):
    NEW = "new"
    CHANGED = "changed"
    DROPPED = "dropped"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Change:
    status: Status
    before: Passage | None
    after: Passage | None
    similarity: float = 0.0
    # The later text states an amount that the earlier text did not. For a new passage
    # there is no earlier text, so this is true whenever it states an amount.
    newly_quantified: bool = False
    # For a pair that wording did not match: the model that paired the two passages.
    paired_by: str | None = None


def has_amount(text: str) -> bool:
    """True when the text states a sum of money or a percentage."""
    return bool(_AMOUNT.search(text))


def _tokens(text: str) -> list[str]:
    # Years are masked so that "in 2022" becoming "in 2023" does not count as a rewording.
    return ["<year>" if _YEAR.match(t) else t for t in _TOKEN.findall(normalize(text).lower())]


def similarity(a: str, b: str) -> float:
    """Word-level similarity between 0 and 1, ignoring layout, letter case and years."""
    return _similarity(_tokens(a), _tokens(b))


def _similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def compare_years(
    before: Sequence[Passage],
    after: Sequence[Passage],
    *,
    unchanged_at: float = 0.95,
    related_at: float = 0.4,
    pairs: Sequence[Pair] = (),
) -> list[Change]:
    """Pair each passage with its closest counterpart in the other year.

    Every passage is used at most once. Pairs at or above ``unchanged_at`` are unchanged,
    pairs at or above ``related_at`` are changed, and whatever stays unpaired is new or
    dropped. The result lists new passages first, then changed ones starting with the most
    heavily reworded, then dropped and unchanged ones.

    ``pairs`` holds passages that were written anew, as a model paired them. A pair is used
    when wording has left both of its passages unmatched.
    """
    before_tokens = [_tokens(p.text) for p in before]
    after_tokens = [_tokens(p.text) for p in after]

    scored = []
    for i, a in enumerate(before_tokens):
        a_set = set(a)
        for j, b in enumerate(after_tokens):
            b_set = set(b)
            union = len(a_set | b_set)
            # Cheap check first: passages sharing few words cannot be similar enough.
            if not union or len(a_set & b_set) / union < related_at / 2:
                continue
            score = _similarity(a, b)
            if score >= related_at:
                scored.append((score, i, j))

    used_before: set[int] = set()
    used_after: set[int] = set()
    changed, unchanged = [], []
    for score, i, j in sorted(scored, key=lambda item: (-item[0], item[1], item[2])):
        if i in used_before or j in used_after:
            continue
        used_before.add(i)
        used_after.add(j)
        if score >= unchanged_at:
            unchanged.append(Change(Status.UNCHANGED, before[i], after[j], score))
        else:
            quantified = has_amount(after[j].text) and not has_amount(before[i].text)
            changed.append(Change(Status.CHANGED, before[i], after[j], score, quantified))

    index_before = {p.id: i for i, p in enumerate(before)}
    index_after = {p.id: j for j, p in enumerate(after)}
    for pair in pairs:
        i, j = index_before.get(pair.before_id), index_after.get(pair.after_id)
        if i is None or j is None or i in used_before or j in used_after:
            continue
        used_before.add(i)
        used_after.add(j)
        score = _similarity(before_tokens[i], after_tokens[j])
        quantified = has_amount(after[j].text) and not has_amount(before[i].text)
        changed.append(Change(Status.CHANGED, before[i], after[j], score, quantified, pair.model))

    new = [
        Change(Status.NEW, None, p, newly_quantified=has_amount(p.text))
        for j, p in enumerate(after)
        if j not in used_after
    ]
    dropped = [
        Change(Status.DROPPED, p, None) for i, p in enumerate(before) if i not in used_before
    ]

    new.sort(key=lambda change: change.after.page)
    changed.sort(key=lambda change: (change.similarity, change.after.page))
    dropped.sort(key=lambda change: change.before.page)
    unchanged.sort(key=lambda change: change.after.page)
    return new + changed + dropped + unchanged


def unmatched(changes: Sequence[Change]) -> tuple[list[Passage], list[Passage]]:
    """The dropped passages and the new ones: those without a counterpart so far."""
    dropped = [change.before for change in changes if change.status is Status.DROPPED]
    new = [change.after for change in changes if change.status is Status.NEW]
    return dropped, new
