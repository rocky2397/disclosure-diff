"""Tell table rows apart from prose.

Text extracted from the financial statements of an annual report is mostly figures. Those
passages say nothing about a topic, yet they matched the old keyword search (for example
through "trade receivables"), so they are filtered out before retrieval.
"""

from __future__ import annotations

import re

from document_impact_analyzer.passages import normalize

# 630 · 9,061 · (147) · 25% · 1.5 · – (an empty table cell) · a currency sign on its own
_FIGURE = re.compile(r"^(?:[(\-–−]?[$€£]?\d[\d.,]*%?\)?[.,;:]?|[–—\-]|[$€£])$")
_YEAR = re.compile(r"^(?:19|20)\d\d[.,;:]?$")


def figure_share(text: str) -> float:
    """Share of whitespace-separated tokens that are figures. Years in prose count too."""
    tokens = normalize(text).split()
    if not tokens:
        return 0.0
    return sum(1 for token in tokens if _FIGURE.match(token)) / len(tokens)


def looks_like_table(text: str, *, threshold: float = 0.2) -> bool:
    """True when enough of the passage is figures that it reads as table rows.

    Prose that quotes a few amounts stays well under the threshold: a sentence with two
    figures in twenty-five words has a share of 0.08.
    """
    tokens = normalize(text).split()
    if len(tokens) < 5:
        return False
    figures = [token for token in tokens if _FIGURE.match(token)]
    if all(_YEAR.match(token) for token in figures):
        # "In 2022 and 2023 …" is prose, however many years it names.
        return False
    return len(figures) / len(tokens) >= threshold
