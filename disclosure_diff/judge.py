"""Judge candidate passages with Claude.

One request per passage. The answer has a fixed format (structured outputs), and the quote
the model gives as evidence is checked against the text afterwards.

A report often describes an event in one paragraph and says what it means for the company
in the next. Judged alone, the first paragraph reads as background. So a passage that comes
back as background gets a second look, this time with the paragraphs printed before and
after it. It becomes a passage about the company only if the model can quote, word for
word, the neighbouring sentence that states the link.

The neighbours are not shown the first time. When they were, on the 31 passages of the
first reference, the answer to "says what the company does about it" got worse: it matched
the reference on 55 to 57 of 62 attempts, against 62 of 62 without them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from disclosure_diff.judgements import (
    Concreteness,
    Direction,
    Judgement,
    Relevance,
    evidence_is_verbatim,
)
from disclosure_diff.pairing import (
    PAIR_PROMPT,
    PAIR_SCHEMA,
    Pair,
    build_pair_request,
    pairs_from_answer,
)
from disclosure_diff.passages import Neighbours, Passage, normalize
from disclosure_diff.topics import Topic

# Chosen after judging the same 31 passages with claude-opus-5-5 and with this model: the
# verdicts matched on 28, differed only on borderline passages, and this model cost about
# a fortieth. The comparison is in docs/judge-model-comparison.md.
DEFAULT_MODEL = "claude-haiku-5-5"
# Sorting a paragraph into three classes does not need deep reasoning, so the effort is
# set low; raise it if a comparison says so.
DEFAULT_EFFORT = "low"
# If a safety classifier declines a request, the API retries it on the fallback model it
# recommends instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def supports_fallback(model: str) -> bool:
    """Haiku models have no server-side fallback, and their requests should not ask for one."""
    return "haiku" not in model


SYSTEM_PROMPT = """\
You are helping an analyst read annual reports. A phrase search has pulled out passages \
that mention a topic. For one passage at a time, you decide what the passage says about \
the reporting company and that topic.

The analysis is about disclosure: what the company itself reports. Judge only what the \
passage states. Leave out anything you know about the company or the events from \
elsewhere, because the result is shown to readers as the company's own words.

relevance
- "company": the passage presents the topic as something that affects, has affected or \
could affect the reporting company: its costs, revenues, projects, supply chain, \
investments, strategy or risks. A passage that says what the company is doing in response \
also counts.
- "context": the passage is about the topic, but as background. Typical cases are the \
general economy, stock market or commodity price movements, and a neutral description of \
a law or political event with no stated link to the company's business. A passage that \
names the topic only in a list of general uncertainties, without saying how the company \
is touched, is also context.
- "off_topic": the search phrase is used in a different sense, or the passage is not \
about the topic. Where the request has a line "Not this topic", it names the typical \
cases.

When a passage describes an event and then links it to the company, for example by saying \
that it concerns components the company buys, choose "company".

direction, from the company's point of view as the passage presents it
"risk", "opportunity", "both" or "none". Use "none" for context and off_topic passages, \
and for company passages that only describe.

concreteness
- "generic": wording that could stand unchanged in any company's report.
- "specific": names a particular measure, country, product, project, supplier region or \
event.
- "quantified": gives a figure for the topic or its effect, such as a rate, an amount of \
money or a share. A figure about something else in the passage, such as GDP growth or an \
index level, does not count.

states_response
true when the passage says what the company does or has done about the topic.

evidence
The one sentence, or part of a sentence, from the passage that best supports your \
relevance decision, copied exactly. It is checked against the passage by a program, so \
copy it character for character without ellipses, corrections or paraphrase.
"""

# Added to the system prompt for the second look at a passage judged as background.
NEIGHBOURS_PROMPT = """
neighbouring paragraphs
The paragraphs printed directly before and after the passage are included, marked \
<before> and <after>. A report often describes an event in one paragraph and says what it \
means for the company in the next.

If a neighbouring paragraph states how the thing this passage describes affects the \
company, choose "company" for the passage, take the direction from the two paragraphs \
read together, and copy the evidence from that neighbouring paragraph, without the marks \
around it.

If neither neighbour does that, judge the passage as if they were not there. A neighbour \
that is about the company in some other respect, or about a different matter, changes \
nothing.

