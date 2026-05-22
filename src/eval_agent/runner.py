from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .schemas import TaskSpec, TestCase, ModelOutput


def run_extraction(
    test_cases: list[TestCase],
    task_spec: TaskSpec,
    model: str,
    max_workers: int = 10,
) -> list[ModelOutput]:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_case = {
            executor.submit(_extract_single, case, task_spec, model): case
            for case in test_cases
        }
        results_map: dict[str, ModelOutput] = {}
        for future in as_completed(future_to_case):
            output = future.result()
            results_map[output.test_case_id] = output

    # Preserve input order
    return [results_map[case.id] for case in test_cases]


def _extract_single(test_case: TestCase, task_spec: TaskSpec, model: str) -> ModelOutput:
    fields_desc = "\n".join(
        f"- {f.name}: {f.description}" + (f" Allowed values: {f.values}" if f.values else "")
        for f in task_spec.fields
    )
    constraints = "\n".join(f"- {c}" for c in task_spec.constraints)
    field_names = [f.name for f in task_spec.fields]

    prompt = f"""Extract structured information from this call transcript.

Fields to extract:
{fields_desc}

Constraints:
{constraints}

Transcript:
{test_case.transcript.full_text}

Respond with a JSON object containing exactly these fields: {field_names}
Use null for any field where there is insufficient evidence. Respond with valid JSON only."""

    start = time.monotonic()
    try:
        raw, tokens = _call_model(model, prompt)
        extracted = json.loads(raw)
        error = None
    except Exception as e:
        raw, extracted, tokens, error = "", {}, 0, str(e)

    return ModelOutput(
        test_case_id=test_case.id,
        model=model,
        raw_response=raw,
        extracted_fields=extracted,
        latency_ms=int((time.monotonic() - start) * 1000),
        tokens_used=tokens,
        error=error,
    )


def _call_model(model: str, prompt: str) -> tuple[str, int]:
    if model.startswith("claude"):
        from anthropic import Anthropic
        client = Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens
    else:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content
        tokens = response.usage.total_tokens
        return text, tokens
