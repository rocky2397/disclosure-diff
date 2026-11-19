"""Pair passages that were written anew from one year to the next.

Comparing wording finds a paragraph that was edited. It misses one that was rewritten: the
same statement in other words shows up as one passage dropped and one new, which overstates
how much changed. So the passages that wording could not match are shown to Claude in one
request, and it says which later passage takes the place of which earlier one.

The model only pairs. It writes no description of the difference: the report prints both
texts, and the reader sees it there.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from document_impact_analyzer.passages import Passage, normalize
from document_impact_analyzer.settings import DataDir
from document_impact_analyzer.topics import Topic

# One request holds every unmatched passage of both years. Beyond this many, the request
# gets long and the pairs unreliable, so it is refused instead of silently cut.
MAX_PASSAGES = 120

PAIR_PROMPT = """\
You are helping an analyst compare two annual reports of the same company. A program has \
already matched the passages whose wording is nearly the same. What is left are passages \
of the earlier report without a match in the later one, and passages of the later report \
without a match in the earlier one. Some of them are the same statement written anew.

Find those. A later passage takes the place of an earlier one when a reader who lays the \
two reports side by side would say: this is what became of that paragraph. Typically both \
stand at the same point of the same section and make the same kind of statement about the \
same matter, for example the same risk or the same market. The facts, the figures and \
even the assessment may have changed. That change is what the analyst wants to see.

Do not pair two passages only because they are on the same topic, name the same country \
or measure, or stand in the same section. An earlier passage without a counterpart was \
dropped, and a later passage without one is new. Both are common, and leaving a passage \
unpaired is better than a forced pair.

Each passage can be in one pair at most. Give each pair as the numbers of the earlier \
passage (E) and the later passage (L). If there are none, give an empty list.
"""

PAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"earlier": {"type": "integer"}, "later": {"type": "integer"}},
                "required": ["earlier", "later"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pairs"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Pair:
    """A later passage that takes the place of an earlier one, by passage id."""

    before_id: str
    after_id: str
    model: str


@dataclass(frozen=True)
class Pairing:
    """The pairs found for two reports, and the passages that were shown to the model."""

    pairs: list[Pair] = field(default_factory=list)
    # Ids of every passage the model saw. A passage that is not among them was never
    # offered for pairing, for example because it was judged after the pairing was made.
    considered: frozenset[str] = frozenset()


def _listing(letter: str, passages: Sequence[Passage]) -> str:
    entries = []
    for number, passage in enumerate(passages, start=1):
        place = [f'section "{passage.section}"'] if passage.section else []
        if passage.page:
            place.append(f"page {passage.page}")
        head = f"{letter}{number} ({', '.join(place)})" if place else f"{letter}{number}"
        entries.append(f"{head}\n{normalize(passage.text)}")
    return "\n\n".join(entries)


def build_pair_request(earlier: Sequence[Passage], later: Sequence[Passage], topic: Topic) -> str:
    """The user message: the unmatched passages of both years, numbered."""
    return (
        f"Topic: {topic.name}\n"
        f"Company: {earlier[0].company}\n"
        f"Earlier report: {earlier[0].year}. Later report: {later[0].year}.\n\n"
        f"<earlier>\n{_listing('E', earlier)}\n</earlier>\n\n"
        f"<later>\n{_listing('L', later)}\n</later>"
    )


def pairs_from_answer(
    answer: dict[str, Any], earlier: Sequence[Passage], later: Sequence[Passage], model: str
) -> list[Pair]:
    """Turn the model's numbers into pairs.

    A number that names no passage raises ``ValueError``. A passage named a second time is
    left with its first pair.
    """
    pairs: list[Pair] = []
    used_earlier: set[int] = set()
    used_later: set[int] = set()
    for item in answer["pairs"]:
        e, l = int(item["earlier"]), int(item["later"])  # noqa: E741
        if not (1 <= e <= len(earlier) and 1 <= l <= len(later)):
            raise ValueError(f"E{e} and L{l} do not both name a passage")
        if e in used_earlier or l in used_later:
            continue
        used_earlier.add(e)
        used_later.add(l)
        pairs.append(Pair(earlier[e - 1].id, later[l - 1].id, model))
    return pairs


def pairing_path(data: DataDir, company: str, before: int, after: int, topic_key: str) -> Path:
    return data.paired / f"{company}_{before}_{after}_{topic_key}.json"


def write_pairing(path: Path, pairing: Pairing) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "considered": sorted(pairing.considered),
        "pairs": [
            {"before": pair.before_id, "after": pair.after_id, "model": pair.model}
            for pair in pairing.pairs
        ],
    }
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_pairing(path: Path) -> Pairing | None:
    """The stored pairing, or ``None`` when the two reports have not been paired."""
    if not path.is_file():
        return None
    content = json.loads(path.read_text(encoding="utf-8"))
    pairs = [Pair(item["before"], item["after"], item["model"]) for item in content["pairs"]]
    return Pairing(pairs, frozenset(content["considered"]))
