import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from disclosure_diff.judge import (
    ANSWER_SCHEMA,
    FALLBACK_BETA,
    NEIGHBOURS_PROMPT,
    SCAN_PROMPT,
    SYSTEM_PROMPT,
    ClaudeJudge,
    JudgeError,
    build_request,
)
from disclosure_diff.judgements import Concreteness, Direction, Relevance
from disclosure_diff.pairing import PAIR_PROMPT, PAIR_SCHEMA, Pair, build_pair_request
from disclosure_diff.passages import Neighbours, Passage
from disclosure_diff.topics import PROTECTIONISM

anthropic = pytest.importorskip("anthropic")

PASSAGE = Passage(
    "RWE",
    2025,
    64,
    "The increase in tariff barriers caused another risk to materialise. There is a danger "
    "that additional tariffs could be introduced, making component imports more expensive.",
    section="2.9 Development of risks and opportunities",
)
ANSWER = {
    "relevance": "company",
    "direction": "risk",
    "concreteness": "specific",
    "states_response": False,
    "evidence": "additional tariffs could be introduced, making component imports more expensive",
}


class FakeClient:
    """Stands in for anthropic.Anthropic: records the requests and returns canned answers.

    Given a list of answers, it returns them in turn and repeats the last one.
    """

    def __init__(self, answer=ANSWER, *, stop_reason="end_turn", model="claude-opus-5-5"):
        self.requests = []
        answers = answer if isinstance(answer, list) else [answer]
        self._queue = [
            SimpleNamespace(
                stop_reason=stop_reason,
                model=model,
                content=[
                    SimpleNamespace(type="thinking", thinking=""),
                    SimpleNamespace(
                        type="text", text=item if isinstance(item, str) else json.dumps(item)
                    ),
                ],
                usage=SimpleNamespace(input_tokens=700, output_tokens=90),
            )
            for item in answers
        ]
        self._response = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.requests.append(request)
        if isinstance(self._response, Exception):
            raise self._response
        return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]


def test_request_shape():
    client = FakeClient(model="claude-haiku-5-5")
    ClaudeJudge(client).judge(PASSAGE, PROTECTIONISM)

    (request,) = client.requests
    assert request["model"] == "claude-haiku-5-5"
    assert request["system"] == SYSTEM_PROMPT
    assert request["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
    }
    # Thinking is left to the model, and the answer format replaces prefill.
    assert "thinking" not in request and "temperature" not in request
    assert [message["role"] for message in request["messages"]] == ["user"]
    assert request["messages"][0]["content"] == build_request(PASSAGE, PROTECTIONISM)


def test_models_with_a_server_side_fallback_ask_for_it():
    client = FakeClient()
    ClaudeJudge(client, model="claude-opus-5-5").judge(PASSAGE, PROTECTIONISM)
    (request,) = client.requests
    assert request["model"] == "claude-opus-5-5"
    assert request["betas"] == [FALLBACK_BETA] and request["fallbacks"] == "default"


def test_request_text_names_topic_source_and_passage():
    text = build_request(PASSAGE, PROTECTIONISM)
    assert text.startswith("Topic: Protectionism\nQuestion: Does the passage describe")
    # The topic brings its own false friends; the instructions name none.
    assert '\nNot this topic: In the reports of utilities "tariff" often means' in text
    assert "tariff" not in SYSTEM_PROMPT
    plain = build_request(PASSAGE, replace(PROTECTIONISM, not_this=""))
    assert "Not this topic" not in plain and "?\nCompany: RWE" in plain
    assert "Company: RWE" in text
    assert 'section "2.9 Development of risks and opportunities", page 64' in text
    assert text.endswith("more expensive.\n</passage>")


def test_answer_becomes_a_judgement_with_verified_evidence():
    judge = ClaudeJudge(FakeClient())
    judgement = judge.judge(PASSAGE, PROTECTIONISM)

    assert judgement.passage_id == PASSAGE.id
    assert judgement.relevance is Relevance.COMPANY
    assert judgement.direction is Direction.RISK
    assert judgement.concreteness is Concreteness.SPECIFIC
    assert judgement.states_response is False
    assert judgement.evidence_verified
    assert judgement.model == "claude-opus-5-5"
    assert (judge.input_tokens, judge.output_tokens) == (700, 90)


