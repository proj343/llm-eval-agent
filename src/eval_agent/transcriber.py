from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from .schemas import Transcript, SpeakerTurn


class TranscriptionProvider(str, Enum):
    ASSEMBLYAI = "assemblyai"
    WHISPER = "whisper"


def transcribe(audio_path: str, provider: TranscriptionProvider = TranscriptionProvider.ASSEMBLYAI) -> Transcript:
    if provider == TranscriptionProvider.ASSEMBLYAI:
        return _transcribe_assemblyai(audio_path)
    return _transcribe_whisper(audio_path)


def transcribe_directory(
    audio_dir: str,
    provider: TranscriptionProvider = TranscriptionProvider.ASSEMBLYAI,
) -> list[Transcript]:
    audio_dir = Path(audio_dir)
    audio_files = sorted(
        list(audio_dir.glob("*.mp3"))
        + list(audio_dir.glob("*.wav"))
        + list(audio_dir.glob("*.m4a"))
    )
    if not audio_files:
        raise ValueError(f"No audio files found in {audio_dir}")
    return [transcribe(str(f), provider) for f in audio_files]


def _transcribe_assemblyai(audio_path: str) -> Transcript:
    import assemblyai as aai

    aai.settings.api_key = os.environ["ASSEMBLYAI_API_KEY"]
    config = aai.TranscriptionConfig(speaker_labels=True)
    result = aai.Transcriber().transcribe(audio_path, config=config)

    turns = []
    if result.utterances:
        for utterance in result.utterances:
            speaker = "AGENT" if utterance.speaker == "A" else "CUSTOMER"
            turns.append(SpeakerTurn(
                speaker=speaker,
                text=utterance.text,
                start_ms=utterance.start,
                end_ms=utterance.end,
            ))
    else:
        turns = [SpeakerTurn(speaker="UNKNOWN", text=result.text or "")]

    full_text = "\n".join(f"{t.speaker}: {t.text}" for t in turns)
    return Transcript(
        audio_file=audio_path,
        turns=turns,
        full_text=full_text,
        duration_seconds=result.audio_duration,
        source="real",
    )


def _transcribe_whisper(audio_path: str) -> Transcript:
    from openai import OpenAI

    client = OpenAI()
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )

    turns = [SpeakerTurn(speaker="UNKNOWN", text=result)]
    return Transcript(
        audio_file=audio_path,
        turns=turns,
        full_text=result,
        source="real",
    )
