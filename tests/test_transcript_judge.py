"""Unit tests for transcript judge — offline computations only."""

from eval_agent.schemas import SpeakerTurn, Transcript
from eval_agent.transcript_judge import _composite_score, _compute_speaker_accuracy


def _make_transcript(turns: list[tuple[str, str]], ground_truth: str | None = None) -> Transcript:
    speaker_turns = [SpeakerTurn(speaker=s, text=t) for s, t in turns]
    full = "\n".join(f"{s}: {t}" for s, t in turns)
    return Transcript(
        audio_file="test.mp3",
        turns=speaker_turns,
        full_text=full,
        source="synthetic",
        ground_truth_text=ground_truth or full,
    )


class TestSpeakerAccuracy:
    def test_perfect_alternation(self):
        t = _make_transcript([("AGENT", "Hi"), ("CUSTOMER", "Hello"), ("AGENT", "How can I help?")])
        assert _compute_speaker_accuracy(t) == 1.0

    def test_single_speaker(self):
        t = _make_transcript([("AGENT", "Hi"), ("AGENT", "Hello")])
        assert _compute_speaker_accuracy(t) == 0.5  # has AGENT but no CUSTOMER

    def test_only_one_turn(self):
        t = _make_transcript([("AGENT", "Hi")])
        assert _compute_speaker_accuracy(t) == 0.0

    def test_no_alternation(self):
        t = _make_transcript([
            ("AGENT", "Hi"), ("AGENT", "Are you there?"), ("CUSTOMER", "Yes")
        ])
        # 1 alternation out of 2 possible = 0.5
        assert _compute_speaker_accuracy(t) == 0.5


class TestCompositeScore:
    def test_perfect_scores(self):
        scores = {"coherence": 1.0, "completeness": 1.0, "hallucination_flags": []}
        assert _composite_score(None, scores) == 1.0

    def test_wer_penalizes(self):
        scores = {"coherence": 1.0, "completeness": 1.0, "hallucination_flags": []}
        with_wer = _composite_score(0.5, scores)   # 50% WER → quality 0.5 included
        without_wer = _composite_score(None, scores)
        assert with_wer < without_wer

    def test_hallucination_flags_penalize(self):
        clean = _composite_score(None, {"coherence": 0.9, "completeness": 0.9, "hallucination_flags": []})
        flagged = _composite_score(None, {"coherence": 0.9, "completeness": 0.9, "hallucination_flags": ["x"] * 5})
        assert clean > flagged

    def test_score_clamped_to_zero(self):
        scores = {"coherence": 0.0, "completeness": 0.0, "hallucination_flags": ["x"] * 100}
        assert _composite_score(1.0, scores) >= 0.0
