"""LLM-based conflict detection between Phase 1 agents.

Reads Phase 1 agent outputs and uses an LLM to classify conflicts
into severity tiers (0-3). Tests whether conflict tier predicts
prediction errors.

Usage:
    uv run python -m consilium.analysis.conflict_detection \
        --predictions outputs/v2/consilium_v2_openai.gptoss120b1:0_v1_d0.json \
        --visit 1 --cohort A --limit 10
"""

import argparse
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from lib.llm import LLMClient
from consilium.loader import load_ground_truth


CONFLICT_SYSTEM_PROMPT = """You are an expert clinical reasoning analyst. You will be given the outputs of multiple specialist agents who independently assessed the same epilepsy patient case. Your job is to identify conflicts between their assessments that affect the drug selection decision.

Focus on conflicts that affect which drugs should be prescribed. A disagreement about seizure classification is only significant if it implies different drug choices. If both interpretations lead to the same drug, it is not a meaningful conflict.

Classify the overall conflict severity into one of four tiers:

TIER 0 (Consensus): All agents are compatible. No agent's advice constrains or complicates another's. The synthesizer can adopt all advice without trade-offs.

TIER 1 (Non-Blocking Tension): Agents emphasize different priorities but their advice can co-exist. The synthesizer can satisfy all agents by choosing appropriately. No agent's core recommendation is rejected.

TIER 2 (Recommendation Conflict): One agent's recommendation is directly invalidated by another's assessment — typically a drug is recommended by one agent but flagged as unavailable, unsafe, or contraindicated by another. The synthesizer must discard one agent's primary advice.

TIER 3 (Foundation Gridlock): Agents disagree on base clinical facts (seizure type, treatment response, diagnosis) in a way that implies different drug choices. The correct treatment depends on which agent's factual assessment is right.

Respond with ONLY valid JSON in this exact format:
{
  "conflicts": [
    {
      "agents": ["agent1", "agent2"],
      "description": "Brief description of the conflict",
      "drugs_in_conflict": ["drug1", "drug2"]
    }
  ],
  "resolution_tier": 0,
  "tier_justification": "One sentence explaining why this tier was chosen."
}

If there are no conflicts, return an empty conflicts list with tier 0."""


def build_user_prompt(phase1: dict) -> str:
    """Build the user prompt from Phase 1 agent outputs."""
    parts = ["Here are the specialist agent assessments for this patient:\n"]
    for agent_name, output in phase1.items():
        if isinstance(output, str) and output.strip():
            parts.append(f"=== {agent_name.upper()} ===")
            parts.append(output.strip())
            parts.append("")
    return "\n".join(parts)


def drugs_from_option(option: dict) -> set[str]:
    drugs = option.get("drugs", {})
    if isinstance(drugs, list):
        return set(d["drug"].lower() for d in drugs if d.get("action") in ("continue", "start"))
    return set(drug.lower() for drug, action in drugs.items() if action in ("continue", "start"))


