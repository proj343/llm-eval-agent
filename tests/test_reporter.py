"""Unit tests for reporter metrics — no API calls required."""

from eval_agent.reporter import (
    _analyze_failures,
    _compute_correlation,
    _compute_field_metrics,
    render_markdown_report,
)
from eval_agent.schemas import (
    EvalReport,
    ExtractionEvalResult,
    FieldMetrics,
    FieldSpec,
    SpeakerTurn,
    TaskSpec,
    TestCase,
    Transcript,
    TranscriptEvalResult,
)


def _make_task() -> TaskSpec:
    return TaskSpec(
        name="test_task",
        description="Test extraction task",
        fields=[
            FieldSpec(name="urgency", type="enum", values=["high", "medium", "low"], description="Urgency"),
            FieldSpec(name="budget_mentioned", type="bool", description="Budget"),
        ],
    )


def _make_transcript(audio_file: str = "test.mp3") -> Transcript:
    return Transcript(
        audio_file=audio_file,
        turns=[SpeakerTurn(speaker="AGENT", text="Hello"), SpeakerTurn(speaker="CUSTOMER", text="Hi")],
        full_text="AGENT: Hello\nCUSTOMER: Hi",
        source="synthetic",
        ground_truth_text="AGENT: Hello\nCUSTOMER: Hi",
    )


def _make_case(case_id: str, expected: dict) -> TestCase:
    return TestCase(
        id=case_id,
        transcript=_make_transcript(f"{case_id}.mp3"),
        expected_extraction=expected,
        category="happy_path",
        difficulty="easy",
    )


def _make_result(
    case_id: str, field_scores: dict, overall: float = 1.0, failures: list[str] | None = None
) -> ExtractionEvalResult:
    return ExtractionEvalResult(
        test_case_id=case_id,
        model="gpt-4o-mini",
        field_scores=field_scores,
        overall_score=overall,
        judge_reasoning="test",
        failure_categories=failures or [],
    )


class TestFieldMetrics:
    def test_perfect_extraction(self):
        task = _make_task()
        cases = [
            _make_case("c1", {"urgency": "high", "budget_mentioned": True}),
            _make_case("c2", {"urgency": "low", "budget_mentioned": False}),
        ]
        results = [
            _make_result("c1", {"urgency": True, "budget_mentioned": True}),
            _make_result("c2", {"urgency": True, "budget_mentioned": True}),
        ]
        metrics = _compute_field_metrics(task, cases, results)
        assert metrics["urgency"].f1 == 1.0
        assert metrics["budget_mentioned"].f1 == 1.0

    def test_all_wrong(self):
        task = _make_task()
        cases = [_make_case("c1", {"urgency": "high", "budget_mentioned": True})]
        results = [_make_result("c1", {"urgency": False, "budget_mentioned": False}, 0.0)]
        metrics = _compute_field_metrics(task, cases, results)
        assert metrics["urgency"].f1 == 0.0
        assert metrics["budget_mentioned"].f1 == 0.0

    def test_partial_correct(self):
        task = _make_task()
        cases = [
            _make_case("c1", {"urgency": "high", "budget_mentioned": True}),
            _make_case("c2", {"urgency": "low", "budget_mentioned": True}),
        ]
        results = [
            _make_result("c1", {"urgency": True, "budget_mentioned": False}),
            _make_result("c2", {"urgency": True, "budget_mentioned": False}),
        ]
        metrics = _compute_field_metrics(task, cases, results)
        assert metrics["urgency"].f1 == 1.0
        assert metrics["budget_mentioned"].f1 == 0.0

    def test_f1_formula(self):
        """F1 = 2*P*R / (P+R); verify against manual computation."""
        task = _make_task()
        # 2 correct, 1 missed (fn), 1 hallucinated (fp)
        cases = [
            _make_case("c1", {"urgency": "high", "budget_mentioned": True}),
            _make_case("c2", {"urgency": "low", "budget_mentioned": True}),
            _make_case("c3", {"urgency": None, "budget_mentioned": True}),   # null expected
            _make_case("c4", {"urgency": "high", "budget_mentioned": True}),
        ]
        results = [
            _make_result("c1", {"urgency": True, "budget_mentioned": True}),
            _make_result("c2", {"urgency": True, "budget_mentioned": True}),
            _make_result("c3", {"urgency": False, "budget_mentioned": True}),   # fp on urgency
            _make_result("c4", {"urgency": False, "budget_mentioned": True}),   # fn on urgency
        ]
        metrics = _compute_field_metrics(task, cases, results)
        m = metrics["urgency"]
        expected_p = 2 / (2 + 1)
        expected_r = 2 / (2 + 1)
        expected_f1 = 2 * expected_p * expected_r / (expected_p + expected_r)
        assert abs(m.precision - expected_p) < 0.01
        assert abs(m.recall - expected_r) < 0.01
        assert abs(m.f1 - expected_f1) < 0.01


