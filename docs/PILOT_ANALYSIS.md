# Distributed pilot analysis

Two independently operated authorized survey scanners can produce pilot CSV files with the columns session, timestamp, site, target, detected, signal_quality, backend. Each snapshot must contain one row per registered target, with explicit nondetections and an offset-aware timestamp. Signal quality is null for nondetections and an integer from 0 to 100 otherwise.

Run locally:

```sh
python -m spectraseek.pilot measured_linux_S01.csv measured_windows_S02.csv --max-gap 30
```

The report validates each file, summarizes detection frequency and quality conditional on detection, and matches snapshots chronologically without reuse using the chosen tolerance. Session IDs are local to each scanner and are not treated as shared session identifiers. Unmatched observations remain in the descriptive summary.

This is an exploratory diagnostic, not a replacement for the verified survey database. A tolerance selected after data collection is exploratory. Matching timestamps cannot prove synchronized clocks, unchanged AP identities or identical conditions. Different adapters at different sites confound hardware and site effects. Do not pass these files to the original model evaluator or claim a controlled live search benchmark without a separately verified protocol. Keep raw pilot files and local reports private.
