from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .extraction_judge import evaluate_extraction, generate_rubric
from .generator import generate_audio_from_transcripts, generate_test_cases
from .reporter import generate_report, render_markdown_report
from .runner import run_extraction
from .schemas import TaskSpec, TestCase
from .transcriber import TranscriptionProvider, transcribe_directory
from .transcript_judge import evaluate_transcript

load_dotenv()

app = typer.Typer(help="LLM Eval Agent — evaluate extraction quality on call transcripts.")
console = Console()


def _load_task(path: str) -> TaskSpec:
    with open(path) as f:
        return TaskSpec(**yaml.safe_load(f))


@app.command()
def run(
    task: str = typer.Option(..., "--task", "-t", help="Path to task.yaml"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Primary model to evaluate"),
    compare: Optional[str] = typer.Option(None, "--compare", "-c", help="Second model for side-by-side comparison"),
    audio: Optional[str] = typer.Option(None, "--audio", "-a", help="Directory of .mp3/.wav audio files"),
    synthetic: bool = typer.Option(False, "--synthetic", "-s", help="Generate synthetic test cases via LLM"),
    n_cases: int = typer.Option(30, "--n-cases", "-n", help="Number of synthetic test cases to generate"),
    tts: bool = typer.Option(False, "--tts", help="Convert synthetic transcripts to audio via TTS (end-to-end test)"),
    provider: TranscriptionProvider = typer.Option(
        TranscriptionProvider.ASSEMBLYAI, "--provider", help="Transcription provider"
    ),
    workers: int = typer.Option(10, "--workers", "-w", help="Parallel extraction workers"),
    output: str = typer.Option("results", "--output", "-o", help="Output directory for reports"),
) -> None:
    if not audio and not synthetic:
        console.print("[red]Provide --audio <dir> or --synthetic[/red]")
        raise typer.Exit(1)

    task_spec = _load_task(task)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:

        # ── Step 1: get transcripts ──────────────────────────────────────────
        if audio:
            t = progress.add_task("Transcribing audio files...")
            transcripts = transcribe_directory(audio, provider)
            progress.update(t, description=f"Transcribed {len(transcripts)} files ✓")
            test_cases = [
                TestCase(
                    id=uuid.uuid4().hex[:8],
                    transcript=tr,
                    expected_extraction={},
                    category="real",
                    difficulty="unknown",
                )
                for tr in transcripts
            ]
        else:
            t = progress.add_task(f"Generating {n_cases} synthetic test cases...")
            test_cases = generate_test_cases(task_spec, n_cases)
            transcripts = [tc.transcript for tc in test_cases]
            progress.update(t, description=f"Generated {len(test_cases)} test cases ✓")

            if tts:
                t2 = progress.add_task("Generating audio via TTS...")
                audio_dir = str(output_dir / "synthetic_audio")
                generate_audio_from_transcripts(transcripts, audio_dir)
                progress.update(t2, description=f"Audio saved to {audio_dir} ✓")

        # ── Step 2: evaluate transcript quality ─────────────────────────────
        t = progress.add_task("Evaluating transcript quality...")
        transcript_evals = [evaluate_transcript(tr, task_spec) for tr in transcripts]
        progress.update(t, description="Transcript quality evaluated ✓")

        # ── Step 3: generate rubric (once) ──────────────────────────────────
        t = progress.add_task("Generating extraction rubric...")
        rubric = generate_rubric(task_spec)
        progress.update(t, description="Rubric generated ✓")

        # ── Step 4: run extraction + judge for primary model ─────────────────
        evaluable = [tc for tc in test_cases if tc.expected_extraction]
        t = progress.add_task(f"Running extraction with {model}...")
        primary_outputs = run_extraction(evaluable, task_spec, model, workers)
        primary_evals = [
            evaluate_extraction(tc, out, task_spec, rubric)
            for tc, out in zip(evaluable, primary_outputs)
        ]
        progress.update(t, description=f"Extraction evaluated ({model}) ✓")

        # ── Step 5: comparison model (optional) ──────────────────────────────
        comparison_evals = None
        if compare:
            t = progress.add_task(f"Running extraction with {compare}...")
            comp_outputs = run_extraction(evaluable, task_spec, compare, workers)
            comparison_evals = [
                evaluate_extraction(tc, out, task_spec, rubric)
                for tc, out in zip(evaluable, comp_outputs)
            ]
            progress.update(t, description=f"Extraction evaluated ({compare}) ✓")

    # ── Step 6: report ───────────────────────────────────────────────────────
    report = generate_report(
        task_spec=task_spec,
        model=model,
        test_cases=evaluable,
        extraction_results=primary_evals,
        transcript_results=transcript_evals[: len(evaluable)],
        comparison_model=compare,
        comparison_extraction_results=comparison_evals,
    )

    md = render_markdown_report(report)
    console.print("\n" + md)

    slug = model.replace("/", "-").replace(":", "-")
    md_path = output_dir / f"{task_spec.name}_{slug}.md"
    json_path = output_dir / f"{task_spec.name}_{slug}.json"
    md_path.write_text(md)
    json_path.write_text(json.dumps(report.model_dump(), indent=2))

    console.print(f"\n[green]Report saved → {md_path}[/green]")


def main() -> None:
    app()
