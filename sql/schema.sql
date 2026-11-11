CREATE TABLE dim_supplier (
  supplier_id SERIAL PRIMARY KEY,
  name TEXT, country TEXT, avg_lead_days INT
);
CREATE TABLE dim_product (
  product_id SERIAL PRIMARY KEY,
  name TEXT, category TEXT,
  supplier_id INT REFERENCES dim_supplier,
  reorder_point INT
);
CREATE TABLE dim_warehouse (
  warehouse_id SERIAL PRIMARY KEY,
  name TEXT, city TEXT
);
CREATE TABLE fact_inventory (
  ts TIMESTAMP, product_id INT, warehouse_id INT, stock_units INT
);
CREATE TABLE fact_sales (
  ts TIMESTAMP, product_id INT, warehouse_id INT, units_sold INT
);
CREATE TABLE fact_shipments (
  shipment_id SERIAL PRIMARY KEY,
  supplier_id INT, product_id INT, warehouse_id INT,
  order_ts TIMESTAMP, promised_ts TIMESTAMP, delivered_ts TIMESTAMP,
  qty INT, status TEXT
);
CREATE TABLE anomaly_truth (
  id SERIAL PRIMARY KEY,
  anomaly_type TEXT, supplier_id INT, product_id INT,
  start_ts TIMESTAMP, end_ts TIMESTAMP, description TEXT
);