Concreteness and states_response are judged on the passage alone.
"""

# Added to the system prompt for a passage the phrase search did not find.
SCAN_PROMPT = """
unselected passage
This passage was not found by the phrase search. It is one of all the paragraphs of the \
report, and most of them have nothing to do with the topic. Answer "off_topic" for a \
passage that is not about the topic, with direction "none", concreteness "generic" and \
states_response false, and copy its first few words as evidence.

Choose "company" or "context" only if the passage is about the topic itself, said in \
other words. A passage about something the topic could influence, such as prices, supply \
chains, costs or regulation in general, is not about the topic.
"""

# A model sometimes copies the closing mark of a paragraph along with its last sentence.
_MARK = re.compile(r"</?(?:before|passage|after)>")

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "relevance": {"type": "string", "enum": [item.value for item in Relevance]},
        "direction": {"type": "string", "enum": [item.value for item in Direction]},
        "concreteness": {"type": "string", "enum": [item.value for item in Concreteness]},
        "states_response": {"type": "boolean"},
        "evidence": {"type": "string"},
    },
    "required": ["relevance", "direction", "concreteness", "states_response", "evidence"],
    "additionalProperties": False,
}


class JudgeError(RuntimeError):
    """A passage could not be judged."""


class Judge(Protocol):
    def judge(
        self, passage: Passage, topic: Topic, neighbours: Neighbours | None = None
    ) -> Judgement: ...

    def scan(self, passage: Passage, topic: Topic) -> Judgement: ...

    def pair(
        self, earlier: Sequence[Passage], later: Sequence[Passage], topic: Topic
    ) -> list[Pair]: ...


def system_prompt(neighbours: Neighbours | None = None) -> str:
    return SYSTEM_PROMPT + NEIGHBOURS_PROMPT if neighbours else SYSTEM_PROMPT


def build_request(passage: Passage, topic: Topic, neighbours: Neighbours | None = None) -> str:
    """The user message for one passage."""
    section = f', section "{passage.section}"' if passage.section else ""
    page = f", page {passage.page}" if passage.page else ""
    not_this = f"Not this topic: {topic.not_this}\n" if topic.not_this else ""
    parts = [
        f"Topic: {topic.name}\n"
        f"Question: {topic.question}\n"
        f"{not_this}"
        f"Company: {passage.company}\n"
        f"Source: {passage.document}{section}{page}"
    ]
    if neighbours and neighbours.before:
        parts.append(f"<before>\n{normalize(neighbours.before.text)}\n</before>")
    parts.append(f"<passage>\n{normalize(passage.text)}\n</passage>")
    if neighbours and neighbours.after:
        parts.append(f"<after>\n{normalize(neighbours.after.text)}\n</after>")
    return "\n\n".join(parts)


def locate_evidence(
    evidence: str, passage: Passage, neighbours: Neighbours | None = None
) -> str | None:
    """Where the evidence stands word for word: "passage", "before", "after" or nowhere."""
    places = {"passage": passage}
    if neighbours:
        places |= {"before": neighbours.before, "after": neighbours.after}
    for place, source in places.items():
        if source is not None and evidence_is_verbatim(evidence, source.text):
            return place
    return None


def judgement_from_answer(
    answer: dict[str, Any], passage: Passage, model: str, neighbours: Neighbours | None = None
) -> Judgement:
    """Turn the model's answer into a judgement and check its evidence against the text."""
    try:
        evidence = _MARK.sub("", str(answer["evidence"])).strip()
        found = locate_evidence(evidence, passage, neighbours)
        return Judgement(
            passage_id=passage.id,
            relevance=Relevance(answer["relevance"]),
            direction=Direction(answer["direction"]),
            concreteness=Concreteness(answer["concreteness"]),
            states_response=bool(answer["states_response"]),
            evidence=evidence,
            evidence_verified=found is not None,
            model=model,
            evidence_from=found or "passage",
            saw_neighbours=bool(neighbours),
        )
    except (KeyError, ValueError, TypeError) as error:
        raise JudgeError(f"Unexpected answer for passage {passage.id}: {error}") from error


