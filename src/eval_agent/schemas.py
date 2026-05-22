from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SpeakerTurn(BaseModel):
    speaker: str  # "AGENT" or "CUSTOMER"
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class Transcript(BaseModel):
    audio_file: str
    turns: list[SpeakerTurn]
    full_text: str
    duration_seconds: Optional[float] = None
    source: str = "real"  # "real" or "synthetic"
    ground_truth_text: Optional[str] = None  # populated in synthetic mode for WER


class FieldSpec(BaseModel):
    name: str
    type: str  # "enum", "bool", "string"
    values: Optional[list[str]] = None
    description: str
    nullable: bool = True


class TaskSpec(BaseModel):
    name: str
    description: str
    fields: list[FieldSpec]
    constraints: list[str] = []
    examples: list[dict] = []


class TestCase(BaseModel):
    id: str
    transcript: Transcript
    expected_extraction: dict
    category: str  # "happy_path", "edge_case", "adversarial", "boundary", "real"
    difficulty: str
    notes: Optional[str] = None


class ModelOutput(BaseModel):
    test_case_id: str
    model: str
    raw_response: str
    extracted_fields: dict
    latency_ms: int
    tokens_used: int
    error: Optional[str] = None


class TranscriptEvalResult(BaseModel):
    audio_file: str
    wer: Optional[float] = None
    speaker_accuracy: Optional[float] = None
    coherence_score: float
    completeness_score: float
    hallucination_flags: list[str] = []
    overall_quality: float


class ExtractionEvalResult(BaseModel):
    test_case_id: str
    model: str
    field_scores: dict[str, bool]
    overall_score: float
    judge_reasoning: str
    failure_categories: list[str] = []


class FieldMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    n_cases: int


class EvalReport(BaseModel):
    task_name: str
    model: str
    comparison_model: Optional[str] = None
    n_transcripts: int
    transcript_quality: Optional[TranscriptEvalResult] = None
    field_metrics: dict[str, FieldMetrics]
    overall_extraction_f1: float
    failure_patterns: list[str]
    transcript_extraction_correlation: Optional[float] = None
    comparison_field_metrics: Optional[dict[str, FieldMetrics]] = None