def test_evidence_that_is_not_in_the_passage_is_marked():
    answer = ANSWER | {"evidence": "tariffs cost RWE €120 million in 2025"}
    judgement = ClaudeJudge(FakeClient(answer)).judge(PASSAGE, PROTECTIONISM)
    assert not judgement.evidence_verified


def test_the_answering_model_is_recorded_after_a_fallback():
    judgement = ClaudeJudge(FakeClient(model="claude-opus-5")).judge(PASSAGE, PROTECTIONISM)
    assert judgement.model == "claude-opus-5"


@pytest.mark.parametrize(
    ("client", "message"),
    [
        (FakeClient(stop_reason="refusal"), "declined"),
        (FakeClient(stop_reason="max_tokens"), "cut off"),
        (FakeClient("not json"), "not JSON"),
        (FakeClient(ANSWER | {"relevance": "maybe"}), "Unexpected answer"),
    ],
)
def test_unusable_answers_raise(client, message):
    with pytest.raises(JudgeError, match=message):
        ClaudeJudge(client).judge(PASSAGE, PROTECTIONISM)


def test_api_errors_become_judge_errors():
    client = FakeClient()
    client._response = anthropic.APIConnectionError(request=SimpleNamespace())
    with pytest.raises(JudgeError, match="Could not reach the Anthropic API"):
        ClaudeJudge(client).judge(PASSAGE, PROTECTIONISM)


def test_missing_credentials_are_explained(monkeypatch, tmp_path):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no stored login profile either
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # The SDK refuses to build the request, so nothing is sent.
    with pytest.raises(JudgeError, match="No Anthropic credentials found"):
        ClaudeJudge().judge(PASSAGE, PROTECTIONISM)


