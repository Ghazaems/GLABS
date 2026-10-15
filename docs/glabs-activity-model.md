# GLABS activity model v2

Experimental daily OHLCV heuristics, sourced only from Purbaya. These are not
BandarMetrics formulas, transaction classification, broker identity, actual
ownership changes, float turnover, or measured rupiah inflow.

## Inputs and formulas

Use the last at most 180 valid source sessions through the completed screening
session. Prices and volumes are validated before calculation. Let:

- CLV = (2 * Close - High - Low) / (High - Low).
- RVOL20 = Volume / mean(volume of the previous 20 sessions), excluding today.
- Intensity = max(RVOL20 - 1, 0)^2.
- Directional contribution = CLV * RVOL20.
- Pressure = EMA(span=5, adjust=False) of cumulative directional contribution.
- Activity rotation proxy = RVOL20 * (1 - abs(CLV)).
- Money Flow bar = CLV * Volume, in shares.
- Money Flow line = cumulative Money Flow bar, anchored at history_start.

The first 20 rows have no relative indicators. A zero volume baseline produces
null, not infinity. High=Low has unknown close location: use zero directional
contribution (and zero Money Flow), but null rotation. This is not evidence that
no intraday transactions occurred.

## Interpretation and assumptions

Intensity measures excess participation against the stock's own recent volume.
Normal/below-normal volume has score 0; 2x volume has score 1; 3x has score 4.
The square deliberately emphasizes spikes. It is a chosen sensitivity transform,
not a parameter fitted to the screenshots or an empirically validated threshold.

Pressure uses close location as a coarse direction proxy, not actual buyer/seller
initiated flow. Smoothing limits one-session jaggedness; it does not establish
large-player participation. Compare slopes within one window. The cumulative
anchor resets when the 180-session window shifts, so absolute levels must not be
compared across stocks or windows.

Rotation is a deliberately limited balanced-close activity proxy: high relative
volume with a close nearer the middle of its range yields more weight. It does
not prove churn, absorption, matching orders, or ownership turnover. Green <1,
yellow [1,2), red >=2 are heuristic activity bands, not buy/sell recommendations.
OHLCV cannot establish whether the price traversed its range once or many times.

A split, suspension, feed adjustment, unusual auction, or volume regime shift
can distort interpretation. There is no independently verified free-float,
transaction-frequency, aggressor-side, or broker input in these formulas.
Neither predictive power nor threshold calibration has been statistically tested.

## Publication and compatibility

method_version=2 is required by the UI. Old v1 indicators cannot be displayed
under new labels. Valid same-session Purbaya OHLCV caches can be revalidated and
recomputed; the new history_start and bars describe the actual retained input,
not the old longer history. Invalid caches fall back only to a fresh Purbaya
fetch. Source/session checks stay strict; unavailable rows have no invented
indicators. If every source fails, the previous publication is retained.

No primary screening score/signal, Yahoo fallback, or main screening logic is
modified. Regression tests include known formulas, lagged baseline, causality
within the fixed window, scale invariance, source guards, cache migration,
insufficient/invalid history, five UI panels, and unchanged primary scores.
