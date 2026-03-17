"""
Drug prediction using clean leak-free inputs.

Input is built on the fly from:
  - raw_text/split_results.json  (per-visit clinical notes)
  - raw_text/clean_output.json   (per-visit clean prescriptions)
  - data/combined_dataset.csv    (demographics)

System prompt: raw_text/predict_prompt.txt (7-stage reasoning pipeline)

Output: raw_text/drug/{model}_v{N}_options.json  +  matching .csv
"""

import os
import re
import json
import asyncio
import random
import aiohttp
import pandas as pd
from tqdm import tqdm
import dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
dotenv.load_dotenv(os.path.join(_HERE, '.env'))

# ============ CONFIGURATION ============
model      = 'openai/gpt-oss-120b'
visit_num  = 1          # 1, 2, or 3
thinking_budget = 6000
max_tokens      = 16000
max_concurrency = 8
limit_patients  = None  # int for debugging, None for all
# ========================================

DRUG_COLUMNS   = [
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
]
ALLOWED_ACTIONS = {"continue", "start", "stop"}

VISIT_LABELS = {
    "Visit_1": "Visit 1 (0 months)",
    "Visit_2": "Visit 2 (6 months)",
    "Visit_3": "Visit 3 (12 months)",
}


# ── Provider routing ──────────────────────────────────────────────────────────

def get_provider(model_name: str) -> str:
    m = model_name.lower()
    if m.startswith("claude"):
        return "anthropic"
    if any(m.startswith(p) for p in ("gpt-", "o1", "o3", "o4", "text-")):
        return "openai"
    return "together"


def get_short_model_name(model_name: str) -> str:
    name = model_name.replace("/", "_").replace("-", "").replace(".", "")
    return name[:20] if len(name) > 20 else name


# ── Input builder (no LLM) ───────────────────────────────────────────────────

def safe_get(row, col):
    val = row.get(col, '')
    s = str(val).strip()
    return s if s and s.lower() != 'nan' else ''


def build_patient_header(row) -> str:
    age   = safe_get(row, 'Age')
    sex   = safe_get(row, 'Sex:')
    dx    = safe_get(row, 'Seizure Diagnosis')
    onset = safe_get(row, 'Age of onset of seizure')
    dur   = safe_get(row, 'Duration of Seizure')

    parts = ["For this patient, here is what you have:\n"]
    demo = " | ".join(x for x in [
        f"Age: {age}"         if age   else "",
        f"Sex: {sex}"         if sex   else "",
        f"Diagnosis: {dx}"    if dx    else "",
    ] if x)
    if demo:
        parts.append(demo)
    detail = " | ".join(x for x in [
        f"Seizure onset: {onset}" if onset else "",
        f"Seizure duration: {dur}" if dur   else "",
    ] if x)
    if detail:
        parts.append(detail)
    return "\n".join(parts)


def build_visit_block(label: str, input_text: str, prescription: str = None) -> str:
    lines = [f"[{label} - Clinical Notes]"]
    lines.append(input_text.strip() if input_text.strip() else "(no clinical notes recorded)")
    if prescription is not None:
        lines.append(f"\n[{label} - Prescription]")
        lines.append(prescription.strip() if prescription.strip() else "(no prescription recorded)")
    return "\n".join(lines)


def build_input(pid: str, visit_name: str, split_results: dict,
                clean_output: dict, pid_to_row: dict) -> str:
    visit_order = ["Visit_1", "Visit_2", "Visit_3"]
    current_idx = visit_order.index(visit_name)

    row = pid_to_row.get(pid)
    header = build_patient_header(row) if row is not None else "For this patient, here is what you have:\n"

    blocks = [header, ""]

    for prev in visit_order[:current_idx]:
        label = VISIT_LABELS[prev]
        inp  = split_results[pid].get(prev, {}).get("input_text", "")
        pres = clean_output.get(pid, {}).get(prev, "")
        blocks.append(build_visit_block(label, inp, prescription=pres))
        blocks.append("")

    label = VISIT_LABELS[visit_name]
    inp = split_results[pid].get(visit_name, {}).get("input_text", "")
    blocks.append(build_visit_block(label, inp, prescription=None))

    return "\n".join(blocks).strip()


# ── Output parsing ────────────────────────────────────────────────────────────

