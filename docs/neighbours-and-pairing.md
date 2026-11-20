# Neighbouring paragraphs and written-anew passages

Recorded on 19 November 2026.

Two weaknesses were known: a paragraph was judged without the paragraphs around it, and a
paragraph that was written anew showed up as one dropped and one new. This is what was
built for each, what was tried first, and what it changed on the reports read so far.

## Decisions

- **A passage judged as background gets a second look with the paragraphs before and
  after it.** It becomes a passage about the company only if the model quotes, word for
  word, the neighbouring sentence that states the link. Passages judged as about the
  company or as off topic are not looked at again.
- **`disclosure-diff pair` asks the model which unmatched passages of two reports are the same
  statement written anew.** One request holds all of them. The model only pairs; it
  writes nothing about the difference, and the report prints both texts.
- Both use the default judge, `claude-haiku-5-5` at low effort.

## Neighbouring paragraphs

A neighbour is the paragraph read just before or after a passage, if it is in the same
section and on the same or the adjoining page.

### What was tried first: neighbours on every request

The first version sent the neighbours with every passage. Measured with
`disclosure-diff eval` on the 31 reference passages (verdicts by `claude-opus-5-5`, each
made on the passage alone), two runs each, 62 answers:

| Setup | Company, background or off topic | Risk or opportunity | Concreteness | Says what the company does | Evidence word for word | Input tokens |
| --- | --- | --- | --- | --- | --- | --- |
| Passage alone (18 November) | 57 | 57 | 46 | 62 | 62 | 87,668 |
| Neighbours always, first wording | 56 | 56 | 50 | 56 | 62 | 125,026 |
| Neighbours always, "only if the passage alone is background" | 54 | 53 | 49 | 57 | 59 | 125,956 |
| Neighbours always, "response is judged on the passage alone" | 56 | 56 | 51 | 55 | 59 | 126,576 |
| **Second look for background only** | 57 | 57 | 47 | 61 | 62 | 114,348 |

Numbers are matching answers out of 62. With 62 answers, a difference under about 13
points is within noise, so most of these differences prove nothing on their own. Two
things were consistent across all three wordings, though:

- "Says what the company does about it" matched the reference on 55 to 57 answers,
  against 62 without neighbours. With the neighbours in view the model took that answer
  from them, and telling it not to did not help.
- The first answer did not improve. The same three passages differed from the reference
  as before.

One cause of unverified evidence was found and fixed: the model sometimes copied the
closing mark of a paragraph along with its last sentence. Marks are now dropped before
the quote is checked.

### What the second look changed

Nothing, on these four reports. When the 31 passages were judged again, six came back as
background and were looked at a second time. All six are about stock markets, the
general economy or commodity prices, and none was changed.

The case the second look is for did not occur. The passage that prompted it, the
description of the new US tariffs in RWE's 2025 report, is judged as about the company by
the default model on its own; it was the earlier default, `claude-opus-5-5`, that called
it background. So the second look is a guard that has not yet caught anything, at a cost
of about 30% more input tokens.

## Pairing

Wording matches a paragraph that was edited. For the passages it leaves over, the model
is asked which later passage takes the place of which earlier one.

### Result

With the verdicts of the default judge, before and after pairing:

| | New | Changed | Dropped | Unchanged |
| --- | --- | --- | --- | --- |
| RWE 2024 to 2025, wording only | 5 | 1 | 5 | 1 |
| RWE 2024 to 2025, with pairing | 3 | 3 | 3 | 1 |
| Chevron 2024 to 2025, wording only | 2 | 0 | 2 | 2 |
| Chevron 2024 to 2025, with pairing | 1 | 1 | 1 | 2 |

The three pairs:

| Company | Earlier | Later | Wording similarity |
| --- | --- | --- | --- |
| RWE | 2024, p. 31: "USA: new tariffs", in the business environment chapter | 2025, p. 31: "New tariffs on imports into the United States" | 0.13 |
| RWE | 2024, p. 65: the political framework in the USA, in the risk chapter | 2025, p. 64: regulatory risks after the change of administration | 0.13 |
| Chevron | 2024, p. 30: tariffs announced, "significant uncertainty" about their impact | 2025, p. 30: the tariff impact was "less than one percent" of third-party spend | 0.39 |

The Chevron pair is the kind of change the tool is meant to show: a risk described as
uncertain in one year is given a size in the next.

### Two models

`claude-opus-5-5` was given the same two requests. It found the same three pairs and one
more: the paragraphs about the investing environment in the two letters from RWE's CEO
(2024, p. 7 and 2025, p. 6). `claude-haiku-5-5` left those two unpaired. Both readings
are defensible. The instruction says that leaving a passage unpaired is better than a
forced pair, so the more cautious model stays the default.

## What this does and does not show

- Four pairs from two companies are too few to measure anything. No person has checked
  the pairs; they were read once while writing this note.
- A pair cannot be checked by a program the way a quote can. The report marks every pair
  a model made and gives its wording similarity, so a reader can see which ones to read
  with care.
- The comparison of setups rests on agreement with one model's earlier verdicts, not on
  accuracy.

## Consequences

- The 31 stored judgements were made again with the default judge on 19 November 2026.
  The earlier verdicts by `claude-opus-5-5` are still in the same files as earlier lines,
  and in the frozen reference.
- The reference now also holds the neighbouring paragraphs of each passage. They were
  added to the existing file; its passages, verdicts and date are unchanged.
- A pairing is stored with the list of passages the model saw. `disclosure-diff changes` says when
  passages have been added since, so that `disclosure-diff pair` can be run again.
