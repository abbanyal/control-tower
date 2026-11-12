CREATE OR REPLACE VIEW v_whatif AS
SELECT t.*,
  CASE WHEN t.days_of_cover < t.new_arrival_days THEN 'STOCK-OUT RISK' ELSE 'OK' END AS outcome,
  ROUND(GREATEST(0, t.new_arrival_days - t.days_of_cover), 1) AS days_short,
  ROUND(GREATEST(0, t.new_arrival_days - t.days_of_cover) * t.forecast_daily_demand, 0) AS est_units_lost
FROM (
  SELECT d.delay_days, v.product_id, v.product, v.supplier, v.stock,
         v.forecast_daily_demand, v.days_of_cover,
         ROUND(GREATEST(COALESCE(v.days_to_arrival, sp.avg_lead_days), 0), 1) AS base_arrival_days,
         ROUND(GREATEST(COALESCE(v.days_to_arrival, sp.avg_lead_days), 0) + d.delay_days, 1) AS new_arrival_days
  FROM v_forecast_vs_stock v
  JOIN dim_product p ON p.product_id = v.product_id
  JOIN dim_supplier sp ON sp.supplier_id = p.supplier_id
  CROSS JOIN (VALUES (0), (3), (7), (14)) AS d(delay_days)
) t;

CREATE OR REPLACE VIEW v_whatif_summary AS
SELECT supplier, delay_days,
       COUNT(*) AS products,
       COUNT(*) FILTER (WHERE outcome = 'STOCK-OUT RISK') AS products_at_risk,
       COALESCE(SUM(est_units_lost), 0) AS est_units_lost
FROM v_whatif
GROUP BY supplier, delay_days;
