"""
Appends simulated hourly data (sales, inventory, shipments) up to the current UTC hour.
Idempotent: safe to run repeatedly, and it catches up on missed hours.
"""
import os
from datetime import datetime, timedelta, timezone
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

DB = dict(host=os.getenv("PGHOST", "localhost"),
          port=int(os.getenv("PGPORT", "5433")),
          dbname=os.getenv("PGDATABASE", "control_tower"),
          user=os.getenv("PGUSER", "ct_user"),
          password=os.getenv("PGPASSWORD", "ct_pass"))


def current_hour():
    return datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def run():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    cur.execute("SELECT MAX(ts) FROM fact_inventory")
    last_ts = cur.fetchone()[0]
    if last_ts is None:
        raise RuntimeError("No data found. Run generate_data.py first.")
    target = current_hour()
    if last_ts >= target:
        print(f"Already up to date (latest hour: {last_ts})")
        conn.close()
        return 0

    # ---- Load reference data and current state from the database
    cur.execute("SELECT product_id, warehouse_id, base_rate FROM sim_params")
    base = {(p, w): r for p, w, r in cur.fetchall()}
    cur.execute("SELECT product_id, supplier_id, reorder_point FROM dim_product")
    prod = {p: (s, rp) for p, s, rp in cur.fetchall()}
    cur.execute("SELECT supplier_id, avg_lead_days, on_time_prob FROM dim_supplier")
    sup = {s: (lead, otp) for s, lead, otp in cur.fetchall()}
    cur.execute("SELECT product_id, warehouse_id, stock_units FROM fact_inventory WHERE ts = %s", (last_ts,))
    stock = {(p, w): u for p, w, u in cur.fetchall()}
    cur.execute("""SELECT shipment_id, product_id, warehouse_id, sim_arrival_ts, qty
                   FROM fact_shipments WHERE delivered_ts IS NULL""")
    open_order = {(p, w): (sid, arr, qty) for sid, p, w, arr, qty in cur.fetchall()}

    inv_rows, sale_rows = [], []
    hours, new_orders, deliveries = 0, 0, 0
    ts = last_ts
    while ts < target:
        ts += timedelta(hours=1)
        hours += 1
        rng = np.random.default_rng(int((ts - datetime(2000, 1, 1)).total_seconds()))
        hour_mult = 1 + 0.5 * np.sin((ts.hour - 6) / 24 * 2 * np.pi)

        for key in sorted(base):
            pid, wid = key
            sup_id, rp = prod[pid]

            # 1) receive delivery
            order = open_order.get(key)
            if order and ts >= order[1]:
                stock[key] += order[2]
                cur.execute("UPDATE fact_shipments SET delivered_ts=%s, status='delivered' WHERE shipment_id=%s",
                            (order[1], order[0]))
                del open_order[key]
                deliveries += 1

            # 2) demand
            demand = int(rng.poisson(base[key] * hour_mult))
            sold = min(demand, stock[key])
            stock[key] -= sold

            # 3) reorder
            if stock[key] <= rp and key not in open_order:
                lead_days, on_time_p = sup[sup_id]
                promised = ts + timedelta(days=lead_days)
                actual = promised
                if rng.random() > on_time_p:
                    actual += timedelta(days=int(rng.integers(1, 3)))
                qty = int(base[key] * 24 * 10)
                cur.execute("""INSERT INTO fact_shipments
                    (supplier_id,product_id,warehouse_id,order_ts,promised_ts,delivered_ts,qty,status,sim_arrival_ts)
                    VALUES (%s,%s,%s,%s,%s,NULL,%s,'in_transit',%s) RETURNING shipment_id""",
                            (sup_id, pid, wid, ts, promised, qty, actual))
                open_order[key] = (cur.fetchone()[0], actual, qty)
                new_orders += 1

            sale_rows.append((ts, pid, wid, sold))
            inv_rows.append((ts, pid, wid, stock[key]))

    execute_values(cur, "INSERT INTO fact_sales (ts,product_id,warehouse_id,units_sold) VALUES %s "
                        "ON CONFLICT DO NOTHING", sale_rows)
    execute_values(cur, "INSERT INTO fact_inventory (ts,product_id,warehouse_id,stock_units) VALUES %s "
                        "ON CONFLICT DO NOTHING", inv_rows)
    conn.commit()
    conn.close()
    print(f"Added {hours} hour(s) up to {target}: {len(sale_rows)} sales rows, "
          f"{new_orders} new orders, {deliveries} deliveries")
    return hours


if __name__ == "__main__":
    run()
