# Disclosure Diff

Shows what a company's annual reports say about a topic, and how that changed from one
year to the next. Every finding is a quote with its place in the report, so it can be
checked against the source.

## Example: Caterpillar and tariffs

```bash
disclosure-diff run CAT 2024 2025
```

This downloads Caterpillar's annual filings for both years from the SEC, reads about 490
paragraphs in each, finds the 7 and 17 that mention trade barriers, and has Claude judge
which of them are about Caterpillar itself. It takes half a minute and costs less than a
cent.

| | 2024 | 2025 |
| --- | --- | --- |
| Paragraphs about Caterpillar and trade barriers | 5 | 15 |
| Of those, in the management discussion | 0 | 10 |
| Of those, stating a figure | 0 | 6 |

In the 2024 filing the topic appears only among the risk factors, as something that
could happen. The same five paragraphs stand unchanged in the 2025 filing:

> The implementation of more restrictive trade policies (such as more detailed inspections, higher tariffs or new barriers to entry) in countries where we sell large quantities of products and services could negatively impact our business, results of operations and financial condition.
>
> CAT Form 10-K 2024, Item 1A. Risk Factors

The 2025 filing adds ten paragraphs, all in the management discussion, in which tariffs
are a cost with an amount:

> Operating profit was $11.151 billion in 2025, a decrease of $1.921 billion, or 15 percent, compared with $13.072 billion in 2024. The decrease was primarily due to unfavorable manufacturing costs of $2.148 billion and unfavorable price realization of $817 million, partially offset by the profit impact of higher sales volume of $1.218 billion. Unfavorable manufacturing costs largely reflected the impact of higher tariffs.
>
> CAT Form 10-K 2025, Item 7. Management's Discussion and Analysis

> Based on the incremental tariffs announced in 2025 and in place by January 29, 2026, we expect the impact from tariffs to be around $2.6 billion in 2026, which is $800 million higher than incurred in 2025. If we do not take the mitigating actions we plan to take in 2026, the impact from tariffs could be around 20 percent higher. We remain confident that we will manage the impact of tariffs over time.
>
> CAT Form 10-K 2025, Item 7. Management's Discussion and Analysis

The three quotes are picked for this page. The report as the tool wrote it, with all 15
paragraphs, is [docs/examples/CAT_protectionism_2024_2025.md](docs/examples/CAT_protectionism_2024_2025.md).