def parse_options(content: str) -> dict:
    sec2 = re.search(r'---\s*SECTION\s*2.*?---\s*(.*?)$', content, re.DOTALL | re.IGNORECASE)
    section_text = sec2.group(1).strip() if sec2 else content

    options = {}
    block_pattern = re.compile(
        r'Option\s+(\d)\s*:\s*(.+?)(?=Option\s+\d\s*:|$)',
        re.DOTALL | re.IGNORECASE,
    )
    for m in block_pattern.finditer(section_text):
        num = int(m.group(1))
        if num not in (1, 2, 3):
            continue
        block_lines = m.group(2).strip().split('\n')
        label = block_lines[0].strip() if block_lines else ""
        drugs, rationale_parts, in_rationale = [], [], False

        for line in block_lines[1:]:
            s = line.strip()
            if not s:
                continue
            rat = re.match(r'Rationale\s*:\s*(.*)', s, re.IGNORECASE)
            if rat:
                in_rationale = True
                rationale_parts.append(rat.group(1).strip())
                continue
            if in_rationale:
                rationale_parts.append(s)
                continue
            dm = re.match(r'-\s*(\w+)\s*:\s*(\w+)', s)
            if dm:
                drug   = dm.group(1).lower()
                action = dm.group(2).lower()
                if drug in DRUG_COLUMNS and action in ALLOWED_ACTIONS:
                    drugs.append({"drug": drug, "action": action})

        options[f"option_{num}"] = {
            "label": label,
            "drugs": drugs,
            "rationale": " ".join(rationale_parts),
        }
    return options


def parse_structured(thinking: str, content: str) -> dict:
    reasoning = ""
    sec1 = re.search(
        r'---\s*SECTION\s*1.*?---\s*(.*?)(?=---\s*SECTION\s*2|$)',
        content, re.DOTALL | re.IGNORECASE,
    )
    if sec1:
        reasoning = sec1.group(1).strip()
    options = parse_options(content)
    return {"think": thinking, "reasoning": reasoning, "raw_content": content, **options}


def format_drugs_str(drugs: list) -> str:
    return "; ".join(f"{d['drug']}:{d['action']}" for d in drugs)


# ── Async API call ────────────────────────────────────────────────────────────

async def call_api_with_retries(
    session: aiohttp.ClientSession,
    api_key: str,
    system_prompt: str,
    user_content: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 6,
) -> tuple:
    provider = get_provider(model)

    async def _one_call():
        if provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
                "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
            }
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"{resp.status}: {await resp.text()}")
                data = await resp.json()
            reasoning, content = "", ""
            for block in data.get("content", []):
                if block.get("type") == "thinking":
                    reasoning = block.get("thinking", "")
                elif block.get("type") == "text":
                    content = block.get("text", "")
            return reasoning.strip(), content.strip()

        elif provider == "openai":
            url = "https://api.openai.com/v1/responses"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "max_output_tokens": max_tokens,
            }
            if any(model.lower().startswith(p) for p in ("gpt-5", "o1", "o3", "o4")):
                payload["reasoning"] = {"effort": "none", "summary": "auto"}
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"{resp.status}: {await resp.text()}")
                data = await resp.json()
            reasoning, content = "", ""
            for item in data.get("output", []):
                if item.get("type") == "reasoning":
                    reasoning = " ".join(s.get("text", "") for s in item.get("summary", [])).strip()
                elif item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "output_text":
                            content = block.get("text", "").strip()
            return reasoning, content

        else:  # together
            url = "https://api.together.xyz/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": max_tokens,
                "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
            }
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"{resp.status}: {await resp.text()}")
                data = await resp.json()
            msg = data["choices"][0]["message"]
            return (msg.get("reasoning") or "").strip(), (msg.get("content") or "").strip()

    for attempt in range(max_retries):
        try:
            async with semaphore:
                return await _one_call()
        except Exception as e:
            msg = str(e).lower()
            retryable = any(s in msg for s in [
                "rate", "429", "timeout", "temporar", "overload", "503", "502", "500", "connection"
            ])
            if not retryable or attempt == max_retries - 1:
                print(f"[ERROR] {e}")
                return "", ""
            await asyncio.sleep(0.8 * (2 ** attempt) + random.random() * 0.3)
    return "", ""


# ── Main ──────────────────────────────────────────────────────────────────────

