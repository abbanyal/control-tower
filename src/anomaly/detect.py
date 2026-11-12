"""Z-score anomaly detection for supplier delays and demand spikes.
Writes to the `anomalies` table. Idempotent: re-running never creates duplicates."""
import os
from datetime import timedelta
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB = dict(host=os.getenv("PGHOST", "localhost"),
          port=int(os.getenv("PGPORT", "5433")),
          dbname=os.getenv("PGDATABASE", "control_tower"),
          user=os.getenv("PGUSER", "ct_user"),
          password=os.getenv("PGPASSWORD", "ct_pass"))

Z_DELAY, MIN_LATE_DAYS = 3.0, 3.0     # delay rule
Z_SPIKE, MIN_RATIO = 4.0, 2.0         # spike rule

DDL = """
CREATE TABLE IF NOT EXISTS anomalies (
  id SERIAL PRIMARY KEY,
  anomaly_key TEXT UNIQUE,
  anomaly_type TEXT, supplier_id INT, product_id INT, shipment_id INT,
  ts TIMESTAMP, value REAL, baseline REAL, score REAL,
  detected_at TIMESTAMP DEFAULT now()
)"""


def detect_delays(cur, since):
    cur.execute("""SELECT shipment_id, supplier_id, product_id, delivered_ts,
                   EXTRACT(EPOCH FROM (delivered_ts - promised_ts)) / 86400.0
                   FROM fact_shipments WHERE delivered_ts IS NOT NULL""")
    df = pd.DataFrame(cur.fetchall(),
                      columns=["shipment_id", "supplier_id", "product_id", "delivered_ts", "late_days"])
    if df.empty:
        return []
    df["late_days"] = df["late_days"].astype(float)
    mu, sd = df["late_days"].mean(), max(df["late_days"].std(), 0.5)
    df["z"] = (df["late_days"] - mu) / sd
    hit = df[(df.z >= Z_DELAY) & (df.late_days >= MIN_LATE_DAYS)]
    if since is not None:
        hit = hit[hit.delivered_ts >= since]
    return [(f"delay:{r.shipment_id}", "supplier_delay", int(r.supplier_id), int(r.product_id),
             int(r.shipment_id), r.delivered_ts.to_pydatetime(),
             float(r.late_days), float(mu), float(r.z)) for r in hit.itertuples()]


def detect_spikes(cur, since):
    cur.execute("SELECT ts, product_id, SUM(units_sold)::int FROM fact_sales GROUP BY ts, product_id")
    df = pd.DataFrame(cur.fetchall(), columns=["ts", "product_id", "units"])
    if df.empty:
        return []
    df["hod"] = df["ts"].dt.hour
    g = df.groupby(["product_id", "hod"])["units"]
    df["mean"] = g.transform("mean")
    df["std"] = g.transform("std").clip(lower=1.0)
    df["z"] = (df["units"] - df["mean"]) / df["std"]
    hit = df[(df.z >= Z_SPIKE) & (df.units >= MIN_RATIO * df["mean"])]
    if since is not None:
        hit = hit[hit.ts >= since]
    return [(f"spike:{r.product_id}:{r.ts:%Y%m%d%H}", "demand_spike", None, int(r.product_id),
             None, r.ts.to_pydatetime(), float(r.units), float(r.mean), float(r.z))
            for r in hit.itertuples()]


def run(lookback_hours=None):
    conn = psycopg2.connect(**DB)
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        since = None
        if lookback_hours:
            cur.execute("SELECT MAX(ts) FROM fact_inventory")
            since = cur.fetchone()[0] - timedelta(hours=lookback_hours)
        delays = detect_delays(cur, since)
        spikes = detect_spikes(cur, since)
        rows = delays + spikes
        if rows:
            execute_values(cur, """INSERT INTO anomalies
                (anomaly_key, anomaly_type, supplier_id, product_id, shipment_id, ts, value, baseline, score)
                VALUES %s ON CONFLICT (anomaly_key) DO NOTHING""", rows)
        cur.execute("SELECT anomaly_type, COUNT(*) FROM anomalies GROUP BY 1 ORDER BY 1")
        totals = cur.fetchall()
    conn.close()
    print(f"Flagged this run: {len(delays)} delays, {len(spikes)} spikes. Table totals: {totals}")
    return len(rows)


if __name__ == "__main__":
    run()
