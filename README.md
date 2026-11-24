# SpectraSeek

**AI-Based Target Discovery and Search Optimization in Wireless Networks**

A Python research prototype for authorized wireless site surveys. Given a fixed inventory of approved access points and candidate survey sites, estimate the probability of detecting each access point at each site and select observation sites that maximize unique discoveries under a scan budget. No device tracking, geolocation inference, association, packet capture, or attack functionality. AetherLens was a conceptual reference only; no original source modules are retained.

## Quick start

Python 3.11+ (3.12 recommended). Live collection supports native Windows WLAN and Linux NetworkManager. The simulation, ML, and interfaces run on either platform.

On Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
```

Run the demo on either platform:

```bash
spectraseek demo --output data/synthetic.csv
spectraseek evaluate data/synthetic.csv --budget 3 --windows 1 --output results/evaluation.json
spectraseek recommend data/synthetic.csv --visited S01 --found AP01
spectraseek study data/synthetic.csv --budgets 1 2 3 6 12 --windows 3
pytest -q
streamlit run dashboard.py
```

The local demonstration API is optional: `uvicorn spectraseek.api:app --host 127.0.0.1 --port 8000`. Visit `/docs`, `/health`, `/demo/evaluation` or `/demo/recommend`. The API uses simulated data only; it is not a production authenticated service.

## Live collection (authorized lab only)

1. Run `spectraseek interfaces` to list supported adapters. On Linux, use a Wi-Fi adapter managed by NetworkManager (`nmcli`). On Windows, run the Windows Python installation in PowerShell and use a Native Wi-Fi adapter. If Windows denies a scan, check **Settings > Privacy & security > Location** and location access for desktop apps. Both collectors request fresh OS scans and report the driver's 0–100 signal quality.
2. Copy `.env.example` to `.env` and choose a strong database password. Start PostgreSQL: `docker compose up -d --wait`. Set `DATABASE_URL` in your shell, e.g. `export DATABASE_URL='postgresql+psycopg://spectraseek:YOUR_URL_ENCODED_PASSWORD@localhost:5432/spectraseek'`. Use `$env:DATABASE_URL = 'postgresql+psycopg://...'` in Windows PowerShell. Compose loads `.env` for the database service. Set `DATABASE_URL` separately for SpectraSeek.
3. Run `spectraseek init-db` to initialize the schema. Copy `examples/survey.example.json` to `survey.local.json` and replace the placeholder BSSIDs with access points you own or are authorized to survey. Set local site coordinates in metres and use unique aliases. The first successful scan records a fingerprint of the inventory, site coordinates, and signal threshold. The database rejects scans with different settings or a different collector. Use the same adapter throughout a survey and start a fresh database when switching between Windows and Linux. Only approved target outcomes are stored.
4. At each registered site in a survey session, run `spectraseek scan --session 00001 --site S01 --config survey.local.json --authorized`. When more than one adapter is available, add `--interface` with the exact name shown by `spectraseek interfaces`. Quote a Windows adapter name containing spaces. Repeat for all sites, then repeat the complete survey on different sessions. Use zero-padded, lexically chronological session IDs. A failed scan is an error, not a negative label. One scan per site per session; duplicate scans are rejected. The OS may use active discovery internally; no connection to APs is attempted.
5. `spectraseek export --output data/measured.csv`. Evaluate only complete survey sessions using `spectraseek evaluate data/measured.csv --windows 3 --output results/measured-evaluation.json`. Use one window for a four-session survey. Collect enough sessions for meaningful validation (at least four required, 20–40 recommended for a pilot). Keep measured data private.

If a database already contains scans made before protocol tracking, export them separately and use a fresh database for new scans. Running `init-db` again creates the protocol table without altering existing measurements.

To run PostgreSQL integration tests locally, set `SPECTRASEEK_TEST_DATABASE_URL` to an isolated PostgreSQL database using the same URL format as `DATABASE_URL`. The tests create and drop temporary schemas. GitHub Actions provides a PostgreSQL service for these tests.

## Research protocol

A sample is a session/site/target triple. Features: site and target aliases, their interaction and local site coordinates. Label: 1 if a registered AP was detected under the chosen survey protocol, otherwise 0. Nondetections are explicit. The dataset must contain all target/site pairs per session. The default evaluation trains on the first 75% of chronologically ordered sessions (rounded down) and tests on the remainder. Use `--windows 3` to start with the first half and test the remaining sessions in three consecutive batches. Each batch uses only earlier sessions for training and planning. The dashboard and demo API also accept a window count. This estimates performance on later sessions at the same registered sites.

- Logistic regression and random forest are compared with a per-site, per-target historical detection frequency baseline. The report pools held-out predictions for accuracy, precision, recall, F1, ROC-AUC, Brier score, and confusion matrices.
- Search comparisons: random (30 trials/session), historical binary coverage, empirical detection-frequency greedy, ML-probability greedy, and exhaustive hindsight oracle for manageable combinations. All use the same scan budget. Coverage denominator is the number of targets detectable at any registered site in the held-out session, not the full inventory. Empty denominators are undefined. The oracle is not deployable. Expected coverage uses an independence approximation.
- The report records each window's split and site plan, the dataset fingerprint, feature and model settings, random seed, and dependency versions. The top-level plan is from the final window. Paired bootstrap intervals use 2,000 session resamples to estimate uncertainty in the mean coverage difference versus empirical greedy. Sessions with no detectable targets are excluded from this comparison. Intervals assume independent sessions and can be unstable for a small pilot.
- The interactive recommendation re-trains on the complete supplied historical dataset and excludes already visited sites and already found targets. This interactive behavior is not the fixed-plan benchmark. The separate offline adaptive replay compares fixed and adaptive policies across budgets; see [the protocol](docs/ADAPTIVE_EVALUATION.md).
- Synthetic data is generated from a stochastic distance model, with seed 42 by default. It is NOT real Wi-Fi evidence. No ML superiority is assumed; compare against the empirical baseline. Validate with authorized measured surveys and report whether any improvement holds across evaluation windows.

## Structure

`src/spectraseek/` contains the scanner, PostgreSQL repository, dataset validation, simulation, ML, coverage planner, CLI and local API. `dashboard.py` is the Streamlit interface. `docs/` contains the initial requirements and design. `tests/` contains automated tests. `data/synthetic.csv` and `results/evaluation.json` are reproducible demonstration artifacts.

The prototype uses Python and PostgreSQL. Live collection requires a compatible adapter visible to the operating system running SpectraSeek. WSL needs a Linux-visible Wi-Fi device, such as a compatible USB adapter attached through [USB/IP](https://learn.microsoft.com/en-us/windows/wsl/connect-usb). The repository is licensed under the MIT license; see [LICENSE](LICENSE).

## Dashboard datasets

Choose **Synthetic** to generate a demonstration or upload a synthetic survey CSV. Choose **Measured survey** for a complete export from the verified PostgreSQL survey protocol. The dashboard shows held-out model scores, target detection heatmaps, location plans, budget curves, scan efficiency and fixed-versus-adaptive replay for these complete surveys. Evaluation and replay reports can be downloaded as JSON.

Choose **Measured pilot** for two independent scanner CSVs. This view shows scanner-specific detection and signal quality, one-to-one timestamp alignment, unmatched scans and downloadable exploratory held-out reports when supported. For unattended Linux and Windows collection, run the synchronized `pilot-collect` workflow. See [the pilot validation and collection protocol](docs/PILOT_ANALYSIS.md) for the data requirements for a measured benchmark.