The tool measures **disclosure**: what the company reports and how the wording moved. It
does not measure how exposed the company really is, and nobody has checked its verdicts
by hand; see [Limits](#limits).

## Quick start

```bash
pip install -e ".[llm]"
mkdir disclosure-diff-data
export DISCLOSURE_DIFF_DATA_DIR="$PWD/disclosure-diff-data"
export ANTHROPIC_API_KEY="your key"
export DISCLOSURE_DIFF_SEC_CONTACT="you@example.org"
disclosure-diff run CAT 2024 2025
```

- Requires Python 3.10 or newer. The `llm` extra is the Anthropic SDK.
- The SEC asks automated tools to name a contact address, which is taken from
  `DISCLOSURE_DIFF_SEC_CONTACT`.
- Any ticker of a company that files a Form 10-K works in place of `CAT`, and
  `--topic artificial_intelligence` or another of the five topics in place of the default,
  protectionism.
- `--dry-run` downloads and reads, shows how many paragraphs would be sent to Claude, and
  sends nothing.
- Every step keeps its results in the data folder. Running the command again downloads
  nothing and sends nothing twice.
- For a company that does not file with the SEC, put its reports into the data folder
  as `reports/<COMPANY>/<year>.pdf`, named after the reporting year, and run
  `disclosure-diff run <COMPANY> 2024 2025`.

## The steps one by one

`disclosure-diff run` is these commands in a row. Each can be run alone, with more options.

```bash
disclosure-diff fetch CAT 2024 2025
disclosure-diff extract
disclosure-diff judge CAT 2024
disclosure-diff judge CAT 2025
disclosure-diff pair CAT 2024 2025
disclosure-diff changes CAT 2024 2025
```

- **`fetch`** downloads a company's annual filing with the SEC (Form 10-K) by ticker.
- **`extract`** reads every report into paragraphs with their section, and their page
  where the report has pages.
- **`judge`** asks Claude, one request per paragraph found, whether it is about the
  company, only background, or off topic. A paragraph that comes back as background is
  sent once more with the paragraphs before and after it, in case the link to the company
  is stated there. It costs money, though little: 31 paragraphs cost less than a cent
  with the default model. `--dry-run` only counts. Results are stored, so nothing is sent
  twice.
- **`pair`** asks Claude, in one request, which of the paragraphs that wording could not
  match are the same statement written anew. Optional; without it such a paragraph
  appears as one dropped and one new.
- **`changes`** compares the two years and writes
  `output/CAT_protectionism_2024_2025.md`. It makes no requests. Without judgements it
  compares everything found and says so.

Two more commands look across a report or across years:

```bash
disclosure-diff years RWE
```

```bash
disclosure-diff scan RWE 2025
```

- **`years`** prints one line per report: paragraphs found, how many are about the
  company, and how many of those state a figure or a response. It makes no requests.
- **`scan`** has Claude read every paragraph the search did *not* find and writes those
  it calls relevant to `output/RWE_2025_protectionism_missed.md`, to be read before
  search phrases are added. One request per paragraph: about 13 cents for a report of
  700 paragraphs. It can be interrupted and continued.

Useful options:

| Option | What it does |
| --- | --- |
| `extract --ocr` | Also reads text that exists only as pictures or cannot be decoded. Needs `pip install -e ".[ocr]"` and Tesseract (`brew install tesseract`). |
| `extract --allow-restricted` | Reads PDFs whose publisher switched off text extraction. They are skipped otherwise. |
| `extract --force` | Reads reports again. |
| `judge --model`, `--effort` | Another model or effort level, also for `pair` and `eval`. The default is `claude-haiku-5-5` at low effort; see [docs/judge-model-comparison.md](docs/judge-model-comparison.md). |
| `judge --again` | Judges paragraphs that already have a verdict. The new verdict replaces the old one; the old line stays in the file. |
| `judge --no-context` | No second look with the neighbouring paragraphs. Also for `eval`. |
| `changes --include-context` | Keeps background mentions too. |
| `changes --all-passages` | Ignores the judgements. |

### Evaluate

```bash
disclosure-diff eval-freeze
```

```bash
disclosure-diff eval
```

`eval-freeze` keeps the current verdicts, with their passages, as a fixed reference.
`eval` judges those passages again, twice by default, with any `--model` and `--effort`,
and reports how many answers match, how stable the judge is, whether its evidence is
quoted word for word, and what the run used. It needs no labelling. It measures
agreement with the model that made the reference, not accuracy; see
[docs/evaluation.md](docs/evaluation.md) for what that is good for and the first run.

Five topics are defined in `disclosure_diff/topics.py`: protectionism, climate
change, artificial intelligence, Covid-19 and cybersecurity. Pass for example
`--topic artificial_intelligence` to any command. A topic is a list of search phrases, the
question a passage has to answer, and a sentence on what the phrases also find that is not
the topic. Adding one takes a few lines; `disclosure-diff scan` then shows what its phrases miss.

## Results so far

Protectionism:

| | RWE 2021 | RWE 2022 | RWE 2023 | RWE 2024 | RWE 2025 | Chevron 2024 | Chevron 2025 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| How it was read | PDF text | PDF text | PDF text | PDF text | PDF text | PDF text | OCR |
| Paragraphs read | 345 | 436 | 414 | 729 | 721 | 571 | 760 |
| Found | 6 | 6 | 4 | 9 | 13 | 4 | 7 |
| About the company | 5 | 5 | 4 | 8 | 8 | 4 | 4 |
| Background only | 0 | 1 | 0 | 1 | 5 | 0 | 0 |
| Off topic | 1 | 0 | 0 | 0 | 0 | 0 | 3 |

Comparison of the paragraphs about the company:

| | New | Changed | Dropped | Unchanged |
| --- | --- | --- | --- | --- |
| RWE 2021 to 2022 | 2 | 3 | 2 | 0 |
| RWE 2022 to 2023 | 2 | 2 | 3 | 0 |
| RWE 2023 to 2024 | 4 | 4 | 0 | 0 |
| RWE 2024 to 2025 | 3 | 4 | 3 | 1 |
| Chevron 2024 to 2025 | 1 | 1 | 1 | 2 |

From 2024 to 2025, RWE's risk section moves from describing import duties as something
that could raise costs to saying that the increase in tariff barriers caused a risk to
materialise, and a new paragraph says what RWE does about it.

Over the five RWE reports the topic moves from sanctions against Russia (2021, 2022) to
US customs rules for solar modules (2022), fades to a general supply chain risk (2023),
and returns with the US tariffs (2024, 2025). Climate change has been run on the same
seven reports, 278 passages. Both, and the scan of one whole report, are written up in
[docs/scan-years-and-climate.md](docs/scan-years-and-climate.md).

From filings with the SEC ([docs/sec-filings.md](docs/sec-filings.md)), passages about
the company, with those that state a figure in brackets:

| | Chevron 2024 | Chevron 2025 | Caterpillar 2024 | Caterpillar 2025 | Microsoft 2024 | Microsoft 2025 |
| --- | --- | --- | --- | --- | --- | --- |
| Protectionism | 7 (0) | 7 (1) | 5 (0) | 15 (6) | 3 (0) | 5 (0) |
| Artificial intelligence | 6 (0) | 6 (1) | 2 (0) | 3 (0) | 60 (1) | 55 (1) |

Ten more companies, one `disclosure-diff run` each, none of which needed a change to the reader.
Passages on protectionism about the company, in the two latest filings:

| | Deere | Ford | Apple | Nike | Walmart | Boeing | Nucor | P&G | Whirlpool | Nvidia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Earlier filing | 9 (0) | 11 (1) | 1 (0) | 14 (0) | 8 (0) | 9 (0) | 5 (4) | 8 (0) | 9 (0) | 26 (0) |
| Later filing | 17 (2) | 30 (4) | 5 (0) | 16 (0) | 8 (0) | 16 (0) | 6 (1) | 13 (1) | 24 (2) | 36 (1) |

Ford states gross tariff costs of "about $3 billion" for 2025. Whirlpool and Nucor
present the tariffs partly as an advantage, and the judge marks those passages as an
opportunity.

Three more topics show three shapes over the same reports
([docs/more-topics.md](docs/more-topics.md)). Passages about the company:

| Topic | RWE 2021 | RWE 2022 | RWE 2023 | RWE 2024 | RWE 2025 |
| --- | --- | --- | --- | --- | --- |
| Artificial intelligence | 0 | 0 | 0 | 3 | 16 |
| Covid-19 | 15 | 4 | 0 | 0 | 0 |
| Cybersecurity | 2 | 4 | 3 | 3 | 3 |

All judgements were made by `claude-haiku-5-5`. For protectionism, nine of the 14 changed
paragraphs were written anew and paired by that model; see
[docs/neighbours-and-pairing.md](docs/neighbours-and-pairing.md).

## How it works

1. **Read.** For a PDF, sections come from its bookmarks and paragraphs from a layout
   analysis that keeps columns apart; only body text in narrative sections is kept
   (`ingest.py`, `sections.py`). For a filing with the SEC, paragraphs are the block
   elements of the page and sections are the items of the form (`sec.py`, `filings.py`).
2. **Filter tables.** Paragraphs that are mostly figures are dropped (`tables.py`).
3. **Find.** A topic lists search phrases, matched as whole words in any case,
   hyphenation and inflection, with exclusions such as "feed-in tariff" (`topics.py`,
   `retrieval.py`).
4. **Judge.** Claude answers in a fixed format and returns the sentence it relied on,
   which is checked word for word against the paragraph (`judge.py`, `judgements.py`).
5. **Compare.** Paragraphs of two years are paired by wording (`changes.py`). Those left
   over can be paired by Claude (`pairing.py`).
6. **Report.** Quotes with citations, nothing summarised (`report.py`).

## Limits

- **Accuracy is not measured.** No person has labelled anything. `disclosure-diff eval` measures
  agreement with a frozen set of one model's verdicts: the default judge matches it on
  92% of answers. For RWE, two other models also read the same paragraphs without seeing
  the verdicts and agreed with the earlier judge, `claude-opus-5-5`, on 19 of 20. All of
  that is agreement between models.
- **Pairs made by the model cannot be checked by a program, and they vary.** The report
  marks them and prints both texts. Two models agreed on three of four pairs, and the
  same model gave different pairs for one comparison in two runs.
- **What the search misses is known for four scans.** One report was scanned for each of
  protectionism, artificial intelligence, Covid-19 and cybersecurity, all of them RWE's.
  They showed two misses in about 2,100 paragraphs. Climate change is not scanned.
- **Only protectionism has a reference.** No second model has judged the other four
  topics, so there is no agreement figure for them.
- **A single verdict on a borderline passage is not stable.** The same paragraph has been
  called about the company in one request and off topic in another.
- **The second look at background paragraphs rarely changes anything.** It changed none
  of 6 passages on protectionism and 4 of 50 on climate change.
- **Filings: thirteen companies, Form 10-K only.** All are large companies listed in the
  United States. BP's 20-F does not follow the item structure and is refused. A filing is cited by
  item, which is coarse: one item can hold 200 paragraphs.
- **Every new company's PDF has needed a fix so far.** E.ON's reports have no chapter
  numbers and switch off text extraction. Chevron's have no bookmarks, tight line spacing
  and, for 2025, text that cannot be decoded. More years of a company already read needed
  none. Filings are steadier: of thirteen companies' filings, one needed a fix to the
  reading and one to the counting.
- **Without bookmarks there are no sections**, so the financial statements are searched
  too.
- **OCR** has been run on Chevron's 2025 report, whose pages are clean renderings, and
  not on a real scan. It reads English only as set up.
- **The thresholds** for tables, pairing and paragraph splitting were set by looking at
  these two companies.

## Data folder

```text
<data folder>/
  reports/     annual reports as <COMPANY>/<year>.pdf, filings as <TICKER>/<year>.htm
  extracted/   paragraphs read from the PDFs
  judged/      judgements on the paragraphs found for a topic
  paired/      pairs of paragraphs that were written anew
  scanned/     judgements on paragraphs the search did not find
  eval/        the frozen reference for disclosure-diff eval
  output/      comparison reports
```

The folder is taken from `--data-dir`, then the `DISCLOSURE_DIFF_DATA_DIR` environment
variable, then a `.disclosure-diff-data-dir` file in the current directory that holds the
path. That file is ignored by git. If the folder is on an external drive that is not
plugged in, the tool says so.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The OCR tests need Tesseract and are skipped without it. Commits are kept small, one
logical change each. Decisions that should outlive a commit message go into `docs/`.

## History

The first version scored "vulnerability" from single-word overlap and a movie-review
sentiment model. It was replaced in November 2026; the 13 passages it wrongly marked as
relevant are kept as a test. Commands for labelling passages by hand and scoring against
those labels were built and then removed, because nobody was going to label;
`disclosure-diff eval` replaced them.

The project was first called Document Impact Analyzer, and its command `dia`. Both were
renamed because the tool measures disclosure, not impact.

## License

MIT, see [LICENSE](LICENSE).
