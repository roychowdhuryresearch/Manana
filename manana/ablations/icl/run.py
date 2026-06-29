"""In-context-learning ablation for Manana.

This study does no self-learning. It inserts training records directly into
the single-system predictor prompt, then evaluates held-out cases.

Usage:
    uv run python -m manana.ablations.icl.run --config configs/uganda_example.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import os

from lib.llm import DEFAULT_MODEL, LLMClient
from manana.ablations.common import (
    best_matching_option,
    get_gt_key,
    get_visit_num,
    load_split,
    make_output_dir,
    parsed_options,
    print_header,
    summarize_eval,
    write_json,
)
from manana.prompts import load_rendered_prompt

TRUNCATION_MARKER = "\n\n[... record truncated by ICL ablation runner ...]\n\n"


def format_drug_list(items: list[str] | None) -> str:
    if not items:
        return "(none)"
    return ", ".join(str(item).lower() for item in items)


def maybe_truncate(text: str, max_chars: int | None) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if max_chars <= len(TRUNCATION_MARKER) + 20:
        return text[:max_chars]
    body_chars = max_chars - len(TRUNCATION_MARKER)
    head = body_chars // 2
    tail = body_chars - head
    return text[:head] + TRUNCATION_MARKER + text[-tail:]


def build_icl_examples(
    train_cases: list,
    gt_data: dict,
    train_limit: int | None,
    max_record_chars: int | None,
) -> tuple[str, list[dict]]:
    selected_cases = train_cases[:train_limit] if train_limit else train_cases
    parts = [
        "IN-CONTEXT TRAINING RECORDS",
        "",
        "The following are prior training examples from the same task.",
        "Each example contains the patient clinical record and the doctor's ground-truth answer.",
        "Use these examples as in-context evidence for local prescribing patterns.",
        "When answering the new patient record, do not quote training patient identifiers.",
        "",
    ]
    metadata: list[dict] = []

    for idx, case in enumerate(selected_cases, 1):
        key = get_gt_key(case)
        gt_entry = gt_data.get(key)
        if not gt_entry or not gt_entry.get("prescribed"):
            continue

        raw_record = case.build_input_text()
        record = maybe_truncate(raw_record, max_record_chars)
        gt_output = str(gt_entry.get("output", "")).strip()
        visit = get_visit_num(case)

        parts.extend([
            f"TRAINING EXAMPLE {idx:03d}",
            f"Patient ID: {case.patient_id}",
            f"Visit: {visit}",
            f"Cohort: {getattr(case, 'cohort', '') or 'unknown'}",
            "",
            "PATIENT CLINICAL RECORD:",
            record,
            "",
            "DOCTOR GROUND-TRUTH ANSWER:",
            f"Prescribed antiseizure drugs: {format_drug_list(gt_entry.get('prescribed'))}",
            f"Stopped antiseizure drugs: {format_drug_list(gt_entry.get('stopped'))}",
            "Original doctor output:",
            gt_output if gt_output else "(not available)",
            f"END TRAINING EXAMPLE {idx:03d}",
            "",
        ])
        metadata.append({
            "example": idx,
            "patient_id": case.patient_id,
            "visit": visit,
            "key": key,
            "cohort": getattr(case, "cohort", None),
            "prescribed": gt_entry.get("prescribed", []),
            "stopped": gt_entry.get("stopped", []),
            "original_record_chars": len(raw_record),
            "record_chars": len(record),
            "record_truncated": len(record) < len(raw_record),
            "gt_output_chars": len(gt_output),
        })

    parts.extend(["END IN-CONTEXT TRAINING RECORDS", ""])
    return "\n".join(parts), metadata


def build_predictor_prompt(template: str, icl_block: str) -> str:
    return template.replace("{shared_learnings}", icl_block)


async def run_case(
    client: LLMClient,
    predictor_prompt: str,
    case,
    gt_data: dict,
    temperature: float | None,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry.get("prescribed"):
        return None

    gt_drugs = {d.lower() for d in gt_entry["prescribed"]}
    _, pred_raw = await client.call(predictor_prompt, case.build_input_text(), temperature=temperature)
    if not pred_raw:
        return None

    options = parsed_options(pred_raw)
    best_option = best_matching_option(options, gt_drugs)
    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "cohort": getattr(case, "cohort", None),
        "gt": sorted(gt_drugs),
        "pred_option1": options["option_1"],
        "pred_options": options,
        "is_poly": len(gt_drugs) > 1,
        "top1_match": set(options["option_1"]) == gt_drugs,
        "top3_match": best_option is not None,
        "best_option": best_option,
        "raw_content": pred_raw,
    }


def summarize(per_case: list[dict]) -> dict:
    total = len(per_case)
    mono_cases = [case for case in per_case if not case["is_poly"]]
    poly_cases = [case for case in per_case if case["is_poly"]]
    return {
        "total": total,
        "top1_correct": sum(1 for case in per_case if case["top1_match"]),
        "top3_correct": sum(1 for case in per_case if case["top3_match"]),
        "top1_rate": sum(1 for case in per_case if case["top1_match"]) / total if total else 0,
        "top3_rate": sum(1 for case in per_case if case["top3_match"]) / total if total else 0,
        "mono_top3": sum(1 for case in mono_cases if case["top3_match"]),
        "mono_total": len(mono_cases),
        "poly_top3": sum(1 for case in poly_cases if case["top3_match"]),
        "poly_total": len(poly_cases),
        "per_case": per_case,
    }


async def main(args) -> None:
    configured = load_split(args.config, args.seed)
    output_dir = make_output_dir(configured.config, "single", "icl", args.model, args.seed, configured.tag)
    predictor_template = load_rendered_prompt("single", "predictor", configured.config)
    icl_block, train_examples = build_icl_examples(
        configured.train_cases,
        configured.gt_data,
        args.train_limit,
        args.max_record_chars,
    )
    predictor_prompt = build_predictor_prompt(predictor_template, icl_block)

    eval_cases = configured.test_cases if args.split == "test" else configured.eval_cases
    if args.limit:
        eval_cases = eval_cases[:args.limit]

    print_header("MANANA ICL ABLATION", [
        ("Config:", args.config),
        ("Split:", args.split),
        ("Train ex:", str(len(train_examples))),
        ("Eval cases:", str(len(eval_cases))),
        ("Prompt chars:", str(len(predictor_prompt))),
        ("Output:", output_dir),
    ])

    client = LLMClient(model=args.model, max_concurrency=args.concurrency)
    try:
        tasks = [run_case(client, predictor_prompt, case, configured.gt_data, args.temp) for case in eval_cases]
        results = await asyncio.gather(*tasks)
    finally:
        await client.close()

    per_case = [result for result in results if result is not None]
    eval_summary = summarize(per_case)
    write_json(os.path.join(output_dir, "train_examples.json"), train_examples)
    write_json(os.path.join(output_dir, "predictions.json"), per_case)
    write_json(os.path.join(output_dir, "eval.json"), eval_summary)
    print(f"  [Eval] {summarize_eval(eval_summary)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Manana ICL ablation.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--split", choices=["eval", "test"], default="eval")
    parser.add_argument("--train-limit", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-record-chars", type=int, default=2500)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--temp", type=float, default=None)
    asyncio.run(main(parser.parse_args()))
