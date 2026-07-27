# MediShield — Evaluation Results

_Generated 2026-07-27 16:46_

## Summary

| Metric | Rubric weight | Score |
|---|---|---|
| Classification accuracy | 20% | **95.9%** (116/121) |
| Extraction completeness | 20% | **96.7%** (claim fields present) |
| — CPT code recall | — | 100.0% |
| Policy coverage accuracy | 15% | **100.0%** |
| Decision correctness | 25% | **62.5%** (15/24) |

## Decision confusion matrix

Rows = expected, columns = predicted.

| expected ↓ / got → | APPROVE | REJECT | ESCALATE |
|---|---|---|---|
| APPROVE | 3 | 3 | 0 |
| REJECT | 1 | 7 | 2 |
| ESCALATE | 0 | 3 | 5 |

## Classification confusion (nonzero cells)

| expected | predicted | count |
|---|---|---|
| CLAIM_FORM | CLAIM_FORM | 25 |
| DISCHARGE_SUMMARY | DISCHARGE_SUMMARY | 24 |
| ID_DOCUMENT | ID_DOCUMENT | 19 |
| ID_DOCUMENT | UNKNOWN  ⟵ miss | 5 |
| POLICY_AMENDMENT | POLICY_AMENDMENT | 24 |
| PRESCRIPTION | PRESCRIPTION | 24 |

## Per-case decisions

| case | expected | got | ok | fraud | notes |
|---|---|---|---|---|---|
| C_001 | ESCALATE | ESCALATE | ✅ | 0.8 | readmission_30d |
| C_002 | ESCALATE | ESCALATE | ✅ | 0.8 | date_conflict |
| C_003 | ESCALATE | ESCALATE | ✅ | 0.85 | proc_diag_mismatch |
| C_004 | ESCALATE | ESCALATE | ✅ | 0.8 | amount_under_10k |
| C_005 | ESCALATE | ESCALATE | ✅ | 0.85 | duplicate_claim |
| C_006 | ESCALATE | REJECT | ❌ | 0.0 | name_mismatch |
| C_007 | REJECT | REJECT | ✅ | 0.0 | uncovered_procedure |
| C_008 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_009 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_010 | REJECT | REJECT | ✅ | 0.0 | expired_id |
| C_011 | REJECT | REJECT | ✅ | 0.0 | expired_id |
| C_012 | REJECT | ESCALATE | ❌ | 0.8 | uncovered_procedure |
| C_013 | ESCALATE | REJECT | ❌ | 0.0 | tampered_id |
| C_014 | REJECT | APPROVE | ❌ | 0.0 | expired_id |
| C_015 | REJECT | REJECT | ✅ | 0.0 | uncovered_procedure |
| C_016 | APPROVE | REJECT | ❌ | 0.0 | expiring_soon_id |
| C_017 | APPROVE | APPROVE | ✅ | 0.0 | clean |
| C_018 | ESCALATE | REJECT | ❌ | 0.0 | tampered_id |
| C_019 | APPROVE | APPROVE | ✅ | 0.0 | clean |
| C_020 | REJECT | ESCALATE | ❌ | 0.8 | uncovered_procedure |
| C_021 | APPROVE | REJECT | ❌ | 0.0 | expiring_soon_id |
| C_022 | APPROVE | REJECT | ❌ | 0.0 | expiring_soon_id |
| C_023 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_024 | APPROVE | APPROVE | ✅ | 0.0 | expiring_soon_id |
