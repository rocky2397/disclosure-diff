# Choosing the judge model

Recorded on 18 November 2026.

## Decision

The judging step uses `claude-haiku-5-5` by default, at low effort. Until this date the
default was `claude-opus-5-5`. Any other model can be chosen per run with
`dia judge --model`.

## Why

Judging is one request per passage, so its cost grows with every company and year added.
The question was whether a much cheaper model gives the same verdicts.

## What was compared

All 31 passages the phrase search had found for protectionism so far were judged by both
models with the same prompt, the same answer format and low effort:

- RWE 2024 (8 passages) and 2025 (12)
- Chevron 2024 (4) and 2025 (7)

| | `claude-opus-5-5` | `claude-haiku-5-5` |
| --- | --- | --- |
| Input tokens | 43,834 | 43,834 |
| Output tokens | 2,756 | 2,652 |
| Cost at list prices | about $0.23 | about $0.006 |
| Evidence quote found word for word in the passage | 31 of 31 | 31 of 31 |

How often the cheaper model gave the same answer as the other one:

| Answer | Same on |
| --- | --- |
| About the company, background or off topic | 28 of 31 |
| Risk, opportunity, both or neither | 28 of 31 |
| Generic, specific or quantified | 25 of 31 |
| Says what the company does about it | 31 of 31 |

List prices used: $4 and $20 per million input and output tokens for `claude-opus-5-5`,
$0.10 and $0.50 for `claude-haiku-5-5`.

## Where they differ

All three differences on the first answer are paragraphs from the "Business environment"
chapter of RWE's reports. The last column is what two further models said when they
labelled the RWE passages without seeing any verdict (a GPT model through Codex on all
of them, a second Claude model on a sample).

| Passage | `claude-opus-5-5` | `claude-haiku-5-5` | Other readers |
| --- | --- | --- | --- |
| RWE 2024, p. 31: the election year in two core markets | company | background | both: background |
| RWE 2024, p. 31: description of the new US tariffs | background | company | GPT: background |
| RWE 2025, p. 31: description of the new US tariffs | background | company | both: background |

In the first case the cheaper model agrees with the other readers and the previous
default does not. In the other two it stands alone. Those two are factual descriptions
of the tariffs whose link to the company is stated in the paragraph that follows, which
is the known weakness of judging paragraphs one at a time.

All eleven Chevron verdicts are the same, including the three passages that use
"sanctioning" for approving a project, which both models marked off topic.

Of the six differences in concreteness, three are the passages above. In the other three
the cheaper model says "generic" where the other says "specific", each time for a short
paragraph that names no country, measure or amount.

## What this does and does not show

- The two models differ only on passages that every reader so far has found hard.
- 31 passages are too few to say which model is better. No person has labelled any of
  them, so there is no ground truth to measure either model against.
- It was one topic and two companies.

## Consequences

- Judgements stored before this date were made by `claude-opus-5-5` and are kept. Each
  stored judgement records the model that made it, and the comparison report names the
  models it draws on.
- Requests to Haiku models do not carry the refusal-fallback parameter, because those
  models have no server-side fallback.

## Repeating the comparison

There is no command for it. It was done with a short script that reads the stored
passages and judgements, calls `ClaudeJudge(model=...)` for each passage, and counts the
matching answers. The raw answers of that run are kept in the data folder as
`output/judge_comparison_haiku_vs_opus.json`.
