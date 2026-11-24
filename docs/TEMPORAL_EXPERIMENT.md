# Experimental temporal predictors

Run a separate chronological study using prior-session statistics:

```sh
spectraseek study data/synthetic.csv --budgets 1 2 3 --windows 3 --temporal --output results/temporal-study.json
```

The recent-frequency comparator uses a smoothed detection rate from up to five prior sessions. Temporal logistic regression learns from lagged examples using only preceding labels: smoothed full-history and recent detection rates, last outcome, and aggregate site and target rates. Every evaluation window forecasts from completed earlier sessions. It does not consume labels within the held-out batch for training. The five-session window is a fixed experimental setting, not tuned on held-out data.

Compare both new predictors with the original empirical and ML controls. The temporal predictor is optional, requires both classes among its training examples, and is not guaranteed to improve coverage. It is an offline authorized survey research experiment only.
