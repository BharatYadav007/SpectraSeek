# Synthetic stress scenarios

The original generator remains the stationary control. Two optional stress profiles share its initial geometry, pair effects and per-session random draws: transient site attenuation (25% site/session probability, -1.8 logit) and persistent site/target logit shifts after the midpoint (normal offsets with standard deviations 1.2 and 0.8). These are illustrative assumptions, not estimated parameters or calibrated physical RF models.

```sh
spectraseek demo --scenario interference --output data/interference.csv
spectraseek demo --scenario drift --output data/drift.csv
spectraseek study data/drift.csv --budgets 1 2 3 6 12 --windows 3 --output results/drift-study.json
```

Preserve the scenario name, seed, dimensions, generator version and dataset fingerprint with every experiment. Compare all models on the same generated dataset, report failures as well as improvements, and avoid tuning on held-out outcomes. The CSV schema intentionally remains compatible with the original dataset. Scenario names are not recorded in its source column, which is always synthetic; retain the command or a separate manifest. Real validation still requires authorized measurements.
