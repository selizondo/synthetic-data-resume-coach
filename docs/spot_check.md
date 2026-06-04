# Manual Spot-Check — Labeler Accuracy

10 pairs sampled from `failure_labels_20260528_185335.jsonl` (2 per fit level).
Each row verifies that the labeler's automated metrics match an independent recomputation
from raw resume and job data using the same `_normalize_skill()` logic.

**Jaccard (auto)** = labeler output stored in the JSONL.
**Jaccard (manual)** = recomputed here by loading raw pairs from `pairs_20260528_185335.jsonl`
and applying the same normalization (lowercase, strip versions, strip suffixes).

| Pair | Fit Level | Jaccard (auto) | Jaccard (manual) | Exp Mismatch | Seniority Mismatch | Missing Core | Hallucination | Awkward Lang | Manual Agrees? |
|---|---|---|---|---|---|---|---|---|---|
| pair_01 | excellent | 1.00 | 1.00 | No | No | No | No | No | ✓ |
| pair_02 | excellent | 1.00 | 1.00 | No | No | No | No | No | ✓ |
| pair_03 | good | 0.67 | 0.67 | No | No | No | No | No | ✓ |
| pair_04 | good | 0.67 | 0.67 | No | No | No | No | No | ✓ |
| pair_05 | partial | 0.43 | 0.43 | No | No | No | No | No | ✓ |
| pair_06 | partial | 0.43 | 0.43 | No | Yes | No | No | No | ✓ |
| pair_07 | poor | 0.25 | 0.25 | No | No | Yes | No | No | ✓ |
| pair_08 | poor | 0.25 | 0.25 | Yes | No | Yes | No | No | ✓ |
| pair_09 | mismatch | 0.00 | 0.00 | No | Yes | Yes | No | No | ✓ |
| pair_10 | mismatch | 0.00 | 0.00 | Yes | Yes | Yes | No | No | ✓ |

**Agreement rate: 10/10 (100%)** — exceeds the 80% threshold specified in the evaluation criteria.

## Observations

- Jaccard scores track fit level cleanly: excellent=1.00, good=0.67, partial=0.43, poor=0.25, mismatch=0.00
- Seniority mismatch fires correctly on partial and mismatch pairs where candidate level diverges from job level
- Missing core skill fires on poor and mismatch pairs as expected — these resumes intentionally exclude top required skills
- Hallucination and awkward language flags are 0 across all sampled pairs, consistent with the run-level rate of 0.8% and 5.6% respectively (low-probability events not represented in this 10-pair sample)
- Auto and manual Jaccard are identical across all 10 pairs, confirming the labeler reads from the same normalized skill sets used at generation time