def test_the_default_model_is_a_haiku_and_does_not_ask_for_a_fallback():
    client = FakeClient(model="claude-haiku-5-5")
    judgement = ClaudeJudge(client).judge(PASSAGE, PROTECTIONISM)

    (request,) = client.requests
    assert request["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in request and "betas" not in request
    assert request["output_config"]["format"]["schema"] == ANSWER_SCHEMA
    assert judgement.model == "claude-haiku-5-5"


# A description of an event, and the paragraph after it that says what it means for the company.
EVENT = Passage(
    "RWE",
    2025,
    31,
    "In April the US government announced new tariffs on imports from nearly all countries.",
    section="2.1 Business environment",
)
LINK = Passage(
    "RWE",
    2025,
    32,
    "The measures raise the cost of components for our US onshore wind and solar projects.",
    section="2.1 Business environment",
)
BACKGROUND = ANSWER | {
    "relevance": "context",
    "direction": "none",
    "evidence": "the US government announced new tariffs",
}
LINKED = ANSWER | {"evidence": "The measures raise the cost of components"}


def test_a_passage_judged_as_background_gets_a_second_look_with_its_neighbours():
    client = FakeClient([BACKGROUND, LINKED], model="claude-haiku-5-5")
    judge = ClaudeJudge(client)
    judgement = judge.judge(EVENT, PROTECTIONISM, Neighbours(after=LINK))

    first, second = client.requests
    assert first["system"] == SYSTEM_PROMPT
    assert first["messages"][0]["content"] == build_request(EVENT, PROTECTIONISM)
    assert second["system"] == SYSTEM_PROMPT + NEIGHBOURS_PROMPT
    text = second["messages"][0]["content"]
    assert "<before>" not in text
    assert text.index("<passage>") < text.index("<after>\nThe measures raise the cost")
    assert text.endswith("solar projects.\n</after>")

    # The neighbouring sentence is quoted word for word, so the passage is about the company.
    assert judgement.relevance is Relevance.COMPANY and judgement.evidence_verified
    assert judgement.direction is Direction.RISK
    assert judgement.evidence_from == "after" and judgement.saw_neighbours
    assert (judge.input_tokens, judge.output_tokens) == (1400, 180)


def test_the_second_look_does_not_change_what_the_passage_itself_says():
    second = LINKED | {"concreteness": "quantified", "states_response": True}
    client = FakeClient([BACKGROUND, second])
    judgement = ClaudeJudge(client).judge(EVENT, PROTECTIONISM, Neighbours(after=LINK))
    assert judgement.relevance is Relevance.COMPANY and judgement.evidence_from == "after"
    # Both were judged on the passage alone the first time, and that stands.
    assert judgement.concreteness is Concreteness.SPECIFIC and not judgement.states_response


def test_a_passage_about_the_company_is_not_looked_at_again():
    client = FakeClient(model="claude-haiku-5-5")
    judgement = ClaudeJudge(client).judge(PASSAGE, PROTECTIONISM, Neighbours(after=LINK))
    assert len(client.requests) == 1
    assert not judgement.saw_neighbours and judgement.evidence_from == "passage"


def test_background_without_neighbours_is_judged_once():
    client = FakeClient(BACKGROUND)
    judgement = ClaudeJudge(client).judge(EVENT, PROTECTIONISM, Neighbours())
    assert len(client.requests) == 1 and judgement.relevance is Relevance.CONTEXT


@pytest.mark.parametrize(
    "second",
    [
        BACKGROUND,
        # Says company, but quotes the passage itself: no link from a neighbour.
        ANSWER | {"evidence": "the US government announced new tariffs"},
        # Says company and points at a sentence that is in neither neighbour.
        ANSWER | {"evidence": "Tariffs cost us €120 million."},
    ],
)
def test_the_first_verdict_stands_unless_a_neighbour_is_quoted(second):
    client = FakeClient([BACKGROUND, second])
    judgement = ClaudeJudge(client).judge(EVENT, PROTECTIONISM, Neighbours(before=LINK))
    assert len(client.requests) == 2
    assert judgement.relevance is Relevance.CONTEXT and judgement.evidence_from == "passage"
    assert judgement.evidence_verified and judgement.saw_neighbours


def test_a_mark_copied_along_with_the_evidence_is_dropped():
    answer = LINKED | {"evidence": "for our US onshore wind and solar projects.</after>"}
    client = FakeClient([BACKGROUND, answer])
    judgement = ClaudeJudge(client).judge(EVENT, PROTECTIONISM, Neighbours(after=LINK))
    assert judgement.evidence == "for our US onshore wind and solar projects."
    assert judgement.evidence_verified and judgement.evidence_from == "after"


def test_pairing_is_one_request_with_its_own_prompt_and_answer_format():
    client = FakeClient({"pairs": [{"earlier": 1, "later": 1}]}, model="claude-haiku-5-5")
    judge = ClaudeJudge(client)
    earlier, later = [EVENT], [LINK, PASSAGE]

    assert judge.pair(earlier, later, PROTECTIONISM) == [
        Pair(EVENT.id, LINK.id, "claude-haiku-5-5")
    ]
    (request,) = client.requests
    assert request["system"] == PAIR_PROMPT
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": PAIR_SCHEMA}
    assert request["messages"][0]["content"] == build_pair_request(earlier, later, PROTECTIONISM)
    assert (judge.input_tokens, judge.output_tokens) == (700, 90)


def test_pairing_sends_nothing_when_one_year_has_no_passages_left():
    client = FakeClient({"pairs": []})
    assert ClaudeJudge(client).pair([], [LINK], PROTECTIONISM) == []
    assert client.requests == []


def test_a_pair_that_names_no_passage_is_an_error():
    client = FakeClient({"pairs": [{"earlier": 4, "later": 1}]})
    with pytest.raises(JudgeError, match="Unexpected answer for the pairing: E4 and L1"):
        ClaudeJudge(client).pair([EVENT], [LINK], PROTECTIONISM)


def test_a_scan_is_one_request_that_says_the_passage_was_not_selected():
    answer = BACKGROUND | {"relevance": "off_topic"}
    client = FakeClient(answer, model="claude-haiku-5-5")
    judgement = ClaudeJudge(client).scan(EVENT, PROTECTIONISM)

    (request,) = client.requests
    assert request["system"] == SYSTEM_PROMPT + SCAN_PROMPT
    assert request["messages"][0]["content"] == build_request(EVENT, PROTECTIONISM)
    assert judgement.relevance is Relevance.OFF_TOPIC and not judgement.saw_neighbours


def test_a_scan_does_not_look_twice_at_background():
    client = FakeClient(BACKGROUND)
    assert ClaudeJudge(client).scan(EVENT, PROTECTIONISM).relevance is Relevance.CONTEXT
    assert len(client.requests) == 1


def test_a_filing_is_named_as_such_in_the_request_and_has_no_page():
    filing = Passage("CVX", 2024, 0, PASSAGE.text, "Item 1A. Risk Factors", form="10-K")
    text = build_request(filing, PROTECTIONISM)
    assert 'Source: Form 10-K 2024, section "Item 1A. Risk Factors"\n\n<passage>' in text
