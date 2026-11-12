"""Daily demand forecast per product with Prophet, plus a 7-day holdout accuracy check.
Writes demand_forecast, forecast_accuracy and the view v_forecast_vs_stock."""
import os
import logging
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from prophet import Prophet

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

DB = dict(host=os.getenv("PGHOST", "localhost"),
          port=int(os.getenv("PGPORT", "5433")),
          dbname=os.getenv("PGDATABASE", "control_tower"),
          user=os.getenv("PGUSER", "ct_user"),
          password=os.getenv("PGPASSWORD", "ct_pass"))

DDL = """
CREATE TABLE IF NOT EXISTS demand_forecast (
  product_id INT, ds DATE, yhat REAL, yhat_lower REAL, yhat_upper REAL,
  generated_at TIMESTAMP DEFAULT now(), PRIMARY KEY (product_id, ds));
CREATE TABLE IF NOT EXISTS forecast_accuracy (
  product_id INT PRIMARY KEY, mape REAL, wape REAL, baseline_wape REAL,
  generated_at TIMESTAMP DEFAULT now());

-- Forecast vs current stock and incoming shipments (totals across warehouses)
CREATE OR REPLACE VIEW v_forecast_vs_stock AS
WITH now_ts AS (SELECT MAX(ts) AS t FROM fact_inventory),
cur AS (
  SELECT product_id, SUM(stock_units) AS stock FROM fact_inventory
  WHERE ts = (SELECT t FROM now_ts) GROUP BY product_id),
fc AS (
  SELECT product_id, AVG(yhat) AS fc_daily FROM demand_forecast
  WHERE ds >= (SELECT t::date FROM now_ts) AND ds < (SELECT t::date FROM now_ts) + 7
  GROUP BY product_id),
inb AS (
  SELECT product_id, SUM(qty) AS inbound_qty, MIN(sim_arrival_ts) AS next_arrival
  FROM fact_shipments WHERE delivered_ts IS NULL GROUP BY product_id)
SELECT p.product_id, p.name AS product, s.name AS supplier,
       c.stock,
       ROUND(f.fc_daily::numeric, 1) AS forecast_daily_demand,
       ROUND((c.stock / NULLIF(f.fc_daily, 0))::numeric, 1) AS days_of_cover,
       COALESCE(i.inbound_qty, 0) AS inbound_qty,
       i.next_arrival,
       ROUND((EXTRACT(EPOCH FROM (i.next_arrival - (SELECT t FROM now_ts))) / 86400.0)::numeric, 1)
         AS days_to_arrival,
       CASE
         WHEN i.next_arrival IS NOT NULL
              AND c.stock / NULLIF(f.fc_daily, 0)
                  < EXTRACT(EPOCH FROM (i.next_arrival - (SELECT t FROM now_ts))) / 86400.0
           THEN 'RUNS OUT BEFORE DELIVERY'
         WHEN i.next_arrival IS NULL AND c.stock / NULLIF(f.fc_daily, 0) < s.avg_lead_days
           THEN 'REORDER NOW'
         WHEN c.stock / NULLIF(f.fc_daily, 0) < 3 THEN 'LOW'
         ELSE 'OK' END AS risk
FROM dim_product p
JOIN dim_supplier s ON s.supplier_id = p.supplier_id
JOIN cur c ON c.product_id = p.product_id
LEFT JOIN fc f ON f.product_id = p.product_id
LEFT JOIN inb i ON i.product_id = p.product_id;
"""


def fit_predict(df, periods):
    m = Prophet(yearly_seasonality=False, daily_seasonality=False,
                weekly_seasonality=True, interval_width=0.8)
    m.fit(df)
    return m.predict(m.make_future_dataframe(periods=periods))


def run(horizon=14, holdout=7, force=False):
    conn = psycopg2.connect(**DB)
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("""SELECT COALESCE(MAX(generated_at) > now()::timestamp - interval '24 hours', false)
                       FROM demand_forecast""")
        if cur.fetchone()[0] and not force:
            print("Forecast is less than 24h old, skipping.")
            return 0

        # complete days only: drop the partial first day and the current partial day
        cur.execute("""SELECT ts::date AS ds, product_id, SUM(units_sold)::int
                       FROM fact_sales
                       WHERE ts >= (SELECT date_trunc('day', MIN(ts)) + interval '1 day' FROM fact_sales)
                         AND ts <  (SELECT date_trunc('day', MAX(ts)) FROM fact_sales)
                       GROUP BY 1, 2 ORDER BY 1, 2""")
        data = pd.DataFrame(cur.fetchall(), columns=["ds", "product_id", "y"])
        data["ds"] = pd.to_datetime(data["ds"])

        fc_rows, acc_rows = [], []
        for pid, d in data.groupby("product_id"):
            d = d[["ds", "y"]].reset_index(drop=True)
            train, test = d.iloc[:-holdout], d.iloc[-holdout:]

            # accuracy on the held-out last 7 days
            pred = fit_predict(train, holdout).tail(holdout)["yhat"].clip(lower=0).values
            y = test["y"].values
            mape = float(np.mean(np.abs(y - pred) / np.maximum(y, 1)))
            wape = float(np.abs(y - pred).sum() / y.sum())
            naive = train["y"].tail(7).mean()
            base_wape = float(np.abs(y - naive).sum() / y.sum())
            acc_rows.append((int(pid), mape, wape, base_wape))

            # final forecast trained on all complete days
            out = fit_predict(d, horizon).tail(horizon)
            for r in out.itertuples():
                fc_rows.append((int(pid), r.ds.date(), max(float(r.yhat), 0.0),
                                max(float(r.yhat_lower), 0.0), max(float(r.yhat_upper), 0.0)))

        cur.execute("DELETE FROM demand_forecast")
        cur.execute("DELETE FROM forecast_accuracy")
        execute_values(cur, "INSERT INTO demand_forecast (product_id, ds, yhat, yhat_lower, yhat_upper) VALUES %s", fc_rows)
        execute_values(cur, "INSERT INTO forecast_accuracy (product_id, mape, wape, baseline_wape) VALUES %s", acc_rows)

    conn.close()
    a = np.array([r[1:] for r in acc_rows])
    print(f"Forecast done for {len(acc_rows)} products. Holdout {holdout}d: "
          f"MAPE {a[:,0].mean():.1%}, WAPE {a[:,1].mean():.1%}, naive-baseline WAPE {a[:,2].mean():.1%}")
    return len(fc_rows)


if __name__ == "__main__":
    run(force=True)
