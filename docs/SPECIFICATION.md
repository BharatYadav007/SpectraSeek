# SpectraSeek — baseline requirements and design

## Problem and scope
Network administrators and student researchers need to survey a known, authorized AP inventory efficiently. A fixed-budget manual survey wastes scans on locations with overlapping coverage. SpectraSeek recommends sites with high predicted marginal coverage. It does not locate people or devices outside an authorized inventory, infer physical AP positions, detect attacks, or optimize walking routes in this release.

## Requirements and traceability
| ID | Requirement / acceptance criterion | Design / implementation | Test |
|---|---|---|---|
| FR-01 | Collect approved AP visibility at a selected site; malformed or failed scan must not be accepted | Collector adapter, CLI scan | scanner_parser, scan_failure_not_negative |
| FR-02 | Persist one complete scan and its target outcomes atomically in PostgreSQL; reject duplicate site/session | SurveyRepository, composite keys | postgres_schema (DDL only; live integration pending) |
| FR-03 | Validate complete datasets with explicit negatives and stable coordinates | dataset.validate | invalid_duplicate, missing_negative, invalid_label, inconsistent_coordinates |
| FR-04 | Generate reproducible simulated survey data, marked synthetic | dataset.simulate | reproducible |
| FR-05 | Train two ML models without test-label leakage, report classification metrics | experiment.evaluate | holdout, no_test_label_leakage |
| FR-06 | Compare search plans under identical site budgets | planning.greedy/oracle, experiment.evaluate | greedy, holdout |
| FR-07 | Recommend a remaining site excluding found targets | experiment.recommend | next_site |
| FR-08 | Expose evaluation via CLI, local API and dashboard | cli, api, dashboard | cli, api; manual dashboard pending |

Nonfunctional: validated inputs, explicit failures, stable seeds, session isolation, local-only default binding, no stored unrelated BSSIDs, no embedded credentials, Python-only source, modular design and documented limitations. Prototype usability: CLI and local dashboard; no production latency or scale claims.

Use case: operator registers authorized inventory and sites, collects full sessions, exports CSV, evaluates models and search baselines, then recommends a remaining site. Alternate flow: invalid/incomplete dataset or unavailable adapter → error, no fabricated results. Acceptance: tests pass and synthetic experiment reproducible; real-world validation is a separate milestone.

## Design
```mermaid
flowchart TD
    A[Authorized survey operator] --> B[Linux NetworkManager adapter]
    B --> C[PostgreSQL repository]
    C --> D[Validated CSV]
    E[Synthetic generator] --> D
    D --> F[Session split and feature encoding]
    F --> G[Logistic regression and random forest]
    F --> H[Non-ML baselines]
    G --> I[Expected coverage planner]
    H --> I
    I --> J[Held-out evaluator]
    J --> K[CLI / dashboard / demo API]
```

Data model: `scans(session, site, captured_at, x, y)` with composite PK `(session, site)`. `observations(session, site, target, detected, signal_quality)` has PK `(session, site, target)` and FK to scans; detection and signal constraints apply. The inventory lives in operator-controlled JSON. A database instance is for one stable deployment/configuration. Schema creation is included; migrations are a future task. No raw BSSID persistence.

Class/module responsibilities: immutable `ScanResult` carries timestamp and signal quality map; `SurveyRepository` owns transactions and exports; pure dataset/planning functions validate and optimize; experiment owns training and evaluation; CLI/API/UI are presentation layers. This keeps hardware and persistence separate from research algorithms.

## UI wireframe
```
SpectraSeek | survey CSV | site budget
Records | Sites | Targets | Held-out sessions
[Search performance] [ML evaluation] [Survey data]
Coverage comparison chart | model metrics | recommendations
Next site: [visited] [found] [strategy] [Recommend]
[Download evaluation] [Download survey CSV]
```

## Limits and academic compliance
The baseline contains synthetic data only. Collect authorized real surveys and retain evidence, report actual dataset records and measured results, document training/test split and hardware configuration, and prepare the final SRS/SDD and presentation. The guideline's Java implementation requirement is intentionally not met; instructor approval is needed. The design is not a production service; authentication, migration workflow, Windows adapter, adaptive policy evaluation and deployment hardening remain outstanding.
