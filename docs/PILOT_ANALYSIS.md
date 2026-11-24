# Distributed pilot evaluation

An independently operated scanner can export a CSV with the columns session, timestamp, site, target, detected, signal_quality and backend. Each scan contains one row per registered target with an explicit binary detection label. Timestamps require a UTC offset. Signal quality is an integer from 0 to 100 for a detection and empty for a nondetection. Adapter identity and calibration require a separate collection log.

## Reproduce the existing diagnostic

```sh
python -m spectraseek.pilot measured_linux_S01.csv measured_windows_S02.csv --max-gap 30
```

The report defaults to `results/pilot.local.json`. The Streamlit **Measured pilot** view uses the same validator and scoring code. Use a private instance for measured CSVs and keep the report out of Git.

For independent CSVs, the matcher takes the earliest feasible one-to-one pairs using actual UTC timestamps. It does not infer common sessions from local scan IDs. For collection runs produced by `pilot-collect`, it requires equal scheduled round IDs, validates each actual timestamp against that round’s capture window and applies the chosen timestamp gap. Unmatched scans stay visible and contribute to descriptive counts.

The supplied pilot yielded 11 pairs at 30 seconds, with 8 training and 3 held-out rounds. Every pair had the same site/target detection pattern. Linux AP01 was always detected and Linux AP02 was always absent. Both Windows targets were detected in every matched round. The varying Windows AP01 observations in the complete CSV were outside the matched subset. The report withholds classification and coverage scores for this pilot.

## Automated synchronized collection

Use two stationary machines at two distinct authorized sites. Keep the same adapter on each machine throughout the run. Copy the **same private** `survey.local.json` to both machines. Register both sites and verify each approved AP's BSSID-to-alias mapping on both machines before collection. Choose the detection threshold in advance. Record OS, driver, adapter, site, clock source, outages and major changes privately. Keep both machines awake. A single run of 24 scans per scanner takes roughly 24 minutes and requires no per-round action. Targets must be genuinely observed under the intended survey conditions. Keep every successfully captured round.

The commands assume both machines already have a Git checkout and Python installed. Open a terminal in each checkout. On Linux, verify time synchronization and list adapters:

```bash
git pull --ff-only
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
timedatectl status
.venv/bin/python -m spectraseek interfaces
```

On Windows, use PowerShell. Confirm the time source and recent successful sync. If needed, run `w32tm /resync` in an elevated PowerShell with Windows Time configured. Allow location access for desktop apps if Windows WLAN denies scanning.

```powershell
git pull --ff-only
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
w32tm /query /status
.\.venv\Scripts\python.exe -m spectraseek interfaces
```

Check both clocks against a common time source and resolve visible drift before starting. Generate a UTC start five minutes ahead on Linux, then copy the exact value to Windows. Start both collectors before that time. Select the adapter listed by the interface command.

Linux:

```bash
START=$(.venv/bin/python -c 'from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds"))')
printf '%s\n' "$START"
read -r -p 'Linux Wi-Fi interface: ' IFACE
.venv/bin/python -m spectraseek pilot-collect --config survey.local.json --site S01 --interface "$IFACE" --start "$START" --rounds 24 --interval 60 --output measured_linux_sync.csv --authorized
```

Windows PowerShell:

```powershell
$Start = Read-Host 'Paste the exact UTC start printed by Linux'
$Adapter = Read-Host 'Windows Wi-Fi interface'
.\.venv\Scripts\python.exe -m spectraseek pilot-collect --config survey.local.json --site S02 --interface "$Adapter" --start "$Start" --rounds 24 --interval 60 --output measured_windows_sync.csv --authorized
```

Each machine independently schedules fresh scans on the same UTC grid. Failed or late scans are omitted and logged, so they cannot turn into negative labels. A round accepts scan completions within 45 seconds of its scheduled start. The command preserves the actual completion time, site and backend and writes only registered aliases. It refuses to overwrite an existing CSV. Clock alignment and collection time do not guarantee that channel observations were made at the same instant.

Copy the Windows CSV privately to the Linux checkout, then run:

```bash
.venv/bin/python -m spectraseek.pilot measured_linux_sync.csv measured_windows_sync.csv --max-gap 30 --verified-rounds --output results/pilot.local.json
.venv/bin/python -m streamlit run dashboard.py
```

Use `--verified-rounds` or the dashboard's **Verified synchronized rounds** checkbox only after confirming the shared inventory and threshold, both sites and adapter records, and synchronized clocks. The evaluator also checks round IDs and timestamps. An operator attests to the physical setup and AP identities, which the alias-only CSVs cannot establish. If collection support is still insufficient, schedule a new complete run in another representative period and apply the same predeclared settings. Keep earlier runs and report their support. To test hardware effects separately, repeat with each scanner covering both sites in counterbalanced runs.

## What the evaluation measures

- The first three quarters of matched rounds are eligible for training. The remaining rounds form a fixed holdout. Training rounds whose latest actual scan time reaches the earliest held-out scan time are excluded. Both scanners and every target stay together within a round.
- The evaluator requires eight training rounds, four held-out rounds, both classes in at least three rounds per split, and at least two different detection patterns per split. These are exploratory reporting gates, not evidence of statistical power or independent rounds. Expect serial dependence within a short run. Scores describe the surveyed scanners, locations, times and target aliases.
- Logistic regression and random forest use site, alias and their interaction. Comparators use training-only site/target frequency and global frequency. No signal quality, timestamps, test labels, threshold search or class resampling are used as model inputs or fitting decisions. Accuracy, precision, recall, F1 and ROC-AUC use untouched held-out outcomes. Precision is reported as zero when a model predicts no positives, with the confusion matrix available to interpret that case.
- Discovery coverage needs verified synchronized rounds and a supported holdout. Each fixed one- or two-site plan uses training probabilities only. Its held-out denominator is the distinct targets seen at either site within each round. Coverage excludes rounds with no detectable targets. Targets per scan includes those rounds as zero discoveries. The two-site budget is the observed full-coverage reference. This replay estimates behavior in the two observed sites and does not establish that a deployed system improves search elsewhere.
- Scanner and site effects remain confounded when each scanner stays at one site. Signal-quality readings are not calibrated between scanners. Keep all synthetic reports separate.
