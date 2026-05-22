from __future__ import annotations

import json
import re

from anthropic import Anthropic

from .schemas import TaskSpec, Transcript, TranscriptEvalResult

_client = Anthropic()


def _parse_json(text: str) -> object:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)


def evaluate_transcript(transcript: Transcript, task_spec: TaskSpec) -> TranscriptEvalResult:
    wer = _compute_wer(transcript) if transcript.ground_truth_text else None
    speaker_accuracy = _compute_speaker_accuracy(transcript) if transcript.source == "synthetic" else None
    llm_scores = _llm_judge(transcript, task_spec)
    overall = _composite_score(wer, llm_scores)

    return TranscriptEvalResult(
        audio_file=transcript.audio_file,
        wer=wer,
        speaker_accuracy=speaker_accuracy,
        coherence_score=llm_scores["coherence"],
        completeness_score=llm_scores["completeness"],
        hallucination_flags=llm_scores.get("hallucination_flags", []),
        overall_quality=overall,
    )


def _compute_wer(transcript: Transcript) -> float:
    from jiwer import wer
    return round(wer(transcript.ground_truth_text, transcript.full_text), 4)


def _compute_speaker_accuracy(transcript: Transcript) -> float:
    speakers = [t.speaker for t in transcript.turns]
    if len(speakers) < 2:
        return 0.0
    has_both = "AGENT" in speakers and "CUSTOMER" in speakers
    if not has_both:
        return 0.5
    alternations = sum(1 for i in range(1, len(speakers)) if speakers[i] != speakers[i - 1])
    return round(alternations / (len(speakers) - 1), 4)


def _llm_judge(transcript: Transcript, task_spec: TaskSpec) -> dict:
    prompt = f"""You are a quality reviewer for call transcripts used in an LLM extraction pipeline.

Task context: {task_spec.description}

Transcript:
{transcript.full_text}

Evaluate the transcript quality on these dimensions and respond with JSON only:
{{
  "coherence": <float 0.0-1.0, does this read as a plausible real conversation>,
  "completeness": <float 0.0-1.0, does the conversation feel complete without abrupt cuts or missing context>,
  "hallucination_flags": [<specific words or phrases that appear garbled, impossible, or likely transcription errors>],
  "reasoning": "<one sentence explanation>"
}}"""

    response = _client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(response.content[0].text)


def _composite_score(wer: float | None, llm_scores: dict) -> float:
    scores = [llm_scores["coherence"], llm_scores["completeness"]]
    if wer is not None:
        scores.append(max(0.0, 1.0 - wer))
    penalty = min(0.2, len(llm_scores.get("hallucination_flags", [])) * 0.02)
    return round(max(0.0, sum(scores) / len(scores) - penalty), 4)
