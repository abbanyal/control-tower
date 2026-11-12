CREATE OR REPLACE VIEW v_demand_actual_vs_forecast AS
SELECT s.ts::date AS day, p.name AS product, 'actual' AS series, SUM(s.units_sold)::float AS units
FROM fact_sales s JOIN dim_product p ON p.product_id = s.product_id
WHERE s.ts >= (SELECT MAX(ts) FROM fact_sales) - interval '30 days'
  AND s.ts <  (SELECT date_trunc('day', MAX(ts)) FROM fact_sales)
GROUP BY 1, 2
UNION ALL
SELECT f.ds, p.name, 'forecast', f.yhat::float
FROM demand_forecast f JOIN dim_product p ON p.product_id = f.product_id;

CREATE OR REPLACE VIEW v_anomaly_feed AS
SELECT a.ts, a.anomaly_type, sp.name AS supplier, p.name AS product,
       ROUND(a.value::numeric, 1) AS value, ROUND(a.baseline::numeric, 1) AS baseline,
       ROUND(a.score::numeric, 1) AS z_score
FROM anomalies a
LEFT JOIN dim_product p ON p.product_id = a.product_id
LEFT JOIN dim_supplier sp ON sp.supplier_id = COALESCE(a.supplier_id, p.supplier_id);
