from __future__ import annotations

import json
import re

from anthropic import Anthropic

from .schemas import ExtractionEvalResult, ModelOutput, TaskSpec, TestCase

_client = Anthropic()


def _parse_json(text: str) -> object:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)


def generate_rubric(task_spec: TaskSpec) -> dict:
    """Generate a task-specific scoring rubric. Called once and reused across all test cases."""
    fields_json = json.dumps(
        [{"name": f.name, "type": f.type, "values": f.values, "description": f.description}
         for f in task_spec.fields],
        indent=2,
    )
    prompt = f"""Create a scoring rubric for evaluating LLM extraction quality.

Task: {task_spec.description}
Constraints: {json.dumps(task_spec.constraints)}

Fields:
{fields_json}

For each field define what counts as correct vs incorrect extraction.
Respond with JSON only:
{{
  "<field_name>": {{
    "exact_match_required": true/false,
    "null_is_valid_when": "<when null is the correct answer>",
    "common_errors": ["<likely mistakes>"]
  }}
}}"""

    response = _client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(response.content[0].text)


def evaluate_extraction(
    test_case: TestCase,
    output: ModelOutput,
    task_spec: TaskSpec,
    rubric: dict,
) -> ExtractionEvalResult:
    if output.error:
        return ExtractionEvalResult(
            test_case_id=test_case.id,
            model=output.model,
            field_scores={f.name: False for f in task_spec.fields},
            overall_score=0.0,
            judge_reasoning=f"Model error: {output.error}",
            failure_categories=["model_error"],
        )

    prompt = f"""Score this LLM extraction against the ground truth.

Ground truth: {json.dumps(test_case.expected_extraction)}
Model output: {json.dumps(output.extracted_fields)}
Rubric: {json.dumps(rubric)}

Transcript (first 400 chars): {test_case.transcript.full_text[:400]}

Determine if each field was extracted correctly per the rubric.

Respond with JSON only:
{{
  "field_scores": {{{", ".join(f'"{f.name}": true/false' for f in task_spec.fields)}}},
  "overall_score": <float 0.0-1.0>,
  "failure_categories": ["hallucination"|"wrong_value"|"missed_null"|"format_error"],
  "reasoning": "<one sentence on key failures if any>"
}}"""

    response = _client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_json(response.content[0].text)

    return ExtractionEvalResult(
        test_case_id=test_case.id,
        model=output.model,
        field_scores=result["field_scores"],
        overall_score=result["overall_score"],
        judge_reasoning=result["reasoning"],
        failure_categories=result.get("failure_categories", []),
    )
