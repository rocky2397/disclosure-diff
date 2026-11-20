"""Command line.

``dia run`` does everything below for one company and two years, in one go.
``dia fetch`` downloads a company's annual filing from the SEC by ticker.
``dia extract`` reads the reports in the data folder into passages.
``dia judge`` asks Claude whether each passage found for a topic is about the company.
``dia scan`` has Claude read the passages the phrase search did not find.
``dia pair`` asks Claude which passages of two reports are the same statement written anew.
``dia years`` counts, report by report, what a company says about a topic.
``dia changes`` compares what two reports of a company say about a topic.
``dia eval-freeze`` keeps the current verdicts as a reference.
``dia eval`` judges the reference passages again and counts matching answers.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from disclosure_diff import evalset, sec
from disclosure_diff.changes import Change, compare_years, unmatched
from disclosure_diff.filings import UnreadableFiling, extract_filing
from disclosure_diff.ingest import OcrUnavailable, extract, extraction_allowed
from disclosure_diff.judge import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    ClaudeJudge,
    Judge,
    JudgeError,
)
from disclosure_diff.judgements import (
    Concreteness,
    Judgement,
    Relevance,
    append_judgement,
    judgements_path,
    read_judgements,
)
from disclosure_diff.library import (
    REPORT_SUFFIXES,
    ReportFile,
    extracted_path,
    find_reports,
    record_source,
)
from disclosure_diff.pairing import (
    MAX_PASSAGES,
    Pairing,
    pairing_path,
    read_pairing,
    write_pairing,
)
from disclosure_diff.passages import (
    Neighbours,
    Passage,
    find_neighbours,
    read_jsonl,
    write_jsonl,
)
from disclosure_diff.report import YearRow, render_changes, render_missed, render_years
from disclosure_diff.retrieval import find_candidates
from disclosure_diff.settings import DataDir, DataDirError, resolve_data_dir
from disclosure_diff.tables import looks_like_table
from disclosure_diff.topics import TOPICS, Topic, get_topic

SECOND_LOOK = (
    "A passage that comes back as background is sent once more, with the paragraphs before "
    "and after it."
)


def _stored_name(data: DataDir, name: str) -> str:
    """The name of the folder a company's reports are in, however it was typed.

    A company without a folder gets its name in capitals, as tickers are written.
    """
    if data.reports.is_dir():
        for folder in data.reports.iterdir():
            if folder.is_dir() and folder.name.upper() == name.upper():
                return folder.name
    return name.upper()


def _fetch(data: DataDir, args: argparse.Namespace) -> int:
    company = _stored_name(data, args.name or args.ticker)
    folder = data.reports / company
    wanted = []
    for year in args.years:
        present = [name for s in REPORT_SUFFIXES if (folder / (name := f"{year}{s}")).exists()]
        if present:
            print(f"{company} {year}: {present[0]} is already there, skipped")
        else:
            wanted.append(year)
    if not wanted:
        return 0

    get = args.sec_get or sec.http_get(sec.contact_from())
    cik, name = sec.find_company(args.ticker, get)
    filings = sec.annual_filings(cik, get)
    print(f"{args.ticker.upper()} is {name}.")
    for year in wanted:
        filing = sec.pick(filings, year, args.ticker.upper())
        content = sec.download(filing, get)
        folder.mkdir(parents=True, exist_ok=True)
        report = ReportFile(company, year, folder / f"{year}.htm")
        report.path.write_bytes(content)
        record_source(data, report, filing.url, content)
        print(
            f"{company} {year}: Form {filing.form} for the period ending {filing.period_end}, "
            f"filed {filing.filed}, {len(content) / 1e6:.1f} MB"
        )
    if args.command == "fetch":
        print("Run 'dia extract' to read them.")
    return 0


def _extract(data: DataDir, args: argparse.Namespace) -> int:
    reports = find_reports(data, args.company)
    if args.years:
        reports = [report for report in reports if report.year in args.years]
    if not reports:
        print(f"No reports found in {data.reports}", file=sys.stderr)
        return 1
    data.extracted.mkdir(exist_ok=True)
    for report in reports:
        target = extracted_path(data, report.company, report.year)
        if target.exists() and not args.force:
            print(f"{report.company} {report.year}: already extracted, skipped")
            continue
        if report.is_filing:
            try:
                result = extract_filing(report.path, report.company, report.year)
            except UnreadableFiling as error:
                print(f"{report.company} {report.year}: not read, because {error}")
                continue
            write_jsonl(result.passages, target)
            form = next((p.form for p in result.passages if p.form), None)
            kind = f"Form {form} filing" if form else "filing whose form is not stated"
            sections = len({p.section for p in result.passages if p.section})
            print(
                f"{report.company} {report.year}: {len(result.passages)} passages from a "
                f"{kind}, in {sections} items"
            )
            continue
        if not extraction_allowed(report.path) and not args.allow_restricted:
            print(
                f"{report.company} {report.year}: not read. The publisher has switched off "
                "text extraction in this PDF. Pass --allow-restricted if you decide to read "
                "it anyway."
            )
            continue
        result = extract(report.path, report.company, report.year, ocr=args.ocr)
        write_jsonl(result.passages, target)
        line = f"{report.company} {report.year}: {len(result.passages)} passages"
        if result.ocr_pages:
            by_ocr = sum(1 for passage in result.passages if passage.ocr)
            line += f", {by_ocr} of them read by OCR ({len(result.ocr_pages)} pages checked)"
        print(line)
        unreadable = len(result.textless_pages) + len(result.undecodable_pages)
        if not args.ocr and (unreadable or result.image_pages):
            print(
                f"  {unreadable} pages have no readable text and "
                f"{len(result.image_pages)} have text plus pictures. Pass --ocr to also read "
                "text that exists only as pictures."
            )
        if not args.ocr and result.undecodable_pages:
            print(
                f"  On {len(result.undecodable_pages)} of those pages the PDF has text that "
                "cannot be decoded, so nothing on them was read."
            )
    return 0


def _passages(data: DataDir, company: str, year: int) -> list[Passage]:
    path = extracted_path(data, company, year)
    if not path.is_file():
        raise ValueError(f"No extracted passages for {company} {year}. Run 'dia extract' first.")
    return list(read_jsonl(path))


def _on_topic(data: DataDir, company: str, year: int, topic: Topic) -> list[Passage]:
    passages = _passages(data, company, year)
    return [candidate.passage for candidate in find_candidates(passages, topic)]


def _judge(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    passages = _passages(data, args.company, args.year)
    candidates = [candidate.passage for candidate in find_candidates(passages, topic)]
    neighbours: dict[str, Neighbours] = {} if args.no_context else find_neighbours(passages)
    path = judgements_path(data, args.company, args.year, topic.key)
    done = read_judgements(path)
    unjudged = [passage for passage in candidates if args.again or passage.id not in done]
    pending = unjudged if args.limit is None else unjudged[: args.limit]
    print(
        f"{args.company} {args.year}, {topic.name}: {len(candidates)} passages found, "
        f"{sum(1 for passage in candidates if passage.id in done)} already judged, "
        f"{len(pending)} to send to {args.model}."
    )
    if pending and not args.no_context:
        print(SECOND_LOOK)
    if args.dry_run or not pending:
        return 0

    judge: Judge = args.judge_factory(model=args.model, effort=args.effort)
    try:
        for passage in pending:
            judgement = judge.judge(passage, topic, neighbours.get(passage.id))
            append_judgement(path, judgement)
            labels = [judgement.relevance.value]
            if judgement.relevance.value == "company":
                labels += [judgement.direction.value, judgement.concreteness.value]
            unverified = "" if judgement.evidence_verified else "  (evidence not found in passage)"
            print(f"  {passage.where}: {', '.join(labels)}{unverified}")
    finally:
        tokens_in = getattr(judge, "input_tokens", 0)
        if tokens_in:
            print(f"Tokens used: {tokens_in} in, {judge.output_tokens} out.")
    print(f"Written to {path}")
    return 0


def scan_path(data: DataDir, company: str, year: int, topic_key: str) -> Path:
    return data.scanned / f"{company}_{year}_{topic_key}.jsonl"


def _scan(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    passages = _passages(data, args.company, args.year)
    found = {candidate.passage.id for candidate in find_candidates(passages, topic)}
    rest = [p for p in passages if p.id not in found and not looks_like_table(p.text)]
    # A paragraph that the report repeats word for word is read once.
    rest = list({passage.id: passage for passage in reversed(rest)}.values())[::-1]
    path = scan_path(data, args.company, args.year, topic.key)
    done = read_judgements(path)
    unread = [passage for passage in rest if passage.id not in done]
    pending = unread if args.limit is None else unread[: args.limit]
    print(
        f"{args.company} {args.year}, {topic.name}: the search found {len(found)} of "
        f"{len(found) + len(rest)} passages. Of the other {len(rest)}, "
        f"{len(rest) - len(unread)} are read already and {len(pending)} go to {args.model}, "
        "one request each."
    )
    if args.dry_run:
        return 0

    if pending:
        judge: Judge = args.judge_factory(model=args.model, effort=args.effort)
        try:
            for number, passage in enumerate(pending, start=1):
                judgement = judge.scan(passage, topic)
                append_judgement(path, judgement)
                done[passage.id] = judgement
                if judgement.relevance is not Relevance.OFF_TOPIC:
                    print(f"  {passage.where}: {judgement.relevance.value}")
                if number % 100 == 0:
                    print(f"  {number} of {len(pending)} read")
        finally:
            tokens_in = getattr(judge, "input_tokens", 0)
            if tokens_in:
                print(f"Tokens used: {tokens_in} in, {judge.output_tokens} out.")

    read = [(passage, done[passage.id]) for passage in rest if passage.id in done]
    missed = [item for item in read if item[1].relevance is Relevance.COMPANY]
    background = [item for item in read if item[1].relevance is Relevance.CONTEXT]
    stored = read_judgements(judgements_path(data, args.company, args.year, topic.key))
    judged = [stored[passage_id] for passage_id in found if passage_id in stored]
    found_company = (
        sum(1 for j in judged if j.relevance is Relevance.COMPANY)
        if len(judged) == len(found)
        else None
    )
    text = render_missed(
        args.company,
        topic,
        args.year,
        scanned=len(read),
        found=len(found),
        found_company=found_company,
        missed=missed,
        background=background,
        model=", ".join(sorted({j.model for _, j in read})) or args.model,
    )
    data.output.mkdir(exist_ok=True)
    target = data.output / f"{args.company}_{args.year}_{topic.key}_missed.md"
    target.write_text(text, encoding="utf-8")
    print(text.splitlines()[2])
    if len(read) < len(rest):
        print(f"{len(rest) - len(read)} passages are still unread. Run the command again.")
    print(f"Written to {target}")
    return 0


def _select(
    data: DataDir, args: argparse.Namespace, topic: Topic
) -> tuple[list[Passage], list[Passage], dict[str, Judgement], list[str]]:
    """The passages of both years to compare, the judgements on them, and notes for the report.

    If both years are judged, only passages about the company are kept. If neither is,
    every passage found is kept. One judged year and one unjudged year would compare a
    filtered list with an unfiltered one, so that is refused.
    """
    years = (args.year_before, args.year_after)
    found = {year: _on_topic(data, args.company, year, topic) for year in years}
    paths = {year: judgements_path(data, args.company, year, topic.key) for year in years}
    with_judgements = [year for year in years if paths[year].is_file()]
    # A report in which nothing was found has nothing to judge, so it counts as judged.
    judged_years = [year for year in years if paths[year].is_file() or not found[year]]

    if args.all_passages or not with_judgements:
        note = (
            "Not judged: this includes passages that mention the topic only in passing. "
            "Run 'dia judge' for both years to keep only passages about the company."
        )
        return found[years[0]], found[years[1]], {}, [note]
    if len(judged_years) == 1:
        missing = next(year for year in years if year not in judged_years)
        raise ValueError(
            f"{args.company} {judged_years[0]} is judged but {missing} is not. "
            f"Run 'dia judge {args.company} {missing}' or pass --all-passages."
        )

    keep = {Relevance.COMPANY} | ({Relevance.CONTEXT} if args.include_context else set())
    judgements: dict[str, Judgement] = {}
    kept: dict[int, list[Passage]] = {}
    left_out = {Relevance.CONTEXT: 0, Relevance.OFF_TOPIC: 0}
    unjudged = 0
    for year in years:
        stored = read_judgements(paths[year])
        kept[year] = []
        for passage in found[year]:
            judgement = stored.get(passage.id)
            if judgement is None:
                unjudged += 1
                kept[year].append(passage)
            elif judgement.relevance in keep:
                judgements[passage.id] = judgement
                kept[year].append(passage)
            else:
                left_out[judgement.relevance] += 1

    models = ", ".join(sorted({judgement.model for judgement in judgements.values()})) or "Claude"
    note = f"Judged by {models}. Left out: {left_out[Relevance.OFF_TOPIC]} off-topic passages"
    if not args.include_context:
        note += f" and {left_out[Relevance.CONTEXT]} that mention the topic only as background"
    notes = [note + "."]
    if unjudged:
        notes.append(f"{unjudged} passages are not judged yet and are included.")
    return kept[years[0]], kept[years[1]], judgements, notes


def _pair(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    before, after, _, _ = _select(data, args, topic)
    dropped, new = unmatched(compare_years(before, after))
    years = f"{args.year_before} to {args.year_after}"
    print(
        f"{args.company} {years}, {topic.name}: wording leaves {len(dropped)} passages of "
        f"{args.year_before} and {len(new)} of {args.year_after} without a counterpart."
    )
    if not dropped or not new:
        print("Nothing to pair.")
        return 0
    if len(dropped) + len(new) > MAX_PASSAGES:
        raise ValueError(
            f"That is more than the {MAX_PASSAGES} passages one pairing request can hold."
        )
    print(f"All of them go to {args.model} in one request.")
    if args.dry_run:
        return 0

    judge: Judge = args.judge_factory(model=args.model, effort=args.effort)
    pairs = judge.pair(dropped, new, topic)
    by_id = {passage.id: passage for passage in dropped + new}
    for pair in pairs:
        earlier, later = by_id[pair.before_id], by_id[pair.after_id]
        print(f"  {earlier.year} {earlier.where} -> {later.year} {later.where}")
    print(f"{len(pairs)} pairs found.")
    tokens_in = getattr(judge, "input_tokens", 0)
    if tokens_in:
        print(f"Tokens used: {tokens_in} in, {judge.output_tokens} out.")
    target = pairing_path(data, args.company, args.year_before, args.year_after, topic.key)
    write_pairing(target, Pairing(pairs, frozenset(by_id)))
    print(f"Written to {target}")
    return 0


def _changes(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    before, after, judgements, notes = _select(data, args, topic)
    pairing = read_pairing(
        pairing_path(data, args.company, args.year_before, args.year_after, topic.key)
    )
    changes = compare_years(before, after, pairs=pairing.pairs if pairing else ())
    notes = [*notes, *_pairing_notes(changes, pairing, args)]
    text = render_changes(
        args.company,
        topic,
        args.year_before,
        args.year_after,
        changes,
        judgements=judgements,
        notes=notes,
        include_unchanged=args.include_unchanged,
    )
    data.output.mkdir(exist_ok=True)
    name = f"{args.company}_{topic.key}_{args.year_before}_{args.year_after}.md"
    target = data.output / name
    target.write_text(text, encoding="utf-8")
    print(text.splitlines()[2])
    for note in notes:
        print(note)
    print(f"Written to {target}")
    return 0


def _pairing_notes(
    changes: Sequence[Change], pairing: Pairing | None, args: argparse.Namespace
) -> list[str]:
    """What the reader should know about passages that were written anew."""
    dropped, new = unmatched(changes)
    command = f"'dia pair {args.company} {args.year_before} {args.year_after}'"
    if pairing is None:
        if not dropped or not new:
            return []
        return [
            "Passages are matched by wording only, so one that was written anew appears as "
            f"one dropped and one new passage. Run {command} to match those."
        ]
    notes = []
    models = sorted({change.paired_by for change in changes if change.paired_by})
    if models:
        count = sum(1 for change in changes if change.paired_by)
        notes.append(
            f"Written anew and paired by {', '.join(models)}: {count} of the changed "
            "passages. The others were matched by wording."
        )
    unseen = [p for p in dropped + new if p.id not in pairing.considered]
    if unseen and dropped and new:
        notes.append(
            f"Dropped or new passages the model has not seen for pairing: {len(unseen)}. "
            f"Run {command} again to include them."
        )
    return notes


def _years(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    years = {report.year for report in find_reports(data, args.company)}
    rows = []
    for year in sorted(years):
        if not extracted_path(data, args.company, year).is_file():
            rows.append(YearRow(year))
            continue
        passages = _passages(data, args.company, year)
        found = [candidate.passage for candidate in find_candidates(passages, topic)]
        stored = read_judgements(judgements_path(data, args.company, year, topic.key))
        verdicts = [stored[passage.id] for passage in found if passage.id in stored]
        if len(verdicts) < len(found):
            rows.append(YearRow(year, len(passages), len(found)))
            continue
        about = [v for v in verdicts if v.relevance is Relevance.COMPANY]
        rows.append(
            YearRow(
                year,
                len(passages),
                len(found),
                judged=True,
                company=len(about),
                quantified=sum(1 for v in about if v.concreteness is Concreteness.QUANTIFIED),
                response=sum(1 for v in about if v.states_response),
                background=sum(1 for v in verdicts if v.relevance is Relevance.CONTEXT),
                off_topic=sum(1 for v in verdicts if v.relevance is Relevance.OFF_TOPIC),
            )
        )
    if not rows:
        raise ValueError(f"No reports for {args.company} in {data.reports}")
    text = render_years(args.company, topic, rows)
    data.output.mkdir(exist_ok=True)
    target = data.output / f"{args.company}_{topic.key}_years.md"
    target.write_text(text, encoding="utf-8")
    print(text.split("\n", 2)[2].rstrip())
    print(f"Written to {target}")
    return 0


def _step(args: argparse.Namespace, **values: object) -> argparse.Namespace:
    """The arguments for one step of ``dia run``: those given, plus what the step needs."""
    return argparse.Namespace(**{**vars(args), **values})


def _run(data: DataDir, args: argparse.Namespace) -> int:
    """Fetch what is missing, read, judge both years, pair and compare.

    Every step keeps what it has done, so running the command again sends nothing twice.
    """
    topic = get_topic(args.topic)
    years = [args.year_before, args.year_after]
    company = _stored_name(data, args.company)
    folder = data.reports / company
    missing = [y for y in years if not any((folder / f"{y}{s}").exists() for s in REPORT_SUFFIXES)]
    if missing:
        try:
            _fetch(data, _step(args, ticker=args.company, name=None, years=missing))
        except sec.SecError as error:
            raise sec.SecError(
                f"{error} For a company that does not file with the SEC, put its reports in "
                f"the data folder as reports/{company}/<year>.pdf."
            ) from error

    reading = _step(args, company=company, years=years, force=False, ocr=False)
    _extract(data, _step(reading, allow_restricted=False))
    unread = [str(year) for year in years if not extracted_path(data, company, year).is_file()]
    if unread:
        raise ValueError(
            f"{company} {' and '.join(unread)} could not be read, for the reason given above, "
            "so there is nothing to compare."
        )

    for year in years:
        _judge(data, _step(args, company=company, year=year, limit=None, again=False))
    if args.dry_run:
        print("Nothing was sent. Without --dry-run, those passages are judged and compared.")
        return 0

    comparing = _step(
        args, company=company, include_context=False, all_passages=False, include_unchanged=False
    )
    before, after, _, _ = _select(data, comparing, topic)
    dropped, new = unmatched(compare_years(before, after))
    stored = read_pairing(pairing_path(data, company, years[0], years[1], topic.key))
    leftover = dropped + new
    if dropped and new and stored and all(p.id in stored.considered for p in leftover):
        print("The passages that wording could not match are paired already.")
    elif dropped and new and len(leftover) > MAX_PASSAGES:
        print(
            f"Not paired: wording leaves {len(leftover)} passages without a counterpart, more "
            f"than the {MAX_PASSAGES} one request can hold. They appear as dropped and new."
        )
    else:
        _pair(data, comparing)
    return _changes(data, comparing)


def reference_path(data: DataDir, topic_key: str) -> Path:
    return data.root / "eval" / f"reference_{topic_key}.jsonl"


def _eval_freeze(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    target = reference_path(data, topic.key)
    if target.exists() and not args.force:
        raise ValueError(
            f"{target} already exists. A reference is meant to stay fixed; pass --force to "
            "replace it with the current verdicts."
        )
    suffix = f"_{topic.key}.jsonl"
    cases = []
    files = sorted(data.judged.glob(f"*{suffix}")) if data.judged.is_dir() else []
    for path in files:
        if path.name.startswith("._"):
            continue
        company, year = path.name[: -len(suffix)].rsplit("_", 1)
        judgements = read_judgements(path)
        passages = _passages(data, company, int(year))
        neighbours = find_neighbours(passages)
        for candidate in find_candidates(passages, topic):
            passage = candidate.passage
            if passage.id in judgements:
                cases.append(
                    evalset.make_case(passage, judgements[passage.id], neighbours[passage.id])
                )
    if not cases:
        raise ValueError(f"No judged passages for {topic.name.lower()}. Run 'dia judge' first.")
    evalset.write_reference(cases, target, frozen_on=date.today().isoformat())
    models = ", ".join(sorted({case.reference_model for case in cases}))
    print(f"{len(cases)} passages frozen as the reference, with verdicts by {models}.")
    print(f"Written to {target}")
    return 0


def _eval(data: DataDir, args: argparse.Namespace) -> int:
    topic = get_topic(args.topic)
    source = reference_path(data, topic.key)
    if not source.is_file():
        raise ValueError(f"No reference at {source}. Run 'dia eval-freeze' first.")
    cases, frozen_on = evalset.read_reference(source)
    made_by = ", ".join(sorted({case.reference_model for case in cases}))
    requests = len(cases) * args.runs
    context = not args.no_context
    print(
        f"Reference: {len(cases)} passages, frozen on {frozen_on} with verdicts by {made_by}. "
        f"{len(cases)} passages x {args.runs} runs = {requests} requests to {args.model}."
    )
    if context and any(case.neighbours for case in cases):
        print(SECOND_LOOK)
    elif context:
        print("The reference holds no neighbouring paragraphs, so no passage gets a second look.")
    if args.dry_run:
        return 0

    judge: Judge = args.judge_factory(model=args.model, effort=args.effort)
    attempts, failures = evalset.run(
        cases, judge, topic, runs=args.runs, model=args.model, context=context
    )
    name = f"{topic.key}_{args.model}_{args.effort}{'' if context else '_no-context'}.jsonl"
    target = data.output / "eval" / name
    evalset.write_results(target, cases, attempts, failures)
    result = evalset.summarise(cases, attempts, failures, args.runs)

    print(
        f"Judged by {args.model} at {args.effort} effort: {result.attempts} answers, "
        f"{result.failures} failed attempts (not scored)."
    )
    if not attempts:
        return 1
    print("Answers that match the reference:")
    for answer, wording in evalset.ANSWERS.items():
        print(
            f"  {wording}: {result.matching[answer]} of {result.attempts} "
            f"({result.share[answer]:.0%})"
        )
    print(
        f'For comparison, answering "{result.majority_answer}" every time would match the first '
        f"line on {result.majority_share:.0%}."
    )
    if result.repeated:
        print(
            f"Same first answer in all {args.runs} runs: {result.stable} of {result.repeated} "
            "passages."
        )
    print(f"Evidence quoted word for word: {result.evidence_verified} of {result.attempts}.")
    print(f"Tokens: {result.input_tokens} in, {result.output_tokens} out.")
    print(
        f"With {result.attempts} answers, a difference under about {result.noise_points:.0f} "
        "percentage points is within noise."
    )
    print(
        f"The reference is the verdicts of {made_by}, so this is agreement with that model, "
        "not accuracy."
    )
    if result.differing:
        print("Passages whose first answer differs from the reference:")
        for case, given in result.differing:
            print(
                f"  {case.label}: reference {case.reference['relevance']}, got {', '.join(given)}"
            )
    print(f"Every answer is in {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dia", description="What annual reports disclose about a topic, and how it changes."
    )
    parser.add_argument("--data-dir", help="data folder (default: DIA_DATA_DIR or .dia-data-dir)")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="everything for one company and two years: download from the SEC if needed, "
        "read, judge, pair and compare (uses the API)",
    )
    run.add_argument(
        "company",
        help="ticker symbol at the SEC, for example CAT, or the name of a company whose "
        "reports are in the data folder",
    )
    run.add_argument("year_before", type=int)
    run.add_argument("year_after", type=int)
    run.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--effort", default=DEFAULT_EFFORT)
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="download and read, then show what would be sent to Claude and send nothing",
    )
    run.set_defaults(run=_run, no_context=False)

    fetch = commands.add_parser(
        "fetch", help="download a company's annual filing (10-K, 20-F) from the SEC by ticker"
    )
    fetch.add_argument("ticker", help="ticker symbol, for example CVX")
    fetch.add_argument("years", type=int, nargs="+", help="fiscal years, for example 2024 2025")
    fetch.add_argument("--name", help="company name to store the filings under (default: ticker)")
    fetch.set_defaults(run=_fetch)

    extract = commands.add_parser("extract", help="read reports into passages")
    extract.add_argument("--company", help="only this company's reports")
    extract.add_argument("--force", action="store_true", help="extract again, replacing results")
    extract.add_argument(
        "--ocr",
        action="store_true",
        help="read text that exists only as pictures: scanned pages and pictures on pages",
    )
    extract.add_argument(
        "--allow-restricted",
        action="store_true",
        help="also read PDFs whose publisher has switched off text extraction",
    )
    extract.set_defaults(run=_extract, years=None)

    judge = commands.add_parser(
        "judge", help="ask Claude whether each passage found is about the company (uses the API)"
    )
    judge.add_argument("company")
    judge.add_argument("year", type=int)
    judge.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    judge.add_argument("--model", default=DEFAULT_MODEL)
    judge.add_argument("--effort", default=DEFAULT_EFFORT)
    judge.add_argument("--limit", type=int, help="judge at most this many passages")
    judge.add_argument(
        "--again",
        action="store_true",
        help="also judge passages that are judged already; the new verdict replaces the old",
    )
    judge.add_argument(
        "--no-context",
        action="store_true",
        help="no second look, with its neighbouring paragraphs, at a passage judged as background",
    )
    judge.add_argument(
        "--dry-run", action="store_true", help="show what would be sent, send nothing"
    )
    judge.set_defaults(run=_judge)

    freeze = commands.add_parser(
        "eval-freeze", help="keep the current verdicts as the reference for 'dia eval'"
    )
    freeze.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    freeze.add_argument("--force", action="store_true", help="replace an existing reference")
    freeze.set_defaults(run=_eval_freeze)

    evaluate = commands.add_parser(
        "eval", help="judge the reference passages again and count matching answers (uses the API)"
    )
    evaluate.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    evaluate.add_argument("--model", default=DEFAULT_MODEL)
    evaluate.add_argument("--effort", default=DEFAULT_EFFORT)
    evaluate.add_argument("--runs", type=int, default=2, help="times each passage is judged")
    evaluate.add_argument(
        "--no-context",
        action="store_true",
        help="no second look, with its neighbouring paragraphs, at a passage judged as background",
    )
    evaluate.add_argument("--dry-run", action="store_true", help="send nothing, only count")
    evaluate.set_defaults(run=_eval)

    scan = commands.add_parser(
        "scan",
        help="have Claude read the passages the search did not find, to see what it misses "
        "(uses the API, one request per passage of the report)",
    )
    scan.add_argument("company")
    scan.add_argument("year", type=int)
    scan.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    scan.add_argument("--model", default=DEFAULT_MODEL)
    scan.add_argument("--effort", default=DEFAULT_EFFORT)
    scan.add_argument("--limit", type=int, help="read at most this many passages")
    scan.add_argument("--dry-run", action="store_true", help="send nothing, only count")
    scan.set_defaults(run=_scan)

    pair = commands.add_parser(
        "pair",
        help="ask Claude which passages of two reports are one statement written anew "
        "(uses the API)",
    )
    pair.add_argument("company")
    pair.add_argument("year_before", type=int)
    pair.add_argument("year_after", type=int)
    pair.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    pair.add_argument("--model", default=DEFAULT_MODEL)
    pair.add_argument("--effort", default=DEFAULT_EFFORT)
    pair.add_argument("--include-context", action="store_true", help="as in 'dia changes'")
    pair.add_argument("--all-passages", action="store_true", help="as in 'dia changes'")
    pair.add_argument(
        "--dry-run", action="store_true", help="show what would be sent, send nothing"
    )
    pair.set_defaults(run=_pair)

    years = commands.add_parser(
        "years", help="count, report by report, what a company says about a topic"
    )
    years.add_argument("company")
    years.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    years.set_defaults(run=_years)

    changes = commands.add_parser("changes", help="compare two reports of a company on a topic")
    changes.add_argument("company")
    changes.add_argument("year_before", type=int)
    changes.add_argument("year_after", type=int)
    changes.add_argument("--topic", default="protectionism", choices=sorted(TOPICS))
    changes.add_argument("--include-unchanged", action="store_true")
    changes.add_argument(
        "--include-context",
        action="store_true",
        help="also keep passages that mention the topic only as background",
    )
    changes.add_argument(
        "--all-passages", action="store_true", help="ignore judgements and compare everything found"
    )
    changes.set_defaults(run=_changes)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    judge_factory: Callable[..., Judge] = ClaudeJudge,
    sec_get: sec.Get | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    args.judge_factory = judge_factory
    args.sec_get = sec_get
    try:
        data = resolve_data_dir(args.data_dir)
        return args.run(data, args)
    except (DataDirError, JudgeError, OcrUnavailable, sec.SecError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        # Typically the external drive with the data folder went away during a long run.
        print(
            f"Error: a file could not be read or written ({error}). If the data folder is "
            "on an external drive, check that it is still plugged in, then run the command "
            "again: what was finished is kept.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