class TestCorrelation:
    def _make_transcript_eval(self, audio_file: str, quality: float) -> TranscriptEvalResult:
        return TranscriptEvalResult(
            audio_file=audio_file,
            coherence_score=quality,
            completeness_score=quality,
            overall_quality=quality,
        )

    def test_positive_correlation(self):
        t_evals = [self._make_transcript_eval(f"f{i}", v) for i, v in enumerate([0.9, 0.7, 0.5, 0.3])]
        e_evals = [
            ExtractionEvalResult(test_case_id=f"c{i}", model="m", field_scores={}, overall_score=v, judge_reasoning="")
            for i, v in enumerate([0.9, 0.7, 0.5, 0.3])
        ]
        r = _compute_correlation(t_evals, e_evals)
        assert r is not None
        assert r > 0.9

    def test_too_few_points(self):
        t_evals = [self._make_transcript_eval("f0", 0.9), self._make_transcript_eval("f1", 0.5)]
        e_evals = [
            ExtractionEvalResult(test_case_id="c0", model="m", field_scores={}, overall_score=0.9, judge_reasoning=""),
            ExtractionEvalResult(test_case_id="c1", model="m", field_scores={}, overall_score=0.5, judge_reasoning=""),
        ]
        assert _compute_correlation(t_evals, e_evals) is None

    def test_no_variance(self):
        t_evals = [self._make_transcript_eval(f"f{i}", 0.8) for i in range(5)]
        e_evals = [
            ExtractionEvalResult(test_case_id=f"c{i}", model="m", field_scores={}, overall_score=0.8,
                                 judge_reasoning="")
            for i in range(5)
        ]
        assert _compute_correlation(t_evals, e_evals) is None


class TestFailureAnalysis:
    def test_counts_categories(self):
        cases = [_make_case(f"c{i}", {"urgency": "high"}) for i in range(4)]
        results = [
            _make_result("c0", {}, failures=["hallucination"]),
            _make_result("c1", {}, failures=["hallucination"]),
            _make_result("c2", {}, failures=["wrong_value"]),
            _make_result("c3", {}, failures=[]),
        ]
        patterns = _analyze_failures(cases, results)
        assert any("hallucination" in p for p in patterns)
        assert any("2/" in p for p in patterns if "hallucination" in p)

    def test_empty_failures(self):
        cases = [_make_case("c0", {"urgency": "high"})]
        results = [_make_result("c0", {}, failures=[])]
        assert _analyze_failures(cases, results) == []


class TestMarkdownReport:
    def test_renders_without_error(self):
        report = EvalReport(
            task_name="test",
            model="gpt-4o-mini",
            n_transcripts=10,
            field_metrics={"urgency": FieldMetrics(precision=0.9, recall=0.85, f1=0.87, n_cases=10)},
            overall_extraction_f1=0.87,
            failure_patterns=["hallucination: 2/10 cases (20%)"],
        )
        md = render_markdown_report(report)
        assert "gpt-4o-mini" in md
        assert "urgency" in md
        assert "0.870" in md

    def test_comparison_table_included(self):
        report = EvalReport(
            task_name="test",
            model="gpt-4o-mini",
            comparison_model="gpt-4.1",
            n_transcripts=10,
            field_metrics={"urgency": FieldMetrics(precision=0.9, recall=0.85, f1=0.87, n_cases=10)},
            comparison_field_metrics={"urgency": FieldMetrics(precision=0.95, recall=0.90, f1=0.92, n_cases=10)},
            overall_extraction_f1=0.87,
            failure_patterns=[],
        )
        md = render_markdown_report(report)
        assert "gpt-4.1" in md
        assert "Δ" in md or "Delta" in md or "-0.050" in md
