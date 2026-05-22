from __future__ import annotations

from collections import defaultdict

from .schemas import (
    EvalReport,
    ExtractionEvalResult,
    FieldMetrics,
    TaskSpec,
    TestCase,
    TranscriptEvalResult,
)


def generate_report(
    task_spec: TaskSpec,
    model: str,
    test_cases: list[TestCase],
    extraction_results: list[ExtractionEvalResult],
    transcript_results: list[TranscriptEvalResult],
    comparison_model: str | None = None,
    comparison_extraction_results: list[ExtractionEvalResult] | None = None,
) -> EvalReport:
    field_metrics = _compute_field_metrics(task_spec, test_cases, extraction_results)
    failure_patterns = _analyze_failures(test_cases, extraction_results)
    transcript_agg = _aggregate_transcript_quality(transcript_results)
    correlation = _compute_correlation(transcript_results, extraction_results)

    comparison_metrics = None
    if comparison_model and comparison_extraction_results:
        comparison_metrics = _compute_field_metrics(task_spec, test_cases, comparison_extraction_results)

    overall_f1 = (
        sum(m.f1 for m in field_metrics.values()) / len(field_metrics)
        if field_metrics else 0.0
    )

    return EvalReport(
        task_name=task_spec.name,
        model=model,
        comparison_model=comparison_model,
        n_transcripts=len(test_cases),
        transcript_quality=transcript_agg,
        field_metrics=field_metrics,
        overall_extraction_f1=round(overall_f1, 3),
        failure_patterns=failure_patterns,
        transcript_extraction_correlation=correlation,
        comparison_field_metrics=comparison_metrics,
    )


def _compute_field_metrics(
    task_spec: TaskSpec,
    test_cases: list[TestCase],
    results: list[ExtractionEvalResult],
) -> dict[str, FieldMetrics]:
    results_by_id = {r.test_case_id: r for r in results}
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    for case in test_cases:
        result = results_by_id.get(case.id)
        if not result or not case.expected_extraction:
            continue
        for field in task_spec.fields:
            expected = case.expected_extraction.get(field.name)
            correct = result.field_scores.get(field.name, False)
            if expected is not None and correct:
                tp[field.name] += 1
            elif expected is not None and not correct:
                fn[field.name] += 1
            elif expected is None and not correct:
                fp[field.name] += 1

    metrics = {}
    for field in task_spec.fields:
        t, f_p, f_n = tp[field.name], fp[field.name], fn[field.name]
        precision = t / (t + f_p) if (t + f_p) > 0 else 0.0
        recall = t / (t + f_n) if (t + f_n) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[field.name] = FieldMetrics(
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1=round(f1, 3),
            n_cases=t + f_p + f_n,
        )
    return metrics


def _analyze_failures(
    test_cases: list[TestCase],
    results: list[ExtractionEvalResult],
) -> list[str]:
    results_by_id = {r.test_case_id: r for r in results}
    counts: dict[str, int] = defaultdict(int)
    for case in test_cases:
        result = results_by_id.get(case.id)
        if result:
            for cat in result.failure_categories:
                counts[cat] += 1

    total = len(test_cases)
    return [
        f"{cat}: {n}/{total} cases ({100 * n // total}%)"
        for cat, n in sorted(counts.items(), key=lambda x: -x[1])
        if n > 0
    ]


def _aggregate_transcript_quality(
    results: list[TranscriptEvalResult],
) -> TranscriptEvalResult | None:
    if not results:
        return None
    n = len(results)
    wer_vals = [r.wer for r in results if r.wer is not None]
    spk_vals = [r.speaker_accuracy for r in results if r.speaker_accuracy is not None]
    return TranscriptEvalResult(
        audio_file="aggregate",
        wer=round(sum(wer_vals) / len(wer_vals), 4) if wer_vals else None,
        speaker_accuracy=round(sum(spk_vals) / len(spk_vals), 4) if spk_vals else None,
        coherence_score=round(sum(r.coherence_score for r in results) / n, 4),
        completeness_score=round(sum(r.completeness_score for r in results) / n, 4),
        hallucination_flags=[f for r in results for f in r.hallucination_flags],
        overall_quality=round(sum(r.overall_quality for r in results) / n, 4),
    )


