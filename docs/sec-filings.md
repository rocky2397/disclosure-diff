# Reading filings with the SEC

Recorded on 19 November 2026.

Until now every report was a PDF, and every new company needed a fix to the PDF reading.
A company listed in the United States also files its annual report with the SEC as a web
page with a prescribed structure. `disclosure-diff fetch` downloads that filing by ticker, and
`disclosure-diff extract` reads it.

## How it works

- **Fetch.** The ticker is looked up at the SEC, and the annual filing (Form 10-K, or 20-F
  and 40-F for foreign companies) whose reported period ends in the year asked for is
  stored as `reports/<TICKER>/<year>.htm`. A fiscal year that ends in June 2025 is 2025.
  The SEC's list reaches back about five to seven years.
- **Contact.** The SEC asks automated tools to name a contact address. It is taken from
  the environment variable `DISCLOSURE_DIFF_SEC_CONTACT`, and nothing is sent without it.
- **Paragraphs** are the block elements of the page. Hidden machine-readable data is left
  out. A table cell that holds a sentence, as in a bullet list set as a table, is a
  paragraph; a cell with a number is too short to be kept.
- **Sections** are the items of the form, found by their headings: "Item 1A. Risk
  Factors", "Item 7. Management's Discussion and Analysis". For a 10-K the prescribed
  title is used, whatever capitals the filer chose.
- **Narrative only.** As for PDFs, the financial statements and their notes are left out,
  and so are the items that only point to the proxy statement. Kept for a 10-K: items 1,
  1A, 1B, 1C, 2, 3, 7 and 7A.
- **Citation.** A filing has no pages. A passage is cited by its item, for example
  "CAT Form 10-K 2025, Item 7. Management's Discussion and Analysis". The quote itself
  is word for word, so it can be found by searching the filing.

## What real filings needed

Tried on Chevron (CVX), Caterpillar (CAT), Microsoft (MSFT) and BP, each for 2024 and 2025.

