"""
Regression tests against golden fixtures — no API calls.

Golden fixtures capture expected metric values for a fixed set of test cases.
Run after any change to reporter logic, scoring, or schema to catch regressions.
Update fixtures intentionally with: pytest --update-golden
"""

import json
from pathlib import Path

import pytest

from eval_agent.reporter import generate_report, render_markdown_report
from eval_agent.schemas import (
    ExtractionEvalResult,
    FieldSpec,
    SpeakerTurn,
    TaskSpec,
    TestCase,
    Transcript,
    TranscriptEvalResult,
)

GOLDEN_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR.mkdir(exist_ok=True)
GOLDEN_FILE = GOLDEN_DIR / "regression_report.json"


def _task() -> TaskSpec:
    return TaskSpec(
        name="regression_task",
        description="Regression test extraction task",
        fields=[
            FieldSpec(name="urgency", type="enum", values=["high", "medium", "low"], description="Urgency level"),
            FieldSpec(name="budget_mentioned", type="bool", description="Budget explicitly stated"),
        ],
    )


def _transcript(i: int) -> Transcript:
    return Transcript(
        audio_file=f"case_{i}.mp3",
        turns=[SpeakerTurn(speaker="AGENT", text="Hello"), SpeakerTurn(speaker="CUSTOMER", text="Hi")],
        full_text="AGENT: Hello\nCUSTOMER: Hi",
        source="synthetic",
    )


def _test_cases() -> list[TestCase]:
    return [
        TestCase(id=f"c{i}", transcript=_transcript(i),
                 expected_extraction={"urgency": "high", "budget_mentioned": True},
                 category="happy_path", difficulty="easy")
        for i in range(10)
    ]


def _extraction_results(correct_count: int) -> list[ExtractionEvalResult]:
    results = []
    for i in range(10):
        correct = i < correct_count
        results.append(ExtractionEvalResult(
            test_case_id=f"c{i}",
            model="test-model",
            field_scores={"urgency": correct, "budget_mentioned": correct},
            overall_score=1.0 if correct else 0.0,
            judge_reasoning="test",
            failure_categories=[] if correct else ["wrong_value"],
        ))
    return results


def _transcript_results() -> list[TranscriptEvalResult]:
    return [
        TranscriptEvalResult(
            audio_file=f"case_{i}.mp3",
            coherence_score=0.9,
            completeness_score=0.85,
            overall_quality=0.87,
        )
        for i in range(10)
    ]


def test_report_metrics_stable(request):
    """Assert that report metrics match golden fixture values within tolerance."""
    task = _task()
    test_cases = _test_cases()
    extraction_results = _extraction_results(correct_count=8)  # 80% correct
    transcript_results = _transcript_results()

    report = generate_report(
        task_spec=task,
        model="test-model",
        test_cases=test_cases,
        extraction_results=extraction_results,
        transcript_results=transcript_results,
    )

    current = {
        "overall_extraction_f1": report.overall_extraction_f1,
        "field_metrics": {
            field: {"precision": m.precision, "recall": m.recall, "f1": m.f1}
            for field, m in report.field_metrics.items()
        },
        "n_transcripts": report.n_transcripts,
    }

    update_golden = request.config.getoption("--update-golden", default=False)

    if update_golden or not GOLDEN_FILE.exists():
        GOLDEN_FILE.write_text(json.dumps(current, indent=2))
        pytest.skip("Golden file written — re-run without --update-golden to validate")

    golden = json.loads(GOLDEN_FILE.read_text())

    assert abs(current["overall_extraction_f1"] - golden["overall_extraction_f1"]) < 0.01, (
        f"Overall F1 regressed: {current['overall_extraction_f1']} vs golden {golden['overall_extraction_f1']}"
    )
    for field in golden["field_metrics"]:
        for metric in ("precision", "recall", "f1"):
            curr_val = current["field_metrics"][field][metric]
            gold_val = golden["field_metrics"][field][metric]
            assert abs(curr_val - gold_val) < 0.01, (
                f"{field}.{metric} regressed: {curr_val} vs golden {gold_val}"
            )


def test_markdown_report_contains_required_sections():
    task = _task()
    report = generate_report(
        task_spec=task,
        model="test-model",
        test_cases=_test_cases(),
        extraction_results=_extraction_results(8),
        transcript_results=_transcript_results(),
    )
    md = render_markdown_report(report)
    assert "## Layer 2: Extraction Quality" in md
    assert "urgency" in md
    assert "budget_mentioned" in md
    assert "test-model" in md


