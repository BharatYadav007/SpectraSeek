# SpectraSeek

**AI-Based Target Discovery and Search Optimization in Wireless Networks**

A Python research prototype for authorized wireless site surveys. Given a fixed inventory of approved access points and candidate survey sites, estimate the probability of detecting each access point at each site and select observation sites that maximize unique discoveries under a scan budget. No device tracking, geolocation inference, association, packet capture, or attack functionality. AetherLens was a conceptual reference only; no original source modules are retained.

## Quick start

Python 3.11+ (3.12 recommended). Linux is required only for live collection; the simulation, ML, and interface are cross-platform.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'
spectraseek demo --output data/synthetic.csv
spectraseek evaluate data/synthetic.csv --budget 3 --output results/evaluation.json
spectraseek recommend data/synthetic.csv --visited S01 --found AP01
pytest -q
streamlit run dashboard.py
```

The local demonstration API is optional: `uvicorn spectraseek.api:app --host 127.0.0.1 --port 8000`. Visit `/docs`, `/health`, `/demo/evaluation` or `/demo/recommend`. The API uses simulated data only; it is not a production authenticated service.

## Live collection (authorized lab only)

1. Install NetworkManager (`nmcli`) and use a supported Linux Wi-Fi adapter. `spectraseek interfaces` lists managed Wi-Fi devices. The adapter requests a fresh OS scan, and reports signal quality (0–100, not dBm). No monitor mode or special hardware is required.
2. Copy `.env.example` to `.env` and choose a strong database password. Start PostgreSQL: `docker compose up -d --wait`. Set `DATABASE_URL` in your shell, e.g. `export DATABASE_URL='postgresql+psycopg://spectraseek:YOUR_URL_ENCODED_PASSWORD@localhost:5432/spectraseek'`. `.env` is used by Compose, not automatically read by the Python CLI.
3. `spectraseek init-db` initializes the schema. Copy `examples/survey.example.json` to `survey.local.json` and replace the placeholder BSSIDs with access points you own or are authorized to survey. Set your own local site coordinates in metres. Use unique target aliases. Maintain the same inventory and threshold throughout an experiment. Only approved target outcomes are stored; unrelated networks are discarded.
4. At each registered site in a survey session, run e.g. `spectraseek scan --session 00001 --site S01 --config survey.local.json --interface wlan0 --authorized`. Repeat for all sites, then repeat the complete survey on different sessions. Use zero-padded, lexically chronological session IDs. A failed scan is an error, not a negative label. One scan per site per session; duplicate scans are rejected. The OS may use active discovery internally; no connection to APs is attempted.
5. `spectraseek export --output data/measured.csv`. Evaluate only complete survey sessions using `spectraseek evaluate data/measured.csv`. Collect enough sessions for meaningful validation (at least four required, 20–40 recommended for a pilot). Keep measured data private.

## Research protocol

A sample is a session/site/target triple. Features: site and target aliases, their interaction and local site coordinates. Label: 1 if a registered AP was detected under the chosen survey protocol, otherwise 0. Nondetections are explicit. The dataset must contain all target/site pairs per session. The final 25% of chronologically ordered sessions are held out; training and planning never use their detection labels. This is a within-deployment experiment, not proof of transfer to unseen locations.

- Classifiers: logistic regression, random forest. Metrics: accuracy, precision, recall, F1, ROC-AUC, Brier score and confusion matrices.
- Search comparisons: random (30 trials/session), historical binary coverage, empirical detection-frequency greedy, ML-probability greedy, and exhaustive hindsight oracle for manageable combinations. All use the same scan budget. Coverage denominator is the number of targets detectable at any registered site in the held-out session, not the full inventory. Empty denominators are undefined. The oracle is not deployable. Expected coverage uses an independence approximation.
- The interactive recommendation re-trains on the complete supplied historical dataset and excludes already visited sites and already found targets. This interactive behavior is not the fixed-plan benchmark; adaptive policy evaluation remains future work.
- Synthetic data is generated from a stochastic distance model, with seed 42 by default. It is NOT real Wi-Fi evidence. No ML superiority is assumed; compare against the empirical baseline. Real data, hardware testing, robustness, statistical uncertainty and permission verification are required before final academic claims.

## Structure

`src/spectraseek/` contains the scanner, PostgreSQL repository, dataset validation, simulation, ML, coverage planner, CLI and local API. `dashboard.py` is the Streamlit interface. `docs/` contains the initial requirements and design. `tests/` contains automated tests. `data/synthetic.csv` and `results/evaluation.json` are reproducible demonstration artifacts.

No Java or SQLite. PostgreSQL integration and live scans require external services/hardware. The SE guideline requires Java; the Python-only deviation needs faculty approval. No license has been selected for this new project.