- **Caterpillar and Microsoft** read correctly as first written.
- **Chevron** prints its management discussion and its statements after Item 14, each
  page headed only with the title of its part. Its Item 7 is one sentence that points
  there. The reader therefore also follows the prescribed titles ("Management's
  Discussion and Analysis…", "Notes to the Consolidated Financial Statements"). Without
  that, 220 paragraphs of discussion were left out.
- **BP is not read.** Its 20-F is the printed annual report converted to a 33 MB page,
  with every line as its own block and the items only in a cross-reference table at the
  end. Reading it by items gave 31 stray paragraphs out of 9,700. Such a filing is now
  refused with that explanation. A 20-F that does follow the item structure should work,
  but none has been tried.

| | CVX 2024 | CVX 2025 | CAT 2024 | CAT 2025 | MSFT 2024 | MSFT 2025 |
| --- | --- | --- | --- | --- | --- | --- |
| Size of the filing | 6.0 MB | 6.1 MB | 6.1 MB | 6.1 MB | 6.9 MB | 8.2 MB |
| Paragraphs kept | 495 | 509 | 485 | 491 | 433 | 383 |
| Items they stand in | 8 | 8 | 8 | 8 | 9 | 9 |

Reading a filing takes well under a second.

## The same company as PDF and as filing

Chevron's PDF annual report had been read before. Passages found, 2024 and 2025:

| Topic | Form 10-K | PDF annual report |
| --- | --- | --- |
| Protectionism | 8 and 12 | 4 and 7 |
| Climate change | 32 and 26 | 13 and 11 |
| Cybersecurity | 15 and 18 | 0 and 0 |
| Artificial intelligence | 6 and 6 | 7 and 8 |

The 10-K has the risk factors and the cybersecurity item, which the PDF does not. The PDF
has the letter to shareholders, which the 10-K does not, and Chevron writes about
artificial intelligence there too.

## Results on two topics

Passages about the company, with those that state a figure in brackets:

| | CVX 2024 | CVX 2025 | CAT 2024 | CAT 2025 | MSFT 2024 | MSFT 2025 |
| --- | --- | --- | --- | --- | --- | --- |
| Protectionism | 7 (0) | 7 (1) | 5 (0) | 15 (6) | 3 (0) | 5 (0) |
| Artificial intelligence | 6 (0) | 6 (1) | 2 (0) | 3 (0) | 60 (1) | 55 (1) |

2024 to 2025 (new, changed, dropped, unchanged):

| | Protectionism | Artificial intelligence |
| --- | --- | --- |
| Chevron | 1, 4, 1, 2 | 2, 4, 2, 0 |
| Caterpillar | 10, 0, 0, 5 | 1, 1, 0, 1 |
| Microsoft | 2, 3, 0, 0 | 12, 24, 17, 19 |

- **Caterpillar** is the clearest case so far of what the tool is for. In 2024 tariffs
  appear in five general risk paragraphs. In 2025 ten new passages stand in the
  management discussion, six of them with figures. Unfavourable manufacturing costs
  "largely reflected the impact of higher tariffs", and the company expects "the impact
  from tariffs to be around $2.6 billion in 2026".
- **Chevron** shows the same tariff paragraph as its PDF did, from "significant
  uncertainty" in 2024 to "less than one percent of the company's third party spend" in
  2025.
- **Microsoft** has about 60 passages on artificial intelligence in each year, which
  makes its comparison long: 72 entries.

All judging was done by `claude-haiku-5-5`; the 199 passages and six pairing requests
cost about 4 cents.

## Ten more companies

Added on 19 November 2026, after `disclosure-diff run` existed. One command each, for protectionism:
Deere (DE), Ford (F), Apple (AAPL), Nike (NKE), Walmart (WMT), Boeing (BA), Nucor (NUE),
Procter & Gamble (PG), Whirlpool (WHR) and Nvidia (NVDA). The two latest filings of each
were compared. A year is the year in which the reported period ends, so Walmart and
Nvidia, whose business year ends in January, are compared for 2025 and 2026.

**All twenty filings were read without a change to the reader.** Each has its business
description, risk factors and management discussion where the form puts them, with
between 53 and 408 paragraphs of discussion. The twenty files are 79 MB together, from
1.5 MB (Apple) to 10.8 MB (Deere). The ten runs took seven minutes.

| Company | Years | Paragraphs kept | Found | About the company | With a figure | New, changed, dropped, unchanged |
| --- | --- | --- | --- | --- | --- | --- |
| Deere | 2024, 2025 | 525, 567 | 14, 26 | 9, 17 | 0, 2 | 11, 5, 3, 1 |
| Ford | 2024, 2025 | 666, 686 | 15, 32 | 11, 30 | 1, 4 | 19, 10, 0, 1 |
| Apple | 2024, 2025 | 248, 238 | 1, 6 | 1, 5 | 0, 0 | 4, 1, 0, 0 |
| Nike | 2024, 2025 | 442, 432 | 17, 19 | 14, 16 | 0, 0 | 3, 9, 1, 4 |
| Walmart | 2025, 2026 | 372, 359 | 14, 12 | 8, 8 | 0, 0 | 1, 3, 1, 4 |
| Boeing | 2024, 2025 | 364, 359 | 13, 20 | 9, 16 | 0, 0 | 7, 6, 0, 3 |
| Nucor | 2024, 2025 | 359, 369 | 7, 7 | 5, 6 | 4, 1 | 2, 2, 1, 2 |
| Procter & Gamble | 2024, 2025 | 300, 302 | 10, 14 | 8, 13 | 0, 1 | 5, 3, 0, 5 |
| Whirlpool | 2024, 2025 | 364, 335 | 12, 28 | 9, 24 | 0, 2 | 16, 4, 1, 4 |
| Nvidia | 2025, 2026 | 433, 431 | 27, 37 | 26, 36 | 0, 1 | 14, 12, 4, 10 |

Over the ten companies the passages about the company go from 100 to 171, and those
with a figure from 5 to 11. Nine companies say more in the later filing; Walmart says
the same amount.

What the comparisons show:

- **Ford** puts an amount on it: "Ford’s gross costs related to tariffs implemented or
  revised in 2025 was about $3 billion, including the impact of tariff relief, and the
  net EBIT impact was about $2 billion after offsets." One passage is judged an
  opportunity: Ford expects "lower tariff costs of about $1.0 billion" in 2026.
- **Deere** gives an amount as well: "The direct impact of incremental tariffs incurred
  by us in 2025 was approximately $600". The filing presents all amounts in millions of
  dollars, which the quote alone does not show.
- **Whirlpool** goes from 9 to 24 passages and presents the tariffs as an advantage too:
  "approximately 80% of the major appliances we sell in the U.S. are produced in the
  U.S." The judge marks that passage as an opportunity.
- **Nucor**, a steel maker, is the one company for which most passages of the later
  filing, four of six, are judged an opportunity or both. It counts "142 AD/CVD orders
  in place on core steel product lines made by Nucor".
- **Nvidia** is about export controls, not tariffs: 26 passages, then 36.
- **Procter & Gamble** names "10 basis points of higher costs from tariffs".
- **Nike** has no figure. Its 2025 business year ended in May 2025.
- **Walmart**: four of the twelve paragraphs found use "sanctions" for legal penalties.
  The judge marked all four off topic.

### What the ten runs exposed

Nvidia prints the same paragraphs on export controls word for word in its business
description, its risk factors and its management discussion. A filing has no pages, so
such repeats share one identifier. They were judged several times, and counted several
times: 32 and 44 passages found instead of 27 and 37. A paragraph that a filing repeats
is now found once, where it first stands. None of the other filings read so far repeats
a paragraph that was found for any of the five topics, so no earlier figure changes.

### What it cost

343 paragraphs were judged and eight pairing requests sent, all by `claude-haiku-5-5`:
609,574 tokens in and 40,937 out, about 8 cents. Twelve of the 343 were the Nvidia
repeats.

### What was checked

The evidence sentence was word for word in the paragraph for 342 of the 343 verdicts.
Beyond that, the sentences with figures, the off-topic verdicts for Walmart and a few
background verdicts for Deere were read once. Nothing else was checked, by a person or
by a second model. One borderline case stood out: a bullet in a list of risks,
"increased tariffs, trade barriers, trade agreements, and other restrictions on
international trade", was judged background for Deere, while Caterpillar's bullet
"imposition of new or additional tariffs or quotas" was judged about the company.

## Limits

- Thirteen companies read, one refused. Every one of them is large and files a modern,
  machine-generated page. Older or hand-made filings, small companies and foreign filers
  are untried.
- A company that puts its management discussion into a separate exhibit, and only refers
  to it, will have no Item 7 here. None of the thirteen does.
- An item is a coarse place to cite. Item 7 of Chevron's filing has 220 paragraphs.
- The tables inside the narrative items are dropped, including those that state amounts.
- Nobody has checked the passages of the new companies beyond reading the comparisons
  once while writing this note.
- Business years differ. A filing for 2025 can end in May 2025 (Nike) or in November
  2025 (Deere), so the same year does not cover the same events for every company.
- A paragraph that a filing repeats in several items is counted once and cited by the
  first of them.
