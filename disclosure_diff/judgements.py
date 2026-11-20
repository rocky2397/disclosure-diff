"""What a reader decided about one candidate passage, and where those decisions are kept.

Phrase search finds passages that mention a topic. A judgement says whether such a passage
is about the company being affected, and if so in which direction and how concretely.
Judgements are stored per company, year and topic so that a passage is judged only once.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from disclosure_diff.passages import normalize
from disclosure_diff.settings import DataDir


class Relevance(str, Enum):
    COMPANY = "company"  # the topic affects, or could affect, the company
    CONTEXT = "context"  # about the topic, but as background: economy, markets, politics
    OFF_TOPIC = "off_topic"  # the phrase is used in another sense


class Direction(str, Enum):
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    BOTH = "both"
    NONE = "none"


class Concreteness(str, Enum):
    GENERIC = "generic"  # could stand unchanged in any company's report
    SPECIFIC = "specific"  # names a measure, country, product, project or event
    QUANTIFIED = "quantified"  # states a figure for the topic or its effect


@dataclass(frozen=True)
class Judgement:
    passage_id: str
    relevance: Relevance
    direction: Direction
    concreteness: Concreteness
    # The company says what it does about it.
    states_response: bool
    # The sentence from the passage that supports the judgement, word for word.
    evidence: str
    # False when the evidence could not be found in the passage or, if the judge was shown
    # the neighbouring paragraphs, in those.
    evidence_verified: bool
    model: str
    # Where the evidence stands: "passage", or "before" or "after" for a neighbouring
    # paragraph that states the link to the company.
    evidence_from: str = "passage"
    # The passage read as background and was judged a second time with the paragraphs
    # before and after it.
    saw_neighbours: bool = False

    def to_json(self) -> str:
        return json.dumps(
            asdict(self) | {k: getattr(self, k).value for k in _ENUM_FIELDS}, ensure_ascii=False
        )

    @classmethod
    def from_json(cls, line: str) -> Judgement:
        data = json.loads(line)
        for key, enum in _ENUM_FIELDS.items():
            data[key] = enum(data[key])
        return cls(**data)


_ENUM_FIELDS = {"relevance": Relevance, "direction": Direction, "concreteness": Concreteness}


def evidence_is_verbatim(evidence: str, passage_text: str) -> bool:
    """True when the evidence appears in the passage, ignoring layout and letter case."""
    needle = normalize(evidence).casefold()
    return bool(needle) and needle in normalize(passage_text).casefold()


def judgements_path(data: DataDir, company: str, year: int, topic_key: str) -> Path:
    return data.judged / f"{company}_{year}_{topic_key}.jsonl"


def read_judgements(path: Path) -> dict[str, Judgement]:
    """Judgements by passage id. A later line for the same passage replaces an earlier one."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        judgements = [Judgement.from_json(line) for line in handle if line.strip()]
    return {judgement.passage_id: judgement for judgement in judgements}


def append_judgement(path: Path, judgement: Judgement) -> None:
    """Add one judgement to the file, so an interrupted run keeps what it has done."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(judgement.to_json() + "\n")
