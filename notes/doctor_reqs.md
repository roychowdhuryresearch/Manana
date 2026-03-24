# Doctor Requirements — Raj & JP

## 2026-03-23

### Must-have

**1. Trace evaluation (blinded comparison)**
- 40 cases (20 per dataset)
- For each case they see:
  - Patient clinical notes
  - Output A: multi-agent reasoning trace + prescription
  - Output B: single-agent reasoning + prescription
  - Ground truth prescription (what was actually prescribed)
  - A and B are randomly assigned (blinded)
- Rate each output on:
  - Clinical accuracy (1-5): is the prescription appropriate?
  - Reasoning quality (1-5): is the reasoning sound and complete?
  - Actionability (1-5): would you trust this as decision support?
  - Preference: A or B (forced choice)
- Both Raj and JP review all 40 cases (for inter-rater reliability)

**2. Disagreement adjudication**
- 30-50 cases where our system disagrees with ground truth prescription
- For each: who was right? Options:
  - System was more appropriate
  - Original doctor was more appropriate
  - Both reasonable alternatives
  - Both inappropriate
- Addresses "ground truth is imperfect" — may show system sometimes outperforms the original prescriber

### Should-have

**3. Error category validation**
- We have 7 failure categories from their original 120 reviews:
  1. Seizure type/syndrome misclassification
  2. Weight-based dosing errors in children
  3. Drug-seizure type contraindications
  4. De-escalating working regimens
  5. Missing infectious etiologies
  6. Ignoring drug availability constraints
  7. Drug-drug interactions
- Confirm: are these the right categories? Any missing?
- For 20-30 cases where the system catches an error: does the doctor agree it's a real error?

**4. Inter-rater reliability**
- Both Raj and JP independently rate the same 40 trace cases (item 1 above)
- We compute Cohen's kappa for agreement
- Standard requirement for clinical evaluation papers

### Nice-to-have

**5. Retrospective outcome review**
- 10-15 cases where system disagrees with GT AND the next visit suggests the system may have been right (e.g., doctor switched drugs, patient got worse, then switched back)
- Have them judge: was the system's alternative clinically superior?

**6. Safety sign-off**
- Review any cases where the system prescribed a known dangerous combination
- Brief statement: "We reviewed X flagged cases and found no clinically dangerous prescriptions"

### Logistics

- **Total cases per doctor: ~60** (40 trace comparisons + 20 disagreement adjudications)
- **Format: spreadsheet** — one row per case, columns for patient summary, Output A, Output B, GT, rating columns
- **Estimated time: 3-4 hours each**
- **Both doctors review same 40 trace cases** (inter-rater reliability)
- **Disagreement cases can be split** between them (20 each, different cases)
- Item 1 (trace evaluation) is the highest priority — if we can only get one thing, it's this
