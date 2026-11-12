"""Pipeline tests. Run from the project root with the Docker stack up: python -m pytest -v"""
import os, sys
import psycopg2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

DB = dict(host="localhost", port=5433, dbname="control_tower", user="ct_user", password="ct_pass")


@pytest.fixture(scope="module")
def cur():
    conn = psycopg2.connect(**DB)
    c = conn.cursor()
    yield c
    conn.close()


def one(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def test_no_negative_stock(cur):
    assert one(cur, "SELECT COUNT(*) FROM fact_inventory WHERE stock_units < 0") == 0


def test_no_duplicate_hours(cur):
    assert one(cur, """SELECT COUNT(*) FROM (SELECT ts, product_id, warehouse_id FROM fact_sales
                       GROUP BY 1,2,3 HAVING COUNT(*) > 1) d""") == 0


def test_sales_and_inventory_aligned(cur):
    assert one(cur, "SELECT COUNT(*) FROM fact_sales") == one(cur, "SELECT COUNT(*) FROM fact_inventory")


def test_delivery_after_order(cur):
    assert one(cur, "SELECT COUNT(*) FROM fact_shipments WHERE delivered_ts < order_ts") == 0


def test_data_is_fresh(cur):
    hours_old = one(cur, "SELECT EXTRACT(EPOCH FROM (now() AT TIME ZONE 'utc' - MAX(ts)))/3600 FROM fact_inventory")
    assert hours_old < 48, f"latest data is {hours_old:.0f}h old, is Airflow running?"


def test_stockout_rate_between_0_and_1(cur):
    assert one(cur, "SELECT COUNT(*) FROM kpi_hourly WHERE stockout_rate < 0 OR stockout_rate > 1") == 0


def test_supplier_kpis_complete(cur):
    assert one(cur, "SELECT COUNT(*) FROM v_supplier_kpis") == 5
    assert one(cur, "SELECT COUNT(*) FROM v_supplier_kpis WHERE on_time_pct NOT BETWEEN 0 AND 100") == 0


def test_corepack_has_worst_p90_lead_time(cur):
    assert one(cur, "SELECT supplier FROM v_supplier_kpis ORDER BY p90_lead_days DESC LIMIT 1") == "CorePack Ltd"


def test_supplier_delay_detection_quality(cur):
    cur.execute("""SELECT f.shipment_id FROM fact_shipments f JOIN anomaly_truth t
                   ON t.anomaly_type='supplier_delay' AND f.supplier_id=t.supplier_id
                   AND f.order_ts>=t.start_ts AND f.order_ts<t.end_ts WHERE f.delivered_ts IS NOT NULL""")
    truth = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT shipment_id FROM anomalies WHERE anomaly_type='supplier_delay'")
    flagged = {r[0] for r in cur.fetchall()}
    tp = len(truth & flagged)
    assert truth and tp / len(truth) >= 0.9, "delay recall below 0.9"
    assert tp / max(len(flagged), 1) >= 0.9, "delay precision below 0.9"


def test_spike_detection_quality(cur):
    cur.execute("""SELECT t.product_id, g FROM anomaly_truth t,
                   generate_series(t.start_ts, t.end_ts - interval '1 hour', interval '1 hour') g
                   WHERE t.anomaly_type='demand_spike'""")
    truth = {(r[0], r[1]) for r in cur.fetchall()}
    cur.execute("SELECT product_id, ts FROM anomalies WHERE anomaly_type='demand_spike'")
    flagged = {(r[0], r[1]) for r in cur.fetchall()}
    tp = len(truth & flagged)
    assert tp / len(truth) >= 0.8, "spike recall below 0.8"
    assert tp / max(len(flagged), 1) >= 0.5, "spike precision below 0.5"


def test_forecast_shape_and_bounds(cur):
    assert one(cur, "SELECT COUNT(*) FROM demand_forecast") == 280
    assert one(cur, "SELECT COUNT(*) FROM demand_forecast WHERE yhat < 0 OR yhat_lower > yhat OR yhat > yhat_upper") == 0


def test_forecast_accuracy_reasonable(cur):
    assert one(cur, "SELECT AVG(wape) FROM forecast_accuracy") < 0.30


def test_whatif_risk_grows_with_delay(cur):
    cur.execute("""SELECT delay_days, COUNT(*) FILTER (WHERE outcome='STOCK-OUT RISK')
                   FROM v_whatif GROUP BY 1 ORDER BY 1""")
    counts = [r[1] for r in cur.fetchall()]
    assert counts == sorted(counts), f"risk should not fall as delay grows: {counts}"


def test_simulator_step_is_idempotent(cur):
    from simulator.step import run
    run()
    before = one(cur, "SELECT COUNT(*) FROM fact_sales")
    cur.connection.rollback()
    run()
    cur.connection.rollback()
    assert one(cur, "SELECT COUNT(*) FROM fact_sales") == before
