# ComplianceOS — Evaluation & Metrics

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §7

---

## 1. Purpose

Test extraction accuracy, missed obligations, false alerts, citation correctness,
and whether regulatory changes are detected in time. Every evaluation runs in CI
as a regression gate.

## 2. Golden dataset

Stored in `tests/compliance/golden/` as versioned JSON files:

```json
{
  "regulation": {
    "citation": "CFPB Reg Z 1026.17",
    "title": "Disclosure of Credit Terms",
    "jurisdiction": "US-FEDERAL",
    "source_url": "https://www.ecfr.gov/...",
    "text": "Full regulatory text..."
  },
  "expected_obligations": [
    {
      "normalized_text": "Creditors must disclose APR and finance charges",
      "applicability": "CONFIRMED",
      "citation_chunks": [0, 1, 2],
      "responsible_entity": "lending"
    }
  ],
  "expected_findings": [],
  "notes": "Standard Reg Z disclosure requirements"
}
```

## 3. Metrics

| Metric | Target | Measured by | Phase |
|---|---|---|---|
| Obligation extraction precision | ≥ 0.90 | Golden dataset | 2 |
| Obligation extraction recall | ≥ 0.85 | Golden dataset | 2 |
| Citation correctness | 100% | Every citation resolves to exact source text | 2 |
| False-positive rate | < 10% | Reviewed obligations vs confirmed | 2 |
| Missed renewal rate | 0% | Simulated 90-day run | 1 |
| Time to identify a regulatory change | < 24h | `regulation_versions.ingested_at − publication_date` | 2 |
| Time to prepare an audit package | < 2h | Package generation timestamp delta | 3 |
| Manual hours eliminated | Baseline-relative | Time-tracking study | 3 |

## 4. Evaluation harness

```
tests/compliance/
├── golden/
│   ├── reg_z_1026_17.json
│   ├── ca_mtl_renewal.json
│   └── ...
├── test_extraction.py       # precision/recall on golden dataset
├── test_citation.py         # citation resolves to exact text
├── test_deadline.py         # deadline computation golden tests
├── test_severity.py         # severity assignment golden tests
└── conftest.py              # golden dataset fixtures
```

### 4.1 Extraction evaluation

```python
def test_obligation_extraction_precision():
    for golden in load_golden_dataset():
        result = obligation_mapping_agent.run(golden.regulation)
        predicted = set(result.obligations)
        expected = set(golden.expected_obligations)
        precision = len(predicted & expected) / len(predicted) if predicted else 1.0
        assert precision >= 0.90, f"Precision {precision} < 0.90 for {golden.citation}"
```

### 4.2 Citation correctness

```python
def test_citation_resolves():
    for golden in load_golden_dataset():
        result = obligation_mapping_agent.run(golden.regulation)
        for obligation in result.obligations:
            for chunk_id in obligation.citation_chunk_ids:
                chunk = get_chunk(chunk_id)
                assert obligation.normalized_text in chunk.text or \
                       chunk.text in obligation.normalized_text, \
                    f"Citation {chunk_id} does not support obligation"
```

### 4.3 CI integration

```yaml
# .github/workflows/compliance-eval.yml
- name: Run compliance evaluation
  run: uv run pytest tests/compliance/ --json-report
- name: Check metrics
  run: uv run python scripts/check_eval_metrics.py --threshold precision=0.90,recall=0.85
```

Regression gate: if any metric drops below threshold, CI fails.

## 5. Model quality assessment

### Phase 0 evaluation

Before building agents, evaluate free OpenRouter models on:
1. Obligation extraction accuracy (precision/recall on 10 regulations)
2. Citation quality (does the model produce resolvable citations?)
3. Structured output reliability (does it produce valid JSON consistently?)
4. Prompt-injection resistance (does it follow instructions when fed adversarial regulatory text?)

If free models are insufficient, document the cost tradeoff for paid models.

### Metrics to track per model

| Model | Precision | Recall | Citation % | JSON validity | Injection resistance |
|---|---|---|---|---|---|
| nvidia/nemotron-3.5-lightning:free | TBD | TBD | TBD | TBD | TBD |
| (other free models) | TBD | TBD | TBD | TBD | TBD |