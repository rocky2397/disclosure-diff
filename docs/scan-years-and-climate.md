# A scan, five years of one company, and a second topic

Recorded on 19 November 2026. Three things were run for the first time: a scan of a whole
report to see what the phrase search misses, three more years of RWE, and the climate
change topic. All judging was done by `claude-haiku-5-5` at low effort. Together the runs
cost about 22 cents at list prices.

## What the phrase search misses

`dia scan RWE 2025` had the judge read every paragraph the search had not found.

| | Paragraphs |
| --- | --- |
| In the report, tables left out | 717 |
| Found by the search | 12, of which 7 are about the company |
| Read by the scan | 705 |
| Called about the company by the scan | 4 |
| Called background by the scan | 13 |

The 17 flagged paragraphs were then read by hand, once:

| Paragraph | Reading |
| --- | --- |
| p. 67, risk chapter: "If cross-border trade is limited, it may prove impossible to deliver certain projects." | A miss. A trade restriction said in other words. |
| p. 6, letter from the CEO: components bought early, more sourcing from US suppliers | Borderline. The response to US trade policy, which the paragraph does not name. |
| p. 23 and p. 31: US offshore wind projects paused, approval processes reviewed | Energy policy, not trade. |
| 13 paragraphs called background | Regulation in general, gas supply, UK support schemes. None about trade. |

So on this report the search found 7 of the 8 or 9 paragraphs about the company. The
scan used 1.07 million input tokens, about 13 cents.

**Consequence.** The phrase "cross-border trade" was added to the topic. In the nine
reports read so far it finds that risk paragraph in RWE's 2022, 2024 and 2025 reports and
nothing else.

**Limits.** One report, one topic, one model. A paragraph that the judge would also get
wrong stays invisible. The scan flags loosely: 15 of its 17 were not about trade. That is
the cheaper error for this purpose, since a flagged paragraph only costs a minute to
read.

## Five years of RWE

The 2021, 2022 and 2023 reports were added. The 2022 and 2023 PDFs carry the publisher's
setting against copying text. The tool skips such files unless told otherwise; the owner
of this repository decided on 19 November 2026 to read them, with
`dia extract --allow-restricted`. No reading fix was needed for any of the three.

Protectionism, from `dia years RWE`:

| Year | Paragraphs read | Found | About the company | With a figure | Says what the company does | Background | Off topic |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 345 | 6 | 5 | 0 | 1 | 0 | 1 |
| 2022 | 436 | 6 | 5 | 2 | 2 | 1 | 0 |
| 2023 | 414 | 4 | 4 | 0 | 3 | 0 | 0 |
| 2024 | 729 | 9 | 8 | 2 | 2 | 1 | 0 |
| 2025 | 721 | 13 | 8 | 1 | 3 | 5 | 0 |

The reports from 2024 on are much longer because they contain the sustainability
statement, so the counts are not comparable without the first column.

Year to year, with pairing:

| | New | Changed | Dropped | Unchanged |
| --- | --- | --- | --- | --- |
| 2021 to 2022 | 2 | 3 | 2 | 0 |
| 2022 to 2023 | 2 | 2 | 3 | 0 |
| 2023 to 2024 | 4 | 4 | 0 | 0 |
| 2024 to 2025 | 3 | 4 | 3 | 1 |

What the reports say, in the order it appears:

- **2021** (published just after Russia invaded Ukraine): sanctions against Russia as a
  risk to the outlook and to European energy supply.
- **2022**: the halt of coal imports from Russia, with figures. Two new paragraphs on the
  US: customs requirements for solar modules from Xinjiang and an anti-dumping
  investigation against south-east Asian manufacturers, both with delays for RWE's
  projects. The risk chapter gains a paragraph on state restrictions on cross-border
  trade.
- **2023**: the two US solar paragraphs and the Russian coal paragraph are gone. Trade
  appears as a general supply chain risk ("potential trade embargoes or import duties").
- **2024**: tariffs return with the new US administration, with figures, and reach the
  letter from the CEO.
- **2025**: the risk is described as having materialised, and a new paragraph says what
  RWE does about it.

**Limits.** Pairing is not stable from run to run: the pairs for 2022 to 2023 differed
between two runs made an hour apart. Nobody has checked the pairs of the earlier years.

## Climate change

The second topic, on all seven reports. 278 passages were judged.

| | Paragraphs read | Found | About the company | With a figure | Says what the company does | Background | Off topic |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RWE 2021 | 345 | 34 | 25 | 12 | 15 | 7 | 2 |
| RWE 2022 | 436 | 37 | 30 | 5 | 22 | 7 | 0 |
| RWE 2023 | 414 | 34 | 30 | 7 | 18 | 4 | 0 |
| RWE 2024 | 729 | 82 | 58 | 10 | 43 | 15 | 9 |
| RWE 2025 | 721 | 67 | 46 | 9 | 33 | 11 | 10 |
| Chevron 2024 | 571 | 13 | 12 | 2 | 8 | 1 | 0 |
| Chevron 2025 | 760 | 11 | 9 | 1 | 5 | 1 | 1 |

| | New | Changed | Dropped | Unchanged |
| --- | --- | --- | --- | --- |
| RWE 2021 to 2022 | 22 | 8 | 17 | 0 |
| RWE 2022 to 2023 | 13 | 17 | 13 | 0 |
| RWE 2023 to 2024 | 35 | 23 | 7 | 0 |
| RWE 2024 to 2025 | 9 | 37 | 21 | 0 |
| Chevron 2024 to 2025 | 0 | 6 | 3 | 3 |

- The evidence was quoted word for word in 275 of 278 judgements.
- 50 passages came back as background and got a second look with their neighbouring
  paragraphs. Four were changed to "about the company". On protectionism the second look
  had changed none.
- Of the passages about the company, 68 present the topic as an opportunity, 57 as a
  risk, 35 as both and 50 only describe.
- Chevron's 2025 report no longer has three passages its 2024 report had, among them the
  planned lower-carbon capital spend of about $10 billion through 2028. "No longer has"
  means the search found no counterpart. The 2025 report was read by OCR, so this should
  be checked in the PDF before it is relied on.

**Limits.** The judge's instructions use examples from protectionism, and no second model
has judged the climate passages, so there is not even agreement between models to report.
There is no frozen reference for this topic. With 40 to 80 passages a year, RWE's
comparisons run to more than 60 entries each, which is a lot to read.