def _compute_correlation(
    transcript_results: list[TranscriptEvalResult],
    extraction_results: list[ExtractionEvalResult],
) -> float | None:
    # Lists are positionally aligned (same order as test_cases)
    paired = [
        (t.overall_quality, e.overall_score)
        for t, e in zip(transcript_results, extraction_results)
    ]
    if len(paired) < 3:
        return None

    xs = [p[0] for p in paired]
    ys = [p[1] for p in paired]
    n = len(paired)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in paired) / n
    std_x = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    std_y = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    if std_x == 0 or std_y == 0:
        return None
    return round(cov / (std_x * std_y), 3)


def render_markdown_report(report: EvalReport) -> str:
    lines = [
        f"# Eval Report — {report.task_name}",
        f"**Model:** `{report.model}`  |  **Transcripts evaluated:** {report.n_transcripts}",
        "",
    ]

    if report.transcript_quality:
        tq = report.transcript_quality
        lines += [
            "## Layer 1: Transcript Quality",
            "",
            "| Metric | Score |",
            "|--------|-------|",
            f"| WER | {f'{tq.wer:.1%}' if tq.wer is not None else 'N/A'} |",
            f"| Speaker accuracy | {f'{tq.speaker_accuracy:.1%}' if tq.speaker_accuracy is not None else 'N/A'} |",
            f"| Coherence | {tq.coherence_score:.2f} |",
            f"| Completeness | {tq.completeness_score:.2f} |",
            f"| Overall quality | **{tq.overall_quality:.2f}** |",
            "",
        ]
        if tq.hallucination_flags:
            sample = ", ".join(f'"{f}"' for f in tq.hallucination_flags[:5])
            lines += [f"**Hallucination flags:** {sample}", ""]

    lines += ["## Layer 2: Extraction Quality", ""]

    if report.comparison_field_metrics and report.comparison_model:
        lines += [
            f"| Field | P | R | F1 `{report.model}` | F1 `{report.comparison_model}` | Δ F1 |",
            "|-------|---|---|-----|-----|------|",
        ]
        for field, m in report.field_metrics.items():
            comp = report.comparison_field_metrics.get(field)
            if comp:
                delta = m.f1 - comp.f1
                sign = "+" if delta >= 0 else ""
                lines.append(
                    f"| {field} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} | {comp.f1:.3f} | {sign}{delta:.3f} |"
                )
    else:
        lines += ["| Field | Precision | Recall | F1 |", "|-------|-----------|--------|----|"]
        for field, m in report.field_metrics.items():
            lines.append(f"| {field} | {m.precision:.3f} | {m.recall:.3f} | **{m.f1:.3f}** |")

    lines += ["", f"**Overall F1:** {report.overall_extraction_f1:.3f}", ""]

    if report.failure_patterns:
        lines += ["## Failure Patterns", ""]
        for p in report.failure_patterns:
            lines.append(f"- {p}")
        lines.append("")

    if report.transcript_extraction_correlation is not None:
        r = report.transcript_extraction_correlation
        lines += [
            "## Transcript Quality → Extraction Quality Correlation",
            "",
            f"Pearson r = **{r:.3f}**",
            "",
            "> Calls with lower transcript quality scores tend to show proportionally lower extraction F1."
            if r > 0.3 else
            "> Calls with higher transcript quality scores paradoxically correlate with lower extraction F1"
            " — investigate prompt sensitivity or scoring artifacts."
            if r < -0.3 else
            "> Low correlation — transcript quality is not the primary driver of extraction failures.",
            "",
        ]

    return "\n".join(lines)
