# Three more topics

Recorded on 19 November 2026. Artificial intelligence, the Covid-19 pandemic and
cybersecurity were added and run on the seven reports read so far (RWE 2021 to 2025,
Chevron 2024 and 2025). The topics were chosen for their shape over the five RWE years:
one that should rise, one that should fade, and one that should stay the same. All
judging was done by `claude-haiku-5-5` at low effort; the round cost about 30 cents, 26 of
them for the three scans.

## What had to change first

The judge's instructions explained "off topic" and "quantified" with examples from
protectionism (a tariff as a price plan). They are now neutral, and a topic carries a
sentence of its own, `not_this`, on what its search phrases also find. It is sent with
each request.

`dia eval` on the protectionism reference, before and after:

| Answer | Before | After |
| --- | --- | --- |
| About the company, background or off topic | 57 of 62 | 57 of 62 |
| Risk, opportunity, both or neither | 57 of 62 | 57 of 62 |
| Generic, specific or quantified | 47 of 62 | 51 of 62 |
| Says what the company does about it | 61 of 62 | 56 of 62 |

The first answer, which decides what a comparison shows, did not move. The other
differences are within the noise of 62 answers (about 13 points).

## Results

Passages about the company, with the passages found in brackets:

| Topic | RWE 2021 | RWE 2022 | RWE 2023 | RWE 2024 | RWE 2025 | Chevron 2024 | Chevron 2025 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Artificial intelligence | 0 (0) | 0 (0) | 0 (0) | 3 (5) | 16 (21) | 7 (7) | 8 (8) |
| Covid-19 | 15 (19) | 4 (7) | 0 (0) | 0 (0) | 0 (0) | 0 (0) | 0 (0) |
| Cybersecurity | 2 (2) | 4 (5) | 3 (3) | 3 (3) | 3 (3) | 0 (0) | 0 (0) |

Year to year (new, changed, dropped, unchanged):

| | Artificial intelligence | Covid-19 | Cybersecurity |
| --- | --- | --- | --- |
| RWE 2021 to 2022 | none found | 0, 4, 11, 0 | 2, 1, 0, 1 |
| RWE 2022 to 2023 | none found | 0, 0, 4, 0 | 0, 3, 1, 0 |
| RWE 2023 to 2024 | 3, 0, 0, 0 | none found | 0, 1, 0, 2 |
| RWE 2024 to 2025 | 13, 3, 0, 0 | none found | 0, 3, 0, 0 |
| Chevron 2024 to 2025 | 5, 3, 4, 0 | none found | none found |

The evidence was quoted word for word in 81 of the 82 judgements.

- **Artificial intelligence** appears in RWE's reports in 2024: electricity demand driven
  by AI, and the sale of land to Microsoft. In 2025 it is in the letter from the CEO, the
  strategy, the earnings and the outlook, and six passages give figures. All but one of
  the passages present it as an opportunity. Chevron writes about supplying power to data
  centres from natural gas, and in 2025 about using AI in its own operations.
- **Covid-19** has 15 passages in RWE's 2021 report, 4 in 2022 and none after.
- **Cybersecurity** is the same handful of paragraphs every year: the risk chapter, the
  Supervisory Board's report and the description of who is responsible. Chevron's PDF has
  none, because that material is in its filing with the SEC.

## What the new topics exposed

Three defects, each fixed with a test:

- **A year with nothing found could not be compared.** It has no judgements because there
  was nothing to judge, and the comparison took it for unjudged. That blocked the year in
  which a topic appears or disappears.
- **OCR reads "AI" as "Al".** In Chevron's 2025 report, read by OCR, four paragraphs were
  missed. In text read by OCR, the word "Al" is now searched as "AI". Chevron 2025 went
  from 3 passages found to 7, and to 8 with the fix for compounds described below.
- **A dropped drive ended a run in a traceback.** The external drive with the data folder
  went away twice during scans. The command now says so and that a rerun continues.

## What the searches miss

One scan per topic, each on the report where the topic is strongest. Every flagged
paragraph was read by hand, once.

| Topic | Report | Paragraphs read | Flagged | Misses |
| --- | --- | --- | --- | --- |
| Covid-19 | RWE 2021 | 326 | 3 | none |
| Cybersecurity | RWE 2023 | 411 | 1 | none |
| Artificial intelligence | RWE 2025 | 697 | 5 | one, and two borderline |

- The four flags for Covid-19 and cybersecurity are about a biomass law, the economic
  upswing, the general price level and US support for renewables.
- The miss for artificial intelligence is a paragraph on "Al-powered video analyses",
  spelt with a lowercase l in RWE's own PDF. Compounds of this kind are now found in any
  text. The judge then called that paragraph off topic, although the scan had called it
  about the company: a single verdict on a borderline passage is not stable.
- The two borderline paragraphs are about power supply contracts with "US technology
  companies" and with Amazon. They concern the same demand but name neither AI nor data
  centres, and the phrase list was left as it is.

## Limits

- No second model has judged these topics and none has a frozen reference, so there is
  no agreement figure for them.
- Each phrase list was scanned on one report of one company. Chevron's wording was not
  scanned.
- RWE and Chevron are both energy companies. For them AI is mostly electricity demand;
  the topic's question was written with that in mind and may fit other industries badly.
