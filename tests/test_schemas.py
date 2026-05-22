"""Smoke tests — schemas parse correctly and reject invalid input."""

import pytest
from pydantic import ValidationError

from eval_agent.schemas import FieldSpec, SpeakerTurn, TaskSpec, Transcript


def test_transcript_full_text_required():
    with pytest.raises(ValidationError):
        Transcript(audio_file="f.mp3", turns=[], full_text=None)  # type: ignore


def test_task_spec_defaults():
    t = TaskSpec(name="x", description="y", fields=[])
    assert t.constraints == []
    assert t.examples == []


def test_field_spec_nullable_default():
    f = FieldSpec(name="urgency", type="enum", description="test")
    assert f.nullable is True


def test_speaker_turn_optional_timestamps():
    turn = SpeakerTurn(speaker="AGENT", text="Hello")
    assert turn.start_ms is None
    assert turn.end_ms is None
