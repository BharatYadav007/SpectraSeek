# Adaptive replay and budget sensitivity

The original fixed-plan benchmark remains unchanged. The new offline replay compares fixed expected-coverage greedy with adaptive selection on the same chronological holdouts, probabilities, and site budgets. Adaptive selection removes targets already detected from its objective; it does not retrain or observe unvisited sites. Each visit reveals that site's recorded binary outcomes only after selection.

Use Python after installing the project:

```python
from spectraseek.dataset import simulate
from spectraseek.adaptive import study
report = study(simulate(), budgets=[1, 2, 3, 6, 12], windows=3)
print(report['summary'])
```

The report retains per-session site traces, cumulative discoveries, an optional hindsight bound, and paired mean coverage differences. Coverage is undefined if no inventory target is detectable. The full-budget and one-step results serve as controls. No claim of improvement is made until experiments are run. Synthetic results are not measured wireless performance. This is a replay of authorized fixed-site survey data, not a live scanning or tracking system.
