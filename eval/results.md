# MediShield — Evaluation Results

_Generated 2026-07-22 15:46_

## Summary

| Metric | Rubric weight | Score |
|---|---|---|
| Classification accuracy | 20% | **96.8%** (150/155) |
| Extraction completeness | 20% | **96.7%** (claim fields present) |
| — CPT code recall | — | 100.0% |
| Policy coverage accuracy | 15% | **100.0%** |
| Decision correctness | 25% | **61.8%** (21/34) |

## Decision confusion matrix

Rows = expected, columns = predicted.

| expected ↓ / got → | APPROVE | REJECT | ESCALATE |
|---|---|---|---|
| APPROVE | 1 | 1 | 5 |
| REJECT | 0 | 9 | 5 |
| ESCALATE | 2 | 0 | 11 |

## Classification confusion (nonzero cells)

| expected | predicted | count |
|---|---|---|
| CLAIM_FORM | CLAIM_FORM | 31 |
| DISCHARGE_SUMMARY | DISCHARGE_SUMMARY | 30 |
| ID_DOCUMENT | ID_DOCUMENT | 25 |
| ID_DOCUMENT | UNKNOWN  ⟵ miss | 5 |
| POLICY_AMENDMENT | POLICY_AMENDMENT | 30 |
| PRESCRIPTION | PRESCRIPTION | 30 |
| UNKNOWN | UNKNOWN | 4 |

## Per-case decisions

| case | expected | got | ok | fraud | notes |
|---|---|---|---|---|---|
| C_001 | ESCALATE | ESCALATE | ✅ | 0.8 | readmission_30d |
| C_002 | ESCALATE | ESCALATE | ✅ | 0.8 | date_conflict |
| C_003 | ESCALATE | ESCALATE | ✅ | 0.85 | proc_diag_mismatch |
| C_004 | ESCALATE | ESCALATE | ✅ | 0.8 | amount_under_10k |
| C_005 | ESCALATE | ESCALATE | ✅ | 0.85 | duplicate_claim |
| C_006 | ESCALATE | APPROVE | ❌ | 0.0 | name_mismatch |
| C_007 | REJECT | REJECT | ✅ | 0.0 | uncovered_procedure |
| C_008 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_009 | REJECT | ESCALATE | ❌ | 0.0 | missing_fields |
| C_010 | REJECT | ESCALATE | ❌ | 0.0 | expired_id |
| C_011 | REJECT | REJECT | ✅ | 0.0 | expired_id |
| C_012 | REJECT | ESCALATE | ❌ | 0.8 | uncovered_procedure |
| C_013 | ESCALATE | APPROVE | ❌ | 0.0 | tampered_id |
| C_014 | REJECT | ESCALATE | ❌ | 0.0 | expired_id |
| C_015 | REJECT | REJECT | ✅ | 0.0 | uncovered_procedure |
| C_016 | APPROVE | ESCALATE | ❌ | 0.8 | expiring_soon_id |
| C_017 | APPROVE | APPROVE | ✅ | 0.0 | clean |
| C_018 | ESCALATE | ESCALATE | ✅ | 0.0 | tampered_id |
| C_019 | APPROVE | ESCALATE | ❌ | 0.0 | clean |
| C_020 | REJECT | ESCALATE | ❌ | 0.0 | uncovered_procedure |
| C_021 | APPROVE | REJECT | ❌ | 0.0 | expiring_soon_id |
| C_022 | APPROVE | ESCALATE | ❌ | 0.0 | expiring_soon_id |
| C_023 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_024 | APPROVE | ESCALATE | ❌ | 0.0 | expiring_soon_id |
| C_025 | REJECT | REJECT | ✅ | 0.0 | uncovered_procedure |
| C_026 | APPROVE | ESCALATE | ❌ | 0.0 | expiring_soon_id |
| C_027 | REJECT | REJECT | ✅ | 0.0 | missing_fields |
| C_028 | REJECT | REJECT | ✅ | 0.0 | expired_id |
| C_029 | ESCALATE | ESCALATE | ✅ | 0.0 | tampered_id |
| C_030 | REJECT | REJECT | ✅ | 0.0 | expired_id |
| unknown_blurry_scan_001 | ESCALATE | ESCALATE | ✅ | 0.0 | unknown |
| unknown_bank_statement_001 | ESCALATE | ESCALATE | ✅ | 0.0 | unknown |
| unknown_utility_bill_001 | ESCALATE | ESCALATE | ✅ | 0.0 | unknown |
| unknown_blank_scan_001 | ESCALATE | ESCALATE | ✅ | 0.0 | unknown |
