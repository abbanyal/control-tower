"""
Simulates 60 days of hourly retail supply chain data and loads it into PostgreSQL.
Injects two known anomalies and records them in anomaly_truth.
"""
from datetime import datetime, timedelta
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

DB = dict(host="localhost", port=5432, dbname="control_tower",
          user="ct_user", password="ct_pass")
rng = np.random.default_rng(42)       # fixed seed = reproducible results
DAYS = 60

# (name, country, lead_days, on_time_probability)
SUPPLIERS = [
    ("Apex Foods", "India", 3, 0.92),
    ("BlueLine Traders", "Vietnam", 5, 0.85),
    ("CorePack Ltd", "China", 6, 0.88),
    ("Delta Supplies", "Germany", 4, 0.95),
    ("EastWind Co", "UAE", 2, 0.90),
]
WAREHOUSES = [(1, "Delhi DC", "Delhi"), (2, "Mumbai DC", "Mumbai"),
              (3, "Bengaluru DC", "Bengaluru")]
PRODUCT_NAMES = [
    ("Basmati Rice 5kg", "Grocery"), ("Cooking Oil 1L", "Grocery"),
    ("Tea Pack 500g", "Grocery"), ("Biscuits Family Pack", "Grocery"),
    ("Shampoo 340ml", "Personal Care"), ("Toothpaste 150g", "Personal Care"),
    ("Soap 4-pack", "Personal Care"), ("Face Wash 100ml", "Personal Care"),
    ("LED Bulb 9W", "Home"), ("Detergent 2kg", "Home"),
    ("Dish Wash 750ml", "Home"), ("Floor Cleaner 1L", "Home"),
    ("USB Cable", "Electronics"), ("Earphones", "Electronics"),
    ("Power Bank", "Electronics"), ("Phone Case", "Electronics"),
    ("Notebook A4", "Stationery"), ("Ball Pens 10-pack", "Stationery"),
    ("Water Bottle 1L", "Kitchen"), ("Lunch Box", "Kitchen"),
]

# ---- Injected anomalies (day numbers counted from the start of history)
DELAY_SUPPLIER = 3            # CorePack Ltd
DELAY_FROM_DAY, DELAY_TO_DAY, EXTRA_DELAY_DAYS = 30, 40, 5
SPIKE_PRODUCT = 7             # Soap 4-pack
SPIKE_DAY, SPIKE_START_HOUR, SPIKE_HOURS, SPIKE_MULT = 45, 10, 10, 5

end = datetime.now().replace(minute=0, second=0, microsecond=0)
start = end - timedelta(days=DAYS)
delay_start = start + timedelta(days=DELAY_FROM_DAY)
delay_end = start + timedelta(days=DELAY_TO_DAY)
spike_start = start + timedelta(days=SPIKE_DAY, hours=SPIKE_START_HOUR)
spike_end = spike_start + timedelta(hours=SPIKE_HOURS)

# ---- Build reference data
products = []   # (id, name, category, supplier_id, reorder_point)
base = {}       # (product_id, warehouse_id) -> average units sold per hour
for i, (name, cat) in enumerate(PRODUCT_NAMES, start=1):
    sup_id = (i - 1) % len(SUPPLIERS) + 1
    lead = SUPPLIERS[sup_id - 1][2]
    rates = [float(rng.uniform(0.5, 3.0)) for _ in WAREHOUSES]
    for w, r in zip(WAREHOUSES, rates):
        base[(i, w[0])] = r
    reorder_point = int(round(np.mean(rates) * 24 * (lead + 1.5)))
    products.append((i, name, cat, sup_id, reorder_point))
reorder_point = {p[0]: p[4] for p in products}
supplier_of = {p[0]: p[3] for p in products}

# ---- Simulation state
stock = {k: int(base[k] * 24 * 8) for k in base}      # start with ~8 days of stock
open_order = {k: None for k in base}                  # one open order per product+warehouse
inv_rows, sale_rows, ship_rows = [], [], []

for h in range(DAYS * 24):
    ts = start + timedelta(hours=h)
    hour_mult = 1 + 0.5 * np.sin((ts.hour - 6) / 24 * 2 * np.pi)   # busier in the daytime

    for key in base:
        pid, wid = key

        # 1) receive a delivery if it has arrived
        order = open_order[key]
        if order and ts >= order["actual"]:
            stock[key] += order["qty"]
            open_order[key] = None

        # 2) demand for this hour
        lam = base[key] * hour_mult
        if pid == SPIKE_PRODUCT and spike_start <= ts < spike_end:
            lam *= SPIKE_MULT
        demand = int(rng.poisson(lam))
        sold = min(demand, stock[key])          # can't sell what we don't have
        stock[key] -= sold

        # 3) reorder if stock is low and nothing is already on order
        if stock[key] <= reorder_point[pid] and open_order[key] is None:
            sup_id = supplier_of[pid]
            _, _, lead_days, on_time_p = SUPPLIERS[sup_id - 1]
            promised = ts + timedelta(days=lead_days)
            actual = promised
            if rng.random() > on_time_p:        # normal small lateness
                actual += timedelta(days=int(rng.integers(1, 3)))
            if sup_id == DELAY_SUPPLIER and delay_start <= ts < delay_end:
                actual += timedelta(days=EXTRA_DELAY_DAYS)   # injected delay
            qty = int(base[key] * 24 * 10)
            open_order[key] = {"actual": actual, "qty": qty}
            delivered = actual if actual <= end else None
            status = "delivered" if delivered else "in_transit"
            ship_rows.append((sup_id, pid, wid, ts, promised, delivered, qty, status))

        sale_rows.append((ts, pid, wid, sold))
        inv_rows.append((ts, pid, wid, stock[key]))

# ---- Load into PostgreSQL
conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute("""TRUNCATE dim_supplier, dim_product, dim_warehouse, fact_inventory,
               fact_sales, fact_shipments, anomaly_truth RESTART IDENTITY CASCADE""")
execute_values(cur, "INSERT INTO dim_supplier (supplier_id,name,country,avg_lead_days) VALUES %s",
               [(i, s[0], s[1], s[2]) for i, s in enumerate(SUPPLIERS, start=1)])
execute_values(cur, "INSERT INTO dim_warehouse (warehouse_id,name,city) VALUES %s", WAREHOUSES)
execute_values(cur, "INSERT INTO dim_product (product_id,name,category,supplier_id,reorder_point) VALUES %s", products)
execute_values(cur, "INSERT INTO fact_inventory (ts,product_id,warehouse_id,stock_units) VALUES %s", inv_rows, page_size=10000)
execute_values(cur, "INSERT INTO fact_sales (ts,product_id,warehouse_id,units_sold) VALUES %s", sale_rows, page_size=10000)
execute_values(cur, """INSERT INTO fact_shipments
    (supplier_id,product_id,warehouse_id,order_ts,promised_ts,delivered_ts,qty,status)
    VALUES %s""", ship_rows)
cur.execute("""INSERT INTO anomaly_truth (anomaly_type,supplier_id,product_id,start_ts,end_ts,description)
               VALUES ('supplier_delay',%s,NULL,%s,%s,%s), ('demand_spike',NULL,%s,%s,%s,%s)""",
            (DELAY_SUPPLIER, delay_start, delay_end, f"+{EXTRA_DELAY_DAYS} days on orders placed in window",
             SPIKE_PRODUCT, spike_start, spike_end, f"{SPIKE_MULT}x demand"))
conn.commit()
cur.close(); conn.close()
print(f"Loaded: {len(sale_rows)} sales rows, {len(inv_rows)} inventory rows, {len(ship_rows)} shipments")