async def run_conflict_detection(predictions: dict, gt: dict, visit: int, limit: int | None = None):
    """Run conflict detection on predictions."""
    client = LLMClient()

    patient_ids = list(predictions.keys())
    if limit:
        patient_ids = patient_ids[:limit]

    results = []

    for i, pid in enumerate(patient_ids):
        rec = predictions[pid]
        phase1 = rec.get("phase1", {})

        if not phase1:
            continue

        user_prompt = build_user_prompt(phase1)

        print(f"[{i+1}/{len(patient_ids)}] Processing {pid}...", end=" ", flush=True)

        _, response = await client.call(
            CONFLICT_SYSTEM_PROMPT,
            user_prompt,
            temperature=0,
        )

        # Parse JSON response
        conflict_data = None
        try:
            # Try to extract JSON from response
            response_clean = response.strip()
            if response_clean.startswith("```"):
                response_clean = response_clean.split("```")[1]
                if response_clean.startswith("json"):
                    response_clean = response_clean[4:]
            conflict_data = json.loads(response_clean)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    conflict_data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        if conflict_data is None:
            print(f"FAILED to parse JSON")
            conflict_data = {"conflicts": [], "resolution_tier": -1, "tier_justification": "Parse error"}

        # Get correctness
        final = rec.get("final_regimen", {})
        options = []
        for key in ["option_1", "option_2", "option_3"]:
            if key in final:
                options.append(drugs_from_option(final[key]))

        gt_key = None
        for k in gt.keys():
            if pid.split("_", 1)[-1] in k and k.endswith(f"__v{visit}"):
                gt_key = k
                break

        gt_drugs = set()
        if gt_key and gt.get(gt_key, {}).get("prescribed"):
            gt_drugs = set(d.lower() for d in gt[gt_key]["prescribed"])

        em = any(o == gt_drugs for o in options) if gt_drugs else None

        tier = conflict_data.get("resolution_tier", -1)
        n_conflicts = len(conflict_data.get("conflicts", []))

        print(f"Tier {tier}, {n_conflicts} conflicts, EM={em}")

        results.append({
            "pid": pid,
            "tier": tier,
            "n_conflicts": n_conflicts,
            "conflicts": conflict_data.get("conflicts", []),
            "tier_justification": conflict_data.get("tier_justification", ""),
            "exact_match": em,
            "gt_drugs": sorted(gt_drugs) if gt_drugs else [],
            "pred_drugs_opt1": sorted(options[0]) if options else [],
        })

    await client.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="LLM-based conflict detection")
    parser.add_argument("--predictions", type=str, required=True)
    parser.add_argument("--visit", type=int, required=True)
    parser.add_argument("--cohort", type=str, choices=["A", "B"], default="A")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N patients")
    args = parser.parse_args()

    with open(args.predictions, encoding="utf-8") as f:
        predictions = json.load(f)

    gt = load_ground_truth(visit_num=args.visit, cohort=args.cohort)

    results = asyncio.run(run_conflict_detection(predictions, gt, args.visit, args.limit))

    # --- Analysis ---
    valid = [r for r in results if r["exact_match"] is not None and r["tier"] >= 0]

    if not valid:
        print("No valid results.")
        return

    print(f"\n{'='*60}")
    print(f"CONFLICT DETECTION — Visit {args.visit}, Cohort {args.cohort.upper()}")
    print(f"{'='*60}")
    print(f"  Patients analyzed: {len(valid)}")

    # Tier distribution
    from collections import Counter
    tier_counts = Counter(r["tier"] for r in valid)
    print(f"\n  Tier distribution:")
    for t in range(4):
        n = tier_counts.get(t, 0)
        if n > 0:
            em_rate = sum(r["exact_match"] for r in valid if r["tier"] == t) / n
            print(f"    Tier {t}: {n:3d} cases  EM={em_rate:.1%}")

    # Conflict count vs accuracy
    print(f"\n  Accuracy by conflict count:")
    conflict_counts = Counter(r["n_conflicts"] for r in valid)
    for nc in sorted(conflict_counts.keys()):
        subset = [r for r in valid if r["n_conflicts"] == nc]
        em_rate = sum(r["exact_match"] for r in subset) / len(subset)
        print(f"    {nc} conflicts: {len(subset):3d} cases  EM={em_rate:.1%}")

    # Show individual conflicts
    print(f"\n  Sample conflicts:")
    for r in valid[:5]:
        print(f"\n    Patient: {r['pid']} | Tier {r['tier']} | EM={r['exact_match']}")
        for c in r["conflicts"][:3]:
            print(f"      {c['agents']}: {c['description']}")
        print(f"      Justification: {r['tier_justification']}")

    # Save
    out_dir = os.path.join(_ROOT, "outputs", "analysis")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"conflicts_v{args.visit}_{args.cohort}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
