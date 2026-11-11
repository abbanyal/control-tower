-- Hourly KPI table (filled by the refresh task)
CREATE TABLE IF NOT EXISTS kpi_hourly (
  ts TIMESTAMP PRIMARY KEY,
  stockout_count INT,
  total_items INT,
  stockout_rate REAL,
  avg_days_of_inventory REAL,
  units_sold INT
);

-- Days of inventory per product/warehouse/hour (7-day rolling demand)
CREATE OR REPLACE VIEW v_inventory_doi AS
SELECT i.ts, i.product_id, i.warehouse_id, i.stock_units,
       s.avg_daily_demand,
       CASE WHEN s.avg_daily_demand > 0
            THEN i.stock_units / s.avg_daily_demand END AS days_of_inventory
FROM fact_inventory i
JOIN (
  SELECT ts, product_id, warehouse_id,
         SUM(units_sold) OVER (PARTITION BY product_id, warehouse_id ORDER BY ts
                               ROWS BETWEEN 167 PRECEDING AND CURRENT ROW) / 7.0
           AS avg_daily_demand
  FROM fact_sales
) s ON s.ts = i.ts AND s.product_id = i.product_id AND s.warehouse_id = i.warehouse_id;

-- Latest snapshot: what the warehouse looks like right now
CREATE OR REPLACE VIEW v_current_inventory AS
SELECT p.name AS product, p.category, w.name AS warehouse, sp.name AS supplier,
       d.product_id, d.warehouse_id, d.stock_units, p.reorder_point,
       ROUND(d.avg_daily_demand, 1) AS avg_daily_demand,
       ROUND(d.days_of_inventory, 1) AS days_of_inventory,
       CASE WHEN d.stock_units = 0 THEN 'STOCK-OUT'
            WHEN d.stock_units <= p.reorder_point THEN 'LOW'
            ELSE 'OK' END AS status
FROM v_inventory_doi d
JOIN dim_product p ON p.product_id = d.product_id
JOIN dim_warehouse w ON w.warehouse_id = d.warehouse_id
JOIN dim_supplier sp ON sp.supplier_id = p.supplier_id
WHERE d.ts = (SELECT MAX(ts) FROM fact_inventory);

-- Supplier scorecard (all delivered orders)
CREATE OR REPLACE VIEW v_supplier_kpis AS
SELECT s.supplier_id, s.name AS supplier, s.country,
       COUNT(*) AS delivered_orders,
       ROUND(100.0 * AVG((f.delivered_ts <= f.promised_ts)::int), 1) AS on_time_pct,
       ROUND(AVG(f.lt)::numeric, 2) AS avg_lead_days,
       ROUND((percentile_cont(0.9) WITHIN GROUP (ORDER BY f.lt))::numeric, 2) AS p90_lead_days
FROM (
  SELECT *, (EXTRACT(EPOCH FROM (delivered_ts - order_ts)) / 86400.0)::float8 AS lt
  FROM fact_shipments WHERE delivered_ts IS NOT NULL
) f
JOIN dim_supplier s ON s.supplier_id = f.supplier_id
GROUP BY s.supplier_id, s.name, s.country;

-- Supplier trend per day (for charts and anomaly detection)
CREATE OR REPLACE VIEW v_supplier_daily AS
SELECT s.supplier_id, s.name AS supplier,
       date_trunc('day', f.delivered_ts)::date AS day,
       COUNT(*) AS deliveries,
       ROUND(100.0 * AVG((f.delivered_ts <= f.promised_ts)::int), 1) AS on_time_pct,
       ROUND(AVG(EXTRACT(EPOCH FROM (f.delivered_ts - f.order_ts)) / 86400.0)::numeric, 2) AS avg_lead_days
FROM fact_shipments f
JOIN dim_supplier s ON s.supplier_id = f.supplier_id
WHERE f.delivered_ts IS NOT NULL
GROUP BY s.supplier_id, s.name, date_trunc('day', f.delivered_ts);

-- Refresh hourly KPIs (safe to re-run; skips the first 7 days of warm-up)
WITH sales AS (
  SELECT ts, SUM(units_sold) AS units FROM fact_sales GROUP BY ts
)
INSERT INTO kpi_hourly (ts, stockout_count, total_items, stockout_rate,
                        avg_days_of_inventory, units_sold)
SELECT d.ts,
       SUM((d.stock_units = 0)::int),
       COUNT(*),
       AVG((d.stock_units = 0)::int),
       AVG(d.days_of_inventory),
       MAX(sales.units)
FROM v_inventory_doi d
JOIN sales ON sales.ts = d.ts
WHERE d.ts >= (SELECT MIN(ts) FROM fact_inventory) + INTERVAL '7 days'
GROUP BY d.ts
ON CONFLICT (ts) DO UPDATE SET
  stockout_count = EXCLUDED.stockout_count,
  total_items = EXCLUDED.total_items,
  stockout_rate = EXCLUDED.stockout_rate,
  avg_days_of_inventory = EXCLUDED.avg_days_of_inventory,
  units_sold = EXCLUDED.units_sold;

-- One-row summary for dashboard "big number" tiles
CREATE OR REPLACE VIEW v_kpi_summary AS
SELECT k.ts AS as_of,
       ROUND(100 * k.stockout_rate::numeric, 1) AS stockout_rate_pct,
       k.stockout_count,
       ROUND(k.avg_days_of_inventory::numeric, 1) AS avg_days_of_inventory,
       d.on_time_pct_7d, d.avg_lead_days_7d
FROM (SELECT * FROM kpi_hourly ORDER BY ts DESC LIMIT 1) k
CROSS JOIN (
  SELECT ROUND(100.0 * AVG((delivered_ts <= promised_ts)::int), 1) AS on_time_pct_7d,
         ROUND(AVG(EXTRACT(EPOCH FROM (delivered_ts - order_ts)) / 86400.0)::numeric, 2) AS avg_lead_days_7d
  FROM fact_shipments
  WHERE delivered_ts >= (SELECT MAX(ts) FROM fact_inventory) - INTERVAL '7 days'
) d;
