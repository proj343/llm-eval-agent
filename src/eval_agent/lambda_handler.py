"""
Lambda entrypoint. Handles two event sources:

  1. API Gateway HTTP — POST /eval with JSON body
  2. SQS — triggered automatically when audio is uploaded to S3 or a job is enqueued

Event body schema (API Gateway or SQS message body):
  {
    "task": "examples/extraction/task.yaml",   # S3 key or bundled path
    "model": "gpt-4o-mini",
    "mode": "synthetic" | "audio",
    "n_cases": 30,                             # synthetic mode
    "audio_s3_prefix": "audio/batch-001/",     # audio mode — S3 prefix
    "compare": "gpt-4.1"                       # optional
  }

Reports are written to s3://<S3_BUCKET>/reports/<job_id>.[md|json]
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import boto3
import yaml

_ssm = boto3.client("ssm")
_s3 = boto3.client("s3")

S3_BUCKET = os.environ["S3_BUCKET"]
SSM_PREFIX = os.environ["SSM_PREFIX"]


def _load_secrets() -> None:
    """Pull API keys from SSM Parameter Store into environment variables."""
    params = _ssm.get_parameters(
        Names=[
            f"{SSM_PREFIX}/ANTHROPIC_API_KEY",
            f"{SSM_PREFIX}/OPENAI_API_KEY",
            f"{SSM_PREFIX}/ASSEMBLYAI_API_KEY",
        ],
        WithDecryption=True,
    )
    for p in params["Parameters"]:
        key = p["Name"].split("/")[-1]
        os.environ[key] = p["Value"]


def _parse_event(event: dict) -> dict:
    """Normalise API Gateway and SQS event shapes into a job dict."""
    # SQS batch (batch_size=1 so always one record)
    if "Records" in event:
        record = event["Records"][0]
        # Could be SQS or S3-via-SQS notification
        body = json.loads(record.get("body", "{}"))
        # S3 upload notification routed through SQS
        if "Records" in body and body["Records"][0].get("eventSource") == "aws:s3":
            s3_record = body["Records"][0]["s3"]
            prefix = str(Path(s3_record["object"]["key"]).parent) + "/"
            return {"mode": "audio", "audio_s3_prefix": prefix}
        return body

    # API Gateway HTTP
    if "body" in event:
        return json.loads(event["body"] or "{}")

    return event


def handler(event: dict, context: object) -> dict:
    _load_secrets()

    job = _parse_event(event)
    job_id = uuid.uuid4().hex[:12]
    mode = job.get("mode", "synthetic")
    model = job.get("model", "gpt-4o-mini")
    compare = job.get("compare")
    n_cases = int(job.get("n_cases", 30))
    task_path = job.get("task", "examples/extraction/task.yaml")

    # Lazy imports after secrets are loaded
    from eval_agent.extraction_judge import evaluate_extraction, generate_rubric
    from eval_agent.generator import generate_test_cases
    from eval_agent.reporter import generate_report, render_markdown_report
    from eval_agent.runner import run_extraction
    from eval_agent.schemas import TaskSpec, TestCase
    from eval_agent.transcript_judge import evaluate_transcript
    from eval_agent.transcriber import TranscriptionProvider, transcribe_directory

    with open(task_path) as f:
        task_spec = TaskSpec(**yaml.safe_load(f))

    with tempfile.TemporaryDirectory() as tmpdir:
        if mode == "audio":
            audio_prefix = job.get("audio_s3_prefix", "audio/")
            audio_dir = Path(tmpdir) / "audio"
            audio_dir.mkdir()
            _download_s3_prefix(audio_prefix, str(audio_dir))
            transcripts = transcribe_directory(str(audio_dir), TranscriptionProvider.ASSEMBLYAI)
            test_cases = [
                TestCase(
                    id=uuid.uuid4().hex[:8],
                    transcript=t,
                    expected_extraction={},
                    category="real",
                    difficulty="unknown",
                )
                for t in transcripts
            ]
        else:
            test_cases = generate_test_cases(task_spec, n_cases)
            transcripts = [tc.transcript for tc in test_cases]

        transcript_evals = [evaluate_transcript(t, task_spec) for t in transcripts]
        rubric = generate_rubric(task_spec)

        evaluable = [tc for tc in test_cases if tc.expected_extraction]
        primary_outputs = run_extraction(evaluable, task_spec, model, max_workers=10)
        primary_evals = [
            evaluate_extraction(tc, out, task_spec, rubric)
            for tc, out in zip(evaluable, primary_outputs)
        ]

        comparison_evals = None
        if compare:
            comp_outputs = run_extraction(evaluable, task_spec, compare, max_workers=10)
            comparison_evals = [
                evaluate_extraction(tc, out, task_spec, rubric)
                for tc, out in zip(evaluable, comp_outputs)
            ]

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
        report_json = json.dumps(report.model_dump(), indent=2)

        md_key = f"reports/{job_id}.md"
        json_key = f"reports/{job_id}.json"
        _s3.put_object(Bucket=S3_BUCKET, Key=md_key, Body=md.encode(), ContentType="text/markdown")
        _s3.put_object(Bucket=S3_BUCKET, Key=json_key, Body=report_json.encode(), ContentType="application/json")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "job_id": job_id,
            "report_md": f"s3://{S3_BUCKET}/{md_key}",
            "report_json": f"s3://{S3_BUCKET}/{json_key}",
            "overall_f1": report.overall_extraction_f1,
        }),
    }


def _download_s3_prefix(prefix: str, local_dir: str) -> None:
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = Path(key).name
            if filename:
                _s3.download_file(S3_BUCKET, key, str(Path(local_dir) / filename))
