# Evaluation

Recorded on 18 November 2026.

## What the eval is

Nobody labels passages by hand in this project, so there is no ground truth to measure
against. The eval works with a **reference** instead: the verdicts stored at one point in
time, frozen together with the text of their passages.

```bash
dia eval-freeze
```

```bash
dia eval
```

`eval-freeze` writes `eval/reference_<topic>.jsonl` into the data folder and refuses to
replace it without `--force`. `eval` judges every reference passage again, twice by
default, and reports:

- how many answers match the reference, for each of the four answers a verdict has
- what share a constant answer would reach, as a baseline
- on how many passages the judge gave the same answer in every run
- whether the evidence is quoted word for word from the passage
- tokens used
- the passages whose first answer differs from the reference

Every answer is written to `output/eval/<topic>_<model>_<effort>.jsonl`.

## What it is for

- **Did a change alter anything?** After editing the judge's prompt or the request,
  run it again and see which verdicts moved.
- **Is a cheaper or different setup equivalent?** `--model` and `--effort` choose what is
  judged against the reference.
- **How stable is the judge?** `--runs` sets how often each passage is judged.

## What it is not

- **Not accuracy.** The reference is one model's verdicts. A score against it rewards
  answering like that model, and a model that is right where the reference is wrong
  loses points.
- **Not a test of the search.** It runs only on passages the phrase search found, so it
  cannot notice passages the search misses.
- **Not precise.** With 31 passages and two runs, a difference under about 13 percentage
  points is within noise.

A request that fails, or that another model answered, is listed as a failed attempt and
is not scored. A run stops if its first attempt fails or if more than ten do.

## The reference

Frozen on 18 November 2026: 31 passages found for protectionism in RWE's and Chevron's
2024 and 2025 reports, with the verdicts `claude-opus-5-5` gave them at low effort.
20 are about the company, 8 are background, 3 are off topic.

## First run

`claude-haiku-5-5` at low effort, two runs, 62 requests, none failed.

| Answer | Matches the reference |
| --- | --- |
| About the company, background or off topic | 57 of 62 (92%) |
| Risk, opportunity, both or neither | 57 of 62 (92%) |
| Generic, specific or quantified | 46 of 62 (74%) |
| Says what the company does about it | 62 of 62 (100%) |

- Answering "company" every time would match the first answer on 65%.
- The judge gave the same first answer in both runs on 30 of 31 passages.
- The evidence was quoted word for word in all 62 answers.
- The run used 87,668 input and 5,432 output tokens, about one cent at list prices.

Three passages differ from the reference on the first answer, all from the "Business
environment" chapter of RWE's reports:

| Passage | Reference | Run 1 | Run 2 |
| --- | --- | --- | --- |
| RWE 2024, p. 31: the election year in two core markets | company | background | company |
| RWE 2024, p. 31: description of the new US tariffs | background | company | company |
| RWE 2025, p. 31: description of the new US tariffs | background | company | company |

The first is also the one passage the judge answered differently in its two runs. These
are the same three passages on which the two models differed in
[judge-model-comparison.md](judge-model-comparison.md).

## Later runs

On 19 November 2026 the eval was used to choose how the judge is shown the paragraphs
around a passage. Four setups were run against this reference; the figures and the
decision are in [neighbours-and-pairing.md](neighbours-and-pairing.md). Since then the
reference also holds each passage's neighbouring paragraphs, and `dia eval --no-context`
judges every passage alone, as in the first run.
