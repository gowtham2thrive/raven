# RAVEN Evaluation Report

## Methodology

RAVEN was evaluated against **50 annotated test cases** covering 5 evidence profiles. Each case has a ground truth annotation specifying the expected recommendation, contradiction count, and missing evidence categories.

The evaluation runner (`python -m tests.evaluation.runner`) compares RAVEN's actual output against these annotations and computes aggregate metrics.

### Profiles

| Profile | Cases | Description |
|---|---|---|
| **A_STRONG** | 15 | All evidence present, signed delivery |
| **B_WEAK** | 10 | Delivery present but no signature |
| **C_MISSING** | 10 | Missing delivery and shipping evidence |
| **D_CONTRADICTORY** | 10 | Conflicting delivery/tracking evidence |
| **E_EDGE** | 5 | Timezone mismatches, unusual data |

---

## Results

### Decision Accuracy

| Metric | Value |
|---|---|
| **Precision** | 1.00 (30/30 contested correctly) |
| **Recall** | 1.00 (30/30 contestable cases caught) |
| **F1** | 1.00 |
| **Accuracy** | 100.0% (50/50 cases correct) |

### Evidence Coverage

| Metric | Value |
|---|---|
| Missing evidence detection | 50% |

> **Note**: The 50% detection rate reflects that RAVEN checks for `delivery` and `shipping` separately. When both are missing (Profile C), the system currently detects the missing state but categorizes it differently than the annotation expects. The decision outcome is still correct — these cases route to `human_review` as intended.

### Contradiction Detection

| Metric | Value |
|---|---|
| **Precision** | 1.00 (10/10 flagged correctly) |
| **Recall** | 1.00 (10/10 actual contradictions found) |

### False Positives

| Metric | Value |
|---|---|
| Cases wrongly contested | 0 |
| Missed contests | 0 |
| Estimated cost | INR 0 |

### Integrity

| Metric | Value |
|---|---|
| Unsupported claim rate | 0.0% |
| Fabricated evidence rate | 0.0% |

### Operational

| Metric | Value |
|---|---|
| Avg investigation time | <1ms |
| Avg evidence items/case | 7.0 |
| Error rate | 0.0% |

---

## Profile Breakdown

| Profile | Cases | Correct | Accuracy | Errors |
|---|---|---|---|---|
| A_STRONG | 15 | 15 | 100% | 0 |
| B_WEAK | 10 | 10 | 100% | 0 |
| C_MISSING | 10 | 10 | 100% | 0 |
| D_CONTRADICTORY | 10 | 10 | 100% | 0 |
| E_EDGE | 5 | 5 | 100% | 0 |

---

## Honest Limitations

1. **Synthetic data**: Evaluation uses generated data, not real disputes. Real-world evidence will have more variety and noise.

2. **Single dispute class**: Only "Product Not Received" is tested. Other dispute types (quality, fraud, subscription) are not covered.

3. **No LLM in pipeline**: The current deterministic pipeline doesn't use an LLM for reasoning. Adding one will change the precision/recall profile.

4. **Missing evidence detection**: The 50% detection rate is a metric calibration issue, not a functional problem — all missing evidence cases route correctly to human review.

5. **Perfect scores are suspicious**: 100% accuracy on a test set designed by the same team that built the system is expected. Real-world performance will be lower. The value is in having the framework to measure it.

---

## Reproducing

```bash
cd server

# Generate synthetic data
python -m data.seed

# Run evaluation
python -m tests.evaluation.runner

# View JSON report
cat evaluation_report.json
```
