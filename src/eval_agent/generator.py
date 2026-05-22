from __future__ import annotations

import json
import uuid
from pathlib import Path

from anthropic import Anthropic

from .schemas import TaskSpec, TestCase, Transcript, SpeakerTurn

_client = Anthropic()

_CATEGORIES = ["happy_path", "edge_case", "adversarial", "boundary"]
_TARGET_DIST = {"happy_path": 0.30, "edge_case": 0.30, "adversarial": 0.25, "boundary": 0.15}
_CATEGORY_INSTRUCTIONS = {
    "happy_path": "Clear, unambiguous conversations where all fields are easily extractable from explicit statements.",
    "edge_case": "Conversations where some fields require inference or are only partially mentioned.",
    "adversarial": "Conversations designed to cause hallucination: budget mentioned in passing but not real, false urgency cues, contradictory sentiment, misleading objection signals.",
    "boundary": "Very short calls (3-5 turns), abrupt endings, or calls with only one speaker contributing.",
}


def generate_test_cases(task_spec: TaskSpec, n: int = 30) -> list[TestCase]:
    cases: list[TestCase] = []
    counts = {c: 0 for c in _CATEGORIES}

    while len(cases) < n:
        total = max(len(cases), 1)
        gaps = {c: _TARGET_DIST[c] - counts[c] / total for c in _CATEGORIES}
        category = max(gaps, key=gaps.get)
        batch_size = min(5, n - len(cases))
        batch = _generate_batch(task_spec, category, batch_size)
        cases.extend(batch)
        counts[category] += len(batch)

    return cases[:n]


def _generate_batch(task_spec: TaskSpec, category: str, n: int) -> list[TestCase]:
    fields_desc = "\n".join(
        f"- {f.name} ({f.type}"
        + (f", values: {f.values}" if f.values else "")
        + f"): {f.description}"
        for f in task_spec.fields
    )
    field_keys = [f.name for f in task_spec.fields]

    prompt = f"""Generate {n} synthetic call transcripts for evaluating an LLM extraction pipeline.

Task: {task_spec.description}

Fields to extract:
{fields_desc}

Constraints: {json.dumps(task_spec.constraints)}

Category: {category}
Instructions: {_CATEGORY_INSTRUCTIONS[category]}

For each transcript respond with a JSON array of objects:
[
  {{
    "turns": [
      {{"speaker": "AGENT", "text": "..."}},
      {{"speaker": "CUSTOMER", "text": "..."}}
    ],
    "expected_extraction": {{{", ".join(f'"{k}": <value or null>' for k in field_keys)}}},
    "difficulty": "easy|medium|hard",
    "notes": "<what makes this case interesting>"
  }}
]

Respond with valid JSON only. Generate exactly {n} items."""

    response = _client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = json.loads(response.content[0].text)
    cases = []
    for item in raw:
        turns = [SpeakerTurn(speaker=t["speaker"], text=t["text"]) for t in item["turns"]]
        full_text = "\n".join(f"{t.speaker}: {t.text}" for t in turns)
        audio_id = f"synthetic_{uuid.uuid4().hex[:8]}"
        transcript = Transcript(
            audio_file=audio_id,
            turns=turns,
            full_text=full_text,
            source="synthetic",
            ground_truth_text=full_text,
        )
        cases.append(TestCase(
            id=uuid.uuid4().hex[:8],
            transcript=transcript,
            expected_extraction=item["expected_extraction"],
            category=category,
            difficulty=item["difficulty"],
            notes=item.get("notes"),
        ))
    return cases


def generate_audio_from_transcripts(transcripts: list[Transcript], output_dir: str) -> list[str]:
    """Convert synthetic transcripts to MP3 via OpenAI TTS for end-to-end audio testing."""
    from openai import OpenAI

    oai = OpenAI()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files = []
    for transcript in transcripts:
        script = " ... ".join(t.text for t in transcript.turns)
        out_path = output_dir / f"{Path(transcript.audio_file).stem}.mp3"

        response = oai.audio.speech.create(model="tts-1", voice="alloy", input=script)
        response.stream_to_file(str(out_path))
        audio_files.append(str(out_path))

    return audio_files
