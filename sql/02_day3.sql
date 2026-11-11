ALTER TABLE dim_supplier ADD COLUMN IF NOT EXISTS on_time_prob REAL;
ALTER TABLE fact_shipments ADD COLUMN IF NOT EXISTS sim_arrival_ts TIMESTAMP;

CREATE TABLE IF NOT EXISTS sim_params (
  product_id INT, warehouse_id INT, base_rate DOUBLE PRECISION,
  PRIMARY KEY (product_id, warehouse_id)
);

-- Unique indexes make the hourly job safe to re-run (no duplicate rows)
CREATE UNIQUE INDEX IF NOT EXISTS ux_sales ON fact_sales (ts, product_id, warehouse_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inv ON fact_inventory (ts, product_id, warehouse_id);
CREATE INDEX IF NOT EXISTS idx_ship_open ON fact_shipments (delivered_ts);
