"""Scores the detector against the injected ground truth in anomaly_truth."""
import psycopg2
from detect import DB


def pr(truth, flagged):
    tp = len(truth & flagged)
    fp = len(flagged - truth)
    fn = len(truth - flagged)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, fn, precision, recall


conn = psycopg2.connect(**DB)
cur = conn.cursor()

# --- Supplier delays: truth = orders from the delayed supplier placed inside the window
cur.execute("""SELECT f.shipment_id FROM fact_shipments f
               JOIN anomaly_truth t ON t.anomaly_type='supplier_delay'
                AND f.supplier_id=t.supplier_id AND f.order_ts>=t.start_ts AND f.order_ts<t.end_ts
               WHERE f.delivered_ts IS NOT NULL""")
truth_d = {r[0] for r in cur.fetchall()}
cur.execute("SELECT shipment_id FROM anomalies WHERE anomaly_type='supplier_delay'")
flag_d = {r[0] for r in cur.fetchall()}

# --- Demand spikes: truth = every (product, hour) inside the spike window
cur.execute("""SELECT t.product_id, g FROM anomaly_truth t,
               generate_series(t.start_ts, t.end_ts - interval '1 hour', interval '1 hour') g
               WHERE t.anomaly_type='demand_spike'""")
truth_s = {(r[0], r[1]) for r in cur.fetchall()}
cur.execute("SELECT product_id, ts FROM anomalies WHERE anomaly_type='demand_spike'")
flag_s = {(r[0], r[1]) for r in cur.fetchall()}
conn.close()

lines = ["| Anomaly | Truth | Flagged | TP | FP | FN | Precision | Recall |",
         "|---|---|---|---|---|---|---|---|"]
for name, t, f in [("Supplier delay (per shipment)", truth_d, flag_d),
                   ("Demand spike (per product-hour)", truth_s, flag_s)]:
    tp, fp, fn, p, r = pr(t, f)
    lines.append(f"| {name} | {len(t)} | {len(f)} | {tp} | {fp} | {fn} | {p:.2f} | {r:.2f} |")
print("\n".join(lines))
print("\nSpike false positives (product, hour):", sorted(flag_s - truth_s)[:10])
print("Delay false positives (shipment ids):", sorted(flag_d - truth_d)[:10])
open("docs/anomaly_results.md", "w").write("# Anomaly detection results\n\n" + "\n".join(lines) + "\n")