class ClaudeJudge:
    """Judges passages through the Anthropic API.

    Credentials come from the environment, as the SDK resolves them: ``ANTHROPIC_API_KEY``,
    ``ANTHROPIC_AUTH_TOKEN`` or an ``ant auth login`` profile.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        max_tokens: int = 16000,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as error:
                raise JudgeError(
                    "The judging step needs the Anthropic SDK: pip install -e '.[llm]'"
                ) from error
            # A scan sends hundreds of requests in a row, so a rate limit is waited out
            # a few more times than the SDK does by default.
            client = anthropic.Anthropic(max_retries=6)
        self._client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.input_tokens = 0
        self.output_tokens = 0

    def judge(
        self, passage: Passage, topic: Topic, neighbours: Neighbours | None = None
    ) -> Judgement:
        """Judge the passage alone, and look again with its neighbours if it is background.

        The second verdict replaces the first only when it says the passage is about the
        company and its evidence is found in a neighbouring paragraph.
        """
        what = f"passage {passage.id}"
        content = build_request(passage, topic)
        answer, model = self._ask(SYSTEM_PROMPT, ANSWER_SCHEMA, content, what)
        alone = judgement_from_answer(answer, passage, model)
        if alone.relevance is not Relevance.CONTEXT or not neighbours:
            return alone

        content = build_request(passage, topic, neighbours)
        answer, model = self._ask(system_prompt(neighbours), ANSWER_SCHEMA, content, what)
        again = judgement_from_answer(answer, passage, model, neighbours)
        linked = again.relevance is Relevance.COMPANY and again.evidence_from != "passage"
        if linked and again.evidence_verified:
            # The neighbour supplies the link and its direction. What the passage itself
            # says, how concretely and about the company's response, stays as first judged.
            return replace(
                again,
                concreteness=alone.concreteness,
                states_response=alone.states_response,
            )
        return replace(alone, saw_neighbours=True)

    def scan(self, passage: Passage, topic: Topic) -> Judgement:
        """Judge a passage that the phrase search did not find. One request, no second look."""
        content = build_request(passage, topic)
        system = SYSTEM_PROMPT + SCAN_PROMPT
        answer, model = self._ask(system, ANSWER_SCHEMA, content, f"passage {passage.id}")
        return judgement_from_answer(answer, passage, model)

    def pair(
        self, earlier: Sequence[Passage], later: Sequence[Passage], topic: Topic
    ) -> list[Pair]:
        """Which later passage takes the place of which earlier one. One request."""
        if not earlier or not later:
            return []
        answer, model = self._ask(
            PAIR_PROMPT, PAIR_SCHEMA, build_pair_request(earlier, later, topic), "the pairing"
        )
        try:
            return pairs_from_answer(answer, earlier, later, model)
        except (KeyError, ValueError, TypeError) as error:
            raise JudgeError(f"Unexpected answer for the pairing: {error}") from error

    def _ask(
        self, system: str, schema: dict[str, Any], content: str, what: str
    ) -> tuple[dict[str, Any], str]:
        """Send one request and return the parsed answer and the model that gave it."""
        response = self._send(system, schema, content)
        usage = getattr(response, "usage", None)
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0

        if response.stop_reason == "refusal":
            raise JudgeError(f"The model declined to answer for {what}.")
        if response.stop_reason == "max_tokens":
            raise JudgeError(f"The answer for {what} was cut off at max_tokens.")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise JudgeError(f"No text in the answer for {what}.")
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as error:
            raise JudgeError(f"The answer for {what} is not JSON.") from error
        # response.model is the model that answered, which differs after a fallback.
        return answer, getattr(response, "model", self.model)

    def _send(self, system: str, schema: dict[str, Any], content: str) -> Any:
        import anthropic

        try:
            request = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "output_config": {
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                "messages": [{"role": "user", "content": content}],
            }
            if supports_fallback(self.model):
                return self._client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **request
                )
            return self._client.messages.create(**request)
        except anthropic.AuthenticationError as error:
            raise JudgeError(
                "The Anthropic API rejected the credentials. Check ANTHROPIC_API_KEY."
            ) from error
        except anthropic.RateLimitError as error:
            raise JudgeError("Rate limited by the Anthropic API. Run again later.") from error
        except anthropic.APIStatusError as error:
            raise JudgeError(f"Anthropic API error {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise JudgeError("Could not reach the Anthropic API.") from error
        except anthropic.AnthropicError as error:
            raise JudgeError(f"Anthropic SDK error: {error}") from error
        except TypeError as error:
            # The SDK raises a plain TypeError when it finds no credentials.
            if "authentication" not in str(error):
                raise
            raise JudgeError(
                "No Anthropic credentials found. Set ANTHROPIC_API_KEY or run 'ant auth login'."
            ) from error
