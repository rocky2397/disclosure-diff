import pytest

from document_impact_analyzer.topics import TOPICS, get_topic


def test_known_topic():
    assert get_topic("protectionism").name == "Protectionism"


def test_unknown_topic_lists_the_known_ones():
    known = "artificial_intelligence, climate_change, covid, cybersecurity, protectionism"
    with pytest.raises(ValueError, match=known):
        get_topic("inflation")


@pytest.mark.parametrize("topic", TOPICS.values(), ids=lambda t: t.key)
def test_phrases_are_specific(topic):
    assert topic.question.endswith("?")
    assert len(set(topic.phrases)) == len(topic.phrases)
    for phrase in topic.phrases:
        assert phrase == phrase.lower().strip()
        # A bare common word would match unrelated text, as "trade" did in the old version.
        assert phrase not in {"trade", "quota", "duty", "foreign", "risk"}
    for phrase in topic.exclude:
        assert any(search in phrase for search in topic.phrases)
