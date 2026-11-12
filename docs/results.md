# Results --- Inventory Control Tower

**As of:** 11 November 2026, 14:00

## 1. Executive KPI Snapshot

  Metric                           Result
  --------------------------- -----------
  Stockout rate                      0.0%
  Stockout count                        0
  Average days of inventory           8.2
  On-time delivery (7-day)          81.1%
  Average lead time (7-day)     4.15 days

## 2. Supplier Performance

  ----------------------------------------------------------------------------
    Supplier Supplier   Country     Delivered  On-time %    Average   P90 lead
          ID                           orders             lead days       days
  ---------- ---------- --------- ----------- ---------- ---------- ----------
           1 Apex Foods India              71      88.7%       3.11       4.00

           2 BlueLine   Vietnam            71      73.2%       5.39       7.00
             Traders                                                

           3 CorePack   China              67      73.1%       6.99      11.00
             Ltd                                                    

           4 Delta      Germany            72      93.1%       4.08       4.00
             Supplies                                               

           5 EastWind   UAE                72      93.1%       2.10       2.00
             Co                                                     
  ----------------------------------------------------------------------------

## 3. Inventory Status

  Status         Count
  ----------- --------
  LOW               18
  OK                42
  **Total**     **60**

## 4. Daily Stockout Trend

  Day            Stockout %
  ------------ ------------
  2026-11-11          1.33%
  2026-11-10          2.43%
  2026-11-09          6.32%
  2026-11-08          4.31%
  2026-11-07          0.97%
  2026-11-06          1.04%
  2026-11-05          2.64%
  2026-11-04          2.57%
  2026-11-03          0.49%
  2026-11-02          0.42%
  2026-11-01          2.36%
  2026-10-31          1.67%
  2026-10-30          1.18%
  2026-10-29          2.64%
  2026-10-28          3.68%
  2026-10-27          5.56%
  2026-10-26          7.78%
  2026-10-25         10.21%
  2026-10-24         13.75%
  2026-10-23          9.79%
  2026-10-22          7.43%
  2026-10-21          5.35%
  2026-10-20          4.10%
  2026-10-19          0.00%
  2026-10-18          0.00%
  2026-10-17          0.00%
  2026-10-16          0.00%
  2026-10-15          0.00%
  2026-10-14          0.49%
  2026-10-13          4.17%
  2026-10-12          3.33%
  2026-10-11          3.89%
  2026-10-10          3.13%
  2026-10-09          0.76%
  2026-10-08          0.00%
  2026-10-07          0.00%
  2026-10-06          0.00%
  2026-10-05          0.00%
  2026-10-04          0.00%
  2026-10-03          0.42%

## 5. Observations

-   The latest KPI snapshot reports a **0.0% stockout rate** and **zero
    stockouts** at 14:00 on 11 November 2026.
-   The inventory status output contains **18 LOW** items and **42 OK**
    items, for 60 items total.
-   EastWind Co and Delta Supplies have the highest reported on-time
    performance at **93.1%**.
-   EastWind Co has the shortest reported average lead time at **2.10
    days** and P90 lead time of **2.00 days**.
-   CorePack Ltd has the longest reported average lead time at **6.99
    days** and P90 lead time of **11.00 days**.
-   In the 40-day stockout trend, the highest daily stockout percentage
    is **13.75% on 24 October 2026**.

*Note: The KPI snapshot and daily trend are reproduced as separate query
outputs supplied for this report. Their values are not reconciled or
recalculated.*

## Demand forecast (Prophet, 7-day holdout, 20 products)

| Model | WAPE | MAPE |
|---|---|---|
| Prophet | 13.0% | 13.7% |
| Naive (last 7-day mean) | 11.4% | n/a |

Prophet did not beat the naive baseline on this data. Demand is simulated without weekly seasonality
and history is only about 52 days, so Prophet's seasonality term fits noise.

## What-if: supplier delayed by N days (products at risk, of 4 per supplier)

| Delay | Apex | BlueLine | CorePack | Delta | EastWind |
|---|---|---|---|---|---|
| 0 days | 0 | 0 | 0 | 0 | 0 |
| 3 days | 0 | 1 | 1 | 1 | 0 |
| 7 days | 4 | 4 | 4 | 4 | 4 |
| 14 days | 4 | 4 | 4 | 4 | 4 |

## Tests

14 pytest tests pass in 0.41s (data integrity, KPIs, anomaly quality, forecast bounds, what-if monotonicity, simulator idempotency).
