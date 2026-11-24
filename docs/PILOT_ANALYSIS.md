# Distributed pilot analysis

An independently operated scanner can export a CSV with the columns session, timestamp, site, target, detected, signal_quality and backend. Each scan contains one row per registered target with an explicit binary detection label. The timestamp requires a UTC offset. Signal quality is an integer from 0 to 100 for a detection and empty for a nondetection. The CSV records the scanner backend. Adapter identity and calibration require a separate collection log.

## Reproduce the diagnostic

Run this command using your local copies of the two files:

```sh
python -m spectraseek.pilot measured_linux_S01.csv measured_windows_S02.csv --max-gap 30
```

The command writes `results/pilot.local.json` by default. The Streamlit **Measured pilot** view uses the same validation and accepts both files as uploads. Use a private Streamlit instance for measured data.

1. The parser groups rows by scanner-local scan ID, validates complete and consistent target inventories, and restores chronological order using UTC timestamps.
2. The matcher compares the earliest remaining scans. If their absolute gap fits the tolerance, it records the pair and advances both scanners. Otherwise it advances the earlier scanner. Each scan appears in at most one pair. This gives an ordered set of feasible pairs. It does not optimize total timestamp distance among all equally sized matchings.
3. The report records both UTC timestamps and the gap for every pair. It lists unmatched scans by scanner and includes those scans in the descriptive detection statistics. Mean signal quality is conditional on detection.

## Why the supplied pilot cannot validate a search model

The scanners sampled asynchronously, with one run of 20 scans per scanner and two target aliases. Timestamp proximity cannot establish clock synchronization, common RF conditions or shared hotspot identity. A hardware and backend change coincides with a site change, and scanner quality values are uncalibrated. Even a chronological split would reuse evidence from the same short runs and could reward constant predictions for nearly constant outcomes. The pilot cannot measure counterfactual discovery at every candidate site within each test block. Its detection counts and signal quality summaries support descriptive analysis.

## Collect a reproducible benchmark

1. **Fix the survey protocol.** Define authorized AP identities and aliases, site coordinates, detection threshold, scan settings, cadence, and maximum matching gap before collection. Verify hotspot identities privately against the approved inventory. Record clock offset, adapter and driver identifiers, OS, backend, collection time, and material changes to conditions in the private run log.
2. **Collect complete survey blocks.** Use `spectraseek init-db`, the same `survey.local.json`, and the authorized scan workflow in the README. Assign a chronological session ID to each block and scan every registered site with the same approved inventory. Rotate or balance site order across blocks. If comparing hardware, have each adapter cover each site across comparable blocks and keep each adapter in a separate survey database. Log failed scans and rerun or exclude incomplete blocks according to a rule set before evaluation.
3. **Repeat across independent blocks.** Collect at least 20–40 complete blocks for an initial pilot across multiple days or conditions. This is a starting point, with adequacy determined by class support, variation and desired precision. Reserve later independent blocks before inspecting results. Keep adjacent or related runs together when assigning blocks to training and test periods.
4. **Freeze the study before scoring.** Export complete sessions using `spectraseek export`. Fix the windows, target and site inventory, metric definitions, budgets and model settings from the training period. Compare historical and recent detection frequencies, logistic regression, random forest and lagged logistic regression using `spectraseek study --temporal` on the verified export. Keep test outcomes and current scan signal quality out of model inputs. Adaptive replay reveals only the outcomes from sites selected so far. The next-site demo uses the supplied history for planning and has a separate purpose from held-out scoring.
5. **Report support and uncertainty.** Report per-window splits and class counts, accuracy, precision, recall, F1, ROC-AUC when both classes occur, Brier score and confusion matrices. For every budget report unique targets found, coverage among targets detectable in that block and targets found per scan. Coverage is undefined for blocks without detectable targets. Document exclusions and device/site effects, preserve timestamps and protocol metadata privately, and label synthetic results separately.
