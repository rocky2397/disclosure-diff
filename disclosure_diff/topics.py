"""Topics to look for in annual reports.

A topic's phrases are used to find candidate passages, so they favour recall: a phrase may
be ambiguous ("sanction" also means a penalty) as long as it is specific enough not to hit
unrelated text. Single common words such as "trade" or "quota" are left out on purpose.
Deciding whether a candidate is really about the topic is a later, separate step.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    name: str
    # What a reader should be able to answer "yes" to for a passage to count.
    question: str
    phrases: tuple[str, ...]
    # Longer phrases that contain a search phrase but mean something else.
    exclude: tuple[str, ...] = ()
    # What the search phrases also find that is not this topic, in a sentence for the judge.
    not_this: str = ""


PROTECTIONISM = Topic(
    key="protectionism",
    name="Protectionism",
    question=(
        "Does the passage describe trade barriers, sanctions or other protectionist "
        "policy as something that affects or could affect the company?"
    ),
    phrases=(
        "protectionism",
        "protectionist",
        "trade barrier",
        "trade restriction",
        "trade war",
        "trade conflict",
        "trade dispute",
        "trade tension",
        "trade policy",
        "trade sanction",
        # Found by 'disclosure-diff scan' on RWE's 2025 report: "If cross-border trade is
        # limited, it may prove impossible to deliver certain projects."
        "cross-border trade",
        "tariff",
        "import duty",
        "customs duty",
        "anti-dumping",
        "countervailing duty",
        "safeguard measure",
        "import quota",
        "import restriction",
        "import ban",
        "export control",
        "export restriction",
        "export ban",
        "local content requirement",
        "sanction",
        "embargo",
        "economic nationalism",
        "deglobalization",
        "deglobalisation",
        "foreign investment restriction",
        "foreign investment screening",
        "nationalization",
        "nationalisation",
        "expropriation",
    ),
    exclude=(
        # For utilities a tariff is a price plan, not a customs duty.
        "feed-in tariff",
        "electricity tariff",
        "gas tariff",
        "energy tariff",
        "network tariff",
        "grid tariff",
        "regulated tariff",
        "social tariff",
        "default tariff",
        "variable tariff",
        "tariff customer",
        "tariff on electricity",
    ),
    not_this=(
        'In the reports of utilities "tariff" often means a price plan or a grid charge, '
        'and "sanction" can mean a penalty for breaking a rule.'
    ),
)

CLIMATE_CHANGE = Topic(
    key="climate_change",
    name="Climate change",
    question=(
        "Does the passage describe climate change, or policy responding to it, as "
        "something that affects or could affect the company?"
    ),
    phrases=(
        "climate change",
        "climate risk",
        "climate policy",
        "climate target",
        "climate neutrality",
        "global warming",
        "greenhouse gas",
        "carbon emission",
        "carbon price",
        "carbon tax",
        "carbon neutral",
        "emissions trading",
        "net zero",
        "paris agreement",
        "decarbonization",
        "decarbonisation",
        "energy transition",
        "extreme weather",
        "sea level rise",
    ),
)

ARTIFICIAL_INTELLIGENCE = Topic(
    key="artificial_intelligence",
    name="Artificial intelligence",
    question=(
        "Does the passage describe artificial intelligence, or the demand for computing "
        "and data centres that it drives, as something that affects or could affect the "
        "company?"
    ),
    phrases=(
        "artificial intelligence",
        # Written "AI" in most reports. As a whole word it has no other meaning there.
        "ai",
        "machine learning",
        "deep learning",
        "large language model",
        "neural network",
        "chatbot",
        "data centre",
        "data center",
        "hyperscaler",
    ),
    not_this=(
        "The company's own IT systems, digital tools or data centres where artificial "
        "intelligence plays no part."
    ),
)

COVID = Topic(
    key="covid",
    name="Covid-19 pandemic",
    question=(
        "Does the passage describe the Covid-19 pandemic, or the measures taken against "
        "it, as something that affects, has affected or could affect the company?"
    ),
    phrases=(
        "covid",
        "coronavirus",
        "corona",
        "sars-cov-2",
        "pandemic",
        "epidemic",
        "lockdown",
    ),
    not_this=(
        '"Corona" can mean an electrical discharge on power lines, and "pandemic" or '
        '"epidemic" can refer to another disease or be a figure of speech.'
    ),
)

CYBERSECURITY = Topic(
    key="cybersecurity",
    name="Cybersecurity",
    question=(
        "Does the passage describe cyberattacks, or the security of IT systems and data, "
        "as something that affects or could affect the company?"
    ),
    phrases=(
        "cyber",
        "cybersecurity",
        "cyberattack",
        "cybercrime",
        "information security",
        "it security",
        "data security",
        "data breach",
        "ransomware",
        "malware",
        "phishing",
        "hacker",
    ),
    not_this=(
        '"Security" in the sense of security of energy supply or of financial securities, '
        "and data protection law where no attack and no IT security is concerned."
    ),
)

TOPICS: dict[str, Topic] = {
    topic.key: topic
    for topic in (PROTECTIONISM, CLIMATE_CHANGE, ARTIFICIAL_INTELLIGENCE, COVID, CYBERSECURITY)
}


def get_topic(key: str) -> Topic:
    try:
        return TOPICS[key]
    except KeyError:
        known = ", ".join(sorted(TOPICS))
        raise ValueError(f"Unknown topic {key!r}. Known topics: {known}") from None