async def main_async():
    provider = get_provider(model)
    key_map = {
        "together":  "TOGETHER_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "anthropic": "CLAUDE_API_KEY",
    }
    api_key = os.getenv(key_map[provider])
    if not api_key:
        print(f"Error: {key_map[provider]} not found")
        return

    # Load data
    with open(os.path.join(_HERE, 'split_results.json'), encoding='utf-8') as f:
        split_results = json.load(f)
    with open(os.path.join(_HERE, 'clean_output.json'), encoding='utf-8') as f:
        clean_output = json.load(f)

    df = pd.read_csv(
        os.path.join(_ROOT, 'data', 'combined_dataset.csv'),
        sep=';', engine='python', quotechar='"', doublequote=True, escapechar='\\',
    )
    df = df.drop_duplicates(subset=[
        'Name: ', 'Date of visit(0 months)',
        'Date of visit(6 months)', 'Date of visit(12 months)'
    ])

    def get_pid(row):
        rid  = str(row.get('Record ID', '')).strip() if pd.notna(row.get('Record ID')) else ''
        name = str(row.get('Name: ', '')).strip()     if pd.notna(row.get('Name: '))    else ''
        return f"{rid}_{name}" if rid and name else name or rid

    pid_to_row = {get_pid(row): row for _, row in df.iterrows()}

    with open(os.path.join(_HERE, 'predict_prompt.txt'), encoding='utf-8') as f:
        system_prompt = f.read()

    visit_name = f"Visit_{visit_num}"
    patient_ids = list(split_results.keys())
    if limit_patients:
        patient_ids = patient_ids[:limit_patients]

    # Build tasks (input construction — no LLM)
    tasks = [
        (pid, build_input(pid, visit_name, split_results, clean_output, pid_to_row))
        for pid in patient_ids
        if split_results[pid].get(visit_name, {}).get("input_text", "").strip()
    ]

    # Output paths
    short_name  = get_short_model_name(model)
    output_dir  = os.path.join(_HERE, 'drug')
    os.makedirs(output_dir, exist_ok=True)
    output_json = os.path.join(output_dir, f"{short_name}_v{visit_num}_options.json")
    output_csv  = output_json.replace('.json', '.csv')

    print(f"\n{'='*60}")
    print(f"DRUG PREDICTION — CLEAN PIPELINE")
    print(f"{'='*60}")
    print(f"Model:      {model}  ({provider})")
    print(f"Visit:      {visit_num}")
    print(f"Patients:   {len(tasks)}")
    print(f"Output:     {output_json}")
    print(f"{'='*60}\n")

    # Run inference
    semaphore = asyncio.Semaphore(max_concurrency)
    results   = {}
    pbar      = tqdm(total=len(tasks), desc="Predicting", unit="patient")

    async def _run_one(pid, user_content, session):
        r, c = await call_api_with_retries(session, api_key, system_prompt, user_content, semaphore)
        return pid, r, c

    async with aiohttp.ClientSession() as session:
        for coro in asyncio.as_completed([_run_one(pid, uc, session) for pid, uc in tasks]):
            pid, reasoning, content = await coro
            results[pid] = (reasoning, content)
            pbar.update(1)

    pbar.close()

    # Parse and save
    ordered, parsed_rows, n_failed = {}, [], 0
    for pid, _ in tasks:
        thinking, content = results.get(pid, ("", ""))
        structured = parse_structured(thinking, content)
        ordered[pid] = structured

        row = {'patient_id': pid}
        for n in [1, 2, 3]:
            opt = structured.get(f"option_{n}", {})
            row[f"option_{n}_label"]     = opt.get("label", "")
            row[f"option_{n}_drugs"]     = format_drugs_str(opt.get("drugs", []))
            row[f"option_{n}_rationale"] = opt.get("rationale", "")
        parsed_rows.append(row)

        if not any(structured.get(f"option_{n}") for n in [1, 2, 3]):
            n_failed += 1

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)

    csv_cols = [
        'patient_id',
        'option_1_label', 'option_1_drugs', 'option_1_rationale',
        'option_2_label', 'option_2_drugs', 'option_2_rationale',
        'option_3_label', 'option_3_drugs', 'option_3_rationale',
    ]
    pd.DataFrame(parsed_rows, columns=csv_cols).to_csv(output_csv, index=False)

    print(f"\n{'='*60}")
    print(f"DONE!  {len(results)} patients saved.")
    print(f"  JSON: {output_json}")
    print(f"  CSV:  {output_csv}")
    if n_failed:
        print(f"  Warning: {n_failed} patients had no options parsed")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main_async())
